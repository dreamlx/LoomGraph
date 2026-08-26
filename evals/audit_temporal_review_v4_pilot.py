"""Read-only audit for a complete, independent v4 temporal-review cohort."""

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

from evals import temporal_review_v4_fixtures as v4  # noqa: E402
from evals.deepswe import claude_orientation as orientation_runner  # noqa: E402
from evals.run_temporal_review_v4_pilot import (  # noqa: E402
    MANIFEST_ID,
    PROTOCOL,
    SURFACE,
    expected_cells,
)

AUDIT_PROTOCOL = "temporal-review-v4-pilot-audit"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return value


def _cell_path(root: Path, task_id: str, replicate: int, condition: str) -> Path:
    return root / task_id / f"rep-{replicate:02d}" / condition


def _require_complete_root(root: Path) -> dict[str, Any]:
    if (root / "protocol-stop.json").exists():
        raise ValueError("refusing audit: v4 cohort has a protocol-stop record")
    design = _read(root / "preregistration.json")
    result = _read(root / "pilot-results.json")
    if not (root / "environment.json").is_file():
        raise ValueError("v4 environment artifact is missing")
    if design.get("protocol") != PROTOCOL or result.get("protocol") != PROTOCOL:
        raise ValueError("refusing non-v4 temporal-review cohort")
    if design.get("manifest_id") != MANIFEST_ID or design.get("surface") != SURFACE:
        raise ValueError("v4 preregistration identity is invalid")
    if design.get("mode") != "voluntary":
        raise ValueError("v4 cohort must be voluntary")
    identity = design.get("model_identity")
    if (
        not isinstance(identity, Mapping)
        or identity.get("identity_mode") not in {"model-specific", "runtime-specific"}
        or not isinstance(identity.get("assistant_models"), list)
        or not identity["assistant_models"]
        or any(not isinstance(identity.get(field), list) for field in ("session_models", "usage_models"))
    ):
        raise ValueError("v4 model identity is invalid")
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
        raise ValueError("v4 retained model identity artifact is invalid")
    retained_identity = _read(identity_path)
    stream_summary = orientation_runner.summarize_stream(_events(stream_path))
    if (
        retained_identity.get("protocol") != "temporal-review-v4-model-identity"
        or retained_identity.get("status") != "complete"
        or retained_identity.get("requested_model") != design.get("model")
        or any(
            retained_identity.get(field) != identity[field]
            or stream_summary.get(field) != identity[field]
            for field in ("assistant_models", "session_models", "usage_models")
        )
        or retained_identity.get("claude_version") != identity.get("claude_version")
        or retained_identity.get("command_sha256") != identity.get("command_sha256")
    ):
        raise ValueError("v4 retained model identity does not match preregistration")
    expected = [
        {"task_id": task, "replicate": rep, "condition": condition}
        for task, rep, condition in expected_cells()
    ]
    expected_identities = set(expected_cells())
    if design.get("expected_cells") != expected:
        raise ValueError("v4 preregistration cell matrix was changed")
    manifest_hash = hashlib.sha256(v4.MANIFEST_PATH.read_bytes()).hexdigest()
    if design.get("manifest_sha256") != manifest_hash:
        raise ValueError("v4 manifest does not match preregistration hash")
    if design.get("selection_preflight_sha256") != v4.selection_preflight_sha256():
        raise ValueError("v4 selection preflight does not match preregistration hash")
    runs = result.get("runs")
    if not isinstance(runs, list) or len(runs) != len(expected):
        raise ValueError("v4 pilot result cardinality is invalid")
    identities = [(run.get("task_id"), run.get("replicate"), run.get("condition")) for run in runs if isinstance(run, Mapping)]
    if len(identities) != len(expected) or set(identities) != expected_identities:
        raise ValueError("v4 pilot result cells do not exactly equal preregistration")
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
                    "observation": v4.parse_raw_response(task_id, response),
                })
    return raw, tool_names, final_result_event_index


