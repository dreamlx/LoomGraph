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
        "availability",
        "edge_trust",
        "resolution.resolved_ratio",
        "resolution.internal_unresolved_ratio",
        "resolution.external_unresolved_ratio",
    ]
    prompt = (root / fixture["instruction_file"]).read_text()
    assert "direct caller" in prompt
    assert "uncertainty" in prompt
    assert "edge_trust" in prompt
    assert "resolved_ratio" in prompt


def test_vulture_reachability_fixture_requires_dynamic_receiver_caveat() -> None:
    root = Path(__file__).parent
    manifest = json.loads((root / "agent-use-fixtures.json").read_text())
    fixture = next(
        item
        for item in manifest["fixtures"]
        if item["id"] == "vulture-reachability-condition-impact"
    )

    assert fixture["task_class"] == "trust-adversary-dynamic-receiver"
    assert fixture["rg_equivalent_single_query"] is False
    assert fixture["oracle_existing_paths"] == [
        "vulture/utils.py",
        "vulture/reachability.py",
        "vulture/core.py",
    ]
    assert fixture["required_trust_fields"] == [
        "availability",
        "edge_trust",
        "resolution.resolved_ratio",
        "resolution.internal_unresolved_ratio",
        "resolution.external_unresolved_ratio",
    ]
    prompt = (root / fixture["instruction_file"]).read_text()
    assert "dynamic\nreceiver" in prompt
    assert "not proof" in prompt
    assert "edge_trust" in prompt
