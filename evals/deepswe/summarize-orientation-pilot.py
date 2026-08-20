#!/usr/bin/env python3
"""Summarize orientation packets without conflating invocation and retrieval."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_RETRIEVAL_COMMAND = re.compile(
    r"(?:^|[\s;&|])(?:[^\s;&|]*/)?loomgraph\s+(?:find|graph|search|deps|impact|topology|overview)\b"
)
_REPLICATE_DIRECTORY = re.compile(
    r"(?:^|-)(?:baseline|treatment)(?:-(?:voluntary|assisted))?-(\d+)$"
)
_EFFICIENCY_FIELDS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "cost_usd",
    "agent_execution_seconds",
    "agent_setup_seconds",
    "trial_wall_seconds",
)


def _is_retrieval_command(command: str) -> bool:
    return bool(_RETRIEVAL_COMMAND.search(command.replace('"', "").replace("'", "")))


def packet_is_valid(packet: dict[str, Any]) -> bool:
    candidates = packet.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 5:
        return False
    if any(not isinstance(candidate.get("path"), str) for candidate in candidates if isinstance(candidate, dict)):
        return False
    if any(not isinstance(candidate, dict) for candidate in candidates):
        return False
    if any(
        candidate["path"].startswith(("docs/", "examples/", "tests/"))
        for candidate in candidates
    ):
        return False
    return packet.get("status") == "complete" and packet.get("pre_edit") is True


def classify_loomgraph_use(commands: object) -> dict[str, bool]:
    """Classify observed CLI commands, rather than trusting a model assertion."""
    command_list = [command for command in commands if isinstance(command, str)] if isinstance(commands, list) else []
    invoked = bool(command_list)
    retrieval_used = any(_is_retrieval_command(command) for command in command_list)
    return {
        "invoked": invoked,
        "retrieval_used": retrieval_used,
        "index_only": invoked and not retrieval_used,
    }


def _unique_paths(packet: dict[str, Any]) -> tuple[list[str], int]:
    candidates = packet.get("candidates")
    paths = [
        candidate["path"]
        for candidate in candidates
        if isinstance(candidate, dict) and isinstance(candidate.get("path"), str)
    ] if isinstance(candidates, list) else []
    unique = list(dict.fromkeys(paths))
    return unique, len(paths) - len(unique)


def _string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
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
    return elapsed.total_seconds() if elapsed.total_seconds() >= 0 else None


def _trial_efficiency(packet_path: Path) -> dict[str, object]:
    """Read Pier's raw execution and token fields beside an orientation artifact."""
    empty = dict.fromkeys(_EFFICIENCY_FIELDS)
    result_path = packet_path.parent.parent / "result.json"
    try:
        result = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(result, dict):
        return empty

    agent_result = result.get("agent_result")
    agent_result = agent_result if isinstance(agent_result, dict) else {}
    input_tokens = _integer(agent_result.get("n_input_tokens"))
    cached_input_tokens = _integer(agent_result.get("n_cache_tokens"))
    uncached_input_tokens = (
        input_tokens - cached_input_tokens
        if input_tokens is not None
        and cached_input_tokens is not None
        and input_tokens >= cached_input_tokens
        else None
    )
    agent_setup = result.get("agent_setup")
    agent_execution = result.get("agent_execution")
    agent_setup = agent_setup if isinstance(agent_setup, dict) else {}
    agent_execution = agent_execution if isinstance(agent_execution, dict) else {}
    return {
        "uncached_input_tokens": uncached_input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": _integer(agent_result.get("n_output_tokens")),
        "cost_usd": _number(agent_result.get("cost_usd")),
        "agent_execution_seconds": _duration_seconds(
            agent_execution.get("started_at"), agent_execution.get("finished_at")
        ),
        "agent_setup_seconds": _duration_seconds(
            agent_setup.get("started_at"), agent_setup.get("finished_at")
        ),
        "trial_wall_seconds": _duration_seconds(result.get("started_at"), result.get("finished_at")),
    }


