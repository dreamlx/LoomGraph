"""Tests for replaying saved temporal-review v2 traces only."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from evals import audit_temporal_review_v2_pilot as audit
from evals import temporal_review_v2_fixtures as v2


def _source_root(run_dir: Path) -> Path:
    source = run_dir / "source"
    file = source / "src/loomgraph/core/impact/risk.py"
    file.parent.mkdir(parents=True)
    file.write_text(
        "class RiskAssessor:\n"
        "    def assess(self):\n"
        "        return None\n",
        encoding="utf-8",
    )
    return source


def _raw(task_id: str) -> dict[str, object]:
    contract = v2.contract(task_id)
    locus = contract.oracle["required_review_loci"][0]
    return {
        "success": True,
        "data": {
            "base": {
                "ref": contract.base_ref,
                "sha": contract.refs["base"]["commit_sha"],
                "workspace": "base",
                "provisioned": "created",
            },
            "head": {
                "ref": contract.head_ref,
                "sha": contract.refs["head"]["commit_sha"],
                "workspace": "head",
                "provisioned": "reused",
            },
            "diff": {
                "content_comparison": {
                    **contract.expected_comparison,
                    "changed": [
                        {
                            "name": f"src.loomgraph.core.impact.risk.{locus['qualname']}",
                            "source_id": f"{locus['path']}:1",
                        }
                    ],
                },
                "edges_added": [],
                "new_chains": [],
                "broken_chains": [],
            },
        },
    }


def _answer(task_id: str, raw: dict[str, object]) -> dict[str, object]:
    contract = v2.contract(task_id)
    comparison = v2.parse_raw_response(task_id, raw)["comparison"]
    return {
        "decision": {**contract.oracle["decision"], "rationale": "registered decision"},
        "review_loci": [
            {
                "path": locus["path"],
                "qualname": locus["qualname"],
                "evidence_kind": locus["evidence_kind"]["treatment"],
                "rationale": "registered identity",
            }
            for locus in contract.oracle["required_review_loci"]
        ],
        "trust": {"availability": "available", "comparison": comparison},
    }


def _write_valid_trace(root: Path) -> dict[str, object]:
    task_id = "sparse-risk-review"
    run_dir = root / task_id / "rep-01" / "treatment"
    source = _source_root(run_dir)
    raw = _raw(task_id)
    answer = _answer(task_id, raw)
    output = run_dir / "output"
    output.mkdir()
    (output / "orientation.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "protocol": audit.V2_ORIENTATION_PROTOCOL,
                "condition": "treatment",
                "status": "complete",
                "source_clean": True,
                **answer,
                "trust_observation": {"raw_branch_diff_responses": [raw]},
            }
        ),
        encoding="utf-8",
    )
    (output / "run.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "condition": "treatment",
                "return_code": 0,
                "final_result_seen": True,
                "source_dir": str(source),
            }
        ),
        encoding="utf-8",
    )
    (root / "pilot-results.json").write_text(
        json.dumps({"schema_version": 2, "protocol": audit.V2_PILOT_PROTOCOL}),
        encoding="utf-8",
    )
    return {"raw": raw, "answer": answer}


def test_audit_replays_v2_contract_and_preserves_raw_comparison(tmp_path: Path) -> None:
    expected = _write_valid_trace(tmp_path)

    result = audit.audit_pilot(tmp_path)

    row = result["runs"][0]
    assert row["status"] == "valid"
    assert row["runtime_status"] == "complete"
    assert row["semantic_status"] == "passed"
    assert row["raw_mcp_status"] == "valid"
    assert row["raw_mcp"]["raw_responses"] == [expected["raw"]]
    assert row["raw_mcp"]["comparisons"][0] == expected["answer"]["trust"]["comparison"]
    assert (tmp_path / "audited-results.json").is_file()


@pytest.mark.parametrize(
    "marker",
    [
        None,
        {"schema_version": 1, "protocol": "temporal-review-pilot"},
        {"schema_version": 1, "protocol": "temporal-review-pilot-audit"},
    ],
)
def test_audit_refuses_missing_or_v1_r2_protocol_root(tmp_path: Path, marker: object) -> None:
    if marker is not None:
        (tmp_path / "pilot-results.json").write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(ValueError, match="refusing|missing|unsupported"):
        audit.audit_pilot(tmp_path)


def test_audit_never_invokes_model_or_mcp(tmp_path: Path, monkeypatch) -> None:
    _write_valid_trace(tmp_path)

    def fail(*_args, **_kwargs):
        raise AssertionError("saved-trace audit must not invoke a process")

    monkeypatch.setattr(subprocess, "run", fail)
    result = audit.audit_pilot(tmp_path)

    assert result["runs"][0]["semantic_status"] == "passed"
