"""Read-only audit for a complete, independent V7 temporal-review cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from evals import temporal_review_v7_fixtures as v7  # noqa: E402
from evals.deepswe import claude_orientation as orientation_runner  # noqa: E402
from evals.run_temporal_review_v7_model_identity import (  # noqa: E402
    _MODEL_SURFACES,
    _categories_valid,
    _model_categories,
)
from evals.run_temporal_review_v7_pilot import (  # noqa: E402
    MANIFEST_ID,
    PROTOCOL,
    SURFACE,
    expected_cells,
)

AUDIT_PROTOCOL = "temporal-review-v7-pilot-audit"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return value


def _payload_from_result(result: Mapping[str, Any]) -> object:
    """Decode one retained Claude result event without schema projection."""
    structured = result.get("structured_output")
    if isinstance(structured, Mapping):
        return dict(structured)
    encoded = result.get("result")
    if isinstance(encoded, str):
        try:
            decoded = json.loads(encoded)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, Mapping) else None
    return None


def _final_payload(path: Path) -> object:
    """Recover the complete final schema payload without packet projection."""
    return _payload_from_result(_read(path))


def _stream_final_payload(path: Path) -> object:
    """Recover the final structured payload from the retained raw stream."""
    for event in reversed(_events(path)):
        if event.get("type") != "result":
            continue
        payload = _payload_from_result(event)
        if payload is not None:
            return payload
    return None


def _canonical_payload(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return None


def _semantic_replay(
    *,
    task_id: str,
    condition: str,
    source_clean: bool,
    source_root: Path,
    raw_response: object | None,
    final_payload: object,
    orientation: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Replay the complete retained answer and bind it to runner scoring."""
    if source_clean:
        outcome = v7.evaluate_answer(
            task_id,
            final_payload,
            condition=condition,
            source_root=source_root,
            raw_response=raw_response,
        )
        semantic: dict[str, Any] = {"passed": outcome.passed, "failures": list(outcome.failures)}
    else:
        semantic = {"passed": False, "failures": ["source_checkout_missing_or_dirty"]}
    observed = orientation.get("task_review_observation")
    matches_orientation = (
        isinstance(observed, Mapping)
        and observed.get("passed") == semantic["passed"]
        and observed.get("failures") == semantic["failures"]
    )
    return semantic, matches_orientation


def _cell_path(root: Path, task_id: str, replicate: int, condition: str) -> Path:
    return root / task_id / f"rep-{replicate:02d}" / condition


