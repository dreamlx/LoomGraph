"""V8 persisted model-category validity witnesses."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from evals import audit_temporal_review_v8_pilot as audit
from evals import run_temporal_review_v8_model_identity as identity
from evals import run_temporal_review_v8_pilot as pilot
from evals import temporal_review_v8_fixtures as fixtures


def _events(
    *, assistant: list[str], session: list[str], usage: list[str]
) -> list[dict[str, object]]:
    return [
        *({"type": "system", "model": value} for value in session),
        *({"type": "assistant", "message": {"model": value, "content": []}} for value in assistant),
        {
            "type": "result",
            "structured_output": {"ok": True},
            "modelUsage": {value: {} for value in usage},
        },
    ]


def _categories(**kwargs: list[str]) -> dict[str, object]:
    return identity._model_categories(_events(**kwargs))


def _write_preflight(
    root: Path, categories: dict[str, object], *, persisted: object = True
) -> None:
    events = _events(
        assistant=list(categories["assistant_models_raw"]),
        session=list(categories["session_models_raw"]),
        usage=list(categories["usage_models_raw"]),
    )
    (root / "claude.stream.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    command = ["claude", "-p", "--model", "runtime"]
    value = {
        "protocol": identity.PROTOCOL,
        "status": "complete",
        "identity_mode": "runtime-specific",
        "requested_model": "runtime",
        **{
            field: categories[field]
            for field in identity._IDENTITY_FIELDS
            if field != "model_categories_valid"
        },
        "claude_version": {"return_code": 0},
        "command": command,
        "command_sha256": hashlib.sha256(
            json.dumps(command, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    if persisted is not None:
        value["model_categories_valid"] = persisted
    (root / "identity-preflight.json").write_text(json.dumps(value), encoding="utf-8")


def test_v8_order_only_change_and_normal_assistant_repetition_are_valid() -> None:
    preflight = _categories(assistant=["runtime", "runtime"], session=["s"], usage=["a", "b"])
    cell = _categories(assistant=["runtime", "runtime", "runtime"], session=["s"], usage=["b", "a"])

    assert preflight["model_categories_valid"] is True
    assert cell["model_categories_valid"] is True
    assert preflight["usage_models_canonical"] == cell["usage_models_canonical"] == ["a", "b"]
    assert cell["assistant_models_raw"] == ["runtime", "runtime", "runtime"]


@pytest.mark.parametrize("persisted", [None, False])
def test_v8_preflight_missing_or_false_validity_witness_is_rejected(
    tmp_path: Path, persisted: object
) -> None:
    categories = _categories(assistant=["runtime"], session=["s"], usage=["a"])
    _write_preflight(tmp_path, categories, persisted=persisted)

    with pytest.raises(ValueError, match="retained categories validity"):
        pilot._model_identity(tmp_path, "runtime")


def test_v8_preflight_rejects_stream_boolean_mismatch(tmp_path: Path) -> None:
    categories = _categories(assistant=["runtime"], session=["s"], usage=["a"])
    _write_preflight(tmp_path, categories, persisted=True)
    value = json.loads((tmp_path / "identity-preflight.json").read_text(encoding="utf-8"))
    value["model_categories_valid"] = False
    (tmp_path / "identity-preflight.json").write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="retained categories validity"):
        pilot._model_identity(tmp_path, "runtime")


def test_v8_rejects_label_and_category_drift() -> None:
    expected = _categories(assistant=["runtime"], session=["session"], usage=["usage"])
    moved = _categories(assistant=["runtime"], session=["usage"], usage=["session"])

    assert expected["assistant_models_canonical"] == moved["assistant_models_canonical"]
    assert expected["session_models_canonical"] != moved["session_models_canonical"]


def _synthetic_root(root: Path) -> None:
    categories = _categories(
        assistant=["runtime", "runtime"], session=["session"], usage=["a", "b"]
    )
    preflight = root / "identity-source"
    preflight.mkdir()
    _write_preflight(preflight, categories)
    retained = json.loads((preflight / "identity-preflight.json").read_text(encoding="utf-8"))
    (root / "model-identity-preflight.json").write_text(json.dumps(retained), encoding="utf-8")
    stream = (preflight / "claude.stream.jsonl").read_bytes()
    (root / "model-identity-preflight.stream.jsonl").write_bytes(stream)
    prereg_identity = {
        "identity_path": "model-identity-preflight.json",
        "stream_path": "model-identity-preflight.stream.jsonl",
        "identity_sha256": hashlib.sha256(
            (root / "model-identity-preflight.json").read_bytes()
        ).hexdigest(),
        "stream_sha256": hashlib.sha256(stream).hexdigest(),
        "identity_mode": "runtime-specific",
        "requested_model": "runtime",
        "claude_version": {"return_code": 0},
        "command_sha256": retained["command_sha256"],
        **{field: categories[field] for field in identity._IDENTITY_FIELDS},
    }
    cells = [
        {"task_id": task, "replicate": rep, "condition": condition}
        for task, rep, condition in pilot.expected_cells()
    ]
    execution_order = [
        {"task_id": task, "replicate": rep, "condition": condition}
        for task in fixtures.TASK_IDS
        for rep in (1, 2)
        for condition in (("baseline", "treatment") if rep % 2 else ("treatment", "baseline"))
    ]
    design = {
        "protocol": pilot.PROTOCOL,
        "manifest_id": pilot.MANIFEST_ID,
        "surface": pilot.SURFACE,
        "mode": "voluntary",
        "model": "runtime",
        "model_identity": prereg_identity,
        "manifest_sha256": hashlib.sha256(fixtures.MANIFEST_PATH.read_bytes()).hexdigest(),
        "selection_preflight_sha256": fixtures.selection_preflight_sha256(),
        "expected_cells": cells,
        "execution_order": execution_order,
    }
    (root / "preregistration.json").write_text(json.dumps(design), encoding="utf-8")
    (root / "environment.json").write_text(json.dumps({"synthetic": True}), encoding="utf-8")
    runs: list[dict[str, object]] = []
    for cell_identity in execution_order:
        task_id = str(cell_identity["task_id"])
        replicate = int(cell_identity["replicate"])
        condition = str(cell_identity["condition"])
        item = fixtures.contract(task_id)
        cell = root / task_id / f"rep-{replicate:02d}" / condition
        source = cell / "source"
        locus = item.oracle["required_review_locus"]
        path = source / locus["path"]
        path.parent.mkdir(parents=True)
        code = (
            "def persist_resolved_ratio():\n    return 1\n"
            if "." not in locus["qualname"]
            else "class RiskAssessor:\n    def assess(self):\n        return 1\n"
        )
        path.write_text(code, encoding="utf-8")
        answer = {
            "decision": {"boundary": item.oracle["boundary"][condition], "rationale": "synthetic"},
            "review_locus": {
                "path": locus["path"],
                "qualname": locus["qualname"],
                "rationale": "synthetic",
            },
        }
        raw = None
        if condition == "treatment":
            raw_path = (
                fixtures.MANIFEST_PATH.parent
                / f"temporal-review-v8-selection-preflight/{task_id}.json"
            )
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        contents: list[dict[str, object]] = []
        if raw is not None:
            contents = [
                {"type": "tool_use", "id": "tool", "name": "mcp__loomgraph__loomgraph_branch_diff"},
                {"type": "tool_result", "tool_use_id": "tool", "content": json.dumps(raw)},
            ]
        events = [
            {"type": "system", "model": "session"},
            {"type": "assistant", "message": {"model": "runtime", "content": contents}},
            {"type": "assistant", "message": {"model": "runtime", "content": []}},
            {"type": "result", "structured_output": answer, "modelUsage": {"a": {}, "b": {}}},
        ]
        output = cell / "output"
        output.mkdir(parents=True)
        (output / "claude.stream.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
        )
        model = {
            "requested": "runtime",
            "model_categories_valid": True,
            **{
                field: categories[field]
                for field in identity._IDENTITY_FIELDS
                if field != "model_categories_valid"
            },
        }
        certificate = (
            None
            if raw is None
            else {
                "selected_raw_event_index": 1,
                "tool_use_id": "tool",
                "raw_sha256": hashlib.sha256(json.dumps(raw).encode()).hexdigest(),
                "comparison": fixtures.parse_raw_response(task_id, raw)["comparison"],
            }
        )
        packet = {
            "protocol": pilot.SURFACE,
            "status": "complete",
            "source_clean": True,
            "tool_call_count": 1 if raw else 0,
            "tool_call_names": ["mcp__loomgraph__loomgraph_branch_diff"] if raw else [],
            "model": model,
            "task_review_observation": {"passed": True, "failures": []},
            "trust_observation": {"selected_certificate": certificate},
        }
        state = {"head": "frozen", "porcelain": ""}
        runner_command = [
            "runner",
            "--condition",
            condition,
            "--treatment-surface",
            pilot.SURFACE,
            "--temporal-review-v8-contract",
            "--model",
            "runtime",
            "--loomgraph-binary",
            "loomgraph",
        ]
        inner_command = [
            "claude",
            "-p",
            "--model",
            "runtime",
            "--strict-mcp-config",
            "--tools",
            "Read,Glob,Grep",
            "--mcp-config",
            (
                '{"mcpServers":{}}'
                if condition == "baseline"
                else '{"mcpServers":{"loomgraph":{"command":"loomgraph","args":["mcp","serve"],"env":{"LOOMGRAPH_MCP_ALLOWED_TOOLS":"loomgraph_branch_diff"}}}}'
            ),
        ]
        if condition == "treatment":
            inner_command.extend(["--allowedTools", "mcp__loomgraph__loomgraph_branch_diff"])
        for name, value in {
            "orientation.json": packet,
            "run.json": {"return_code": 0},
            "command.json": inner_command,
            "pre-state.json": state,
            "post-state.json": state,
            "final-result.json": {"type": "result", "structured_output": answer},
        }.items():
            (output / name).write_text(json.dumps(value), encoding="utf-8")
        driver: dict[str, object] = {
            "task_id": task_id,
            "replicate": replicate,
            "condition": condition,
            "manifest_id": pilot.MANIFEST_ID,
            "contract": {
                "base_ref": item.base_ref,
                "head_ref": item.head_ref,
                "backend": item.backend,
            },
            "runner_command": runner_command,
            "environment_path": str((root / "environment.json").resolve()),
            "source_dir": str(source),
            "source_clean": True,
            "source_status_return_code": 0,
            "runner_return_code": 0,
            "model_identity_matches_preflight": True,
        }
        if raw is not None:
            warm = json.loads(json.dumps(raw))
            warm["data"]["base"]["provisioned"] = "reused"
            warm["data"]["head"]["provisioned"] = "reused"
            warm_path = cell / "warm-branch-diff.json"
            warm_path.write_text(json.dumps(warm), encoding="utf-8")
            driver["warm_repeat"] = {
                "return_code": 0,
                "raw_response_path": str(warm_path),
                "parsed_raw_observation": fixtures.parse_raw_response(task_id, warm),
            }
        (cell / "driver-run.json").write_text(json.dumps(driver), encoding="utf-8")
        runs.append({"task_id": task_id, "replicate": replicate, "condition": condition})
    (root / "pilot-results.json").write_text(
        json.dumps({"protocol": pilot.PROTOCOL, "runs": runs}), encoding="utf-8"
    )


def test_v8_audit_accepts_complete_synthetic_root_and_never_authorizes_expansion(
    tmp_path: Path,
) -> None:
    _synthetic_root(tmp_path)
    result = audit.audit_pilot(tmp_path)

    assert all(record["status"] == "valid" for record in result["records"])
    assert result["expansion_gate"]["automatic_expansion_authorized"] is False


@pytest.mark.parametrize(
    "field,value", [("model_categories_valid", False), ("model_categories_valid", None)]
)
def test_v8_audit_rejects_missing_or_false_preregistered_validity_witness(
    tmp_path: Path, field: str, value: object
) -> None:
    _synthetic_root(tmp_path)
    prereg = json.loads((tmp_path / "preregistration.json").read_text(encoding="utf-8"))
    if value is None:
        prereg["model_identity"].pop(field)
    else:
        prereg["model_identity"][field] = value
    (tmp_path / "preregistration.json").write_text(json.dumps(prereg), encoding="utf-8")

    with pytest.raises(ValueError, match="validity witness"):
        audit.audit_pilot(tmp_path)


def test_v8_audit_rejects_retained_preflight_boolean_stream_mismatch(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    retained_path = tmp_path / "model-identity-preflight.json"
    retained = json.loads(retained_path.read_text(encoding="utf-8"))
    retained["model_categories_valid"] = False
    retained_path.write_text(json.dumps(retained), encoding="utf-8")
    prereg_path = tmp_path / "preregistration.json"
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    prereg["model_identity"]["identity_sha256"] = hashlib.sha256(
        retained_path.read_bytes()
    ).hexdigest()
    prereg_path.write_text(json.dumps(prereg), encoding="utf-8")

    with pytest.raises(ValueError, match="validity does not match raw stream"):
        audit.audit_pilot(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "failed"),
        ("requested_model", "other-runtime"),
        ("identity_mode", "model-specific"),
        ("claude_version", {"return_code": 9}),
    ],
)
def test_v8_audit_rejects_retained_preflight_provenance_drift(
    tmp_path: Path, field: str, value: object
) -> None:
    _synthetic_root(tmp_path)
    retained_path = tmp_path / "model-identity-preflight.json"
    retained = json.loads(retained_path.read_text(encoding="utf-8"))
    retained[field] = value
    retained_path.write_text(json.dumps(retained), encoding="utf-8")
    prereg_path = tmp_path / "preregistration.json"
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    prereg["model_identity"]["identity_sha256"] = hashlib.sha256(
        retained_path.read_bytes()
    ).hexdigest()
    prereg_path.write_text(json.dumps(prereg), encoding="utf-8")

    with pytest.raises(ValueError, match="retained preflight validity"):
        audit.audit_pilot(tmp_path)


def test_v8_audit_rejects_retained_command_hash_rebuild_failure(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    retained_path = tmp_path / "model-identity-preflight.json"
    retained = json.loads(retained_path.read_text(encoding="utf-8"))
    retained["command"].append("--tampered")
    retained_path.write_text(json.dumps(retained), encoding="utf-8")
    prereg_path = tmp_path / "preregistration.json"
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    prereg["model_identity"]["identity_sha256"] = hashlib.sha256(
        retained_path.read_bytes()
    ).hexdigest()
    prereg_path.write_text(json.dumps(prereg), encoding="utf-8")

    with pytest.raises(ValueError, match="retained preflight validity"):
        audit.audit_pilot(tmp_path)


def test_v8_audit_rejects_reordered_pilot_results(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    result_path = tmp_path / "pilot-results.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["runs"].reverse()
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValueError, match="execution order"):
        audit.audit_pilot(tmp_path)


def test_v8_audit_excludes_cell_with_mismatched_retained_command(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    task_id, replicate, condition = pilot.expected_cells()[0]
    command_path = (
        tmp_path / task_id / f"rep-{replicate:02d}" / condition / "output" / "command.json"
    )
    command = json.loads(command_path.read_text(encoding="utf-8"))
    command[command.index("--model") + 1] = "other-runtime"
    command_path.write_text(json.dumps(command), encoding="utf-8")

    result = audit.audit_pilot(tmp_path)

    assert result["records"][0]["status"] == "excluded"
    assert result["records"][0]["command_valid"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("requested_model", "other-runtime"),
        ("identity_mode", "bogus"),
        ("claude_version", {"return_code": 9}),
    ],
)
def test_v8_audit_rejects_invalid_preregistered_identity_provenance(
    tmp_path: Path, field: str, value: object
) -> None:
    _synthetic_root(tmp_path)
    prereg_path = tmp_path / "preregistration.json"
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    prereg["model_identity"][field] = value
    prereg_path.write_text(json.dumps(prereg), encoding="utf-8")

    with pytest.raises(ValueError, match="preregistration"):
        audit.audit_pilot(tmp_path)


def test_v8_audit_excludes_packet_requested_model_mismatch(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    task_id, replicate, condition = pilot.expected_cells()[0]
    packet_path = (
        tmp_path / task_id / f"rep-{replicate:02d}" / condition / "output" / "orientation.json"
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["model"]["requested"] = "other-runtime"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    result = audit.audit_pilot(tmp_path)

    assert result["records"][0]["status"] == "excluded"
    assert result["records"][0]["model_identity_valid"] is False


def test_v8_audit_excludes_treatment_without_exact_branch_diff_allowed_tool(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    task_id, replicate, condition = pilot.expected_cells()[1]
    command_path = (
        tmp_path / task_id / f"rep-{replicate:02d}" / condition / "output" / "command.json"
    )
    command = json.loads(command_path.read_text(encoding="utf-8"))
    allowed = command.index("--allowedTools")
    del command[allowed : allowed + 2]
    command_path.write_text(json.dumps(command), encoding="utf-8")

    result = audit.audit_pilot(tmp_path)

    assert result["records"][1]["status"] == "excluded"
    assert result["records"][1]["inner_command_valid"] is False


def test_v8_audit_excludes_baseline_with_loomgraph_mcp_surface(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    task_id, replicate, condition = pilot.expected_cells()[0]
    command_path = (
        tmp_path / task_id / f"rep-{replicate:02d}" / condition / "output" / "command.json"
    )
    command = json.loads(command_path.read_text(encoding="utf-8"))
    config = command.index("--mcp-config")
    command[config + 1] = '{"mcpServers":{"loomgraph":{}}}'
    command_path.write_text(json.dumps(command), encoding="utf-8")

    result = audit.audit_pilot(tmp_path)

    assert result["records"][0]["status"] == "excluded"
    assert result["records"][0]["inner_command_valid"] is False


def test_v8_audit_excludes_treatment_with_wrong_mcp_env_allowlist(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    task_id, replicate, condition = pilot.expected_cells()[1]
    command_path = (
        tmp_path / task_id / f"rep-{replicate:02d}" / condition / "output" / "command.json"
    )
    command = json.loads(command_path.read_text(encoding="utf-8"))
    config_index = command.index("--mcp-config")
    config = json.loads(command[config_index + 1])
    config["mcpServers"]["loomgraph"]["env"]["LOOMGRAPH_MCP_ALLOWED_TOOLS"] = "loomgraph_find"
    command[config_index + 1] = json.dumps(config)
    command_path.write_text(json.dumps(command), encoding="utf-8")

    result = audit.audit_pilot(tmp_path)

    assert result["records"][1]["status"] == "excluded"
    assert result["records"][1]["inner_command_valid"] is False


def test_v8_audit_excludes_treatment_without_mcp_config(tmp_path: Path) -> None:
    _synthetic_root(tmp_path)
    task_id, replicate, condition = pilot.expected_cells()[1]
    command_path = (
        tmp_path / task_id / f"rep-{replicate:02d}" / condition / "output" / "command.json"
    )
    command = json.loads(command_path.read_text(encoding="utf-8"))
    config = command.index("--mcp-config")
    del command[config : config + 2]
    command_path.write_text(json.dumps(command), encoding="utf-8")

    result = audit.audit_pilot(tmp_path)

    assert result["records"][1]["status"] == "excluded"
    assert result["records"][1]["inner_command_valid"] is False


def test_v8_audit_excludes_treatment_when_inner_server_binary_differs_from_driver(
    tmp_path: Path,
) -> None:
    _synthetic_root(tmp_path)
    task_id, replicate, condition = pilot.expected_cells()[1]
    driver_path = tmp_path / task_id / f"rep-{replicate:02d}" / condition / "driver-run.json"
    driver = json.loads(driver_path.read_text(encoding="utf-8"))
    command = driver["runner_command"]
    command[command.index("--loomgraph-binary") + 1] = "other-loomgraph"
    driver_path.write_text(json.dumps(driver), encoding="utf-8")

    result = audit.audit_pilot(tmp_path)

    assert result["records"][1]["status"] == "excluded"
    assert result["records"][1]["inner_command_valid"] is False
