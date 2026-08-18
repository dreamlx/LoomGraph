#!/usr/bin/env python3
"""Summarize orientation packets without conflating invocation and retrieval."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

_RETRIEVAL_COMMAND = re.compile(
    r"(?:^|[\s;&|])(?:[^\s;&|]*/)?loomgraph\s+(?:find|graph|search|deps|impact|topology|overview)\b"
)


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
    retrieval_used = any(_RETRIEVAL_COMMAND.search(command) for command in command_list)
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
    result: dict[str, object] = {
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
        "loomgraph_index_only": use["index_only"],
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
        match = re.match(r"loomgraph-eval-(?:baseline|treatment)-(.+)$", part)
        if match:
            return match.group(1)
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
            "run": str(path.relative_to(output_dir)),
            **score_packet(packet, targets.get(task_id)),
        }
        rows.append(row)
    return rows


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

    result_path = output_dir / "orientation-summary.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "target_manifest_sha256": hashlib.sha256(
                    args.target_manifest.read_bytes()
                ).hexdigest(),
                "runs": rows,
            },
            indent=2,
        )
        + "\n"
    )
    fields = (
        "task_id",
        "condition",
        "semantic_packet",
        "source_clean_model_phase",
        "instrumentation_cache_paths",
        "loomgraph_invoked",
        "loomgraph_retrieval_used",
        "loomgraph_index_only",
        "loomgraph_backend",
        "loomgraph_trust",
        "target_hit_at_5",
        "existing_target_recall_at_5",
        "new_path_nominated_at_5",
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