def _require_complete_root(root: Path) -> dict[str, Any]:
    if (root / "protocol-stop.json").exists():
        raise ValueError("refusing audit: V7 cohort has a protocol-stop record")
    design = _read(root / "preregistration.json")
    result = _read(root / "pilot-results.json")
    if not (root / "environment.json").is_file():
        raise ValueError("V7 environment artifact is missing")
    if design.get("protocol") != PROTOCOL or result.get("protocol") != PROTOCOL:
        raise ValueError("refusing non-V7 temporal-review cohort")
    if design.get("manifest_id") != MANIFEST_ID or design.get("surface") != SURFACE:
        raise ValueError("V7 preregistration identity is invalid")
    if design.get("mode") != "voluntary":
        raise ValueError("V7 cohort must be voluntary")
    identity = design.get("model_identity")
    if (
        not isinstance(identity, Mapping)
        or identity.get("identity_mode") not in {"model-specific", "runtime-specific"}
        or not _categories_valid(
            identity,
            requested_model=str(identity.get("requested_model", "")),
            identity_mode=str(identity.get("identity_mode", "")),
        )
    ):
        raise ValueError("V7 model identity is invalid")
    identity_path = root / "model-identity-preflight.json"
    stream_path = root / "model-identity-preflight.stream.jsonl"
    if (
        identity.get("identity_path") != "model-identity-preflight.json"
        or identity.get("stream_path") != "model-identity-preflight.stream.jsonl"
        or not isinstance(identity.get("identity_sha256"), str)
        or not isinstance(identity.get("stream_sha256"), str)
        or not identity_path.is_file()
        or not stream_path.is_file()
        or hashlib.sha256(identity_path.read_bytes()).hexdigest() != identity["identity_sha256"]
        or hashlib.sha256(stream_path.read_bytes()).hexdigest() != identity["stream_sha256"]
    ):
        raise ValueError("V7 retained model identity artifact is invalid")
    retained_identity = _read(identity_path)
    stream_summary = orientation_runner.summarize_stream(_events(stream_path))
    stream_categories = _model_categories(_events(stream_path))
    if (
        retained_identity.get("protocol") != "temporal-review-v7-model-identity"
        or retained_identity.get("status") != "complete"
        or retained_identity.get("requested_model") != design.get("model")
        or stream_summary.get("final_result_seen") is not True
        or any(
            retained_identity.get(field) != identity.get(field)
            or stream_categories.get(field) != identity.get(field)
            for field in (
                "assistant_models_raw", "session_models_raw", "usage_models_raw",
                "assistant_models_canonical", "session_models_canonical", "usage_models_canonical",
            )
        )
        or not _categories_valid(
            stream_categories,
            requested_model=str(identity.get("requested_model", "")),
            identity_mode=str(identity.get("identity_mode", "")),
        )
        or retained_identity.get("claude_version") != identity.get("claude_version")
        or retained_identity.get("command_sha256") != identity.get("command_sha256")
    ):
        raise ValueError("V7 retained model identity does not match preregistration")
    expected = [
        {"task_id": task, "replicate": rep, "condition": condition}
        for task, rep, condition in expected_cells()
    ]
    expected_identities = set(expected_cells())
    if design.get("expected_cells") != expected:
        raise ValueError("V7 preregistration cell matrix was changed")
    manifest_hash = hashlib.sha256(v7.MANIFEST_PATH.read_bytes()).hexdigest()
    if design.get("manifest_sha256") != manifest_hash:
        raise ValueError("V7 manifest does not match preregistration hash")
    if design.get("selection_preflight_sha256") != v7.selection_preflight_sha256():
        raise ValueError("V7 selection preflight does not match preregistration hash")
    runs = result.get("runs")
    if not isinstance(runs, list) or len(runs) != len(expected):
        raise ValueError("V7 pilot result cardinality is invalid")
    identities = [(run.get("task_id"), run.get("replicate"), run.get("condition")) for run in runs if isinstance(run, Mapping)]
    if len(identities) != len(expected) or set(identities) != expected_identities:
        raise ValueError("V7 pilot result cells do not exactly equal preregistration")
    return design


def _events(stream_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in stream_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _raw_events(task_id: str, stream_path: Path) -> tuple[list[dict[str, Any]], list[str], int | None]:
    """Rebuild branch-diff event identity from retained JSONL, not certificate."""
    tool_by_id: dict[str, str] = {}
    tool_names: list[str] = []
    raw: list[dict[str, Any]] = []
    events = _events(stream_path)
    final_result_event_index: int | None = None
    for event_index in range(len(events) - 1, -1, -1):
        event = events[event_index]
        if event.get("type") != "result":
            continue
        if isinstance(event.get("structured_output"), Mapping):
            final_result_event_index = event_index
            break
        result = event.get("result")
        if isinstance(result, str):
            try:
                decoded = json.loads(result)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, Mapping):
                final_result_event_index = event_index
                break
    for event_index, event in enumerate(events):
        message = event.get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), list):
            continue
        for item in message["content"]:
            if not isinstance(item, Mapping):
                continue
            tool_use_id = item.get("tool_use_id")
            if item.get("type") == "tool_use" and isinstance(item.get("id"), str):
                name = item.get("name")
                if isinstance(name, str):
                    tool_by_id[item["id"]] = name
                    tool_names.append(name)
            if (
                item.get("type") != "tool_result"
                or not isinstance(tool_use_id, str)
                or tool_by_id.get(tool_use_id) != "mcp__loomgraph__loomgraph_branch_diff"
            ):
                continue
            content = item.get("content")
            values = content if isinstance(content, list) else [content]
            for value in values:
                text = value.get("text") if isinstance(value, Mapping) else value
                if not isinstance(text, str):
                    continue
                try:
                    response = json.loads(text)
                except json.JSONDecodeError:
                    response = None
                raw.append({
                    "stream_event_index": event_index,
                    "tool_use_id": tool_use_id,
                    "raw_json_text": text,
                    "raw_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "raw_response": response,
                    "observation": v7.parse_raw_response(task_id, response),
                })
    return raw, tool_names, final_result_event_index