def score_packet(packet: dict[str, Any], target: dict[str, Any] | None) -> dict[str, object]:
    """Return observational and target-kind metrics for one packet.

    Invalid packets and tasks absent from the frozen manifest are intentionally
    unscored: they are neither hits nor misses.
    """
    valid = packet_is_valid(packet)
    candidate_paths, duplicate_paths = _unique_paths(packet)
    tooling = packet.get("tooling")
    tool = tooling.get("loomgraph") if isinstance(tooling, dict) else None
    commands = _string_list(tool.get("commands")) if isinstance(tool, dict) else []
    use = classify_loomgraph_use(commands)
    tool_call_count = packet.get("tool_call_count")
    result: dict[str, object] = {
        "orientation_mode": packet.get("orientation_mode"),
        "semantic_packet": valid,
        "source_clean_model_phase": packet.get("pre_edit") is True,
        "response_format": packet.get("response_format"),
        "instrumentation_cache_paths": _string_list(packet.get("instrumentation_cache_paths")),
        "candidate_paths": candidate_paths,
        "duplicate_candidate_paths": duplicate_paths,
        "loomgraph_commands": commands,
        "loomgraph_backend": tool.get("backend") if isinstance(tool, dict) else None,
        "loomgraph_trust": tool.get("trust") if isinstance(tool, dict) else None,
        "loomgraph_invoked": use["invoked"],
        "loomgraph_retrieval_used": use["retrieval_used"],
        "loomgraph_retrieval_succeeded": (
            tool.get("retrieval_succeeded") if isinstance(tool, dict) else None
        ),
        "loomgraph_retrieval_evidence_succeeded": (
            tool.get("retrieval_evidence_succeeded") if isinstance(tool, dict) else None
        ),
        "loomgraph_index_only": use["index_only"],
        "tool_call_count": tool_call_count if isinstance(tool_call_count, int) else None,
        "tool_call_budget": packet.get("tool_call_budget"),
        "tool_call_budget_overrun": packet.get("tool_call_budget_overrun"),
        "retrieval_required": packet.get("retrieval_required"),
        "retrieval_requirement_met": packet.get("retrieval_requirement_met"),
        "target_hit_at_5": None,
        "existing_target_recall_at_5": None,
        "new_path_nominated_at_5": None,
    }
    if not valid or target is None:
        return result

    existing = set(target["gold_existing_production_paths"])
    new = set(target["gold_new_production_paths"])
    candidates = set(candidate_paths)
    result["target_hit_at_5"] = bool(candidates & (existing | new))
    if existing:
        result["existing_target_recall_at_5"] = len(candidates & existing) / len(existing)
    if new:
        result["new_path_nominated_at_5"] = bool(candidates & new)
    return result


def _infer_condition(path: Path, output_dir: Path) -> str | None:
    for part in path.relative_to(output_dir).parts:
        match = re.search(r"(?:^|-)\b(baseline|treatment)(?:-|$)", part)
        if match:
            return match.group(1)
    return None


def _infer_task_id(path: Path, output_dir: Path) -> str | None:
    for part in path.relative_to(output_dir).parts:
        if "__" in part:
            return part.split("__", 1)[0]
        match = re.match(
            r"loomgraph-eval-(?:baseline|treatment)-(?:voluntary|assisted)-(.+)$", part
        )
        if match:
            return match.group(1)
    return None


def _infer_use_mode(path: Path, output_dir: Path) -> str | None:
    for part in path.relative_to(output_dir).parts:
        match = re.search(r"(?:^|-)(voluntary|assisted)(?:-|$)", part)
        if match:
            return match.group(1)
    return None


def _infer_replicate(path: Path, output_dir: Path) -> int | None:
    for part in path.relative_to(output_dir).parts:
        match = _REPLICATE_DIRECTORY.fullmatch(part)
        if match:
            return int(match.group(1))
    return None


