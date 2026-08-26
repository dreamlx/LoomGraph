"""Replay saved temporal-review v2 traces without model or MCP execution."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from evals import temporal_review_v2_fixtures as v2  # noqa: E402

V2_PILOT_PROTOCOL = "temporal-review-v2-pilot"
V2_ORIENTATION_PROTOCOL = "temporal-review-v2-additive"
AUDIT_PROTOCOL = "temporal-review-v2-pilot-audit"
AUDIT_SCHEMA_VERSION = 1


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _require_v2_root(output_root: Path) -> dict[str, Any]:
    marker_path = output_root / "pilot-results.json"
    if not marker_path.is_file():
        raise ValueError("refusing audit: v2 pilot-results.json is missing")
    marker = _read_json(marker_path)
    if marker.get("protocol") != V2_PILOT_PROTOCOL:
        raise ValueError(
            "refusing non-v2 temporal-review protocol root: "
            f"{marker.get('protocol')!r}"
        )
    if marker.get("schema_version") != 2:
        raise ValueError("refusing v2 root with an unsupported pilot schema")
    return marker


def _path_identity(orientation_path: Path) -> tuple[str, str, str]:
    try:
        output_dir = orientation_path.parent
        condition_dir = output_dir.parent
        replicate_dir = condition_dir.parent
        task_dir = replicate_dir.parent
        if output_dir.name != "output":
            raise ValueError
        return task_dir.name, replicate_dir.name, condition_dir.name
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"invalid v2 orientation path: {orientation_path}") from exc


def _source_root(run: Mapping[str, Any], run_dir: Path) -> Path | None:
    value = run.get("source_dir") or run.get("source_root")
    if isinstance(value, str) and value:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = run_dir / candidate
    else:
        candidate = run_dir / "source"
    return candidate.resolve() if candidate.is_dir() else None


def _answer(orientation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: orientation.get(key)
        for key in ("decision", "review_loci", "trust")
    }


def _raw_responses(orientation: Mapping[str, Any]) -> list[object]:
    observation = orientation.get("trust_observation")
    if not isinstance(observation, Mapping):
        return []
    raw = observation.get("raw_branch_diff_responses")
    return list(raw) if isinstance(raw, list) else []


def _raw_mcp_observation(
    *,
    task_id: str,
    condition: str,
    answer: Mapping[str, Any],
    raw_responses: list[object],
) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = [
        v2.parse_raw_response(task_id, raw) for raw in raw_responses
    ]
    valid = [item for item in parsed if item.get("valid") is True]
    if condition == "baseline":
        status = "not_required" if not raw_responses else "unexpected"
    elif not raw_responses:
        status = "missing"
    elif valid:
        status = "valid"
    else:
        status = "invalid"
    trust = answer.get("trust")
    aligned = any(
        isinstance(trust, Mapping)
        and trust.get("availability") == "available"
        and trust.get("comparison") == item.get("comparison")
        for item in valid
    )
    return {
        "status": status,
        "raw_responses": raw_responses,
        "parsed_observations": parsed,
        "valid_count": len(valid),
        "comparisons": [item.get("comparison") for item in valid],
        "model_trust_aligned": aligned,
    }


def _semantic_replay(
    *,
    task_id: str,
    condition: str,
    answer: Mapping[str, Any],
    source_root: Path | None,
    raw_responses: list[object],
) -> dict[str, Any]:
    if source_root is None:
        return {"status": "not_evaluated", "outcomes": [], "error": "source_checkout_missing"}
    candidates = raw_responses if condition == "treatment" else [None]
    outcomes: list[dict[str, Any]] = []
    for raw in candidates:
        outcome = v2.evaluate_answer(
            task_id,
            answer,
            condition=condition,
            source_root=source_root,
            raw_response=raw,
        )
        outcomes.append(
            {"passed": outcome.passed, "failures": list(outcome.failures)}
        )
    passed = any(item["passed"] is True for item in outcomes)
    return {
        "status": "passed" if passed else "failed",
        "outcomes": outcomes,
        "error": None,
    }


def _audit_run(orientation_path: Path) -> dict[str, Any]:
    task_id_from_path, replicate, condition_from_path = _path_identity(orientation_path)
    run_path = orientation_path.with_name("run.json")
    if not run_path.is_file():
        raise ValueError(f"v2 run.json is missing beside {orientation_path}")
    orientation = _read_json(orientation_path)
    run = _read_json(run_path)
    task_id = run.get("task_id", task_id_from_path)
    condition = orientation.get("condition", run.get("condition", condition_from_path))
    if task_id != task_id_from_path or condition != condition_from_path:
        raise ValueError(f"v2 trace identity does not match its path: {orientation_path}")
    if not isinstance(task_id, str) or task_id not in v2.TASK_IDS:
        raise ValueError(f"unknown v2 task in saved trace: {task_id!r}")
    if condition not in {"baseline", "treatment"}:
        raise ValueError(f"invalid v2 condition in saved trace: {condition!r}")
    if orientation.get("protocol") != V2_ORIENTATION_PROTOCOL:
        raise ValueError(f"refusing non-v2 orientation protocol: {orientation_path}")

    run_dir = orientation_path.parent.parent
    source_root = _source_root(run, run_dir)
    answer = _answer(orientation)
    raw_responses = _raw_responses(orientation)
    raw_mcp = _raw_mcp_observation(
        task_id=task_id,
        condition=condition,
        answer=answer,
        raw_responses=raw_responses,
    )
    semantic = _semantic_replay(
        task_id=task_id,
        condition=condition,
        answer=answer,
        source_root=source_root,
        raw_responses=raw_responses,
    )
    source_status = "clean" if orientation.get("source_clean") is True else "unverified"
    runtime_status = orientation.get("status")
    if not isinstance(runtime_status, str) or not runtime_status:
        runtime_status = "unknown"
    valid = (
        source_status == "clean"
        and runtime_status == "complete"
        and raw_mcp["status"] in {"valid", "not_required"}
        and semantic["status"] == "passed"
    )
    return {
        "task_id": task_id,
        "replicate": replicate,
        "condition": condition,
        "orientation_path": str(orientation_path),
        "run_path": str(run_path),
        "source_path": str(source_root) if source_root is not None else None,
        "status": "valid" if valid else "excluded",
        "runtime_status": runtime_status,
        "source_status": source_status,
        "raw_mcp_status": raw_mcp["status"],
        "semantic_status": semantic["status"],
        "status_categories": {
            "runtime": runtime_status,
            "source": source_status,
            "raw_mcp": raw_mcp["status"],
            "semantic": semantic["status"],
        },
        "raw_mcp": raw_mcp,
        "semantic": semantic,
    }


def audit_pilot(output_root: Path) -> dict[str, object]:
    """Replay every saved v2 trace under ``output_root`` without side effects."""
    output_root = output_root.resolve()
    _require_v2_root(output_root)
    orientation_paths = sorted(output_root.glob("*/*/*/output/orientation.json"))
    if not orientation_paths:
        raise ValueError("no v2 orientation artifacts found")
    records = [_audit_run(path) for path in orientation_paths]
    result: dict[str, object] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "protocol": AUDIT_PROTOCOL,
        "source_protocol": V2_PILOT_PROTOCOL,
        "runs": records,
    }
    (output_root / "audited-results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(audit_pilot(args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
