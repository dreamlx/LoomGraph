#!/usr/bin/env python3
"""Summarize host-side Claude target-cohort artifacts.

This module deliberately knows nothing about a task checkout, a solution patch,
or the v1 fixture oracle.  The only quality oracle it consumes is the frozen
target manifest supplied by the caller.  That keeps target scoring a
post-hoc, auditable operation and prevents the manifest from becoming agent
context.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_RUNTIME = "claude-code"
TOOL_CALL_BUDGET = 5
_CONDITIONS = {"baseline", "treatment"}
_USE_MODES = {"voluntary", "assisted"}
_RUNTIMES = ("runtime", "agent_runtime", "integration_runtime")
_EXECUTION_FIELDS = ("agent_execution_seconds",)


def _json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text())
    except OSError as exc:
        return None, f"{path.name}_read_error:{exc.__class__.__name__}"
    except json.JSONDecodeError:
        return None, f"{path.name}_malformed_json"
    if not isinstance(value, dict):
        return None, f"{path.name}_not_object"
    return value, None


def load_target_manifest(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    """Load only frozen target metadata and return its content hash.

    No task source, patch, verifier, or run-local oracle is read here.  The
    split path fields are retained as metadata, while scoring uses only the
    manifest's production path union.
    """

    raw = path.read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise ValueError("target manifest must use schema_version 2")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("target manifest has no tasks list")

    targets: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("task_id"), str):
            raise ValueError("target manifest contains a task without task_id")
        task_id = task["task_id"]
        if task_id in targets:
            raise ValueError(f"duplicate target task {task_id!r}")
        stratum = task.get("stratum")
        if not isinstance(stratum, str) or not stratum:
            raise ValueError(f"target {task_id!r} lacks stratum")
        production = task.get("gold_production_paths")
        if not isinstance(production, list) or not all(
            isinstance(item, str) and _safe_relative_path(item) for item in production
        ):
            # The split fields were present in early v1 manifests.  Accepting
            # their union keeps this host-side reader compatible while still
            # sourcing every scored path from the supplied manifest.
            existing = task.get("gold_existing_production_paths")
            new = task.get("gold_new_production_paths")
            if not isinstance(existing, list) or not isinstance(new, list):
                raise ValueError(f"target {task_id!r} lacks production paths")
            production = list(dict.fromkeys([*existing, *new]))
            if not all(isinstance(item, str) and _safe_relative_path(item) for item in production):
                raise ValueError(f"target {task_id!r} has invalid production paths")
        targets[task_id] = {
            "task_id": task_id,
            "stratum": stratum,
            "gold_production_paths": list(production),
            "gold_existing_production_paths": list(
                task.get("gold_existing_production_paths", [])
            ),
            "gold_new_production_paths": list(task.get("gold_new_production_paths", [])),
        }
    return targets, hashlib.sha256(raw).hexdigest()


def _load_targets(path: Path) -> dict[str, dict[str, Any]]:
    """Compatibility helper used by small fixture tests."""

    return load_target_manifest(path)[0]


def _safe_relative_path(value: str) -> bool:
    candidate = Path(value)
    return not candidate.is_absolute() and bool(candidate.parts) and ".." not in candidate.parts


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _as_nonnegative_float(value: object) -> float | None:
    if not _finite_number(value):
        return None
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value)


def _finite_numeric(value: object) -> bool:
    """Accept signed deltas while keeping booleans/non-numbers out."""

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _as_signed_float(value: object) -> float | None:
    if not _finite_numeric(value):
        return None
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value)


def _duration_seconds(start: object, finish: object) -> float | None:
    if not isinstance(start, str) or not isinstance(finish, str):
        return None
    try:
        elapsed = datetime.fromisoformat(finish.replace("Z", "+00:00")) - datetime.fromisoformat(
            start.replace("Z", "+00:00")
        )
    except ValueError:
        return None
    seconds = elapsed.total_seconds()
    return seconds if seconds >= 0 else None


def _metadata_value(record: dict[str, Any], packet: dict[str, Any], *keys: str) -> object:
    for source in (record, packet):
        for key in keys:
            value = source.get(key)
            if value is not None:
                return value
    return None


def _run_root(orientation_path: Path) -> Path:
    return orientation_path.parent.parent if orientation_path.parent.name == "artifacts" else orientation_path.parent


def _infer_condition(root: Path, record: dict[str, Any], packet: dict[str, Any]) -> str | None:
    value = _metadata_value(record, packet, "condition")
    if isinstance(value, str) and value in _CONDITIONS:
        return value
    text = "/".join(root.parts)
    match = re.search(r"(?:^|[-_/])(baseline|treatment)(?:[-_/]|$)", text)
    return match.group(1) if match else None


def _infer_mode(root: Path, record: dict[str, Any], packet: dict[str, Any]) -> str | None:
    value = _metadata_value(record, packet, "use_mode", "orientation_mode")
    if isinstance(value, str) and value in _USE_MODES:
        return value
    text = "/".join(root.parts)
    match = re.search(r"(?:^|[-_/])(voluntary|assisted)(?:[-_/]|$)", text)
    return match.group(1) if match else None


def _infer_replicate(root: Path, record: dict[str, Any]) -> int | None:
    value = record.get("replicate")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    text = "/".join(root.parts)
    match = re.search(
        r"(?:^|[-_/])(?:baseline|treatment)[-_/](?:voluntary|assisted)[-_/](\d+)(?:[-_/]|$)",
        text,
    )
    if match:
        return int(match.group(1))
    match = re.search(r"(?:^|[-_/])rep(?:licate)?[-_](\d+)(?:[-_/]|$)", text)
    return int(match.group(1)) if match else None


def _infer_task_id(root: Path, record: dict[str, Any], targets: dict[str, dict[str, Any]]) -> str | None:
    value = record.get("task_id")
    if isinstance(value, str) and value:
        return value
    parts = root.parts
    for task_id in sorted(targets, key=len, reverse=True):
        if task_id in parts or any(task_id in part for part in parts):
            return task_id
    return None


def _runtime(record: dict[str, Any], packet: dict[str, Any]) -> tuple[str, str]:
    value = _metadata_value(record, packet, *_RUNTIMES)
    if isinstance(value, str) and value:
        return value, "artifact"
    return DEFAULT_RUNTIME, "default"


def _execution_seconds(root: Path, record: dict[str, Any], packet: dict[str, Any]) -> float | None:
    for source in (record, packet):
        value = source.get("agent_execution_seconds")
        number = _as_nonnegative_float(value)
        if number is not None:
            return number
        execution = source.get("agent_execution")
        if isinstance(execution, dict):
            duration = _duration_seconds(execution.get("started_at"), execution.get("finished_at"))
            if duration is not None:
                return duration
    result_path = root / "result.json"
    result, _ = _json_object(result_path) if result_path.is_file() else (None, None)
    if isinstance(result, dict):
        execution = result.get("agent_execution")
        if isinstance(execution, dict):
            return _duration_seconds(execution.get("started_at"), execution.get("finished_at"))
    return None


def _candidate_paths(packet: dict[str, Any]) -> tuple[list[str], list[str]]:
    candidates = packet.get("candidates")
    if not isinstance(candidates, list):
        return [], ["candidates_missing"]
    paths: list[str] = []
    reasons: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("path"), str):
            reasons.append("candidate_path_invalid")
            continue
        path = candidate["path"]
        if not _safe_relative_path(path):
            reasons.append("candidate_path_not_relative")
            continue
        paths.append(path)
    if not paths:
        reasons.append("candidates_empty")
    return paths[:5], list(dict.fromkeys(reasons))


def _retrieval_observed(packet: dict[str, Any]) -> bool:
    tooling = packet.get("tooling")
    loomgraph = tooling.get("loomgraph") if isinstance(tooling, dict) else None
    retrievals = loomgraph.get("structural_retrievals") if isinstance(loomgraph, dict) else None
    return isinstance(retrievals, list) and bool(retrievals) and all(
        isinstance(item, dict) and isinstance(item.get("tool"), str)
        and isinstance(item.get("evidence"), str) and bool(item["evidence"])
        for item in retrievals
    )


def _packet_reasons(
    packet: dict[str, Any], *, condition: str | None, use_mode: str | None, navigation_surface: object
) -> list[str]:
    reasons: list[str] = []
    if packet.get("status") != "complete":
        reasons.append("packet_not_complete")
    if packet.get("source_clean") is not True:
        reasons.append("source_not_clean")
    if packet.get("source_clean_scope") not in (None, "model_phase"):
        reasons.append("source_clean_scope_invalid")
    if packet.get("tool_call_budget_overrun") is not False:
        reasons.append("tool_call_budget_exceeded")
    tool_count = packet.get("tool_call_count")
    budget = packet.get("tool_call_budget")
    tool_count_number = _as_nonnegative_float(tool_count)
    budget_number = _as_nonnegative_float(budget)
    if (
        tool_count_number is not None
        and budget_number is not None
        and tool_count_number > budget_number
        and "tool_call_budget_exceeded" not in reasons
    ):
        reasons.append("tool_call_budget_exceeded")
    if condition == "baseline" and navigation_surface != "text-only":
        reasons.append("baseline_surface_not_text_only")
    if condition == "treatment" and navigation_surface != "additive":
        reasons.append("treatment_surface_not_additive")
    if (
        condition == "treatment"
        and use_mode == "assisted"
        and navigation_surface == "additive"
        and not _retrieval_observed(packet)
    ):
        reasons.append("additive_treatment_retrieval_missing")
    _, candidate_reasons = _candidate_paths(packet)
    reasons.extend(candidate_reasons)
    return list(dict.fromkeys(reasons))


def _row(
    *,
    root: Path,
    orientation_path: Path,
    record: dict[str, Any],
    packet: dict[str, Any],
    packet_error: str | None,
    targets: dict[str, dict[str, Any]],
    output_dir: Path,
    record_error: str | None = None,
) -> dict[str, object]:
    task_id = _infer_task_id(root, record, targets)
    condition = _infer_condition(root, record, packet)
    use_mode = _infer_mode(root, record, packet)
    replicate = _infer_replicate(root, record)
    runtime, runtime_source = _runtime(record, packet)
    target = targets.get(task_id) if task_id is not None else None
    reasons: list[str] = []
    if packet_error is not None:
        reasons.append(packet_error)
    if record_error is not None:
        reasons.append(record_error)
    if task_id is None:
        reasons.append("task_id_missing")
    elif target is None:
        reasons.append("task_not_in_target_manifest")
    if condition is None:
        reasons.append("condition_missing")
    if use_mode is None:
        reasons.append("use_mode_missing")
    if replicate is None:
        reasons.append("replicate_missing")
    packet_condition = packet.get("condition")
    if condition is not None and isinstance(packet_condition, str) and packet_condition != condition:
        reasons.append("condition_metadata_mismatch")
    packet_mode = packet.get("orientation_mode")
    if use_mode is not None and isinstance(packet_mode, str) and packet_mode != use_mode:
        reasons.append("use_mode_metadata_mismatch")
    if packet_error is None:
        reasons.extend(
            _packet_reasons(
                packet,
                condition=condition,
                use_mode=use_mode,
                navigation_surface=packet.get("navigation_surface"),
            )
        )
    run_return_code = _metadata_value(record, packet, "return_code", "runner_return_code")
    if isinstance(run_return_code, int) and run_return_code != 0:
        reasons.append("agent_return_code_nonzero")
    candidate_paths, candidate_reasons = _candidate_paths(packet)
    reasons.extend(candidate_reasons if packet_error is None else [])
    valid = not reasons
    execution_seconds = _execution_seconds(root, record, packet)
    target_hit: bool | None = None
    if valid and target is not None:
        target_paths = set(target["gold_production_paths"])
        target_hit = bool(set(candidate_paths[:5]) & target_paths)
    return {
        "task_id": task_id,
        "stratum": target.get("stratum") if target else None,
        "condition": condition,
        "use_mode": use_mode,
        "orientation_mode": use_mode,
        "runtime": runtime,
        "runtime_source": runtime_source,
        "replicate": replicate,
        "run": str(root.relative_to(output_dir)),
        "artifact": str(orientation_path.relative_to(output_dir)),
        "valid": valid,
        "quality_eligible": valid,
        "excluded": not valid,
        "exclusion_reasons": list(dict.fromkeys(reasons)),
        "packet_status": packet.get("status"),
        "source_clean": packet.get("source_clean"),
        "source_clean_scope": packet.get("source_clean_scope"),
        "navigation_surface": packet.get("navigation_surface"),
        "model": packet.get("model", record.get("model")),
        "image": record.get("image"),
        "tool_call_count": packet.get("tool_call_count"),
        "tool_call_budget": packet.get("tool_call_budget"),
        "tool_call_budget_overrun": packet.get("tool_call_budget_overrun"),
        "structural_retrieval_observed": _retrieval_observed(packet),
        "candidate_paths": candidate_paths,
        "packet_target_hit_at_5": packet.get("target_hit_at_5"),
        "target_hit_at_5": target_hit,
        "agent_execution_seconds": execution_seconds,
    }


def summarize(output_dir: Path, targets: dict[str, dict[str, Any]]) -> list[dict[str, object]]:
    """Read every orientation artifact and retain invalid rows for audit."""

    orientation_paths = sorted(output_dir.rglob("orientation.json"))
    orientation_entries = {
        _run_root(path): path for path in orientation_paths if path.is_file()
    }
    # A Docker/runner failure can leave only driver-run.json.  Keep that run as
    # an explicit invalid row instead of silently turning it into missing data.
    metadata_entries: dict[Path, Path] = {}
    for name in ("run.json", "driver-run.json"):
        for path in sorted(output_dir.rglob(name)):
            root = path.parent
            if root in orientation_entries or any(root in parent.parents for parent in orientation_entries):
                continue
            metadata_entries.setdefault(root, path)

    rows: list[dict[str, object]] = []
    for root, orientation_path in sorted(orientation_entries.items()):
        record: dict[str, Any] = {}
        record_error: str | None = None
        # Claude's direct runner has no result.json contract of its own.  The
        # cohort driver writes driver-run.json beside each condition output;
        # the fallback keeps this reader useful for direct run directories.
        record_paths = (root / "run.json", root / "driver-run.json", root.parent / "driver-run.json")
        for record_path in record_paths:
            if not record_path.is_file():
                continue
            record_value, _ = _json_object(record_path)
            if record_value is not None:
                record = record_value
                break
        packet, packet_error = _json_object(orientation_path)
        rows.append(
            _row(
                root=root,
                orientation_path=orientation_path,
                record=record,
                packet=packet or {},
                packet_error=packet_error,
                targets=targets,
                output_dir=output_dir,
                record_error=record_error,
            )
        )
    for root, record_path in sorted(metadata_entries.items()):
        metadata_record, record_error = _json_object(record_path)
        missing_orientation = root / "orientation.json"
        rows.append(
            _row(
                root=root,
                orientation_path=missing_orientation,
                record=metadata_record or {},
                packet={},
                packet_error="orientation.json_missing",
                targets=targets,
                output_dir=output_dir,
                record_error=record_error,
            )
        )
    return rows


def _pair_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row.get("task_id"),
        row.get("stratum"),
        row.get("use_mode"),
        row.get("runtime"),
        row.get("replicate"),
    )


def pair_efficiency(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Pair one baseline and treatment only inside the same run identity."""

    grouped: dict[tuple[object, ...], dict[str, list[dict[str, object]]]] = {}
    for row in rows:
        if row.get("condition") not in _CONDITIONS:
            continue
        if row.get("replicate") is None:
            continue
        grouped.setdefault(_pair_key(row), {"baseline": [], "treatment": []})[
            str(row["condition"])
        ].append(row)

    pairs: list[dict[str, object]] = []
    for key, conditions in sorted(grouped.items(), key=lambda item: str(item[0])):
        baseline_rows = conditions["baseline"]
        treatment_rows = conditions["treatment"]
        if not baseline_rows or not treatment_rows:
            continue
        baseline = baseline_rows[0]
        treatment = treatment_rows[0]
        reasons: list[str] = []
        if len(baseline_rows) != 1 or len(treatment_rows) != 1:
            reasons.append("duplicate_condition_rows")
        if baseline.get("valid") is not True:
            reasons.append("baseline_excluded")
        if treatment.get("valid") is not True:
            reasons.append("treatment_excluded")
        if not _finite_number(baseline.get("agent_execution_seconds")):
            reasons.append("baseline_execution_seconds_missing")
        if not _finite_number(treatment.get("agent_execution_seconds")):
            reasons.append("treatment_execution_seconds_missing")
        quality_eligible = not reasons
        baseline_seconds = _as_nonnegative_float(baseline.get("agent_execution_seconds"))
        treatment_seconds = _as_nonnegative_float(treatment.get("agent_execution_seconds"))
        delta: float | None = None
        if quality_eligible:
            assert baseline_seconds is not None and treatment_seconds is not None
            delta = treatment_seconds - baseline_seconds
        pairs.append(
            {
                "task_id": key[0],
                "stratum": key[1],
                "use_mode": key[2],
                "runtime": key[3],
                "replicate": key[4],
                "baseline_run": baseline.get("run"),
                "treatment_run": treatment.get("run"),
                "quality_eligible": quality_eligible,
                "pair_exclusion_reasons": reasons,
                "agent_execution_seconds_delta": delta,
            }
        )
    return pairs


