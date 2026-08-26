"""V6 runner and adapter guards independent of historical cohorts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from evals import audit_temporal_review_v6_pilot as audit
from evals import run_temporal_review_v6_pilot as pilot
from evals.deepswe import claude_orientation as orientation
from evals.temporal_review_v6_fixtures import contract, evaluate_answer


def _source(root: Path) -> None:
    analyzer = root / "src/loomgraph/core/impact/analyzer.py"
    git = root / "src/loomgraph/core/git.py"
    analyzer.parent.mkdir(parents=True)
    analyzer.write_text("class ImpactAnalyzer:\n    async def _find_callers(self):\n        return []\n")
    git.write_text("def get_changed_files():\n    return []\n")


def _raw(task_id: str) -> dict[str, object]:
    item = contract(task_id)
    locus = item.oracle["required_review_locus"]
    return {
        "success": True,
        "data": {
            "base": {"ref": item.base_ref, "sha": item.refs["base"]["commit_sha"], "workspace": "base", "provisioned": "created"},
            "head": {"ref": item.head_ref, "sha": item.refs["head"]["commit_sha"], "workspace": "head", "provisioned": "reused"},
            "diff": {"content_comparison": {"version": 1, "scope": "same_backend_only", "status": "available", "reason": None, "base_backend": "codeindex", "head_backend": "codeindex", "changed": [{"source_id": f"{locus['path']}:1", "name": locus["qualname"]}]}},
        },
    }


def _answer(task_id: str, boundary: str) -> dict[str, object]:
    locus = contract(task_id).oracle["required_review_locus"]
    return {
        "decision": {"boundary": boundary, "rationale": "public boundary"},
        "review_locus": {
            "path": locus["path"], "qualname": locus["qualname"], "rationale": "identity",
        },
    }


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
        "protocol": "temporal-review-v6-model-identity", "status": "complete", "identity_mode": mode,
        "requested_model": requested, "assistant_models": assistant, "session_models": session,
        "usage_models": usage, "claude_version": {"return_code": 0, "stdout": "Claude Code 2", "stderr": ""},
        "command": command,
        "command_sha256": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode()).hexdigest(),
    }), encoding="utf-8")
    return root


def test_v6_command_schema_has_no_hidden_outcome_or_trust_or_call_cap() -> None:
    command = orientation.build_command(
        condition="treatment", instruction="review", model="runtime", budget_usd="0.50", loomgraph_binary="loomgraph",
        treatment_surface=orientation.TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE, temporal_review_v6=True,
    )
    schema = json.loads(command[command.index("--json-schema") + 1])

    assert schema["properties"]["decision"]["required"] == ["boundary", "rationale"]
    assert set(schema["properties"]) == {"decision", "review_locus"}
    assert schema["properties"]["review_locus"]["type"] == "object"
    assert "review_loci" not in schema["properties"]
    assert "outcome" not in schema["properties"]["decision"]["properties"]
    assert "trust" not in schema["properties"]


def test_v6_contract_rejects_array_or_extra_locus_fields(tmp_path: Path) -> None:
    task_id = "v6-impact-caller-qualification-primary-navigation"
    _source(tmp_path)
    answer = _answer(task_id, "comparison_not_observed")
    answer["review_locus"] = [answer["review_locus"]]

    result = evaluate_answer(task_id, answer, condition="baseline", source_root=tmp_path)

    assert result.passed is False
    assert "review locus fields are invalid" in result.failures

    extra = _answer(task_id, "comparison_not_observed")
    extra["review_loci"] = []
    assert evaluate_answer(task_id, extra, condition="baseline", source_root=tmp_path).passed is False


def test_v6_condition_requirement_has_no_tool_call_cap() -> None:
    baseline = orientation._append_temporal_review_v6_requirement("review", "baseline")
    treatment = orientation._append_temporal_review_v6_requirement("review", "treatment")

    assert "at most" not in baseline
    assert "at most" not in treatment
    assert "Use the branch-diff tool" in treatment


def test_v6_packet_reports_six_calls_without_a_validity_failure(tmp_path: Path) -> None:
    task_id = "v6-working-tree-diff-default-primary-navigation"
    _source(tmp_path)
    raw = _raw(task_id)
    raw_text = json.dumps(raw, separators=(",", ":"))
    tool_names = [orientation.TEMPORAL_MCP_TOOL, "Read", "Grep", "Grep", "Grep", "StructuredOutput"]

    packet = orientation.build_temporal_review_v6_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path, return_code=0,
        contract=contract(task_id), requested_model="runtime", summary={
            "final_result_seen": True, "final_result_event_index": 7,
            "payload": _answer(task_id, "content_comparison_available"),
            "tool_names": tool_names, "unexpected_mcp_tools": [],
            "raw_branch_diff_events": [{"stream_event_index": 1, "tool_use_id": "raw", "raw_json_text": raw_text, "raw_response": raw, "raw_sha256": hashlib.sha256(raw_text.encode()).hexdigest()}],
        },
    )

    assert packet["status"] == "complete"
    assert packet["hard_protocol_stop"] is False
    assert packet["tool_call_count"] == 6
    assert packet["tool_call_names"] == tool_names
    assert "tool_call_budget" not in packet


def test_v6_audit_reports_six_calls_without_a_threshold_exclusion() -> None:
    tool_names = [orientation.TEMPORAL_MCP_TOOL, "Read", "Grep", "Grep", "Grep", "StructuredOutput"]

    trace = audit._tool_trace(
        tool_names=tool_names,
        condition="treatment",
        orientation={"tool_call_count": 6, "tool_call_names": tool_names},
    )

    assert trace["valid"] is True
    assert trace["count"] == 6
    assert trace["count_is_reporting_only"] is True

    tampered = audit._tool_trace(
        tool_names=tool_names,
        condition="treatment",
        orientation={"tool_call_count": 5, "tool_call_names": tool_names},
    )
    assert tampered["valid"] is False


def test_v6_packet_binds_boundary_identity_and_one_pre_final_raw_event(tmp_path: Path) -> None:
    task_id = "v6-impact-caller-qualification-primary-navigation"
    _source(tmp_path)
    raw = _raw(task_id)
    raw_text = json.dumps(raw, separators=(",", ":"))
    packet = orientation.build_temporal_review_v6_packet(
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
    assert "review_loci" not in packet
    assert packet["review_locus"]["qualname"] == contract(task_id).oracle["required_review_locus"]["qualname"]


def test_v6_packet_stops_on_raw_after_final_result(tmp_path: Path) -> None:
    task_id = "v6-working-tree-diff-default-primary-navigation"
    _source(tmp_path)
    packet = orientation.build_temporal_review_v6_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path, return_code=0,
        contract=contract(task_id), summary={
            "final_result_seen": True, "final_result_event_index": 2,
            "payload": _answer(task_id, "content_comparison_available"),
            "tool_names": [orientation.TEMPORAL_MCP_TOOL], "unexpected_mcp_tools": [], "raw_branch_diff_events": [{"stream_event_index": 3, "tool_use_id": "late", "raw_response": _raw(task_id)}],
        },
    )

    assert packet["hard_protocol_stop"] is True
    assert packet["invalid_reason"] == "branch_diff_response_after_final_result"


def test_v6_model_specific_identity_requires_exact_requested_model(tmp_path: Path) -> None:
    probe = _identity_probe(
        tmp_path / "probe", requested="sonnet", assistant=["glm-5.3"], session=[], usage=[], mode="model-specific"
    )

    with pytest.raises(ValueError, match="match exactly"):
        pilot._model_identity(probe, "sonnet")


def test_v6_runtime_identity_requires_each_cell_to_match_preflight() -> None:
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


def test_v6_model_identity_rebuilds_retained_stream(tmp_path: Path) -> None:
    probe = _identity_probe(
        tmp_path / "probe", requested="runtime-token", assistant=["runtime-a"],
        session=["session-a"], usage=["usage-a"], mode="runtime-specific"
    )

    identity = pilot._model_identity(probe, "runtime-token")

    assert identity["assistant_models"] == ["runtime-a"]
    assert identity["stream_sha256"] == hashlib.sha256((probe / "claude.stream.jsonl").read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("payload", "failure"),
    [
        (
            lambda task_id: {**_answer(task_id, "comparison_not_observed"), "unexpected": True},
            "answer top-level fields are invalid",
        ),
        (
            lambda task_id: {**_answer(task_id, "comparison_not_observed"), "review_loci": []},
            "answer top-level fields are invalid",
        ),
        (
            lambda task_id: {
                **_answer(task_id, "comparison_not_observed"),
                "review_locus": [_answer(task_id, "comparison_not_observed")["review_locus"]],
            },
            "review locus fields are invalid",
        ),
        (
            lambda task_id: {
                **_answer(task_id, "comparison_not_observed"),
                "review_locus": {
                    **_answer(task_id, "comparison_not_observed")["review_locus"],
                    "qualname": "ImpactAnalyzer.missing",
                },
            },
            "review locus does not resolve in frozen head AST",
        ),
    ],
)
def test_v6_audit_replays_full_final_payload_without_packet_projection(
    tmp_path: Path, payload: Any, failure: str
) -> None:
    task_id = "v6-impact-caller-qualification-primary-navigation"
    _source(tmp_path)
    semantic, matches_orientation = audit._semantic_replay(
        task_id=task_id,
        condition="baseline",
        source_clean=True,
        source_root=tmp_path,
        raw_response=None,
        final_payload=payload(task_id),
        orientation={"task_review_observation": {"passed": True, "failures": []}},
    )

    assert semantic["passed"] is False
    assert failure in semantic["failures"]
    assert matches_orientation is False


def test_v6_audit_semantic_replay_requires_runner_observation_alignment(tmp_path: Path) -> None:
    task_id = "v6-impact-caller-qualification-primary-navigation"
    _source(tmp_path)
    semantic, matches_orientation = audit._semantic_replay(
        task_id=task_id,
        condition="baseline",
        source_clean=True,
        source_root=tmp_path,
        raw_response=None,
        final_payload=_answer(task_id, "comparison_not_observed"),
        orientation={"task_review_observation": {"passed": False, "failures": ["tampered"]}},
    )

    assert semantic == {"passed": True, "failures": []}
    assert matches_orientation is False


def test_v6_audit_requires_final_result_payload_to_match_retained_stream(tmp_path: Path) -> None:
    task_id = "v6-impact-caller-qualification-primary-navigation"
    final_path = tmp_path / "final-result.json"
    stream_path = tmp_path / "claude.stream.jsonl"
    final_path.write_text(
        json.dumps({"type": "result", "structured_output": _answer(task_id, "comparison_not_observed")}),
        encoding="utf-8",
    )
    stream_path.write_text(
        json.dumps({
            "type": "result",
            "structured_output": {**_answer(task_id, "comparison_not_observed"), "unexpected": True},
        }) + "\n",
        encoding="utf-8",
    )

    final_payload = audit._final_payload(final_path)
    stream_payload = audit._stream_final_payload(stream_path)

    assert audit._canonical_payload(final_payload) != audit._canonical_payload(stream_payload)


def _gate_records(
    complete_pairs: set[tuple[str, int]], *, failures: dict[tuple[str, int, str], list[str]] | None = None
) -> list[dict[str, Any]]:
    failures = failures or {}
    records: list[dict[str, Any]] = []
    for task_id, replicate, condition in pilot.expected_cells():
        records.append(
            {
                "task_id": task_id,
                "replicate": replicate,
                "condition": condition,
                "status": "valid" if (task_id, replicate) in complete_pairs else "excluded",
                "semantic": {"failures": failures.get((task_id, replicate, condition), [])},
            }
        )
    return records


def test_v6_expansion_gate_requires_three_of_four_complete_pairs() -> None:
    first, second = pilot.TASK_IDS
    two = audit._expansion_gate(
        records=_gate_records({(first, 1), (second, 1)}), no_protocol_stop=True
    )
    three = audit._expansion_gate(
        records=_gate_records({(first, 1), (first, 2), (second, 1)}), no_protocol_stop=True
    )

    assert two["complete_valid_pair_count"] == 2
    assert two["eligible_to_request_72_run"] is False
    assert three["complete_valid_pair_count"] == 3
    assert three["eligible_to_request_72_run"] is True
    assert three["automatic_expansion_authorized"] is False
    assert three["next_action"] == "request_explicit_user_approval_for_72_run"


def test_v6_expansion_gate_rejects_task_with_zero_pairs_or_structure_exclusions() -> None:
    first, second = pilot.TASK_IDS
    task_zero = audit._expansion_gate(
        records=_gate_records({(first, 1), (first, 2)}), no_protocol_stop=True
    )
    excluded = audit._expansion_gate(
        records=_gate_records(
            {(first, 1), (first, 2), (second, 1)},
            failures={
                (first, 1, "baseline"): ["review locus does not resolve in frozen head AST"],
                (second, 1, "treatment"): ["answer top-level fields are invalid"],
            },
        ),
        no_protocol_stop=True,
    )

    assert task_zero["complete_valid_pairs_by_task"][second] == 0
    assert task_zero["eligible_to_request_72_run"] is False
    assert excluded["ast_unresolvable_exclusion_count"] == 1
    assert excluded["multiple_or_extra_structure_exclusion_count"] == 1
    assert excluded["eligible_to_request_72_run"] is False


def test_v6_expansion_gate_rejects_semantic_or_final_stream_replay_mismatches() -> None:
    first, second = pilot.TASK_IDS
    records = _gate_records({(first, 1), (first, 2), (second, 1)})
    records[0]["semantic_replay_matches_orientation"] = False
    records[1]["final_payload_matches_stream"] = False

    gate = audit._expansion_gate(records=records, no_protocol_stop=True)

    assert gate["semantic_replay_mismatch_count"] == 1
    assert gate["final_payload_stream_mismatch_count"] == 1
    assert gate["eligible_to_request_72_run"] is False
    assert gate["automatic_expansion_authorized"] is False
