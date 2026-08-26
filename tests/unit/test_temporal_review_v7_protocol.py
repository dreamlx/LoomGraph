"""V7 model-identity ordering and retained-stream protocol guards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from evals import audit_temporal_review_v7_pilot as audit
from evals import run_temporal_review_v7_model_identity as identity
from evals import run_temporal_review_v7_pilot as pilot
from evals.deepswe import claude_orientation as orientation
from evals.temporal_review_v7_fixtures import contract


def _events(*, assistant: list[str], session: list[str], usage: list[str]) -> list[dict[str, object]]:
    return (
        [{"type": "system", "model": label} for label in session]
        + [{"type": "assistant", "message": {"model": label, "content": []}} for label in assistant]
        + [{"type": "result", "structured_output": {"ok": True}, "modelUsage": {label: {} for label in usage}}]
    )


def _categories(*, assistant: list[str], session: list[str], usage: list[str]) -> dict[str, object]:
    return identity._model_categories(_events(assistant=assistant, session=session, usage=usage))


def _orientation(categories: dict[str, object]) -> dict[str, object]:
    return {
        "model": {
            "requested": "runtime",
            "raw_categories_valid": categories["model_categories_valid"],
            **{key: categories[key] for key in categories if key.endswith(("_raw", "_canonical"))},
        }
    }


def _identity(categories: dict[str, object]) -> dict[str, object]:
    return {
        "requested_model": "runtime",
        "identity_mode": "runtime-specific",
        **{key: categories[key] for key in categories if key.endswith(("_raw", "_canonical"))},
    }


def test_v7_order_only_usage_change_is_compatible_but_raw_order_is_retained() -> None:
    preflight = _categories(assistant=["runtime"], session=["session"], usage=["a", "b"])
    cell = _categories(assistant=["runtime"], session=["session"], usage=["b", "a"])

    assert preflight["usage_models_raw"] == ["a", "b"]
    assert cell["usage_models_raw"] == ["b", "a"]
    assert preflight["usage_models_canonical"] == cell["usage_models_canonical"] == ["a", "b"]
    assert pilot._identity_matches(_orientation(cell), _identity(preflight)) is True


@pytest.mark.parametrize(
    "assistant,session,usage",
    [
        (["runtime"], ["session"], ["a", "b", "extra"]),
        (["runtime"], ["session"], ["a"]),
        (["runtime"], ["session"], ["a", "replacement"]),
        (["runtime"], ["a"], ["session", "b"]),
    ],
)
def test_v7_label_addition_removal_replacement_or_cross_surface_fails(
    assistant: list[str], session: list[str], usage: list[str]
) -> None:
    preflight = _categories(assistant=["runtime"], session=["session"], usage=["a", "b"])
    cell = _categories(assistant=assistant, session=session, usage=usage)

    assert pilot._identity_matches(_orientation(cell), _identity(preflight)) is False


def test_v7_repeated_native_assistant_label_is_valid_and_raw_order_is_retained() -> None:
    categories = _categories(assistant=["runtime", "runtime"], session=[], usage=["a"])

    assert categories["assistant_models_canonical"] == ["runtime"]
    assert categories["assistant_models_raw"] == ["runtime", "runtime"]
    assert categories["model_categories_valid"] is True
    assert identity._categories_valid(categories, requested_model="runtime", identity_mode="runtime-specific") is True


@pytest.mark.parametrize("assistant", [[], [""]])
def test_v7_missing_or_malformed_assistant_label_is_invalid(assistant: list[str]) -> None:
    categories = _categories(assistant=assistant, session=[], usage=["a"])

    assert categories["model_categories_valid"] is False
    assert identity._categories_valid(categories, requested_model="runtime", identity_mode="runtime-specific") is False


def test_v7_identity_preflight_rebuilds_raw_order_and_rejects_json_stream_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "identity"
    root.mkdir()
    events = _events(assistant=["runtime"], session=["session"], usage=["b", "a"])
    stream = root / "claude.stream.jsonl"
    stream.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    categories = identity._model_categories(events)
    command = ["claude", "-p", "--model", "runtime"]
    preflight = {
        "protocol": identity.PROTOCOL,
        "status": "complete",
        "identity_mode": "runtime-specific",
        "requested_model": "runtime",
        **{key: categories[key] for key in categories if key.endswith(("_raw", "_canonical"))},
        "claude_version": {"return_code": 0},
        "command": command,
        "command_sha256": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode()).hexdigest(),
    }
    path = root / "identity-preflight.json"
    path.write_text(json.dumps(preflight), encoding="utf-8")

    rebuilt = pilot._model_identity(root, "runtime")
    assert rebuilt["usage_models_raw"] == ["b", "a"]
    assert rebuilt["usage_models_canonical"] == ["a", "b"]

    preflight["usage_models_raw"] = ["a", "b"]
    path.write_text(json.dumps(preflight), encoding="utf-8")
    with pytest.raises(ValueError, match="retained raw categories"):
        pilot._model_identity(root, "runtime")


def test_v7_packet_keeps_repeated_raw_categories_without_a_validity_failure(tmp_path: Path) -> None:
    task_id = "v7-impact-caller-qualification-primary-navigation"
    item = contract(task_id)
    path = item.oracle["required_review_locus"]["path"]
    source = tmp_path / path
    source.parent.mkdir(parents=True)
    source.write_text("class ImpactAnalyzer:\n    async def _find_callers(self):\n        return []\n")
    raw = {
        "success": True,
        "data": {
            "base": {"ref": item.base_ref, "sha": item.refs["base"]["commit_sha"], "workspace": "base", "provisioned": "created"},
            "head": {"ref": item.head_ref, "sha": item.refs["head"]["commit_sha"], "workspace": "head", "provisioned": "reused"},
            "diff": {"content_comparison": {**item.expected_comparison, "changed": []}},
        },
    }
    answer = {
        "decision": {"boundary": "content_comparison_available", "rationale": "public"},
        "review_locus": {**item.oracle["required_review_locus"], "rationale": "identity"},
    }
    categories = _categories(assistant=["runtime", "runtime"], session=[], usage=["a"])
    packet = orientation.build_temporal_review_v7_packet(
        condition="treatment", use_mode="voluntary", source_clean=True, source_dir=tmp_path,
        return_code=0, contract=item, requested_model="runtime", summary={
            "final_result_seen": True, "final_result_event_index": 2, "payload": answer,
            "tool_names": [orientation.TEMPORAL_MCP_TOOL], "unexpected_mcp_tools": [],
            "raw_branch_diff_events": [{"stream_event_index": 1, "tool_use_id": "raw", "raw_response": raw}],
            **categories,
        },
    )

    assert packet["hard_protocol_stop"] is False
    assert packet["invalid_reason"] != "model_identity_raw_labels_invalid"
    assert packet["model"]["assistant_models_raw"] == ["runtime", "runtime"]


def test_v7_audit_replays_full_final_payload_and_detects_stream_mismatch(tmp_path: Path) -> None:
    final_path = tmp_path / "final-result.json"
    stream_path = tmp_path / "claude.stream.jsonl"
    payload = {"decision": {"boundary": "comparison_not_observed", "rationale": "x"}, "review_locus": {"path": "x", "qualname": "x", "rationale": "x"}}
    final_path.write_text(json.dumps({"type": "result", "structured_output": payload}), encoding="utf-8")
    stream_path.write_text(json.dumps({"type": "result", "structured_output": {**payload, "extra": True}}) + "\n", encoding="utf-8")

    assert audit._canonical_payload(audit._final_payload(final_path)) != audit._canonical_payload(audit._stream_final_payload(stream_path))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _auditable_baseline_cell(
    root: Path, *, stream_categories: dict[str, object], recorded_categories: dict[str, object]
) -> dict[str, Any]:
    task_id, replicate, condition = pilot.expected_cells()[0]
    item = contract(task_id)
    cell = root / task_id / f"rep-{replicate:02d}" / condition
    source = cell / "source"
    locus = item.oracle["required_review_locus"]
    source_path = source / locus["path"]
    source_path.parent.mkdir(parents=True)
    source_path.write_text("class ImpactAnalyzer:\n    async def _find_callers(self):\n        return []\n", encoding="utf-8")
    answer = {
        "decision": {"boundary": "comparison_not_observed", "rationale": "public"},
        "review_locus": {**locus, "rationale": "identity"},
    }
    events = _events(
        assistant=list(stream_categories["assistant_models_raw"]),
        session=list(stream_categories["session_models_raw"]),
        usage=list(stream_categories["usage_models_raw"]),
    )
    events[-1]["structured_output"] = answer
    output = cell / "output"
    output.mkdir(parents=True)
    (output / "claude.stream.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    model = {
        "requested": "runtime",
        "raw_categories_valid": True,
        **{key: recorded_categories[key] for key in recorded_categories if key.endswith(("_raw", "_canonical"))},
    }
    orientation_record = {
        "protocol": audit.SURFACE,
        "status": "complete",
        "source_clean": True,
        "tool_call_count": 0,
        "tool_call_names": [],
        "model": model,
        "task_review_observation": {"passed": True, "failures": []},
        "trust_observation": {"selected_certificate": None},
    }
    state = {"head": "frozen", "porcelain": ""}
    _write_json(output / "orientation.json", orientation_record)
    _write_json(output / "run.json", {"return_code": 0})
    _write_json(output / "command.json", ["claude"])
    _write_json(output / "pre-state.json", state)
    _write_json(output / "post-state.json", state)
    _write_json(output / "final-result.json", {"type": "result", "structured_output": answer})
    _write_json(
        cell / "driver-run.json",
        {
            "task_id": task_id,
            "replicate": replicate,
            "condition": condition,
            "manifest_id": audit.MANIFEST_ID,
            "contract": {"base_ref": item.base_ref, "head_ref": item.head_ref, "backend": item.backend},
            "source_dir": str(source),
            "runner_command": ["runner", "--temporal-review-v7-contract", audit.SURFACE],
            "source_clean": True,
            "source_status_return_code": 0,
            "runner_return_code": 0,
            "model_identity_matches_preflight": True,
        },
    )
    _write_json(
        root / "preregistration.json",
        {"model_identity": {"requested_model": "runtime", "identity_mode": "runtime-specific", **{
            key: recorded_categories[key] for key in recorded_categories if key.endswith(("_raw", "_canonical"))
        }}},
    )
    return audit._audit_cell(root, task_id, replicate, condition)


@pytest.mark.parametrize(
    "stream,recorded",
    [
        (_categories(assistant=["drift"], session=[], usage=["a", "b"]), _categories(assistant=["runtime"], session=[], usage=["a", "b"])),
        (_categories(assistant=["a"], session=["runtime"], usage=["b"]), _categories(assistant=["runtime"], session=["a"], usage=["b"])),
        (_categories(assistant=["runtime"], session=[], usage=["b", "a"]), _categories(assistant=["runtime"], session=[], usage=["a", "b"])),
        (_categories(assistant=["runtime"], session=[], usage=["a", "b"]), {**_categories(assistant=["runtime"], session=[], usage=["a", "b"]), "usage_models_canonical": ["forged"]}),
    ],
)
def test_v7_audit_cell_rejects_retained_stream_identity_drift_even_when_records_claim_match(
    tmp_path: Path, stream: dict[str, object], recorded: dict[str, object]
) -> None:
    row = _auditable_baseline_cell(tmp_path, stream_categories=stream, recorded_categories=recorded)
    records = [
        {
            "task_id": task_id,
            "replicate": replicate,
            "condition": condition,
            "status": "valid",
            "semantic": {"failures": []},
            "semantic_replay_matches_orientation": True,
            "final_payload_matches_stream": True,
            "model_identity_valid": True,
            "model_identity_raw_categories_match_stream": True,
        }
        for task_id, replicate, condition in pilot.expected_cells()
    ]
    records[0] = row

    gate = audit._expansion_gate(records=records, no_protocol_stop=True)

    assert row["status"] == "excluded"
    assert row["model_identity_valid"] is False
    assert row["model_identity_raw_categories_match_stream"] is False
    assert gate["model_identity_integrity_mismatch_count"] == 1
    assert gate["eligible_to_request_72_run"] is False
