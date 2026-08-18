#!/usr/bin/env python3
"""Summarize semantic packets and response-format compliance separately."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


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


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} <pilot-output-dir>", file=sys.stderr)
        return 2

    output_dir = Path(sys.argv[1]).resolve()
    packets = sorted(output_dir.glob("*/**/artifacts/orientation.json"))
    if not packets:
        print(f"no orientation packets under {output_dir}", file=sys.stderr)
        return 2

    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in packets:
        condition = path.relative_to(output_dir).parts[0].split("-", 1)[0]
        if condition not in {"baseline", "treatment"}:
            continue
        try:
            packet = json.loads(path.read_text())
        except json.JSONDecodeError:
            packet = {}
        tool = packet.get("tooling", {}).get("loomgraph", {})
        rows[condition].append(
            {
                "run": path.relative_to(output_dir).parts[0],
                "valid": packet_is_valid(packet),
                "raw_json": packet.get("response_format") == "raw_json",
                "loomgraph_used": tool.get("used") is True,
            }
        )

    print(
        "condition,runs,semantic_packets,semantic_packet_rate,"
        "raw_json_packets,raw_json_rate,loomgraph_used"
    )
    for condition in ("baseline", "treatment"):
        condition_rows = rows[condition]
        valid_count = sum(row["valid"] for row in condition_rows)
        raw_json_count = sum(row["raw_json"] for row in condition_rows)
        used_count = sum(row["loomgraph_used"] for row in condition_rows)
        rate = valid_count / len(condition_rows) if condition_rows else 0.0
        raw_json_rate = raw_json_count / len(condition_rows) if condition_rows else 0.0
        print(
            f"{condition},{len(condition_rows)},{valid_count},{rate:.3f},"
            f"{raw_json_count},{raw_json_rate:.3f},{used_count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
