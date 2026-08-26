"""V4 runner and adapter guards independent of historical cohorts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from evals import run_temporal_review_v4_pilot as pilot
from evals.deepswe import claude_orientation as orientation
from evals.temporal_review_v4_fixtures import contract


def _source(root: Path) -> None:
    analyzer = root / "src/loomgraph/core/impact/analyzer.py"
    git = root / "src/loomgraph/core/git.py"
    analyzer.parent.mkdir(parents=True)
    analyzer.write_text("class ImpactAnalyzer:\n    async def _find_callers(self):\n        return []\n")
    git.write_text("def get_changed_files():\n    return []\n")


def _raw(task_id: str) -> dict[str, object]:
    item = contract(task_id)
    locus = item.oracle["required_review_loci"][0]
    return {
        "success": True,
        "data": {
            "base": {"ref": item.base_ref, "sha": item.refs["base"]["commit_sha"], "workspace": "base", "provisioned": "created"},
            "head": {"ref": item.head_ref, "sha": item.refs["head"]["commit_sha"], "workspace": "head", "provisioned": "reused"},
            "diff": {"content_comparison": {"version": 1, "scope": "same_backend_only", "status": "available", "reason": None, "base_backend": "codeindex", "head_backend": "codeindex", "changed": [{"source_id": f"{locus['path']}:1", "name": locus["qualname"]}]}},
        },
    }


def _answer(task_id: str, boundary: str) -> dict[str, object]:
    locus = contract(task_id).oracle["required_review_loci"][0]
    return {"decision": {"boundary": boundary, "rationale": "public boundary"}, "review_loci": [{"path": locus["path"], "qualname": locus["qualname"], "rationale": "identity"}]}


def _identity_probe(
    root: Path, *, requested: str, assistant: list[str], session: list[str], usage: list[str], mode: str
) -> Path:
    root.mkdir()
    events: list[dict[str, Any]] = [
        {"type": "system", "model": item} for item in session
    ] + [
        {"type": "assistant", "message": {"model": item, "content": []}} for item in assistant
    ] + [
        {"type": "result", "structured_output": {"ok": True}, "modelUsage": {item: {} for item in usage}}
    ]
    stream = root / "claude.stream.jsonl"
    stream.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    command = ["claude", "-p", "--model", requested]
    (root / "identity-preflight.json").write_text(json.dumps({
        "protocol": "temporal-review-v4-model-identity", "status": "complete", "identity_mode": mode,
        "requested_model": requested, "assistant_models": assistant, "session_models": session,
        "usage_models": usage, "claude_version": {"return_code": 0, "stdout": "Claude Code 2", "stderr": ""},
        "command": command,
        "command_sha256": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode()).hexdigest(),
    }), encoding="utf-8")
    return root


def test_v4_command_schema_has_no_hidden_outcome_or_trust() -> None:
    command = orientation.build_command(
        condition="treatment", instruction="review", model="runtime", budget_usd="0.50", loomgraph_binary="loomgraph",
        treatment_surface=orientation.TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE, temporal_review_v4=True,
    )
    schema = json.loads(command[command.index("--json-schema") + 1])

    assert schema["properties"]["decision"]["required"] == ["boundary", "rationale"]
    assert "outcome" not in schema["properties"]["decision"]["properties"]
    assert "trust" not in schema["properties"]


def test_v4_packet_binds_boundary_identity_and_one_pre_final_raw_event(tmp_path: Path) -> None:
    task_id = "impact-caller-qualification-navigation"
    _source(tmp_path)
    raw = _raw(task_id)
    raw_text = json.dumps(raw, separators=(",", ":"))
    packet = orientation.build_temporal_review_v4_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path, return_code=0,
        contract=contract(task_id), requested_model="runtime", summary={
            "final_result_seen": True, "final_result_event_index": 4,
            "payload": _answer(task_id, "content_comparison_available"),
            "tool_names": [orientation.TEMPORAL_MCP_TOOL], "unexpected_mcp_tools": [],
            "assistant_models": ["runtime"], "session_models": [], "usage_models": [], "observed_models": ["runtime"],
            "raw_branch_diff_events": [{"stream_event_index": 3, "tool_use_id": "raw", "raw_json_text": raw_text, "raw_response": raw, "raw_sha256": hashlib.sha256(raw_text.encode()).hexdigest()}],
        },
    )

    assert packet["status"] == "complete"
    assert packet["trust_observation"]["selected_certificate"]["tool_use_id"] == "raw"
    assert "trust" not in packet


def test_v4_packet_stops_on_raw_after_final_result(tmp_path: Path) -> None:
    task_id = "working-tree-diff-default-navigation"
    _source(tmp_path)
    packet = orientation.build_temporal_review_v4_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path, return_code=0,
        contract=contract(task_id), summary={
            "final_result_seen": True, "final_result_event_index": 2,
            "payload": _answer(task_id, "content_comparison_available"),
            "tool_names": [orientation.TEMPORAL_MCP_TOOL], "unexpected_mcp_tools": [], "raw_branch_diff_events": [{"stream_event_index": 3, "tool_use_id": "late", "raw_response": _raw(task_id)}],
        },
    )

    assert packet["hard_protocol_stop"] is True
    assert packet["invalid_reason"] == "branch_diff_response_after_final_result"


def test_v4_model_specific_identity_requires_exact_requested_model(tmp_path: Path) -> None:
    probe = _identity_probe(
        tmp_path / "probe", requested="sonnet", assistant=["glm-5.3"], session=[], usage=[], mode="model-specific"
    )

    with pytest.raises(ValueError, match="match exactly"):
        pilot._model_identity(probe, "sonnet")


def test_v4_runtime_identity_requires_each_cell_to_match_preflight() -> None:
    identity: dict[str, Any] = {
        "requested_model": "runtime-token", "assistant_models": ["runtime-a"],
        "session_models": ["session-a"], "usage_models": ["usage-a"],
    }

    assert not pilot._identity_matches({"model": {
        "requested": "runtime-token", "assistant_observed": ["runtime-a"],
        "session_observed": ["session-b"], "usage_observed": ["usage-a"],
    }}, identity)
    assert pilot._identity_matches({"model": {
        "requested": "runtime-token", "assistant_observed": ["runtime-a"],
        "session_observed": ["session-a"], "usage_observed": ["usage-a"],
    }}, identity)


def test_v4_model_identity_rebuilds_retained_stream(tmp_path: Path) -> None:
    probe = _identity_probe(
        tmp_path / "probe", requested="runtime-token", assistant=["runtime-a"],
        session=["session-a"], usage=["usage-a"], mode="runtime-specific"
    )

    identity = pilot._model_identity(probe, "runtime-token")

    assert identity["assistant_models"] == ["runtime-a"]
    assert identity["stream_sha256"] == hashlib.sha256((probe / "claude.stream.jsonl").read_bytes()).hexdigest()
