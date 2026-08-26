"""Run the frozen 12-cell v3 cohort after a separate explicit approval."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from evals.temporal_review_v3_fixtures import (  # noqa: E402
    MANIFEST_PATH,
    TASK_IDS,
    contract,
    load_instruction,
    parse_raw_response,
)
from evals.temporal_review_v3_materialize import (  # noqa: E402
    materialize_temporal_review_v3_fixture,
)

CONDITIONS = ("baseline", "treatment")
REPLICATES = (1, 2)
PROTOCOL = "temporal-review-v3-pilot"
SURFACE = "temporal-review-v3-adapter-trust"
MANIFEST_ID = "loomgraph-temporal-review-v3-adapter-trust"


def _write_json(path: Path, value: object, *, exclusive: bool = False) -> None:
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def expected_cells() -> tuple[tuple[str, int, str], ...]:
    return tuple((task, rep, condition) for task in TASK_IDS for rep in REPLICATES for condition in CONDITIONS)


def _condition_order(replicate: int) -> tuple[str, str]:
    return CONDITIONS if replicate % 2 else (CONDITIONS[1], CONDITIONS[0])


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


def _version(command: list[str]) -> dict[str, object]:
    result = _run(command, cwd=_REPOSITORY_ROOT)
    return {"command": command, "return_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _environment(loomgraph_binary: str) -> dict[str, object]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "claude": _version(["claude", "--version"]),
        "loomgraph": _version([loomgraph_binary, "--version"]),
    }


def _orientation(output_dir: Path) -> dict[str, object] | None:
    try:
        value = json.loads((output_dir / "orientation.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _selected_certificate(orientation: dict[str, object] | None) -> bool:
    observation = orientation.get("trust_observation") if isinstance(orientation, dict) else None
    return isinstance(observation, dict) and isinstance(observation.get("selected_certificate"), dict)


def _warm_repeat(*, source_dir: Path, run_dir: Path, item: Any, loomgraph_binary: str) -> dict[str, object]:
    storage_root = run_dir / "output" / "loomgraph-storage"
    env = dict(os.environ)
    env["LOOMGRAPH_STORAGE__DB_PATH"] = str(storage_root / "{workspace}.db")
    command = [loomgraph_binary, "branch-diff", f"{item.base_ref}..{item.head_ref}", "--backend", item.backend]
    started = time.monotonic()
    result = _run(command, cwd=source_dir, env=env)
    raw_path = run_dir / "warm-branch-diff.json"
    raw_path.write_text(result.stdout, encoding="utf-8")
    (run_dir / "warm-branch-diff.stderr.txt").write_text(result.stderr, encoding="utf-8")
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        raw = None
    return {
        "command": command,
        "return_code": result.returncode,
        "wall_seconds": time.monotonic() - started,
        "raw_response_path": str(raw_path),
        "parsed_raw_observation": parse_raw_response(item.task_id, raw),
    }


def _design(model: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "manifest_id": MANIFEST_ID,
        "manifest_sha256": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
        "mode": "voluntary",
        "surface": SURFACE,
        "model": model,
        "expected_cells": [
            {"task_id": task, "replicate": rep, "condition": condition}
            for task, rep, condition in expected_cells()
        ],
    }


def _stop(
    *,
    output_root: Path,
    records: list[dict[str, object]],
    ordered: list[tuple[str, int, str]],
    cell_index: int,
    stage: str,
) -> dict[str, object]:
    stop = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "stage": stage,
        "trigger_cell": records[-1] if records else None,
        "completed_cells": len(records),
        "remaining_cells": [
            {"task_id": task, "replicate": rep, "condition": arm}
            for task, rep, arm in ordered[cell_index + 1:]
        ],
    }
    _write_json(output_root / "protocol-stop.json", stop, exclusive=True)
    return {"protocol": PROTOCOL, "status": "stopped", "runs": records}


def run_pilot(
    *, source_repository: Path, output_root: Path, model: str, loomgraph_binary: str, max_budget_usd: str
) -> dict[str, object]:
    """Run exactly the preregistered 3 × 2 × 2 voluntary cells once."""
    output_root = output_root.resolve()
    if output_root.exists():
        raise ValueError("output_root must not already exist")
    output_root.mkdir(parents=True)
    records: list[dict[str, object]] = []
    ordered = [(task, rep, condition) for task in TASK_IDS for rep in REPLICATES for condition in _condition_order(rep)]
    try:
        design = _design(model)
        _write_json(output_root / "preregistration.json", design, exclusive=True)
        environment_path = output_root / "environment.json"
        _write_json(environment_path, _environment(loomgraph_binary), exclusive=True)
    except Exception as exc:
        _write_json(
            output_root / "protocol-stop.json",
            {"schema_version": 1, "protocol": PROTOCOL, "stage": "preregistration", "error": str(exc), "trigger_cell": None, "completed_cells": 0, "remaining_cells": [
                {"task_id": task, "replicate": rep, "condition": arm} for task, rep, arm in ordered
            ]},
            exclusive=True,
        )
        return {"protocol": PROTOCOL, "status": "stopped", "runs": records}
    runner = Path(__file__).with_name("deepswe") / "claude_orientation.py"
    for cell_index, (task_id, replicate, condition) in enumerate(ordered):
        run_dir = output_root / task_id / f"rep-{replicate:02d}" / condition
        run_dir.mkdir(parents=True)
        try:
            item = contract(task_id)
            instruction_path = MANIFEST_PATH.parent / item.instruction_file
            if instruction_path.read_text(encoding="utf-8").strip() != load_instruction(task_id):
                raise RuntimeError("model instruction must be loaded through frozen v3 contract")
        except Exception as exc:
            failure_record = {
                "task_id": task_id, "replicate": replicate, "condition": condition,
                "mode": "voluntary", "manifest_id": MANIFEST_ID,
                "stage": "contract", "hard_protocol_stop": True, "error": str(exc),
            }
            _write_json(run_dir / "driver-run.json", failure_record, exclusive=True)
            records.append(failure_record)
            return _stop(output_root=output_root, records=records, ordered=ordered, cell_index=cell_index, stage="contract")
        try:
            fixture = materialize_temporal_review_v3_fixture(
                task_id, run_dir / "source", source_repository=source_repository
            )
        except Exception as exc:
            failure_record = {
                "task_id": task_id, "replicate": replicate, "condition": condition,
                "mode": "voluntary", "manifest_id": MANIFEST_ID,
                "stage": "materialize", "hard_protocol_stop": True, "error": str(exc),
            }
            _write_json(run_dir / "driver-run.json", failure_record, exclusive=True)
            records.append(failure_record)
            return _stop(output_root=output_root, records=records, ordered=ordered, cell_index=cell_index, stage="materialize")
        command = [
            sys.executable, str(runner), "--condition", condition, "--task-id", task_id,
            "--source-dir", str(fixture.path), "--instruction-file", str(instruction_path),
            "--output-dir", str(run_dir / "output"), "--use-mode", "voluntary",
            "--treatment-surface", SURFACE, "--temporal-review-v3-contract", "--model", model,
            "--max-budget-usd", max_budget_usd, "--loomgraph-binary", loomgraph_binary,
        ]
        started = time.monotonic()
        try:
            completed = _run(command, cwd=_REPOSITORY_ROOT)
        except Exception as exc:
            failure_record = {
                "task_id": task_id, "replicate": replicate, "condition": condition,
                "mode": "voluntary", "manifest_id": MANIFEST_ID,
                "stage": "runner", "hard_protocol_stop": True, "error": str(exc),
            }
            _write_json(run_dir / "driver-run.json", failure_record, exclusive=True)
            records.append(failure_record)
            return _stop(output_root=output_root, records=records, ordered=ordered, cell_index=cell_index, stage="runner")
        (run_dir / "runner.stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "runner.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        orientation = _orientation(run_dir / "output")
        try:
            source_status = _run(
                ["git", "status", "--porcelain", "--untracked-files=all"], cwd=fixture.path
            )
        except Exception as exc:
            failure_record = {
                "task_id": task_id, "replicate": replicate, "condition": condition,
                "mode": "voluntary", "manifest_id": MANIFEST_ID,
                "stage": "source_clean", "hard_protocol_stop": True, "error": str(exc),
            }
            _write_json(run_dir / "driver-run.json", failure_record, exclusive=True)
            records.append(failure_record)
            return _stop(output_root=output_root, records=records, ordered=ordered, cell_index=cell_index, stage="source_clean")
        source_clean = source_status.returncode == 0 and not bool(source_status.stdout)
        record: dict[str, object] = {
            "task_id": task_id, "replicate": replicate, "condition": condition,
            "mode": "voluntary", "model": model,
            "tool_surface": "text-only" if condition == "baseline" else SURFACE,
            "manifest_id": MANIFEST_ID,
            "contract": {"base_ref": item.base_ref, "head_ref": item.head_ref, "backend": item.backend},
            "source_dir": str(fixture.path), "environment_path": str(environment_path),
            "source_clean": source_clean,
            "source_status_return_code": source_status.returncode,
            "runner_command": command, "runner_return_code": completed.returncode,
            "driver_seconds": time.monotonic() - started, "orientation": orientation,
        }
        if condition == "treatment" and _selected_certificate(orientation):
            record["warm_repeat"] = _warm_repeat(source_dir=fixture.path, run_dir=run_dir, item=item, loomgraph_binary=loomgraph_binary)
        _write_json(run_dir / "driver-run.json", record, exclusive=True)
        records.append(record)
        if (
            not isinstance(orientation, dict)
            or orientation.get("protocol") != SURFACE
            or not source_clean
            or orientation.get("hard_protocol_stop") is True
        ):
            stage = "runner_artifact" if not isinstance(orientation, dict) else "protocol_validation"
            return _stop(output_root=output_root, records=records, ordered=ordered, cell_index=cell_index, stage=stage)
    results: dict[str, object] = {"schema_version": 1, "protocol": PROTOCOL, "design": design, "runs": records}
    _write_json(output_root / "pilot-results.json", results, exclusive=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repository", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-budget-usd", default="0.50")
    parser.add_argument("--loomgraph-binary", default="loomgraph")
    args = parser.parse_args()
    print(json.dumps(run_pilot(source_repository=args.source_repository, output_root=args.output_dir, model=args.model, loomgraph_binary=args.loomgraph_binary, max_budget_usd=args.max_budget_usd), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