def _quartile_summary(values: list[float]) -> dict[str, object] | None:
    if not values:
        return None
    median = statistics.median(values)
    if len(values) == 1:
        q1 = q3 = median
    else:
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {"n": len(values), "median": median, "q1": q1, "q3": q3, "iqr": q3 - q1}


def summarize_groups(pairs: list[dict[str, object]]) -> list[dict[str, object]]:
    """Group paired facts without merging mode, runtime, task, or stratum."""

    grouped: dict[tuple[object, object, object, object], list[dict[str, object]]] = {}
    for pair in pairs:
        key = (pair.get("task_id"), pair.get("stratum"), pair.get("runtime"), pair.get("use_mode"))
        grouped.setdefault(key, []).append(pair)
    summaries: list[dict[str, object]] = []
    for key, group in sorted(grouped.items(), key=lambda item: str(item[0])):
        values: list[float] = []
        for pair in group:
            if pair.get("quality_eligible") is not True:
                continue
            number = _as_signed_float(pair.get("agent_execution_seconds_delta"))
            if number is not None:
                values.append(number)
        summaries.append(
            {
                "task_id": key[0],
                "stratum": key[1],
                "runtime": key[2],
                "use_mode": key[3],
                "n_pairs": len(group),
                "n_quality_eligible_pairs": sum(
                    pair.get("quality_eligible") is True for pair in group
                ),
                "pairs": group,
                "agent_execution_seconds_delta": _quartile_summary(values),
            }
        )
    return summaries