def _tool_trace(*, tool_names: list[str], condition: str, orientation: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild reporting-only tool metadata while retaining MCP isolation."""
    forbidden_mcp = [
        name for name in tool_names
        if name.startswith("mcp__") and name != "mcp__loomgraph__loomgraph_branch_diff"
    ]
    count_matches_stream = (
        orientation.get("tool_call_count") == len(tool_names)
        and orientation.get("tool_call_names") == tool_names
    )
    valid = (
        count_matches_stream
        and not forbidden_mcp
        and (condition == "treatment" or not any(name.startswith("mcp__") for name in tool_names))
    )
    return {
        "count": len(tool_names),
        "names": tool_names,
        "valid": valid,
        "count_matches_stream": count_matches_stream,
        "count_is_reporting_only": True,
        "forbidden_mcp": forbidden_mcp,
    }


def _audit_cell(root: Path, task_id: str, replicate: int, condition: str) -> dict[str, Any]:
    cell = _cell_path(root, task_id, replicate, condition)
    required = [cell / "driver-run.json", cell / "output" / "orientation.json", cell / "output" / "run.json", cell / "output" / "command.json", cell / "output" / "pre-state.json", cell / "output" / "post-state.json", cell / "output" / "final-result.json", cell / "output" / "claude.stream.jsonl"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"V7 cell lacks immutable artifacts: {missing}")
    driver, orientation, run = _read(required[0]), _read(required[1]), _read(required[2])
    design = _read(root / "preregistration.json")
    pre_state, post_state = _read(required[4]), _read(required[5])
    if orientation.get("protocol") != SURFACE or driver.get("manifest_id") != MANIFEST_ID:
        raise ValueError(f"V7 cell has wrong protocol identity: {cell}")
    if (driver.get("task_id"), driver.get("replicate"), driver.get("condition")) != (task_id, replicate, condition):
        raise ValueError(f"V7 driver identity does not match path: {cell}")
    item = v7.contract(task_id)
    if driver.get("contract") != {
        "base_ref": item.base_ref,
        "head_ref": item.head_ref,
        "backend": item.backend,
    }:
        raise ValueError(f"V7 driver contract does not match frozen task: {cell}")
    source = Path(driver.get("source_dir", ""))
    runner_command = driver.get("runner_command")
    if (
        not isinstance(runner_command, list)
        or "--temporal-review-v7-contract" not in runner_command
        or SURFACE not in runner_command
        or source.resolve() != (cell / "source").resolve()
    ):
        raise ValueError(f"V7 driver command or source path is invalid: {cell}")
    source_clean = (
        orientation.get("source_clean") is True
        and driver.get("source_clean") is True
        and driver.get("source_status_return_code") == 0
        and pre_state == post_state
        and post_state.get("porcelain") == ""
        and source.is_dir()
    )
    expected_identity = design["model_identity"]
    observed_model = orientation.get("model")
    stream_categories = _model_categories(_events(required[-1]))
    raw_categories_match_stream = isinstance(observed_model, Mapping) and all(
        observed_model.get(f"{surface}_models_raw") == stream_categories.get(f"{surface}_models_raw")
        and observed_model.get(f"{surface}_models_canonical") == stream_categories.get(f"{surface}_models_canonical")
        for surface in _MODEL_SURFACES
    )
    model_identity_valid = (
        driver.get("model_identity_matches_preflight") is True
        and isinstance(observed_model, Mapping)
        and observed_model.get("requested") == expected_identity.get("requested_model")
        and observed_model.get("raw_categories_valid") is True
        and raw_categories_match_stream
        and _categories_valid(
            stream_categories,
            requested_model=str(expected_identity.get("requested_model", "")),
            identity_mode=str(expected_identity.get("identity_mode", "")),
        )
        and all(
            stream_categories.get(f"{surface}_models_canonical")
            == expected_identity.get(f"{surface}_models_canonical")
            for surface in _MODEL_SURFACES
        )
    )
    raw, tool_names, final_result_event_index = _raw_events(task_id, required[-1])
    before_final = [
        event for event in raw
        if final_result_event_index is not None and event["stream_event_index"] < final_result_event_index
    ]
    valid = [event for event in before_final if event["observation"].get("valid") is True]
    selected = valid[-1] if condition == "treatment" and valid else None
    raw_trace_valid = (
        final_result_event_index is not None
        and len(before_final) == len(raw)
        and len(valid) == len(before_final)
        and bool(before_final)
    ) if condition == "treatment" else not raw
    tool_trace = _tool_trace(tool_names=tool_names, condition=condition, orientation=orientation)
    tool_trace_valid = tool_trace["valid"]
    final_payload = _final_payload(required[6])
    stream_final_payload = _stream_final_payload(required[7])
    final_payload_matches_stream = (
        _canonical_payload(final_payload) is not None
        and _canonical_payload(final_payload) == _canonical_payload(stream_final_payload)
    )
    semantic, semantic_matches_orientation = _semantic_replay(
        task_id=task_id,
        condition=condition,
        source_clean=source_clean,
        source_root=source,
        raw_response=selected["raw_response"] if selected else None,
        final_payload=final_payload,
        orientation=orientation,
    )
    certificate = orientation.get("trust_observation", {}).get("selected_certificate") if isinstance(orientation.get("trust_observation"), Mapping) else None
    certificate_matches = (
        isinstance(certificate, Mapping) and selected is not None
        and certificate.get("selected_raw_event_index") == selected["stream_event_index"]
        and certificate.get("tool_use_id") == selected["tool_use_id"]
        and certificate.get("raw_sha256") == selected["raw_sha256"]
        and certificate.get("comparison") == selected["observation"].get("comparison")
    ) if condition == "treatment" else certificate is None
    warm = driver.get("warm_repeat")
    warm_valid = condition == "baseline"
    if condition == "treatment" and selected is not None and isinstance(warm, Mapping):
        warm_path = warm.get("raw_response_path")
        if isinstance(warm_path, str) and Path(warm_path).is_file():
            try:
                warm_raw = json.loads(Path(warm_path).read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                warm_raw = None
            warm_observation = v7.parse_raw_response(task_id, warm_raw)
            comparison = warm_observation.get("comparison") if warm_observation.get("valid") is True else None
            warm_valid = (
                warm.get("return_code") == 0
                and Path(warm_path).resolve().is_relative_to(cell.resolve())
                and warm.get("parsed_raw_observation") == warm_observation
                and isinstance(comparison, Mapping)
                and comparison.get("base_provisioned") == "reused"
                and comparison.get("head_provisioned") == "reused"
            )
    runner_valid = run.get("return_code") == 0 and driver.get("runner_return_code") == 0
    valid_row = source_clean and runner_valid and tool_trace_valid and raw_trace_valid and model_identity_valid and orientation.get("status") == "complete" and semantic["passed"] is True and semantic_matches_orientation and final_payload_matches_stream and certificate_matches and (condition == "baseline" or selected is not None)
    valid_row = valid_row and warm_valid
    exclusion_reason = None
    if not valid_row:
        exclusion_reason = (
            "audit_semantic_replay_mismatch"
            if not semantic_matches_orientation
            else "audit_final_payload_stream_mismatch"
            if not final_payload_matches_stream
            else orientation.get("invalid_reason") or "audit_replay_mismatch"
        )
    return {
        "task_id": task_id, "replicate": replicate, "condition": condition,
        "status": "valid" if valid_row else "excluded",
        "runtime_status": orientation.get("status"), "source_clean": source_clean,
        "agent_execution_seconds": orientation.get("agent_execution_seconds"),
        "raw_mcp": {"count": len(raw), "valid_count": len(valid), "selected": selected, "raw_trace_valid": raw_trace_valid},
        "tool_trace": tool_trace,
        "runner_valid": runner_valid,
        "model_identity_valid": model_identity_valid,
        "model_identity_raw_categories_match_stream": raw_categories_match_stream,
        "certificate_matches_rebuild": certificate_matches,
        "final_payload_sha256": hashlib.sha256(required[6].read_bytes()).hexdigest(),
        "final_payload_matches_stream": final_payload_matches_stream,
        "semantic": semantic,
        "semantic_replay_matches_orientation": semantic_matches_orientation,
        "warm_valid": warm_valid,
        "exclusion_reason": exclusion_reason,
    }


def _paired_navigation_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_cell = {(row["task_id"], row["replicate"], row["condition"]): row for row in records}
    by_task: dict[str, list[dict[str, object]]] = {task_id: [] for task_id in v7.TASK_IDS}
    for task_id in v7.TASK_IDS:
        for replicate in (1, 2):
            if (task_id, replicate, "baseline") not in by_cell:
                continue
            baseline, treatment = (
                by_cell[(task_id, replicate, "baseline")],
                by_cell[(task_id, replicate, "treatment")],
            )
            by_task[task_id].append(
                {
                    "replicate": replicate,
                    "baseline_status": baseline.get("status"),
                    "treatment_status": treatment.get("status"),
                    "complete_valid_pair": (
                        baseline.get("status") == "valid" and treatment.get("status") == "valid"
                    ),
                }
            )
    return by_task


def _expansion_gate(*, records: list[dict[str, Any]], no_protocol_stop: bool) -> dict[str, Any]:
    """Report whether this pilot may request, never start, a 72-run cohort."""
    paired = _paired_navigation_records(records)
    complete_valid_pairs_by_task = {
        task_id: sum(
            1 for row in rows if row.get("complete_valid_pair") is True
        )
        for task_id, rows in paired.items()
    }
    complete_valid_pair_count = sum(complete_valid_pairs_by_task.values())
    ast_unresolvable_exclusion_count = sum(
        1
        for row in records
        if "review locus does not resolve in frozen head AST" in row.get("semantic", {}).get("failures", [])
    )
    multiple_or_extra_structure_exclusion_count = sum(
        1
        for row in records
        if any(
            failure in {
                "answer top-level fields are invalid",
                "review locus fields are invalid",
            }
            for failure in row.get("semantic", {}).get("failures", [])
        )
    )
    semantic_replay_mismatch_count = sum(
        1 for row in records if row.get("semantic_replay_matches_orientation") is False
    )
    final_payload_stream_mismatch_count = sum(
        1 for row in records if row.get("final_payload_matches_stream") is False
    )
    model_identity_integrity_mismatch_count = sum(
        1
        for row in records
        if row.get("model_identity_valid") is not True
        or row.get("model_identity_raw_categories_match_stream") is not True
    )
    exact_8_cell_matrix = len(records) == len(expected_cells())
    eligible = (
        exact_8_cell_matrix
        and no_protocol_stop
        and complete_valid_pair_count >= 3
        and all(count >= 1 for count in complete_valid_pairs_by_task.values())
        and ast_unresolvable_exclusion_count == 0
        and multiple_or_extra_structure_exclusion_count == 0
        and semantic_replay_mismatch_count == 0
        and final_payload_stream_mismatch_count == 0
        and model_identity_integrity_mismatch_count == 0
    )
    return {
        "no_protocol_stop": no_protocol_stop,
        "complete_valid_pair_count": complete_valid_pair_count,
        "complete_valid_pairs_by_task": complete_valid_pairs_by_task,
        "ast_unresolvable_exclusion_count": ast_unresolvable_exclusion_count,
        "multiple_or_extra_structure_exclusion_count": multiple_or_extra_structure_exclusion_count,
        "semantic_replay_mismatch_count": semantic_replay_mismatch_count,
        "final_payload_stream_mismatch_count": final_payload_stream_mismatch_count,
        "model_identity_integrity_mismatch_count": model_identity_integrity_mismatch_count,
        "eligible_to_request_72_run": eligible,
        "automatic_expansion_authorized": False,
        "next_action": (
            "request_explicit_user_approval_for_72_run"
            if eligible
            else "do_not_request_72_run"
        ),
    }


def audit_pilot(output_root: Path) -> dict[str, object]:
    root = output_root.resolve()
    _require_complete_root(root)
    expected_paths = {
        Path(task_id) / f"rep-{replicate:02d}" / condition
        for task_id, replicate, condition in expected_cells()
    }
    discovered_paths = {
        path.parent.relative_to(root)
        for path in root.glob("*/*/*/driver-run.json")
    }
    if discovered_paths != expected_paths:
        raise ValueError("V7 discovered cell artifacts do not exactly equal preregistration")
    records = [_audit_cell(root, task, rep, condition) for task, rep, condition in expected_cells()]
    result: dict[str, object] = {
        "schema_version": 1,
        "protocol": AUDIT_PROTOCOL,
        "source_protocol": PROTOCOL,
        "runs": records,
        "paired_navigation_records_by_task": _paired_navigation_records(records),
        "expansion_gate": _expansion_gate(records=records, no_protocol_stop=True),
    }
    path = root / "audited-results.json"
    if path.exists():
        raise ValueError("refusing to overwrite an existing V7 audit")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_pilot(args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