def _audit_cell(root: Path, task_id: str, replicate: int, condition: str) -> dict[str, Any]:
    cell = _cell_path(root, task_id, replicate, condition)
    required = [cell / "driver-run.json", cell / "output" / "orientation.json", cell / "output" / "run.json", cell / "output" / "command.json", cell / "output" / "pre-state.json", cell / "output" / "post-state.json", cell / "output" / "final-result.json", cell / "output" / "claude.stream.jsonl"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"v4 cell lacks immutable artifacts: {missing}")
    driver, orientation, run = _read(required[0]), _read(required[1]), _read(required[2])
    design = _read(root / "preregistration.json")
    pre_state, post_state = _read(required[4]), _read(required[5])
    if orientation.get("protocol") != SURFACE or driver.get("manifest_id") != MANIFEST_ID:
        raise ValueError(f"v4 cell has wrong protocol identity: {cell}")
    if (driver.get("task_id"), driver.get("replicate"), driver.get("condition")) != (task_id, replicate, condition):
        raise ValueError(f"v4 driver identity does not match path: {cell}")
    item = v4.contract(task_id)
    if driver.get("contract") != {
        "base_ref": item.base_ref,
        "head_ref": item.head_ref,
        "backend": item.backend,
    }:
        raise ValueError(f"v4 driver contract does not match frozen task: {cell}")
    source = Path(driver.get("source_dir", ""))
    runner_command = driver.get("runner_command")
    if (
        not isinstance(runner_command, list)
        or "--temporal-review-v4-contract" not in runner_command
        or SURFACE not in runner_command
        or source.resolve() != (cell / "source").resolve()
    ):
        raise ValueError(f"v4 driver command or source path is invalid: {cell}")
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
    model_identity_valid = (
        driver.get("model_identity_matches_preflight") is True
        and isinstance(observed_model, Mapping)
        and observed_model.get("requested") == expected_identity.get("requested_model")
        and observed_model.get("assistant_observed") == expected_identity.get("assistant_models")
        and observed_model.get("session_observed") == expected_identity.get("session_models")
        and observed_model.get("usage_observed") == expected_identity.get("usage_models")
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
    forbidden_mcp = [name for name in tool_names if name.startswith("mcp__") and name != "mcp__loomgraph__loomgraph_branch_diff"]
    tool_trace_valid = (
        len(tool_names) <= 5 and not forbidden_mcp
        and (condition == "treatment" or not any(name.startswith("mcp__") for name in tool_names))
    )
    answer = {"decision": orientation.get("decision"), "review_loci": orientation.get("review_loci")}
    if source_clean:
        outcome = v4.evaluate_answer(task_id, answer, condition=condition, source_root=source, raw_response=selected["raw_response"] if selected else None)
        semantic = {"passed": outcome.passed, "failures": list(outcome.failures)}
    else:
        semantic = {"passed": False, "failures": ["source_checkout_missing_or_dirty"]}
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
            warm_observation = v4.parse_raw_response(task_id, warm_raw)
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
    valid_row = source_clean and runner_valid and tool_trace_valid and raw_trace_valid and model_identity_valid and orientation.get("status") == "complete" and semantic["passed"] is True and certificate_matches and (condition == "baseline" or selected is not None)
    valid_row = valid_row and warm_valid
    return {
        "task_id": task_id, "replicate": replicate, "condition": condition,
        "status": "valid" if valid_row else "excluded",
        "runtime_status": orientation.get("status"), "source_clean": source_clean,
        "agent_execution_seconds": orientation.get("agent_execution_seconds"),
        "raw_mcp": {"count": len(raw), "valid_count": len(valid), "selected": selected, "raw_trace_valid": raw_trace_valid},
        "tool_trace": {"names": tool_names, "valid": tool_trace_valid, "forbidden_mcp": forbidden_mcp},
        "runner_valid": runner_valid,
        "model_identity_valid": model_identity_valid,
        "certificate_matches_rebuild": certificate_matches, "semantic": semantic,
        "warm_valid": warm_valid,
        "exclusion_reason": None if valid_row else orientation.get("invalid_reason") or "audit_replay_mismatch",
    }


def _paired_navigation_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_cell = {(row["task_id"], row["replicate"], row["condition"]): row for row in records}
    by_task: dict[str, list[dict[str, object]]] = {task_id: [] for task_id in v4.TASK_IDS}
    for task_id in v4.TASK_IDS:
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
        raise ValueError("v4 discovered cell artifacts do not exactly equal preregistration")
    records = [_audit_cell(root, task, rep, condition) for task, rep, condition in expected_cells()]
    result: dict[str, object] = {
        "schema_version": 1,
        "protocol": AUDIT_PROTOCOL,
        "source_protocol": PROTOCOL,
        "runs": records,
        "paired_navigation_records_by_task": _paired_navigation_records(records),
    }
    path = root / "audited-results.json"
    if path.exists():
        raise ValueError("refusing to overwrite an existing v4 audit")
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
