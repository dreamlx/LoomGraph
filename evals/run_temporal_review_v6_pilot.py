"""Run the frozen 8-cell V6 cohort after a separate explicit approval."""

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

from evals.deepswe import claude_orientation as orientation_runner  # noqa: E402
from evals.temporal_review_v6_fixtures import (  # noqa: E402
    MANIFEST_PATH,
    TASK_IDS,
    contract,
    load_instruction,
    parse_raw_response,
    selection_preflight_sha256,
)
from evals.temporal_review_v6_materialize import (  # noqa: E402
    materialize_temporal_review_v6_fixture,
)

CONDITIONS = ("baseline", "treatment")
REPLICATES = (1, 2)
PROTOCOL = "temporal-review-v6-pilot"
SURFACE = "temporal-review-v6-navigation-evidence"
MANIFEST_ID = "loomgraph-temporal-review-v6-navigation-evidence"


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


def _model_identity(directory: Path, model: str) -> dict[str, object]:
    path = directory / "identity-preflight.json"
    stream_path = directory / "claude.stream.jsonl"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("protocol") != "temporal-review-v6-model-identity":
        raise ValueError("V6 model identity preflight is invalid")
    if value.get("requested_model") != model:
        raise ValueError("V6 model identity requested model does not match pilot")
    mode = value.get("identity_mode")
    if not stream_path.is_file():
        raise ValueError("V6 model identity preflight stream is missing")
    events: list[dict[str, Any]] = []
    for line in stream_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    stream_summary = orientation_runner.summarize_stream(events)
    observed: dict[str, list[str]] = {}
    for field in ("assistant_models", "session_models", "usage_models"):
        models = value.get(field)
        if not isinstance(models, list) or not all(isinstance(item, str) and item for item in models):
            raise ValueError(f"V6 model identity {field} evidence is invalid")
        observed[field] = models
    if mode not in {"model-specific", "runtime-specific"} or not observed["assistant_models"]:
        raise ValueError("V6 model identity lacks observed assistant model evidence")
    if mode == "model-specific" and observed["assistant_models"] != [model]:
        raise ValueError("model-specific V6 identity requires requested and observed models to match exactly")
    if value.get("status") != "complete":
        raise ValueError("V6 model identity preflight did not complete")
    if stream_summary.get("final_result_seen") is not True or any(
        stream_summary.get(field) != observed[field]
        for field in ("assistant_models", "session_models", "usage_models")
    ):
        raise ValueError("V6 model identity stream does not match its retained summary")
    version = value.get("claude_version")
    if not isinstance(version, dict) or version.get("return_code") != 0:
        raise ValueError("V6 model identity lacks a successful Claude version record")
    command = value.get("command")
    command_hash = value.get("command_sha256")
    if (
        not isinstance(command, list)
        or not all(isinstance(item, str) for item in command)
        or not isinstance(command_hash, str)
        or command_hash != hashlib.sha256(
            json.dumps(command, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    ):
        raise ValueError("V6 model identity lacks command hash")
    return {
        "identity_path": str(path.resolve()),
        "identity_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "stream_path": str(stream_path.resolve()),
        "stream_sha256": hashlib.sha256(stream_path.read_bytes()).hexdigest(),
        "identity_mode": mode,
        "requested_model": model,
        **observed,
        "claude_version": version,
        "command_sha256": command_hash,
    }


def _identity_matches(orientation: dict[str, object] | None, identity: dict[str, object]) -> bool:
    model = orientation.get("model") if isinstance(orientation, dict) else None
    if not isinstance(model, dict):
        return False
    return (
        model.get("requested") == identity.get("requested_model")
        and model.get("assistant_observed") == identity.get("assistant_models")
        and model.get("session_observed") == identity.get("session_models")
        and model.get("usage_observed") == identity.get("usage_models")
    )


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


def _design(model: str, model_identity: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "manifest_id": MANIFEST_ID,
        "manifest_sha256": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
        "selection_preflight_sha256": selection_preflight_sha256(),
        "mode": "voluntary",
        "surface": SURFACE,
        "model": model,
        "model_identity": model_identity,
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
    *, source_repository: Path, output_root: Path, model: str, loomgraph_binary: str, max_budget_usd: str,
    model_identity_dir: Path,
) -> dict[str, object]:
    """Run exactly the preregistered 2 × 2 × 2 voluntary cells once."""
    output_root = output_root.resolve()
    if output_root.exists():
        raise ValueError("output_root must not already exist")
    output_root.mkdir(parents=True)
    records: list[dict[str, object]] = []
    ordered = [(task, rep, condition) for task in TASK_IDS for rep in REPLICATES for condition in _condition_order(rep)]
    try:
        model_identity = _model_identity(model_identity_dir, model)
        identity_bytes = Path(str(model_identity["identity_path"])).read_bytes()
        stream_bytes = Path(str(model_identity["stream_path"])).read_bytes()
        if hashlib.sha256(identity_bytes).hexdigest() != model_identity["identity_sha256"]:
            raise ValueError("V6 model identity preflight changed while being registered")
        if hashlib.sha256(stream_bytes).hexdigest() != model_identity["stream_sha256"]:
            raise ValueError("V6 model identity preflight stream changed while being registered")
        (output_root / "model-identity-preflight.json").write_bytes(identity_bytes)
        (output_root / "model-identity-preflight.stream.jsonl").write_bytes(stream_bytes)
        model_identity["identity_path"] = "model-identity-preflight.json"
        model_identity["stream_path"] = "model-identity-preflight.stream.jsonl"
        design = _design(model, model_identity)
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
                raise RuntimeError("model instruction must be loaded through frozen V6 contract")
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
            fixture = materialize_temporal_review_v6_fixture(
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
            "--treatment-surface", SURFACE, "--temporal-review-v6-contract", "--model", model,
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
            "model_identity_matches_preflight": _identity_matches(orientation, model_identity),
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
            or not record["model_identity_matches_preflight"]
        ):
            stage = "runner_artifact" if not isinstance(orientation, dict) else (
                "model_identity" if not record["model_identity_matches_preflight"] else "protocol_validation"
            )
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
    parser.add_argument("--model-identity-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_pilot(source_repository=args.source_repository, output_root=args.output_dir, model=args.model, loomgraph_binary=args.loomgraph_binary, max_budget_usd=args.max_budget_usd, model_identity_dir=args.model_identity_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
