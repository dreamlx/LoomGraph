"""V3 runner and audit guards that are independent of v1/v2 artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from evals import audit_temporal_review_v3_pilot as audit
from evals import run_temporal_review_v3_pilot as pilot
from evals.deepswe import claude_orientation as orientation
from evals.run_temporal_review_v3_pilot import (
    MANIFEST_ID,
    PROTOCOL,
    SURFACE,
    _design,
    expected_cells,
)
from evals.temporal_review_v3_fixtures import MANIFEST_PATH, contract


def _raw(task_id: str) -> dict[str, object]:
    item = contract(task_id)
    unavailable = item.backend == "codegraph"
    return {
        "success": True,
        "data": {
            "base": {"ref": item.base_ref, "sha": item.refs["base"]["commit_sha"], "workspace": "base", "provisioned": "created"},
            "head": {"ref": item.head_ref, "sha": item.refs["head"]["commit_sha"], "workspace": "head", "provisioned": "reused"},
            "diff": {
                "content_comparison": {
                    "status": "unavailable" if unavailable else "available",
                    "reason": "backend_has_no_per_entity_content_hash" if unavailable else None,
                    "base_backend": item.backend,
                    "head_backend": item.backend,
                },
                "edges_added": [{"src": "RiskAssessor::assess", "tgt": "threshold"}],
                "new_chains": [{"src": "RiskAssessor::assess", "tgt": "threshold"}],
                "broken_chains": [{"src": "RiskAssessor::assess", "tgt": "threshold"}],
                "content_comparison_changed": [],
            },
        },
    }


def _answer(task_id: str, boundary: str) -> dict[str, object]:
    item = contract(task_id)
    loci = [
        {"path": value["path"], "qualname": value["qualname"], "rationale": "review this implementation"}
        for value in item.oracle["required_review_loci"]
    ]
    return {"decision": {"outcome": item.oracle["decision"]["outcome"], "boundary": boundary, "rationale": "review boundary"}, "review_loci": loci}


def _source(root: Path) -> None:
    risk = root / "src/loomgraph/core/impact/risk.py"
    risk.parent.mkdir(parents=True)
    risk.write_text("class RiskAssessor:\n    def assess(self):\n        return None\n", encoding="utf-8")
    analysis = root / "src/loomgraph/cli/_analysis.py"
    analysis.parent.mkdir(parents=True)
    analysis.write_text("async def _async_impact():\n    return None\n", encoding="utf-8")


def test_v3_command_schema_never_exposes_model_trust_or_evidence_kind() -> None:
    command = orientation.build_command(
        condition="treatment", instruction="review", model="sonnet", budget_usd="0.50",
        loomgraph_binary="loomgraph", treatment_surface=SURFACE, temporal_review_v3=True,
    )
    schema = json.loads(command[command.index("--json-schema") + 1])

    assert schema["required"] == ["decision", "review_loci"]
    assert "trust" not in schema["properties"]
    assert "evidence_kind" not in schema["properties"]["review_loci"]["items"]["properties"]
    assert command[command.index("--allowedTools") + 1] == "mcp__loomgraph__loomgraph_branch_diff"


def test_v3_packet_binds_semantics_and_certificate_to_last_valid_raw_event(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    _source(tmp_path)
    raw = _raw(task_id)
    raw_text = json.dumps(raw, separators=(",", ":"))
    packet = orientation.build_temporal_review_v3_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path,
        return_code=0, contract=contract(task_id), summary={
            "final_result_seen": True, "final_result_event_index": 10, "payload": _answer(task_id, "content_comparison_unavailable"),
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"], "unexpected_mcp_tools": [],
            "raw_branch_diff_events": [{"stream_event_index": 7, "tool_use_id": "tool-7", "raw_json_text": raw_text, "raw_response": raw, "raw_sha256": hashlib.sha256(raw_text.encode()).hexdigest()}],
        },
    )

    assert packet["status"] == "complete"
    certificate = packet["trust_observation"]["selected_certificate"]
    assert certificate["tool_use_id"] == "tool-7"
    assert certificate["comparison"]["content_comparison"]["reason"] == "backend_has_no_per_entity_content_hash"
    assert "trust" not in packet


def test_v3_packet_rejects_cross_event_semantic_composition(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    _source(tmp_path)
    first, last = _raw(task_id), _raw(task_id)
    last["data"]["diff"]["edges_added"] = []  # type: ignore[index]
    last["data"]["diff"]["new_chains"] = []  # type: ignore[index]
    last["data"]["diff"]["broken_chains"] = []  # type: ignore[index]
    packet = orientation.build_temporal_review_v3_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path,
        return_code=0, contract=contract(task_id), summary={
            "final_result_seen": True, "final_result_event_index": 10, "payload": _answer(task_id, "content_comparison_unavailable"),
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"] * 2, "unexpected_mcp_tools": [],
            "raw_branch_diff_events": [
                {"stream_event_index": 1, "tool_use_id": "first", "raw_response": first, "raw_sha256": "a"},
                {"stream_event_index": 2, "tool_use_id": "last", "raw_response": last, "raw_sha256": "b"},
            ],
        },
    )

    assert packet["status"] == "task_review_oracle_failed"
    assert packet["trust_observation"]["selected_certificate"]["tool_use_id"] == "last"


def test_v3_packet_stops_on_malformed_raw_tool_result(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    _source(tmp_path)
    packet = orientation.build_temporal_review_v3_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path,
        return_code=0, contract=contract(task_id), summary={
            "final_result_seen": True, "final_result_event_index": 10, "payload": _answer(task_id, "content_comparison_unavailable"),
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"], "unexpected_mcp_tools": [],
            "raw_branch_diff_events": [{"stream_event_index": 3, "tool_use_id": "bad", "raw_json_text": "not-json", "raw_response": None, "raw_sha256": "x"}],
        },
    )

    assert packet["hard_protocol_stop"] is True
    assert packet["invalid_reason"] == "raw_ref_backend_or_l2_mismatch"


def test_v3_packet_rejects_raw_event_after_structured_result(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    _source(tmp_path)
    raw = _raw(task_id)
    packet = orientation.build_temporal_review_v3_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path,
        return_code=0, contract=contract(task_id), summary={
            "final_result_seen": True, "final_result_event_index": 4,
            "payload": _answer(task_id, "content_comparison_unavailable"),
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"], "unexpected_mcp_tools": [],
            "raw_branch_diff_events": [{"stream_event_index": 5, "tool_use_id": "late", "raw_response": raw, "raw_sha256": "x"}],
        },
    )

    assert packet["hard_protocol_stop"] is True
    assert packet["invalid_reason"] == "branch_diff_response_after_final_result"


def test_v3_instruction_never_requests_raw_field_transcription() -> None:
    value = orientation._append_temporal_review_v3_requirement("review", "treatment")

    assert "copy the returned" not in value
    assert "Do not copy its raw response" in value


def test_v3_audit_rejects_incomplete_or_duplicate_matrix(tmp_path: Path) -> None:
    root = tmp_path / "cohort"
    root.mkdir()
    design = _design("sonnet")
    (root / "preregistration.json").write_text(json.dumps(design), encoding="utf-8")
    (root / "environment.json").write_text("{}", encoding="utf-8")
    (root / "pilot-results.json").write_text(json.dumps({"schema_version": 1, "protocol": PROTOCOL, "runs": [{"task_id": "impact-low-resolution-review", "replicate": 1, "condition": "baseline"}] * 12}), encoding="utf-8")

    with pytest.raises(ValueError, match="cells do not exactly equal preregistration"):
        audit.audit_pilot(root)


def test_v3_audit_rejects_extra_discovered_cell_even_with_twelve_marker_rows(tmp_path: Path) -> None:
    root = tmp_path / "cohort"
    root.mkdir()
    (root / "preregistration.json").write_text(json.dumps(_design("sonnet")), encoding="utf-8")
    (root / "environment.json").write_text("{}", encoding="utf-8")
    runs = [
        {"task_id": task, "replicate": rep, "condition": condition}
        for task, rep, condition in expected_cells()
    ]
    (root / "pilot-results.json").write_text(
        json.dumps({"schema_version": 1, "protocol": PROTOCOL, "runs": runs}), encoding="utf-8"
    )
    extra = root / "extra-task" / "rep-01" / "baseline"
    extra.mkdir(parents=True)
    (extra / "driver-run.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="discovered cell artifacts"):
        audit.audit_pilot(root)


def test_v3_design_freezes_exact_twelve_voluntary_cells() -> None:
    design = _design("sonnet")

    assert design["protocol"] == PROTOCOL
    assert design["manifest_id"] == MANIFEST_ID
    assert design["manifest_sha256"] == hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    assert len(expected_cells()) == 12


def test_v3_audit_reports_quartiles_without_a_cross_task_win_rate() -> None:
    assert audit._quartiles([1.0, 3.0]) == {"median": 2.0, "q1": 1.5, "q3": 2.5, "iqr": 1.0}
    assert audit._quartiles([]) is None


def test_v3_driver_stops_without_creating_a_complete_marker_after_protocol_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()

    def fake_materialize(task_id: str, destination: Path, *, source_repository: Path) -> SimpleNamespace:
        destination.mkdir(parents=True)
        return SimpleNamespace(path=source, task_id=task_id)

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir()
        condition = command[command.index("--condition") + 1]
        (output / "orientation.json").write_text(
            json.dumps({
                "protocol": SURFACE,
                "status": "complete" if condition == "baseline" else "invalid_treatment_comparison_certificate",
                "hard_protocol_stop": condition == "treatment",
            }),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 1 if condition == "treatment" else 0, "", "")

    monkeypatch.setattr(pilot, "materialize_temporal_review_v3_fixture", fake_materialize)
    monkeypatch.setattr(pilot, "_run", fake_run)
    monkeypatch.setattr(pilot, "_environment", lambda _: {})
    root = tmp_path / "output"
    result = pilot.run_pilot(
        source_repository=tmp_path, output_root=root, model="sonnet", loomgraph_binary="loomgraph", max_budget_usd="0.50"
    )

    assert result["status"] == "stopped"
    assert len(result["runs"]) == 2
    assert (root / "protocol-stop.json").is_file()
    assert not (root / "pilot-results.json").exists()
    assert not (root / "sparse-risk-review").exists()


def test_v3_driver_writes_protocol_stop_when_materialization_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pilot, "_environment", lambda _: {})

    def fail_materialize(*args: object, **kwargs: object) -> SimpleNamespace:
        raise RuntimeError("fixture checkout failed")

    monkeypatch.setattr(pilot, "materialize_temporal_review_v3_fixture", fail_materialize)
    root = tmp_path / "output"
    result = pilot.run_pilot(
        source_repository=tmp_path, output_root=root, model="sonnet", loomgraph_binary="loomgraph", max_budget_usd="0.50"
    )

    assert result["status"] == "stopped"
    stop = json.loads((root / "protocol-stop.json").read_text(encoding="utf-8"))
    assert stop["stage"] == "materialize"
    assert not (root / "pilot-results.json").exists()


def test_v3_driver_writes_preflight_stop_when_environment_capture_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_environment(_: str) -> dict[str, object]:
        raise FileNotFoundError("claude")

    monkeypatch.setattr(pilot, "_environment", fail_environment)
    root = tmp_path / "output"
    result = pilot.run_pilot(
        source_repository=tmp_path, output_root=root, model="sonnet", loomgraph_binary="loomgraph", max_budget_usd="0.50"
    )

    assert result["status"] == "stopped"
    assert json.loads((root / "protocol-stop.json").read_text(encoding="utf-8"))["stage"] == "preregistration"
    assert not any(root.glob("*/*/*/driver-run.json"))
    assert not (root / "pilot-results.json").exists()


def test_v3_driver_writes_contract_stop_before_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pilot, "_environment", lambda _: {})

    def fail_contract(_: str) -> SimpleNamespace:
        raise ValueError("manifest drift")

    monkeypatch.setattr(pilot, "contract", fail_contract)
    root = tmp_path / "output"
    result = pilot.run_pilot(
        source_repository=tmp_path, output_root=root, model="sonnet", loomgraph_binary="loomgraph", max_budget_usd="0.50"
    )

    assert result["status"] == "stopped"
    assert json.loads((root / "protocol-stop.json").read_text(encoding="utf-8"))["stage"] == "contract"
    assert not (root / "impact-low-resolution-review" / "rep-01" / "baseline" / "source").exists()


def test_v3_driver_continues_after_nonhard_semantic_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(pilot, "_environment", lambda _: {})
    monkeypatch.setattr(
        pilot,
        "materialize_temporal_review_v3_fixture",
        lambda task_id, destination, source_repository: SimpleNamespace(path=source, task_id=task_id),
    )

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True)
        (output / "orientation.json").write_text(
            json.dumps({"protocol": SURFACE, "status": "task_review_oracle_failed", "hard_protocol_stop": False}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr(pilot, "_run", fake_run)
    root = tmp_path / "output"
    result = pilot.run_pilot(
        source_repository=tmp_path, output_root=root, model="sonnet", loomgraph_binary="loomgraph", max_budget_usd="0.50"
    )

    assert len(result["runs"]) == 12
    assert (root / "pilot-results.json").is_file()
    assert not (root / "protocol-stop.json").exists()


def test_v3_driver_writes_source_clean_stop_when_git_query_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(pilot, "_environment", lambda _: {})
    monkeypatch.setattr(
        pilot,
        "materialize_temporal_review_v3_fixture",
        lambda task_id, destination, source_repository: SimpleNamespace(path=source, task_id=task_id),
    )

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "status"]:
            raise OSError("git unavailable")
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True)
        (output / "orientation.json").write_text(json.dumps({"protocol": SURFACE}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(pilot, "_run", fake_run)
    root = tmp_path / "output"
    result = pilot.run_pilot(
        source_repository=tmp_path, output_root=root, model="sonnet", loomgraph_binary="loomgraph", max_budget_usd="0.50"
    )

    assert result["status"] == "stopped"
    assert json.loads((root / "protocol-stop.json").read_text(encoding="utf-8"))["stage"] == "source_clean"
