"""Contract tests for the separately preregistered temporal-review v2 cohort."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from evals import temporal_review_v2_fixtures as v2


def _source_root(tmp_path: Path) -> Path:
    risk = tmp_path / "src/loomgraph/core/impact/risk.py"
    analysis = tmp_path / "src/loomgraph/cli/_analysis.py"
    risk.parent.mkdir(parents=True)
    analysis.parent.mkdir(parents=True)
    risk.write_text("class RiskAssessor:\n    def assess(self):\n        return None\n")
    analysis.write_text("async def _async_impact():\n    return None\n")
    return tmp_path


def _raw(task_id: str) -> dict[str, object]:
    contract = v2.contract(task_id)
    changed: list[dict[str, str]] = []
    chains: list[dict[str, str]] = []
    for locus in contract.oracle["required_review_loci"]:
        kind = locus["evidence_kind"]["treatment"]
        if kind == "content_delta":
            changed.append(
                {
                    "name": f"src.loomgraph.core.impact.risk.{locus['qualname']}",
                    "source_id": f"{locus['path']}:1",
                }
            )
        else:
            chains.append({"src": locus["qualname"].replace(".", "::"), "tgt": "other"})
    return {
        "success": True,
        "data": {
            "base": {"ref": contract.base_ref, "sha": contract.refs["base"]["commit_sha"], "workspace": "base", "provisioned": "created"},
            "head": {"ref": contract.head_ref, "sha": contract.refs["head"]["commit_sha"], "workspace": "head", "provisioned": "reused"},
            "diff": {
                "content_comparison": {
                    "status": contract.expected_comparison["status"],
                    "reason": contract.expected_comparison["reason"],
                    "base_backend": contract.backend,
                    "head_backend": contract.backend,
                    "changed": changed if contract.expected_comparison["status"] == "available" else None,
                },
                "edges_added": chains,
                "new_chains": chains,
                "broken_chains": [],
            },
        },
    }


def _answer(task_id: str, *, condition: str, raw: dict[str, object] | None = None) -> dict[str, object]:
    contract = v2.contract(task_id)
    comparison = None
    if condition == "treatment":
        parsed = v2.parse_raw_response(task_id, raw)
        assert parsed["valid"]
        comparison = parsed["comparison"]
    return {
        "decision": {**contract.oracle["decision"], "rationale": "registered decision"},
        "review_loci": [
            {
                "path": locus["path"],
                "qualname": locus["qualname"],
                "evidence_kind": locus["evidence_kind"][condition],
                "rationale": "registered identity",
            }
            for locus in contract.oracle["required_review_loci"]
        ],
        "trust": {"availability": "available" if condition == "treatment" else "unavailable", "comparison": comparison},
    }


def test_v2_manifest_and_instructions_are_valid_and_isolated() -> None:
    manifest = v2.load_manifest()
    assert manifest["manifest_id"] != "loomgraph-temporal-review"
    for task_id in v2.TASK_IDS:
        instruction = v2.load_instruction(task_id)
        assert "oracle" not in instruction
        assert v2.contract(task_id).refs["head"]["commit_sha"] not in instruction


@pytest.mark.parametrize("task_id", v2.TASK_IDS)
def test_v2_accepts_pre_registered_ast_identity_and_decision_enums(task_id: str, tmp_path: Path) -> None:
    raw = _raw(task_id)
    answer = _answer(task_id, condition="treatment", raw=raw)

    outcome = v2.evaluate_answer(task_id, answer, condition="treatment", source_root=_source_root(tmp_path), raw_response=raw)

    assert outcome.passed


def test_v2_baseline_requires_source_text_but_not_raw_temporal_evidence(tmp_path: Path) -> None:
    outcome = v2.evaluate_answer(
        "sparse-risk-review",
        _answer("sparse-risk-review", condition="baseline"),
        condition="baseline",
        source_root=_source_root(tmp_path),
    )
    assert outcome.passed


def test_v2_rejects_wrong_identity_enum_and_raw_underscore_rewrite(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    raw = _raw(task_id)
    answer = _answer(task_id, condition="treatment", raw=raw)
    broken = copy.deepcopy(answer)
    broken["review_loci"][0]["path"] = "src/elsewhere.py"
    broken["decision"]["boundary"] = "edge_delta_does_not_prove_behavior"
    broken["trust"]["comparison"]["content_comparison"]["reason"] = "backend_has_no_per-entity_content_hash"

    outcome = v2.evaluate_answer(task_id, broken, condition="treatment", source_root=_source_root(tmp_path), raw_response=raw)

    assert not outcome.passed
    assert any("does not resolve" in failure for failure in outcome.failures)
    assert any("decision enum" in failure for failure in outcome.failures)
    assert any("exactly match" in failure for failure in outcome.failures)


def test_v2_manifest_rejects_v1_style_contract_drift() -> None:
    manifest = copy.deepcopy(v2.load_manifest())
    manifest["tasks"][0]["oracle"]["required_review_loci"][0]["evidence_kind"] = "changed"

    with pytest.raises(v2.V2ContractError, match="identity evidence"):
        v2.validate_manifest(manifest)
