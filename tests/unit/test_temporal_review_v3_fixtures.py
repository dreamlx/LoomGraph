"""Contract tests for the separately preregistered temporal-review v3 cohort."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from evals import temporal_review_v3_fixtures as v3


def _source_root(tmp_path: Path) -> Path:
    risk = tmp_path / "src/loomgraph/core/impact/risk.py"
    analysis = tmp_path / "src/loomgraph/cli/_analysis.py"
    risk.parent.mkdir(parents=True)
    analysis.parent.mkdir(parents=True)
    risk.write_text("class RiskAssessor:\n    def assess(self):\n        return None\n")
    analysis.write_text("async def _async_impact():\n    return None\n")
    return tmp_path


def _raw(task_id: str) -> dict[str, Any]:
    item = v3.contract(task_id)
    changed: list[dict[str, str]] = []
    chains: list[dict[str, str]] = []
    for locus in item.oracle["required_review_loci"]:
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
            "base": {
                "ref": item.base_ref,
                "sha": item.refs["base"]["commit_sha"],
                "workspace": "base",
                "provisioned": "created",
            },
            "head": {
                "ref": item.head_ref,
                "sha": item.refs["head"]["commit_sha"],
                "workspace": "head",
                "provisioned": "reused",
            },
            "diff": {
                "content_comparison": {
                    "status": item.expected_comparison["status"],
                    "reason": item.expected_comparison["reason"],
                    "base_backend": item.backend,
                    "head_backend": item.backend,
                    "changed": changed
                    if item.expected_comparison["status"] == "available"
                    else None,
                },
                "edges_added": chains,
                "new_chains": chains,
                "broken_chains": [],
            },
        },
    }


def _answer(task_id: str, *, condition: str) -> dict[str, Any]:
    item = v3.contract(task_id)
    return {
        "decision": {
            "outcome": item.oracle["decision"]["outcome"],
            "boundary": item.oracle["decision"]["boundary"][condition],
            "rationale": "registered decision",
        },
        "review_loci": [
            {
                "path": locus["path"],
                "qualname": locus["qualname"],
                "rationale": "registered identity",
            }
            for locus in item.oracle["required_review_loci"]
        ],
    }


def test_v3_manifest_and_instructions_are_valid_and_isolated() -> None:
    manifest = v3.load_manifest()
    assert manifest["schema_version"] == 3
    assert manifest["manifest_id"] != "loomgraph-temporal-review-v2-reregistration"
    assert manifest["answer_schema"]["top_level_fields"] == ["decision", "review_loci"]
    assert manifest["answer_schema"]["review_locus_fields"] == ["path", "qualname", "rationale"]
    assert "evals/**" in manifest["fixture_exclusion_globs"]
    for task_id in v3.TASK_IDS:
        instruction = v3.load_instruction(task_id)
        assert '"trust"' not in instruction
        assert "evidence_kind" not in instruction
        assert v3.contract(task_id).refs["head"]["commit_sha"] not in instruction


@pytest.mark.parametrize("task_id", v3.TASK_IDS)
def test_v3_accepts_ast_identity_decision_and_adapter_selected_raw(
    task_id: str, tmp_path: Path
) -> None:
    assert v3.evaluate_answer(
        task_id,
        _answer(task_id, condition="treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed


def test_v3_baseline_requires_not_observed_boundary_without_raw(tmp_path: Path) -> None:
    assert v3.evaluate_answer(
        "sparse-risk-review",
        _answer("sparse-risk-review", condition="baseline"),
        condition="baseline",
        source_root=_source_root(tmp_path),
    ).passed


@pytest.mark.parametrize("extra_field", ["trust", "comparison"])
def test_v3_rejects_model_trust_or_comparison_field(extra_field: str, tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    answer = _answer(task_id, condition="treatment")
    answer[extra_field] = {"reason": "backend_has_no_per_entity_content_hash"}

    outcome = v3.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not outcome.passed
    assert outcome.failures == ("answer top-level fields are invalid",)


def test_v3_rejects_model_evidence_kind_and_wrong_identity(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    answer = _answer(task_id, condition="treatment")
    answer["review_loci"][0]["evidence_kind"] = "graph_boundary"

    extra_field = v3.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not extra_field.passed
    assert any("review locus fields" in failure for failure in extra_field.failures)


def test_v3_rejects_locus_outside_frozen_head_ast(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    answer = _answer(task_id, condition="treatment")
    answer["review_loci"][0]["path"] = "src/elsewhere.py"

    outcome = v3.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not outcome.passed
    assert any("does not resolve" in failure for failure in outcome.failures)


def test_v3_rationale_paraphrase_does_not_rewrite_adapter_per_entity(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    answer = _answer(task_id, condition="treatment")
    answer["decision"]["rationale"] = "per_entity 与 per-entity 都只是叙述，不改变原始证据。"
    answer["review_loci"][0]["rationale"] = "需要复核该位置。"
    raw = _raw(task_id)

    assert (
        v3.parse_raw_response(task_id, raw)["comparison"]["content_comparison"]["reason"]
        == "backend_has_no_per_entity_content_hash"
    )
    assert v3.evaluate_answer(
        task_id, answer, condition="treatment", source_root=_source_root(tmp_path), raw_response=raw
    ).passed


def test_v3_unavailable_raw_requires_unavailable_boundary(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    answer = _answer(task_id, condition="treatment")
    answer["decision"]["boundary"] = "content_comparison_available"

    outcome = v3.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not outcome.passed
    assert any("decision enum" in failure for failure in outcome.failures)


def test_v3_rejects_adapter_reason_rewrite_even_though_model_has_no_reason(tmp_path: Path) -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    raw = _raw(task_id)
    raw["data"]["diff"]["content_comparison"]["reason"] = "backend_has_no_per-entity_content_hash"

    outcome = v3.evaluate_answer(
        task_id,
        _answer(task_id, condition="treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=raw,
    )

    assert not outcome.passed
    assert any(
        "raw response is invalid: content_comparison_mismatch" in failure
        for failure in outcome.failures
    )


def test_v3_manifest_rejects_model_surface_drift() -> None:
    manifest = copy.deepcopy(v3.load_manifest())
    manifest["answer_schema"]["top_level_fields"].append("trust")

    with pytest.raises(v3.V3ContractError, match="answer fields"):
        v3.validate_manifest(manifest)


def test_v3_manifest_rejects_source_only_exclusion_drift() -> None:
    manifest = copy.deepcopy(v3.load_manifest())
    manifest["fixture_exclusion_globs"].remove("evals/**")

    with pytest.raises(v3.V3ContractError, match="source-only exclusions"):
        v3.validate_manifest(manifest)
