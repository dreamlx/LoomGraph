"""Re-evaluate saved temporal-review traces without invoking a model or MCP."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from evals.deepswe.claude_orientation import (  # noqa: E402
    _load_temporal_review_contract,
    build_temporal_review_packet,
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def audit_pilot(output_root: Path) -> dict[str, object]:
    """Rebuild packet validity from immutable run artifacts."""
    output_root = output_root.resolve()
    records: list[dict[str, object]] = []
    for orientation_path in sorted(output_root.glob("*/*/*/output/orientation.json")):
        orientation = _read_json(orientation_path)
        run = _read_json(orientation_path.with_name("run.json"))
        task_id = orientation_path.parents[3].name
        condition = orientation.get("condition")
        if condition not in {"baseline", "treatment"}:
            raise ValueError(f"{orientation_path} lacks condition")
        tooling = orientation.get("tooling")
        loomgraph = tooling.get("loomgraph") if isinstance(tooling, dict) else None
        tools = loomgraph.get("tools") if isinstance(loomgraph, dict) else []
        unexpected = loomgraph.get("unexpected_tools") if isinstance(loomgraph, dict) else []
        raw_observation = orientation.get("trust_observation")
        raw_responses = (
            raw_observation.get("raw_branch_diff_responses")
            if isinstance(raw_observation, dict)
            else []
        )
        packet = build_temporal_review_packet(
            condition=condition,
            use_mode=str(orientation.get("orientation_mode", "")),
            source_clean=orientation.get("source_clean") is True,
            return_code=int(run.get("return_code", 1)),
            summary={
                "final_result_seen": run.get("final_result_seen") is True,
                "payload": {
                    key: orientation.get(key) for key in ("decision", "review_loci", "trust")
                },
                "tool_names": tools,
                "unexpected_mcp_tools": unexpected,
                "raw_branch_diff_responses": raw_responses,
            },
            contract=_load_temporal_review_contract(task_id),
            requested_model=str(orientation.get("model", {}).get("requested", ""))
            if isinstance(orientation.get("model"), dict)
            else "",
            agent_execution_seconds=orientation.get("agent_execution_seconds"),
        )
        records.append(
            {
                "task_id": task_id,
                "replicate": orientation_path.parents[2].name,
                "condition": condition,
                "orientation_path": str(orientation_path),
                "status": packet["status"],
                "invalid_reason": packet["invalid_reason"],
                "source_clean": packet["source_clean"],
                "raw_comparison_aligned": packet["trust_observation"]["raw_comparison_aligned"],
                "valid_raw_branch_diff_count": packet["trust_observation"]["valid_raw_branch_diff_count"],
                "task_review_observation": packet["task_review_observation"],
            }
        )
    if not records:
        raise ValueError("no temporal-review orientation artifacts found")
    result = {"schema_version": 1, "protocol": "temporal-review-pilot-audit", "runs": records}
    (output_root / "audited-results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(audit_pilot(args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
