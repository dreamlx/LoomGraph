#!/usr/bin/env python3
"""Freeze a small, stratified DeepSWE target manifest.

Only patch headers and hashes are read. Gold patch contents never enter an
agent container; the resulting manifest is evaluation metadata for the
consumer, not an agent prompt input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import tomllib
from pathlib import Path
from typing import Any

SEED = 20260818
TASKS_PER_STRATUM = 4
MAX_PRODUCTION_TARGETS = 6
EXCLUDED_TASKS = {
    "textual-richlog-follow-state": "prompt names the target classes and API",
}
STRATA = {
    "codeindex-python": {
        "languages": {"python"},
        "backend": "codeindex",
        "l2_content_hash": "available",
    },
    "codegraph-js-ts": {
        "languages": {"javascript", "typescript"},
        "backend": "codegraph",
        "l2_content_hash": "unavailable",
    },
    "codegraph-go-rust": {
        "languages": {"go", "rust"},
        "backend": "codegraph",
        "l2_content_hash": "unavailable",
    },
}
NON_PRODUCTION_PARTS = {"docs", "examples", "test", "tests", "__snapshots__"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _patch_paths(path: Path) -> list[str]:
    paths: list[str] = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.startswith("diff --git a/"):
            continue
        try:
            target = line.split(" b/", 1)[1]
        except IndexError as exc:
            raise ValueError(f"malformed diff header in {path}: {line!r}") from exc
        if target not in paths:
            paths.append(target)
    return paths


def _production_paths(patch: Path) -> list[str]:
    return [
        path
        for path in _patch_paths(patch)
        if not NON_PRODUCTION_PARTS.intersection(Path(path).parts)
    ]


def _production_paths_by_kind(patch: Path) -> dict[str, list[str]]:
    """Classify production targets from diff headers without reading patch hunks."""
    paths = {"existing": [], "new": []}
    current_path: str | None = None
    current_is_new = False

    def add_current() -> None:
        if current_path is None or NON_PRODUCTION_PARTS.intersection(Path(current_path).parts):
            return
        kind = "new" if current_is_new else "existing"
        if current_path not in paths[kind]:
            paths[kind].append(current_path)

    for line in patch.read_text(errors="replace").splitlines():
        if line.startswith("diff --git a/"):
            add_current()
            try:
                current_path = line.split(" b/", 1)[1]
            except IndexError as exc:
                raise ValueError(f"malformed diff header in {patch}: {line!r}") from exc
            current_is_new = False
        elif line.startswith("new file mode "):
            current_is_new = True
    add_current()
    return paths


def _task_digest(dataset: dict[str, Any], task_id: str) -> str:
    name = f"datacurve/{task_id}"
    for task in dataset.get("tasks", []):
        if task.get("name") == name:
            return str(task.get("digest", ""))
    raise ValueError(f"{name} is absent from dataset.toml")


def _eligible_tasks(root: Path) -> dict[str, list[dict[str, Any]]]:
    eligible = {stratum: [] for stratum in STRATA}
    for task_toml in sorted(root.glob("*/task.toml")):
        metadata = tomllib.loads(task_toml.read_text()).get("metadata", {})
        task_id = str(metadata.get("task_id", ""))
        if task_id in EXCLUDED_TASKS:
            continue
        solution_patch = task_toml.parent / "solution/solution.patch"
        if not solution_patch.exists():
            continue
        targets = _production_paths(solution_patch)
        targets_by_kind = _production_paths_by_kind(solution_patch)
        if not 1 <= len(targets) <= MAX_PRODUCTION_TARGETS:
            continue
        for stratum, spec in STRATA.items():
            if metadata.get("language") in spec["languages"]:
                eligible[stratum].append(
                    {
                        "task_id": task_id,
                        "language": metadata["language"],
                        "repository_url": metadata["repository_url"],
                        "base_commit_hash": metadata["base_commit_hash"],
                        "task_dir": task_toml.parent,
                        "solution_patch": solution_patch,
                        "targets": targets,
                        "targets_by_kind": targets_by_kind,
                    }
                )
                break
    return eligible


def _select(eligible: dict[str, list[dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    selected: list[tuple[str, dict[str, Any]]] = []
    for stratum in STRATA:
        candidates = sorted(eligible[stratum], key=lambda row: row["task_id"])
        random.Random(SEED).shuffle(candidates)
        repositories: set[str] = set()
        for candidate in candidates:
            if candidate["repository_url"] in repositories:
                continue
            selected.append((stratum, candidate))
            repositories.add(candidate["repository_url"])
            if len([item for item in selected if item[0] == stratum]) == TASKS_PER_STRATUM:
                break
        count = len([item for item in selected if item[0] == stratum])
        if count != TASKS_PER_STRATUM:
            raise ValueError(f"{stratum} has only {count} eligible unique repositories")
    return selected


def build_manifest(root: Path) -> dict[str, Any]:
    dataset_path = root / "tasks/dataset.toml"
    dataset = tomllib.loads(dataset_path.read_text())
    tasks = []
    for stratum, row in _select(_eligible_tasks(root / "tasks")):
        spec = STRATA[stratum]
        solution_patch = row["solution_patch"]
        verifier_patch = row["task_dir"] / "tests/test.patch"
        tasks.append(
            {
                "task_id": row["task_id"],
                "stratum": stratum,
                "language": row["language"],
                "backend": spec["backend"],
                "l2_content_hash": spec["l2_content_hash"],
                "repository_url": row["repository_url"],
                "base_commit_hash": row["base_commit_hash"],
                "dataset_task_digest": _task_digest(dataset, row["task_id"]),
                "solution_patch_sha256": _sha256(solution_patch),
                "verifier_patch_sha256": _sha256(verifier_patch),
                "gold_production_paths": row["targets"],
                "gold_existing_production_paths": row["targets_by_kind"]["existing"],
                "gold_new_production_paths": row["targets_by_kind"]["new"],
            }
        )
    return {
        "schema_version": 2,
        "dataset": {
            "name": dataset["dataset"]["name"],
            "manifest_sha256": _sha256(dataset_path),
        },
        "selection": {
            "seed": SEED,
            "tasks_per_stratum": TASKS_PER_STRATUM,
            "max_production_targets": MAX_PRODUCTION_TARGETS,
            "unique_repository_per_stratum": True,
            "excluded_tasks": EXCLUDED_TASKS,
        },
        "tasks": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deep-swe-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.deep_swe_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(manifest['tasks'])} tasks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
