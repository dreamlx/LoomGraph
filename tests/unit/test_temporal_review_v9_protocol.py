"""V9 direct-Flash no-target calibration contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from evals import audit_temporal_review_v9_pilot as audit
from evals import run_temporal_review_v9_model_identity as identity
from evals import run_temporal_review_v9_pilot as pilot


def _events(*, assistant: list[str], session: list[str], usage: list[str]) -> list[dict[str, object]]:
    return [
        *({"type": "system", "model": value} for value in session),
        *({"type": "assistant", "message": {"model": value, "content": []}} for value in assistant),
        {"type": "result", "structured_output": {"decision": {}, "review_locus": {}}, "modelUsage": {value: {} for value in usage}},
    ]


def _categories(*, assistant: list[str] | None = None, session: list[str] | None = None, usage: list[str] | None = None) -> dict[str, object]:
    return identity._model_categories(_events(
        assistant=assistant if assistant is not None else [identity.REQUESTED_MODEL],
        session=session if session is not None else ["glm-5.2[1M]"],
        usage=usage if usage is not None else [identity.REQUESTED_MODEL, "glm-4.7"],
    ))


def _write_calibration(root: Path, *, categories: dict[str, object] | None = None) -> None:
    categories = categories or _categories()
    source = root / "calibration-source" / "src" / "calibration.py"
    source.parent.mkdir(parents=True)
    source.write_text("def calibration_marker() -> str:\n    return 'runtime-identity-only'\n", encoding="utf-8")
    instruction = root / "calibration-instruction.md"
    instruction.write_text("This is a runtime identity calibration. Do not inspect task artifacts or call tools. Return the required JSON with comparison_not_observed and a review_locus for src/calibration.py.", encoding="utf-8")
    records: list[dict[str, object]] = []
    for replicate, condition in identity.CALIBRATION_CELLS:
        relative = Path("calibrations") / f"rep-{replicate:02d}" / condition / "output"
        output = root / relative
        output.mkdir(parents=True)
        stream = output / "claude.stream.jsonl"
        stream.write_text("".join(json.dumps(event) + "\n" for event in _events(
            assistant=list(categories["assistant_models_raw"]), session=list(categories["session_models_raw"]), usage=list(categories["usage_models_raw"]),
        )), encoding="utf-8")
        config: dict[str, object] = {"mcpServers": {}}
        command = ["claude", "-p", "--model", identity.REQUESTED_MODEL, "--tools", "Read,Glob,Grep"]
        if condition == "treatment":
            config = {"mcpServers": {"loomgraph": {"command": "loomgraph", "args": ["mcp", "serve"], "env": {"LOOMGRAPH_MCP_ALLOWED_TOOLS": "loomgraph_branch_diff"}}}}
        command.extend(["--mcp-config", json.dumps(config)])
        if condition == "treatment":
            command.extend(["--allowedTools", "mcp__loomgraph__loomgraph_branch_diff"])
        command_path = output / "command.json"
        command_path.write_text(json.dumps(command), encoding="utf-8")
        (output / "orientation.json").write_text(json.dumps({"status": "complete", "source_clean": True, "model": {"model_categories_valid": True}}), encoding="utf-8")
        outer = ["runner", "--condition", condition, "--task-id", identity.CALIBRATION_TASK_ID, "--use-mode", "voluntary", "--treatment-surface", "temporal-review-v9-primary-navigation-evidence", "--model", identity.REQUESTED_MODEL, "--loomgraph-binary", "loomgraph", "--temporal-review-v9-calibration"]
        records.append({
            "replicate": replicate, "condition": condition, "output_dir": str(relative), "outer_command": outer,
            "outer_command_sha256": hashlib.sha256(json.dumps(outer, separators=(",", ":")).encode()).hexdigest(),
            "outer_return_code": 0,
            "stream_sha256": hashlib.sha256(stream.read_bytes()).hexdigest(), "command_sha256": hashlib.sha256(command_path.read_bytes()).hexdigest(), "categories": categories,
            "command_surface_fingerprint": identity.command_surface_fingerprint(outer, command),
        })
    aggregate = {field: categories[field] for field in identity._IDENTITY_FIELDS if field.endswith("canonical")}
    aggregate["model_categories_valid"] = True
    aggregate["command_surface_fingerprints"] = {
        condition: next(record["command_surface_fingerprint"] for record in records if record["condition"] == condition)
        for condition in ("baseline", "treatment")
    }
    value = {
        "protocol": identity.PROTOCOL, "status": "complete", "identity_mode": "runtime-specific", "requested_model": identity.REQUESTED_MODEL,
        "calibration_protocol": "temporal-review-v9-no-target-runtime-calibration",
        "calibration_matrix": [{"replicate": rep, "condition": arm} for rep, arm in identity.CALIBRATION_CELLS],
        "calibrations": records, "aggregate": aggregate, "calibration_content": {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "instruction_sha256": hashlib.sha256(instruction.read_bytes()).hexdigest()}, "claude_version": {"return_code": 0},
    }
    (root / "identity-preflight.json").write_text(json.dumps(value), encoding="utf-8")


def test_v9_accepts_direct_flash_with_runtime_usage_companion() -> None:
    assert identity._categories_valid(_categories(), requested_model=identity.REQUESTED_MODEL, identity_mode="runtime-specific")


@pytest.mark.parametrize("surface", ["assistant", "session", "usage"])
def test_v9_rejects_empty_raw_category(surface: str) -> None:
    kwargs = {surface: []}
    assert not identity._categories_valid(_categories(**kwargs), requested_model=identity.REQUESTED_MODEL, identity_mode="runtime-specific")


@pytest.mark.parametrize("model", ["sonnet", "glm-5.3"])
def test_v9_commands_reject_non_flash_literal(model: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="glm-5.3-flash"):
        identity.run_preflight(output_dir=tmp_path / "preflight", model=model, identity_mode="runtime-specific", max_budget_usd="0.05")
    with pytest.raises(ValueError, match="glm-5.3-flash"):
        pilot.run_pilot(source_repository=tmp_path, output_root=tmp_path / "pilot", model=model, loomgraph_binary="loomgraph", max_budget_usd="0.50", model_identity_dir=tmp_path)


def test_v9_commands_reject_budget_drift(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="0.50"):
        identity.run_preflight(output_dir=tmp_path / "preflight", model=identity.REQUESTED_MODEL, identity_mode="runtime-specific", max_budget_usd="0.05")
    with pytest.raises(ValueError, match="0.50"):
        pilot.run_pilot(source_repository=tmp_path, output_root=tmp_path / "pilot", model=identity.REQUESTED_MODEL, loomgraph_binary="loomgraph", max_budget_usd="0.05", model_identity_dir=tmp_path)


def test_v9_rejects_model_specific_and_v8_style_assistant() -> None:
    assert not identity._categories_valid(_categories(), requested_model=identity.REQUESTED_MODEL, identity_mode="model-specific")
    assert not identity._categories_valid(_categories(assistant=["glm-5.3"], usage=["glm-5.3", "glm-4.7"]), requested_model=identity.REQUESTED_MODEL, identity_mode="runtime-specific")


def test_v9_calibration_matrix_accepts_counterbalanced_surface_controls(tmp_path: Path) -> None:
    _write_calibration(tmp_path)
    observed = pilot._model_identity(tmp_path, identity.REQUESTED_MODEL)
    assert observed["assistant_models_canonical"] == [identity.REQUESTED_MODEL]
    assert observed["usage_models_canonical"] == ["glm-4.7", identity.REQUESTED_MODEL]


def test_v9_calibration_outer_command_uses_orientation_not_task_contract(tmp_path: Path) -> None:
    command = identity._calibration_outer_command(
        source=tmp_path / "source",
        instruction=tmp_path / "instruction.md",
        output=tmp_path / "output",
        condition="treatment",
        max_budget_usd="0.05",
        loomgraph_binary="loomgraph",
    )
    assert command[1].endswith("evals/deepswe/claude_orientation.py")
    assert command[command.index("--model") + 1] == identity.REQUESTED_MODEL
    assert command[command.index("--treatment-surface") + 1] == "temporal-review-v9-primary-navigation-evidence"
    assert "--temporal-review-v9-calibration" in command
    assert "--temporal-review-v9-contract" not in command


def test_v9_calibration_rejects_missing_cell(tmp_path: Path) -> None:
    _write_calibration(tmp_path)
    value = json.loads((tmp_path / "identity-preflight.json").read_text(encoding="utf-8"))
    value["calibrations"].pop()
    (tmp_path / "identity-preflight.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="matrix|complete"):
        pilot._model_identity(tmp_path, identity.REQUESTED_MODEL)


def test_v9_calibration_rejects_category_drift(tmp_path: Path) -> None:
    _write_calibration(tmp_path)
    value = json.loads((tmp_path / "identity-preflight.json").read_text(encoding="utf-8"))
    record = value["calibrations"][1]
    stream = tmp_path / record["output_dir"] / "claude.stream.jsonl"
    events = _events(assistant=[identity.REQUESTED_MODEL], session=["glm-5.2[1M]"], usage=[identity.REQUESTED_MODEL])
    stream.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    record["stream_sha256"] = hashlib.sha256(stream.read_bytes()).hexdigest()
    record["categories"] = identity._model_categories(events)
    (tmp_path / "identity-preflight.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="complete"):
        pilot._model_identity(tmp_path, identity.REQUESTED_MODEL)


def test_v9_pilot_rejects_cell_canonical_set_drift(tmp_path: Path) -> None:
    _write_calibration(tmp_path)
    frozen = pilot._model_identity(tmp_path, identity.REQUESTED_MODEL)
    packet = {"model": {"requested": identity.REQUESTED_MODEL, "model_categories_valid": True, **_categories(usage=[identity.REQUESTED_MODEL])}}
    assert not pilot._identity_matches(packet, frozen)


def test_v9_pilot_rejects_forged_model_specific_preflight(tmp_path: Path) -> None:
    _write_calibration(tmp_path)
    value = json.loads((tmp_path / "identity-preflight.json").read_text(encoding="utf-8"))
    value["identity_mode"] = "model-specific"
    (tmp_path / "identity-preflight.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="preflight"):
        pilot._model_identity(tmp_path, identity.REQUESTED_MODEL)


def test_v9_calibration_audit_rejects_wrong_surface(tmp_path: Path) -> None:
    _write_calibration(tmp_path)
    value = json.loads((tmp_path / "identity-preflight.json").read_text(encoding="utf-8"))
    record = value["calibrations"][1]
    command_path = tmp_path / record["output_dir"] / "command.json"
    command = json.loads(command_path.read_text(encoding="utf-8"))
    del command[command.index("--allowedTools") : command.index("--allowedTools") + 2]
    command_path.write_text(json.dumps(command), encoding="utf-8")
    record["command_sha256"] = hashlib.sha256(command_path.read_bytes()).hexdigest()
    (tmp_path / "identity-preflight.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="calibration evidence"):
        audit._audit_calibrations(tmp_path, {field: value["aggregate"].get(field) for field in value["aggregate"]})


@pytest.mark.parametrize("index", ["--effort", "--setting-sources", "--json-schema", "--permission-mode"])
def test_v9_fingerprint_rejects_inner_surface_setting_drift(index: str) -> None:
    outer = ["runner", "--condition", "baseline", "--task-id", "one", "--temporal-review-v9-calibration"]
    inner = ["claude", "-p", "--model", identity.REQUESTED_MODEL, "--effort", "low", "--setting-sources", "project,local", "--json-schema", "{}", "--permission-mode", "dontAsk", "--", "one"]
    changed = list(inner)
    changed[changed.index(index) + 1] = "changed"
    assert identity.command_surface_fingerprint(outer, inner) != identity.command_surface_fingerprint(outer, changed)


def test_v9_fingerprint_rejects_treatment_environment_extra_key() -> None:
    outer = ["runner", "--condition", "treatment", "--task-id", "one", "--temporal-review-v9-calibration"]
    inner = ["claude", "--mcp-config", json.dumps({"mcpServers": {"loomgraph": {"env": {"LOOMGRAPH_MCP_ALLOWED_TOOLS": "loomgraph_branch_diff"}}}}), "--", "one"]
    changed = list(inner)
    config = json.loads(changed[changed.index("--mcp-config") + 1])
    config["mcpServers"]["loomgraph"]["env"]["EXTRA"] = "no"
    changed[changed.index("--mcp-config") + 1] = json.dumps(config)
    assert identity.command_surface_fingerprint(outer, inner) != identity.command_surface_fingerprint(outer, changed)


def test_v9_calibration_audit_rejects_content_tamper_and_leak(tmp_path: Path) -> None:
    _write_calibration(tmp_path)
    source = tmp_path / "calibration-source" / "src" / "calibration.py"
    source.write_text(source.read_text(encoding="utf-8") + "# target\n", encoding="utf-8")
    value = json.loads((tmp_path / "identity-preflight.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="protocol"):
        audit._audit_calibrations(tmp_path, {field: value["aggregate"].get(field) for field in value["aggregate"]})


@pytest.mark.parametrize("relative", ["calibration-source/src/calibration.py", "calibration-instruction.md"])
def test_v9_pilot_rejects_tampered_calibration_content(tmp_path: Path, relative: str) -> None:
    _write_calibration(tmp_path)
    path = tmp_path / relative
    path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="calibration content"):
        pilot._model_identity(tmp_path, identity.REQUESTED_MODEL)
