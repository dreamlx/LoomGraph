"""Contract tests for the independently preregistered v4 cohort."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from evals import temporal_review_v4_fixtures as v4


def _source_root(tmp_path: Path) -> Path:
    analyzer = tmp_path / "src/loomgraph/core/impact/analyzer.py"
    git = tmp_path / "src/loomgraph/core/git.py"
    analyzer.parent.mkdir(parents=True)
    analyzer.write_text(
        "class ImpactAnalyzer:\n"
        "    async def _find_callers(self):\n"
        "        return []\n",
        encoding="utf-8",
    )
    git.write_text(
        "def get_changed_files():\n"
        "    return []\n",
        encoding="utf-8",
    )
    return tmp_path


def _raw(task_id: str) -> dict[str, Any]:
    item = v4.contract(task_id)
    changed = [
        {
            "source_id": f"{locus['path']}:1",
            "name": f"src.loomgraph.{locus['qualname']}",
        }
        for locus in item.oracle["required_review_loci"]
    ]
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
                    "version": 1,
                    "scope": "same_backend_only",
                    "status": "available",
                    "reason": None,
                    "base_backend": "codeindex",
                    "head_backend": "codeindex",
                    "changed": changed,
                }
            },
        },
    }


def _answer(task_id: str, condition: str) -> dict[str, Any]:
    item = v4.contract(task_id)
    return {
        "decision": {
            "boundary": item.oracle["boundary"][condition],
            "rationale": "comparison boundary is recorded separately from the raw evidence.",
        },
        "review_loci": [
            {"path": locus["path"], "qualname": locus["qualname"], "rationale": "review this identity"}
            for locus in item.oracle["required_review_loci"]
        ],
    }


def test_v4_manifest_and_instructions_are_isolated() -> None:
    manifest = v4.load_manifest()

    assert manifest["schema_version"] == 4
    assert manifest["manifest_id"] != "loomgraph-temporal-review-v3-adapter-trust"
    assert manifest["answer_schema"]["decision_fields"] == ["boundary", "rationale"]
    assert manifest["selection_preflight_sha256"] == v4.selection_preflight_sha256()
    for task_id in v4.TASK_IDS:
        instruction = v4.load_instruction(task_id)
        assert '"outcome"' not in instruction
        assert '"trust"' not in instruction
        assert v4.contract(task_id).refs["head"]["commit_sha"] not in instruction


@pytest.mark.parametrize("task_id", v4.TASK_IDS)
def test_v4_accepts_public_boundary_ast_identity_and_adapter_raw(task_id: str, tmp_path: Path) -> None:
    assert v4.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed


def test_v4_baseline_requires_only_public_not_observed_boundary(tmp_path: Path) -> None:
    task_id = v4.TASK_IDS[0]

    assert v4.evaluate_answer(
        task_id,
        _answer(task_id, "baseline"),
        condition="baseline",
        source_root=_source_root(tmp_path),
    ).passed


@pytest.mark.parametrize("field", ["outcome", "trust", "comparison", "evidence_kind"])
def test_v4_rejects_non_public_model_fields(field: str, tmp_path: Path) -> None:
    task_id = v4.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    if field == "outcome":
        answer["decision"][field] = "review_required"
    elif field == "evidence_kind":
        answer["review_loci"][0][field] = "content_delta"
    else:
        answer[field] = {"value": "not adapter evidence"}

    outcome = v4.evaluate_answer(
        task_id, answer, condition="treatment", source_root=_source_root(tmp_path), raw_response=_raw(task_id)
    )

    assert not outcome.passed


def test_v4_rejects_wrong_boundary_even_with_persuasive_rationale(tmp_path: Path) -> None:
    task_id = v4.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["decision"]["boundary"] = "content_comparison_unavailable"

    outcome = v4.evaluate_answer(
        task_id, answer, condition="treatment", source_root=_source_root(tmp_path), raw_response=_raw(task_id)
    )

    assert not outcome.passed
    assert any("boundary" in failure for failure in outcome.failures)


def test_v4_rejects_duplicate_identity_without_credit(tmp_path: Path) -> None:
    task_id = v4.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["review_loci"].append(copy.deepcopy(answer["review_loci"][0]))

    outcome = v4.evaluate_answer(
        task_id, answer, condition="treatment", source_root=_source_root(tmp_path), raw_response=_raw(task_id)
    )

    assert not outcome.passed
    assert any("duplicate review locus" in failure for failure in outcome.failures)


def test_v4_rejects_non_ast_qualname(tmp_path: Path) -> None:
    task_id = v4.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["review_loci"][0]["qualname"] = "ImpactAnalyzer::_find_callers"

    outcome = v4.evaluate_answer(
        task_id, answer, condition="treatment", source_root=_source_root(tmp_path), raw_response=_raw(task_id)
    )

    assert not outcome.passed
    assert any("does not resolve" in failure for failure in outcome.failures)


def test_v4_treatment_rejects_unavailable_as_not_unchanged(tmp_path: Path) -> None:
    task_id = v4.TASK_IDS[0]
    raw = _raw(task_id)
    raw["data"]["diff"]["content_comparison"].update(
        {"status": "unavailable", "reason": "backend_has_no_per_entity_content_hash"}
    )

    outcome = v4.evaluate_answer(
        task_id, _answer(task_id, "treatment"), condition="treatment", source_root=_source_root(tmp_path), raw_response=raw
    )

    assert not outcome.passed
    assert any("content_comparison_mismatch" in failure for failure in outcome.failures)


@pytest.mark.parametrize("mutation", ["sha", "backend", "l2", "missing_raw_support"])
def test_v4_rejects_raw_ref_backend_or_identity_mismatch(mutation: str, tmp_path: Path) -> None:
    task_id = v4.TASK_IDS[1]
    raw = _raw(task_id)
    if mutation == "sha":
        raw["data"]["head"]["sha"] = "0" * 40
    elif mutation == "backend":
        raw["data"]["diff"]["content_comparison"]["head_backend"] = "codegraph"
    elif mutation == "l2":
        raw["data"]["diff"]["content_comparison"]["scope"] = "cross_backend"
    else:
        raw["data"]["diff"]["content_comparison"]["changed"] = []

    outcome = v4.evaluate_answer(
        task_id, _answer(task_id, "treatment"), condition="treatment", source_root=_source_root(tmp_path), raw_response=raw
    )

    assert not outcome.passed


def test_v4_manifest_rejects_hidden_outcome_or_wrong_source_only_exclusion() -> None:
    manifest = copy.deepcopy(v4.load_manifest())
    manifest["answer_schema"]["decision_fields"].append("outcome")

    with pytest.raises(v4.V4ContractError, match="answer fields"):
        v4.validate_manifest(manifest)

    manifest = copy.deepcopy(v4.load_manifest())
    manifest["fixture_exclusion_globs"].remove("evals/**")

    with pytest.raises(v4.V4ContractError, match="source-only"):
        v4.validate_manifest(manifest)
