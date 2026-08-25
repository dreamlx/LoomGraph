"""Contract tests for the separate temporal-review product pilot."""

from __future__ import annotations

import copy

import pytest
from evals import temporal_review_fixtures as review


def _contract(task_id: str) -> review.TemporalReviewContract:
    return review.load_temporal_review_contract(task_id)


def _raw(task_id: str) -> dict[str, object]:
    contract = _contract(task_id)
    content_comparison: dict[str, object] = {
        "status": contract.comparison_status,
        "base_backend": contract.backend,
        "head_backend": contract.backend,
    }
    if contract.comparison_reason is not None:
        content_comparison["reason"] = contract.comparison_reason
    return {
        "success": True,
        "data": {
            "base": {
                "ref": contract.base_ref,
                "sha": contract.refs["base"]["commit_sha"],
                "workspace": "pilot:base",
                "provisioned": "created",
            },
            "head": {
                "ref": contract.head_ref,
                "sha": contract.refs["head"]["commit_sha"],
                "workspace": "pilot:head",
                "provisioned": "reused",
            },
            "diff": {
                "broken_chains": [],
                "content_comparison": content_comparison,
            },
        },
    }


def _answer(task_id: str, *, availability: str = "available") -> dict[str, object]:
    contract = _contract(task_id)
    loci = [
        {"symbol": locus["symbol"], "change": locus["change"], "evidence": "raw diff"}
        for locus in contract.oracle["required_review_loci"]
    ]
    decision = "；".join(contract.oracle["required_decision_phrases"]) or "需要复核实现责任"
    comparison: object = None
    if availability == "available":
        comparison = {
            "base_ref": contract.base_ref,
            "head_ref": contract.head_ref,
            "base_backend": contract.backend,
            "head_backend": contract.backend,
            "base_provisioned": "created",
            "head_provisioned": "reused",
            "content_comparison": {
                "status": contract.comparison_status,
                "reason": contract.comparison_reason,
            },
        }
    return {
        "decision": decision,
        "review_loci": loci,
        "trust": {"availability": availability, "comparison": comparison},
    }


def test_manifest_and_instructions_are_valid_and_non_leaking() -> None:
    manifest = review.load_temporal_review_manifest()
    review.validate_temporal_review_manifest(manifest)

    for task_id in review.TEMPORAL_REVIEW_TASK_IDS:
        instruction = review.load_temporal_review_instruction(task_id)
        assert instruction
        contract = _contract(task_id)
        assert contract.refs["base"]["commit_sha"] not in instruction
        assert contract.refs["head"]["commit_sha"] not in instruction
        for locus in contract.oracle["required_review_loci"]:
            assert locus["symbol"] not in instruction


def test_baseline_requires_explicit_unavailable_comparison() -> None:
    assert review.evaluate_baseline_answer(
        "impact-low-resolution-review", _answer("impact-low-resolution-review", availability="unavailable")
    ).passed

    fabricated = _answer("impact-low-resolution-review")
    assert not review.evaluate_baseline_answer("impact-low-resolution-review", fabricated).passed


@pytest.mark.parametrize(
    "task_id",
    ("impact-low-resolution-review", "sparse-risk-review", "sparse-risk-codegraph-uncertainty"),
)
def test_treatment_requires_raw_aligned_task_specific_evidence(task_id: str) -> None:
    assert review.evaluate_treatment_answer(task_id, _answer(task_id), _raw(task_id)).passed


def test_codegraph_unavailable_cannot_be_described_as_unchanged() -> None:
    task_id = "sparse-risk-codegraph-uncertainty"
    answer = _answer(task_id)
    answer["decision"] = "内容没有变化，可以接受。"

    outcome = review.evaluate_treatment_answer(task_id, answer, _raw(task_id))

    assert not outcome.passed
    assert any("不能把 unavailable 说成 unchanged" in failure for failure in outcome.failures)


@pytest.mark.parametrize(
    "path, value, expected_failure",
    (
        (("data", "base", "sha"), "0" * 40, "base_sha_mismatch"),
        (("data", "head", "ref"), "other", "head_ref_mismatch"),
        (("data", "diff", "content_comparison", "base_backend"), "codegraph", "base_backend_mismatch"),
        (("data", "diff", "content_comparison", "status"), "unavailable", "content_comparison_status_mismatch"),
        (("data", "diff", "content_comparison", "reason"), "invented", "content_comparison_reason_mismatch"),
    ),
)
def test_raw_response_rejects_trust_mismatches(
    path: tuple[str, ...], value: str, expected_failure: str
) -> None:
    raw = _raw("impact-low-resolution-review")
    target: object = raw
    for key in path[:-1]:
        assert isinstance(target, dict)
        target = target[key]
    assert isinstance(target, dict)
    target[path[-1]] = value

    outcome = review.evaluate_raw_response("impact-low-resolution-review", raw)

    assert outcome.passed is False
    assert outcome.failures == (expected_failure,)


def test_treatment_rejects_model_raw_mismatch_and_missing_locus() -> None:
    task_id = "impact-low-resolution-review"
    mismatch = _answer(task_id)
    mismatch["trust"]["comparison"]["head_ref"] = "other"
    assert not review.evaluate_treatment_answer(task_id, mismatch, _raw(task_id)).passed

    missing_locus = _answer(task_id)
    missing_locus["review_loci"] = missing_locus["review_loci"][:1]
    assert not review.evaluate_treatment_answer(task_id, missing_locus, _raw(task_id)).passed


def test_manifest_validator_rejects_contract_drift() -> None:
    manifest = copy.deepcopy(review.load_temporal_review_manifest())
    manifest["fixture_exclusion_globs"].remove("tests/**")

    with pytest.raises(review.FixtureContractError, match="fixture exclusions"):
        review.validate_temporal_review_manifest(manifest)
