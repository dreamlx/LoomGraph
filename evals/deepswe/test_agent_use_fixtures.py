"""Contract checks for native-agent structural adoption fixtures."""

from __future__ import annotations

import json
from pathlib import Path


def test_vulture_scan_impact_fixture_has_oracle_and_trust_contract() -> None:
    root = Path(__file__).parent
    manifest = json.loads((root / "agent-use-fixtures.json").read_text())
    fixture = manifest["fixtures"][0]

    assert fixture["id"] == "vulture-scan-impact"
    assert fixture["task_class"] == "structural-impact"
    assert fixture["oracle_existing_paths"] == [
        "vulture/core.py",
        "vulture/utils.py",
        "vulture/noqa.py",
    ]
    assert fixture["required_trust_fields"] == [
        "edge_trust",
        "resolution.resolved_ratio",
        "resolution.internal_unresolved_ratio",
        "resolution.external_unresolved_ratio",
    ]
    prompt = (root / fixture["instruction_file"]).read_text()
    assert "direct caller" in prompt
    assert "uncertainty" in prompt
