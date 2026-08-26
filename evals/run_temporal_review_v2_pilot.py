"""Run the separately preregistered temporal-review v2 pilot.

The driver is intentionally dormant until an explicit approval starts a new
output root.  It never reads or re-evaluates a v1/r2 output directory.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from evals.temporal_review_v2_fixtures import TASK_IDS, contract, load_instruction  # noqa: E402
from evals.temporal_review_v2_materialize import (  # noqa: E402
    materialize_temporal_review_v2_fixture,
)

CONDITIONS = ("baseline", "treatment")
PROTOCOL = "temporal-review-v2-pilot"
SURFACE = "temporal-review-v2-additive"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _condition_order(replicate: int) -> tuple[str, str]:
    return CONDITIONS if replicate % 2 else tuple(reversed(CONDITIONS))


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


def _version_record(command: list[str]) -> dict[str, object]:
    result = _run(command, cwd=_REPOSITORY_ROOT)
    return {
        "command": command,
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _runtime_environment(loomgraph_binary: str) -> dict[str, object]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "claude": _version_record(["claude", "--version"]),
        "loomgraph": _version_record([loomgraph_binary, "--version"]),
    }


def _orientation_record(output_dir: Path) -> dict[str, object] | None:
    try:
        value = json.loads((output_dir / "orientation.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return {
        "status": value.get("status"),
        "invalid_reason": value.get("invalid_reason"),
        "semantic_packet": value.get("semantic_packet"),
        "valid_raw_branch_diff_count": (
            value.get("trust_observation", {}).get("valid_raw_branch_diff_count")
            if isinstance(value.get("trust_observation"), dict)
            else None
        ),
    }


def _has_valid_raw_comparison(orientation: dict[str, object] | None) -> bool:
    """Warm storage only after retained raw evidence, never semantic success alone."""
    return (
        isinstance(orientation, dict)
        and isinstance(orientation.get("valid_raw_branch_diff_count"), int)
        and orientation["valid_raw_branch_diff_count"] > 0
    )


def _warm_record(*, source_dir: Path, run_dir: Path, item: Any, loomgraph_binary: str) -> dict[str, object]:
    """Repeat against the model adapter's storage to measure a true warm snapshot."""
    storage_root = run_dir / "output" / "loomgraph-storage"
    env = dict(os.environ)
    env["LOOMGRAPH_STORAGE__DB_PATH"] = str(storage_root / "{workspace}.db")
    command = [
        loomgraph_binary,
        "branch-diff",
        f"{item.base_ref}..{item.head_ref}",
        "--backend",
        item.backend,
    ]
    started = time.monotonic()
    result = _run(command, cwd=source_dir, env=env)
    wall_seconds = time.monotonic() - started
    raw_path = run_dir / "warm-branch-diff.json"
    stderr_path = run_dir / "warm-branch-diff.stderr.txt"
    raw_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return {
        "command": command,
        "return_code": result.returncode,
        "wall_seconds": wall_seconds,
        "raw_response_path": str(raw_path),
        "stderr_path": str(stderr_path),
    }


def run_pilot(
    *,
    source_repository: Path,
    output_root: Path,
    task_ids: Sequence[str],
    replicates: int,
    model: str,
    loomgraph_binary: str,
    max_budget_usd: str,
) -> dict[str, object]:
    """Materialize and run an independent counterbalanced v2 cohort."""
    if replicates < 1:
        raise ValueError("replicates must be positive")
    output_root = output_root.resolve()
    if output_root.exists():
        raise ValueError("output_root must not already exist")
    output_root.mkdir(parents=True)
    environment_path = output_root / "environment.json"
    _write_json(environment_path, _runtime_environment(loomgraph_binary))
    runner = Path(__file__).with_name("deepswe") / "claude_orientation.py"
    records: list[dict[str, object]] = []
    for task_id in task_ids:
        item = contract(task_id)
        instruction_path = Path(__file__).with_name("temporal-review-v2-instructions") / Path(item.instruction_file).name
        if instruction_path.read_text(encoding="utf-8").strip() != load_instruction(task_id):
            raise RuntimeError("model instruction must be loaded through the frozen v2 contract")
        for replicate in range(1, replicates + 1):
            for condition in _condition_order(replicate):
                run_dir = output_root / task_id / f"rep-{replicate:02d}" / condition
                run_dir.mkdir(parents=True)
                source_dir = run_dir / "source"
                fixture = materialize_temporal_review_v2_fixture(
                    task_id, source_dir, source_repository=source_repository
                )
                output_dir = run_dir / "output"
                command = [
                    sys.executable,
                    str(runner),
                    "--condition", condition,
                    "--task-id", task_id,
                    "--source-dir", str(fixture.path),
                    "--instruction-file", str(instruction_path),
                    "--output-dir", str(output_dir),
                    "--use-mode", "voluntary",
                    "--treatment-surface", SURFACE,
                    "--temporal-review-v2-contract",
                    "--model", model,
                    "--max-budget-usd", max_budget_usd,
                    "--loomgraph-binary", loomgraph_binary,
                ]
                started = time.monotonic()
                result = _run(command, cwd=_REPOSITORY_ROOT)
                driver_seconds = time.monotonic() - started
                (run_dir / "runner.stdout.txt").write_text(result.stdout, encoding="utf-8")
                (run_dir / "runner.stderr.txt").write_text(result.stderr, encoding="utf-8")
                orientation = _orientation_record(output_dir)
                record: dict[str, object] = {
                    "task_id": task_id,
                    "replicate": replicate,
                    "condition": condition,
                    "mode": "voluntary",
                    "model": model,
                    "tool_surface": "text-only" if condition == "baseline" else SURFACE,
                    "manifest_id": "loomgraph-temporal-review-v2-reregistration",
                    "contract": {
                        "base_ref": item.base_ref,
                        "head_ref": item.head_ref,
                        "backend": item.backend,
                        "expected_comparison": item.expected_comparison,
                    },
                    "source_dir": str(source_dir),
                    "environment_path": str(environment_path),
                    "source_clean": not bool(_run(
                        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=source_dir
                    ).stdout),
                    "runner_command": command,
                    "runner_return_code": result.returncode,
                    "driver_seconds": driver_seconds,
                    "orientation": orientation,
                }
                if condition == "treatment" and _has_valid_raw_comparison(orientation):
                    record["warm_repeat"] = _warm_record(
                        source_dir=source_dir, run_dir=run_dir, item=item,
                        loomgraph_binary=loomgraph_binary,
                    )
                _write_json(run_dir / "driver-run.json", record)
                records.append(record)
    result = {"schema_version": 2, "protocol": PROTOCOL, "runs": records}
    _write_json(output_root / "pilot-results.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repository", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--task-id", action="append", choices=TASK_IDS)
    parser.add_argument("--replicates", type=int, default=2)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-budget-usd", default="0.50")
    parser.add_argument("--loomgraph-binary", default="loomgraph")
    args = parser.parse_args(argv)
    result = run_pilot(
        source_repository=args.source_repository,
        output_root=args.output_dir,
        task_ids=args.task_id or TASK_IDS,
        replicates=args.replicates,
        model=args.model,
        loomgraph_binary=args.loomgraph_binary,
        max_budget_usd=args.max_budget_usd,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
