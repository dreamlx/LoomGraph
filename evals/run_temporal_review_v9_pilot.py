"""Run the frozen V9 8-cell pilot; any protocol fault stops expansion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.run_temporal_review_v9_model_identity import (  # noqa: E402
    _IDENTITY_FIELDS,
    _MODEL_SURFACES,
    CALIBRATION_CELLS,
    _calibration_content,
    _require_fixed_budget,
    _require_requested_model,
    _validate_calibration,
    command_surface_fingerprint,
)
from evals.temporal_review_v9_fixtures import (  # noqa: E402
    MANIFEST_PATH,
    TASK_IDS,
    contract,
    load_instruction,
    parse_raw_response,
    selection_preflight_sha256,
)
from evals.temporal_review_v9_materialize import (  # noqa: E402
    materialize_temporal_review_v9_fixture,
)

CONDITIONS = ("baseline", "treatment")
REPLICATES = (1, 2)
PROTOCOL = "temporal-review-v9-pilot"
SURFACE = "temporal-review-v9-primary-navigation-evidence"
MANIFEST_ID = "loomgraph-temporal-review-v9-primary-navigation-evidence"


def _write(path: Path, value: object, *, exclusive: bool = False) -> None:
    with path.open("x" if exclusive else "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def expected_cells() -> tuple[tuple[str, int, str], ...]:
    return tuple(
        (task, replicate, condition)
        for task in TASK_IDS
        for replicate in REPLICATES
        for condition in CONDITIONS
    )


def _events(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def _version(command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, cwd=_ROOT, capture_output=True, text=True)
    return {
        "command": command,
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _model_identity(directory: Path, model: str) -> dict[str, object]:
    _require_requested_model(model)
    path = directory / "identity-preflight.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("protocol") != "temporal-review-v9-model-identity"
        or value.get("requested_model") != model
        or value.get("identity_mode") != "runtime-specific"
        or value.get("calibration_protocol") != "temporal-review-v9-no-target-runtime-calibration"
    ):
        raise ValueError("V9 model identity preflight is invalid")
    matrix = [{"replicate": rep, "condition": arm} for rep, arm in CALIBRATION_CELLS]
    records = value.get("calibrations")
    aggregate = value.get("aggregate")
    if not isinstance(records, list) or not isinstance(aggregate, dict) or value.get("calibration_matrix") != matrix:
        raise ValueError("V9 model identity calibration matrix is invalid")
    try:
        content = _calibration_content(directory)
    except ValueError as exc:
        raise ValueError("V9 model identity calibration content is invalid") from exc
    if value.get("calibration_content") != content:
        raise ValueError("V9 model identity calibration content does not match retained evidence")
    try:
        categories = [_validate_calibration(directory, record) for record in records]
    except ValueError as exc:
        raise ValueError("V9 model identity calibration evidence is invalid") from exc
    if (
        value.get("status") != "complete"
        or len(records) != len(matrix)
        or [
            {"replicate": record.get("replicate"), "condition": record.get("condition")}
            for record in records if isinstance(record, dict)
        ] != matrix
        or aggregate.get("model_categories_valid") is not True
        or not isinstance(aggregate.get("command_surface_fingerprints"), dict)
        or any(
            item.get(f"{surface}_models_canonical") != aggregate.get(f"{surface}_models_canonical")
            for item in categories for surface in _MODEL_SURFACES
        )
        or any(
            not isinstance(record, dict)
            or record.get("command_surface_fingerprint")
            != aggregate["command_surface_fingerprints"].get(record.get("condition"))
            for record in records
        )
    ):
        raise ValueError("V9 model identity preflight did not complete")
    return {
        "identity_dir": str(directory.resolve()),
        "identity_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "identity_mode": "runtime-specific",
        "requested_model": model,
        **{field: aggregate.get(field) for field in _IDENTITY_FIELDS if field.endswith("canonical")},
        "command_surface_fingerprints": aggregate["command_surface_fingerprints"],
        "model_categories_valid": True,
        "claude_version": value.get("claude_version"),
    }


def _identity_matches(packet: object, identity: dict[str, object]) -> bool:
    model = packet.get("model") if isinstance(packet, dict) else None
    return (
        isinstance(model, dict)
        and model.get("requested") == identity.get("requested_model")
        and model.get("model_categories_valid") is True
        and all(
            model.get(f"{surface}_models_canonical") == identity.get(f"{surface}_models_canonical")
            for surface in _MODEL_SURFACES
        )
    )


def _stop(
    root: Path,
    records: list[dict[str, object]],
    ordered: list[tuple[str, int, str]],
    index: int,
    stage: str,
) -> dict[str, object]:
    _write(
        root / "protocol-stop.json",
        {
            "schema_version": 1,
            "protocol": PROTOCOL,
            "stage": stage,
            "trigger_cell": records[-1] if records else None,
            "completed_cells": len(records),
            "remaining_cells": [
                {"task_id": task, "replicate": rep, "condition": arm}
                for task, rep, arm in ordered[index + 1 :]
            ],
        },
        exclusive=True,
    )
    return {"protocol": PROTOCOL, "status": "stopped", "runs": records}


def _warm_repeat(source: Path, run_dir: Path, item: Any, binary: str) -> dict[str, object]:
    env = dict(os.environ)
    env["LOOMGRAPH_STORAGE__DB_PATH"] = str(
        run_dir / "output" / "loomgraph-storage" / "{workspace}.db"
    )
    command = [
        binary,
        "branch-diff",
        f"{item.base_ref}..{item.head_ref}",
        "--backend",
        item.backend,
    ]
    started = time.monotonic()
    result = subprocess.run(command, cwd=source, env=env, capture_output=True, text=True)
    raw = run_dir / "warm-branch-diff.json"
    raw.write_text(result.stdout, encoding="utf-8")
    (run_dir / "warm-branch-diff.stderr.txt").write_text(result.stderr, encoding="utf-8")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        value = None
    return {
        "command": command,
        "return_code": result.returncode,
        "wall_seconds": time.monotonic() - started,
        "raw_response_path": str(raw),
        "parsed_raw_observation": parse_raw_response(item.task_id, value),
    }


def run_pilot(
    *,
    source_repository: Path,
    output_root: Path,
    model: str,
    loomgraph_binary: str,
    max_budget_usd: str,
    model_identity_dir: Path,
) -> dict[str, object]:
    """Run exactly the preregistered cells once; never expands automatically."""
    _require_requested_model(model)
    _require_fixed_budget(max_budget_usd)
    root = output_root.resolve()
    if root.exists():
        raise ValueError("output_root must not already exist")
    root.mkdir(parents=True)
    records: list[dict[str, object]] = []
    ordered = [
        (task, rep, arm)
        for task in TASK_IDS
        for rep in REPLICATES
        for arm in (CONDITIONS if rep % 2 else CONDITIONS[::-1])
    ]
    try:
        identity = _model_identity(model_identity_dir, model)
        retained_identity = root / "model-identity-preflight"
        shutil.copytree(Path(str(identity["identity_dir"])), retained_identity)
        retained = _model_identity(retained_identity, model)
        if retained["identity_sha256"] != identity["identity_sha256"]:
            raise ValueError("V9 model identity preflight changed while being registered")
        identity["identity_dir"] = retained_identity.name
        design = {
            "schema_version": 1,
            "protocol": PROTOCOL,
            "manifest_id": MANIFEST_ID,
            "manifest_sha256": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
            "selection_preflight_sha256": selection_preflight_sha256(),
            "mode": "voluntary",
            "surface": SURFACE,
            "model": model,
            "model_identity": identity,
            "expected_cells": [
                {"task_id": task, "replicate": rep, "condition": arm}
                for task, rep, arm in expected_cells()
            ],
            "execution_order": [
                {"task_id": task, "replicate": rep, "condition": arm} for task, rep, arm in ordered
            ],
        }
        _write(root / "preregistration.json", design, exclusive=True)
        _write(
            root / "environment.json",
            {
                "python": sys.version,
                "platform": platform.platform(),
                "claude": _version(["claude", "--version"]),
                "loomgraph": _version([loomgraph_binary, "--version"]),
            },
            exclusive=True,
        )
    except Exception as exc:
        _write(
            root / "protocol-stop.json",
            {
                "schema_version": 1,
                "protocol": PROTOCOL,
                "stage": "preregistration",
                "error": str(exc),
                "completed_cells": 0,
            },
            exclusive=True,
        )
        return {"protocol": PROTOCOL, "status": "stopped", "runs": records}
    runner = _ROOT / "evals/deepswe/claude_orientation.py"
    for index, (task_id, replicate, condition) in enumerate(ordered):
        run_dir = root / task_id / f"rep-{replicate:02d}" / condition
        run_dir.mkdir(parents=True)
        try:
            item = contract(task_id)
            instruction = MANIFEST_PATH.parent / item.instruction_file
            if instruction.read_text(encoding="utf-8").strip() != load_instruction(task_id):
                raise ValueError("instruction must be loaded through frozen V9 contract")
            fixture = materialize_temporal_review_v9_fixture(
                task_id, run_dir / "source", source_repository=source_repository
            )
            command = [
                sys.executable,
                str(runner),
                "--condition",
                condition,
                "--task-id",
                task_id,
                "--source-dir",
                str(fixture.path),
                "--instruction-file",
                str(instruction),
                "--output-dir",
                str(run_dir / "output"),
                "--use-mode",
                "voluntary",
                "--treatment-surface",
                SURFACE,
                "--temporal-review-v9-contract",
                "--model",
                model,
                "--max-budget-usd",
                max_budget_usd,
                "--loomgraph-binary",
                loomgraph_binary,
            ]
            started = time.monotonic()
            completed = subprocess.run(command, cwd=_ROOT, capture_output=True, text=True)
            (run_dir / "runner.stdout.txt").write_text(completed.stdout, encoding="utf-8")
            (run_dir / "runner.stderr.txt").write_text(completed.stderr, encoding="utf-8")
            packet_path = run_dir / "output/orientation.json"
            packet = (
                json.loads(packet_path.read_text(encoding="utf-8"))
                if packet_path.is_file()
                else None
            )
            clean = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=fixture.path,
                capture_output=True,
                text=True,
            )
            record: dict[str, object] = {
                "task_id": task_id,
                "replicate": replicate,
                "condition": condition,
                "mode": "voluntary",
                "model": model,
                "tool_surface": "text-only" if condition == "baseline" else SURFACE,
                "manifest_id": MANIFEST_ID,
                "contract": {
                    "base_ref": item.base_ref,
                    "head_ref": item.head_ref,
                    "backend": item.backend,
                },
                "source_dir": str(fixture.path),
                "environment_path": str((root / "environment.json").resolve()),
                "source_clean": clean.returncode == 0 and not clean.stdout,
                "source_status_return_code": clean.returncode,
                "runner_command": command,
                "runner_return_code": completed.returncode,
                "driver_seconds": time.monotonic() - started,
                "orientation": packet,
                "model_identity_matches_preflight": _identity_matches(packet, identity),
                "command_surface_fingerprint": (
                    command_surface_fingerprint(
                        command,
                        json.loads((run_dir / "output/command.json").read_text(encoding="utf-8")),
                    )
                    if (run_dir / "output/command.json").is_file()
                    else None
                ),
            }
            if (
                condition == "treatment"
                and isinstance(packet, dict)
                and isinstance(
                    packet.get("trust_observation", {}).get("selected_certificate"), dict
                )
            ):
                record["warm_repeat"] = _warm_repeat(fixture.path, run_dir, item, loomgraph_binary)
        except Exception as exc:
            record = {
                "task_id": task_id,
                "replicate": replicate,
                "condition": condition,
                "mode": "voluntary",
                "manifest_id": MANIFEST_ID,
                "stage": "runner",
                "hard_protocol_stop": True,
                "error": str(exc),
            }
        _write(run_dir / "driver-run.json", record, exclusive=True)
        records.append(record)
        orientation_packet = record.get("orientation")
        fingerprints = identity.get("command_surface_fingerprints")
        expected_fingerprint = fingerprints.get(condition) if isinstance(fingerprints, dict) else None
        if (
            not isinstance(orientation_packet, dict)
            or record.get("source_clean") is not True
            or record.get("model_identity_matches_preflight") is not True
            or record.get("command_surface_fingerprint")
            != expected_fingerprint
            or orientation_packet.get("hard_protocol_stop") is True
        ):
            return _stop(
                root,
                records,
                ordered,
                index,
                "model_identity"
                if record.get("model_identity_matches_preflight") is not True
                else "protocol_validation",
            )
    result = {"schema_version": 1, "protocol": PROTOCOL, "design": design, "runs": records}
    _write(root / "pilot-results.json", result, exclusive=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repository", type=Path, default=_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="glm-5.3-flash")
    parser.add_argument("--max-budget-usd", default="0.50")
    parser.add_argument("--loomgraph-binary", default="loomgraph")
    parser.add_argument("--model-identity-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run_pilot(
                source_repository=args.source_repository,
                output_root=args.output_dir,
                model=args.model,
                loomgraph_binary=args.loomgraph_binary,
                max_budget_usd=args.max_budget_usd,
                model_identity_dir=args.model_identity_dir,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