def _load_targets(path: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 2:
        raise ValueError("target manifest must use schema_version 2")
    targets = {}
    for task in manifest.get("tasks", []):
        if not isinstance(task, dict):
            continue
        if not all(
            isinstance(task.get(key), list)
            for key in ("gold_existing_production_paths", "gold_new_production_paths")
        ):
            raise ValueError(f"task {task.get('task_id')!r} lacks split production targets")
        targets[task["task_id"]] = task
    return targets


def summarize(output_dir: Path, targets: dict[str, dict[str, Any]]) -> list[dict[str, object]]:
    rows = []
    for path in sorted(output_dir.rglob("orientation.json")):
        if path.parent.name != "artifacts":
            continue
        condition = _infer_condition(path, output_dir)
        task_id = _infer_task_id(path, output_dir)
        if condition is None or task_id is None:
            continue
        try:
            packet = json.loads(path.read_text())
        except json.JSONDecodeError:
            packet = {}
        if not isinstance(packet, dict):
            packet = {}
        row = {
            "task_id": task_id,
            "condition": condition,
            "use_mode": _infer_use_mode(path, output_dir),
            "replicate": _infer_replicate(path, output_dir),
            "stratum": targets.get(task_id, {}).get("stratum"),
            "run": str(path.relative_to(output_dir)),
            **score_packet(packet, targets.get(task_id)),
            **_trial_efficiency(path),
        }
        rows.append(row)
    return rows


def _quality_eligible(row: dict[str, object]) -> bool:
    if (
        not row.get("semantic_packet")
        or not row.get("source_clean_model_phase")
        or row.get("tool_call_budget_overrun") is not False
    ):
        return False
    return not (
        row.get("condition") == "treatment"
        and row.get("use_mode") == "assisted"
        and row.get("retrieval_requirement_met") is not True
    )


def pair_efficiency(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Join explicit baseline/treatment replicates without pooling strata."""
    grouped: dict[tuple[object, object, object], dict[str, dict[str, object]]] = {}
    for row in rows:
        replicate = row.get("replicate")
        if not isinstance(replicate, int):
            continue
        key = (row.get("task_id"), row.get("use_mode"), replicate)
        grouped.setdefault(key, {})[str(row.get("condition"))] = row

    pairs: list[dict[str, object]] = []
    for (_, _, replicate), conditions in sorted(grouped.items(), key=lambda item: str(item[0])):
        baseline = conditions.get("baseline")
        treatment = conditions.get("treatment")
        if baseline is None or treatment is None:
            continue
        eligible = _quality_eligible(baseline) and _quality_eligible(treatment)
        budget_compliant = (
            baseline.get("tool_call_budget_overrun") is False
            and treatment.get("tool_call_budget_overrun") is False
        )
        pair: dict[str, object] = {
            "task_id": baseline.get("task_id"),
            "stratum": baseline.get("stratum"),
            "use_mode": baseline.get("use_mode"),
            "replicate": replicate,
            "baseline_run": baseline.get("run"),
            "treatment_run": treatment.get("run"),
            "tool_call_budget_compliant": budget_compliant,
            "quality_eligible": eligible,
        }
        for field in _EFFICIENCY_FIELDS:
            baseline_value = baseline.get(field)
            treatment_value = treatment.get(field)
            pair[f"{field}_delta"] = (
                treatment_value - baseline_value
                if eligible
                and isinstance(baseline_value, (int, float))
                and isinstance(treatment_value, (int, float))
                else None
            )
        pairs.append(pair)
    return pairs


def summarize_pair_deltas(pairs: list[dict[str, object]]) -> list[dict[str, object]]:
    """Report median/IQR per task and stratum without pooling experiments."""
    grouped: dict[tuple[object, object, object], list[dict[str, object]]] = {}
    for pair in pairs:
        key = (pair.get("task_id"), pair.get("stratum"), pair.get("use_mode"))
        grouped.setdefault(key, []).append(pair)

    summaries: list[dict[str, object]] = []
    for (task_id, stratum, use_mode), task_pairs in sorted(grouped.items(), key=lambda item: str(item[0])):
        summary: dict[str, object] = {
            "task_id": task_id,
            "stratum": stratum,
            "use_mode": use_mode,
            "n_pairs": len(task_pairs),
            "n_quality_eligible_pairs": sum(
                pair.get("quality_eligible") is True for pair in task_pairs
            ),
        }
        for field in _EFFICIENCY_FIELDS:
            values = [
                float(value)
                for pair in task_pairs
                if pair.get("quality_eligible") is True
                and isinstance((value := pair.get(f"{field}_delta")), (int, float))
            ]
            if not values:
                summary[f"{field}_delta"] = None
                continue
            median = statistics.median(values)
            if len(values) == 1:
                first_quartile = third_quartile = median
            else:
                first_quartile, _, third_quartile = statistics.quantiles(
                    values, n=4, method="inclusive"
                )
            summary[f"{field}_delta"] = {
                "n": len(values),
                "median": median,
                "q1": first_quartile,
                "q3": third_quartile,
                "iqr": third_quartile - first_quartile,
            }
        summaries.append(summary)
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pilot_output_dir", type=Path)
    parser.add_argument(
        "--target-manifest",
        type=Path,
        default=Path(__file__).with_name("target-manifest.json"),
    )
    args = parser.parse_args()
    output_dir = args.pilot_output_dir.resolve()
    targets = _load_targets(args.target_manifest.resolve())
    rows = summarize(output_dir, targets)
    if not rows:
        parser.error(f"no recognizable orientation packets under {output_dir}")

    pairs = pair_efficiency(rows)
    result_path = output_dir / "orientation-summary.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "target_manifest_sha256": hashlib.sha256(
                    args.target_manifest.read_bytes()
                ).hexdigest(),
                "runs": rows,
                "pairs": pairs,
                "paired_delta_summary": summarize_pair_deltas(pairs),
            },
            indent=2,
        )
        + "\n"
    )
    fields = (
        "task_id",
        "condition",
        "use_mode",
        "replicate",
        "stratum",
        "orientation_mode",
        "semantic_packet",
        "source_clean_model_phase",
        "instrumentation_cache_paths",
        "loomgraph_invoked",
        "loomgraph_retrieval_used",
        "loomgraph_retrieval_succeeded",
        "loomgraph_retrieval_evidence_succeeded",
        "loomgraph_index_only",
        "tool_call_count",
        "tool_call_budget",
        "tool_call_budget_overrun",
        "retrieval_required",
        "retrieval_requirement_met",
        "loomgraph_backend",
        "loomgraph_trust",
        "target_hit_at_5",
        "existing_target_recall_at_5",
        "new_path_nominated_at_5",
        *_EFFICIENCY_FIELDS,
        "duplicate_candidate_paths",
        "candidate_paths",
    )
    writer = csv.DictWriter(sys.stdout, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(row[key]) if isinstance(row[key], (list, dict)) else row[key]
                for key in fields
            }
        )
    print(f"wrote {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