def summarize_pair_deltas(pairs: list[dict[str, object]]) -> list[dict[str, object]]:
    """Compatibility name for callers of the v1 summarizer shape."""

    return summarize_groups(pairs)


def _write_summary(output_dir: Path, manifest_path: Path, rows: list[dict[str, object]]) -> Path:
    targets, manifest_sha = load_target_manifest(manifest_path)
    del targets  # The rows were already scored against the same frozen manifest.
    pairs = pair_efficiency(rows)
    result_path = output_dir / "claude-target-cohort-summary.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "runtimes": sorted({
                    str(row["runtime"])
                    for row in rows
                    if isinstance(row.get("runtime"), str)
                }),
                "target_manifest_sha256": manifest_sha,
                "runs": rows,
                "pairs": pairs,
                "groups": summarize_groups(pairs),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort_output_dir", type=Path)
    parser.add_argument(
        "--target-manifest",
        type=Path,
        default=Path(__file__).with_name("target-manifest.json"),
    )
    args = parser.parse_args()
    output_dir = args.cohort_output_dir.resolve()
    targets, _ = load_target_manifest(args.target_manifest.resolve())
    rows = summarize(output_dir, targets)
    if not rows:
        parser.error(f"no orientation.json artifacts under {output_dir}")
    result_path = _write_summary(output_dir, args.target_manifest.resolve(), rows)
    fields = (
        "task_id", "stratum", "runtime", "condition", "use_mode", "replicate", "valid",
        "quality_eligible", "excluded", "exclusion_reasons", "target_hit_at_5",
        "agent_execution_seconds", "candidate_paths",
    )
    print(",".join(fields))
    for row in rows:
        print(
            ",".join(
                json.dumps(row.get(field), sort_keys=True)
                if isinstance(row.get(field), (list, dict))
                else str(row.get(field, ""))
                for field in fields
            )
        )
    print(f"wrote {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
