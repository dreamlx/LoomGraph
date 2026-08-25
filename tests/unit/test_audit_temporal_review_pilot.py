"""Tests for replaying saved temporal-review evidence without new model calls."""

from __future__ import annotations

import json
from pathlib import Path

from evals import audit_temporal_review_pilot as audit


def test_audit_rebuilds_one_saved_orientation(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "impact-low-resolution-review" / "rep-01" / "treatment" / "output"
    output.mkdir(parents=True)
    (output / "orientation.json").write_text(
        json.dumps(
            {
                "condition": "treatment",
                "orientation_mode": "voluntary",
                "source_clean": True,
                "decision": "review",
                "review_loci": [],
                "trust": {"availability": "available", "comparison": {}},
                "tooling": {"loomgraph": {"tools": [], "unexpected_tools": []}},
                "trust_observation": {"raw_branch_diff_responses": []},
            }
        )
    )
    (output / "run.json").write_text(json.dumps({"return_code": 0, "final_result_seen": True}))

    monkeypatch.setattr(audit, "_load_temporal_review_contract", lambda task_id: task_id)
    monkeypatch.setattr(
        audit,
        "build_temporal_review_packet",
        lambda **_kwargs: {
            "status": "complete",
            "invalid_reason": None,
            "source_clean": True,
            "trust_observation": {"raw_comparison_aligned": True, "valid_raw_branch_diff_count": 1},
            "task_review_observation": {"passed": True, "failures": []},
        },
    )

    result = audit.audit_pilot(tmp_path)

    assert result["runs"] == [
        {
            "task_id": "impact-low-resolution-review",
            "replicate": "rep-01",
            "condition": "treatment",
            "orientation_path": str(output / "orientation.json"),
            "status": "complete",
            "invalid_reason": None,
            "source_clean": True,
            "raw_comparison_aligned": True,
            "valid_raw_branch_diff_count": 1,
            "task_review_observation": {"passed": True, "failures": []},
        }
    ]
    assert (tmp_path / "audited-results.json").is_file()
