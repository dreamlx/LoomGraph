"""Contract tests for the independently preregistered v5 cohort."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from evals import temporal_review_v5_fixtures as v5


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
    item = v5.contract(task_id)
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
    item = v5.contract(task_id)
    return {
        "decision": {
            "boundary": item.oracle["boundary"][condition],
            "rationale": "Comparison boundary is separate from adapter-owned raw evidence.",
        },
        "review_loci": [
            {"path": locus["path"], "qualname": locus["qualname"], "rationale": "Review this identity."}
            for locus in item.oracle["required_review_loci"]
        ],
    }


def test_v5_manifest_declares_an_independent_non_pooled_cohort() -> None:
    manifest = v5.load_manifest()

    assert manifest["schema_version"] == 5
    assert manifest["manifest_id"] != "loomgraph-temporal-review-v4-navigation-evidence"
    assert manifest["cohort_lineage"]["predecessor_evidence"] == "archive_only_not_pooled_or_rescored"
    assert manifest["selection_preflight_sha256"] == v5.selection_preflight_sha256()
    assert manifest["answer_schema"]["scored_model_fields"] == [
        "decision.boundary",
        "review_loci.path",
        "review_loci.qualname",
    ]
    assert "tool" not in v5.MANIFEST_PATH.read_text(encoding="utf-8").lower()
    for task_id in v5.TASK_IDS:
        instruction = v5.load_instruction(task_id)
        assert '"outcome"' not in instruction
        assert '"trust"' not in instruction
        assert v5.contract(task_id).refs["head"]["commit_sha"] not in instruction


@pytest.mark.parametrize("task_id", v5.TASK_IDS)
def test_v5_accepts_public_boundary_ast_identity_and_adapter_raw(task_id: str, tmp_path: Path) -> None:
    assert v5.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed


def test_v5_baseline_requires_only_public_not_observed_boundary(tmp_path: Path) -> None:
    task_id = v5.TASK_IDS[0]

    assert v5.evaluate_answer(
        task_id,
        _answer(task_id, "baseline"),
        condition="baseline",
        source_root=_source_root(tmp_path),
    ).passed


@pytest.mark.parametrize("field", ["outcome", "trust", "comparison", "evidence_kind"])
def test_v5_rejects_non_public_model_fields(field: str, tmp_path: Path) -> None:
    task_id = v5.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    if field == "outcome":
        answer["decision"][field] = "review_required"
    elif field == "evidence_kind":
        answer["review_loci"][0][field] = "content_delta"
    else:
        answer[field] = {"value": "not adapter evidence"}

    outcome = v5.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not outcome.passed


def test_v5_treats_trace_tool_count_as_outside_contract_validity(tmp_path: Path) -> None:
    task_id = v5.TASK_IDS[0]
    raw = _raw(task_id)
    raw["trace_metadata"] = {"tool_calls": 999}

    assert v5.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=raw,
    ).passed


def test_v5_rejects_wrong_boundary_and_duplicate_ast_identity(tmp_path: Path) -> None:
    task_id = v5.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["decision"]["boundary"] = "content_comparison_unavailable"
    answer["review_loci"].append(copy.deepcopy(answer["review_loci"][0]))

    outcome = v5.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not outcome.passed
    assert any("boundary" in failure for failure in outcome.failures)
    assert any("duplicate review locus" in failure for failure in outcome.failures)


@pytest.mark.parametrize("mutation", ["sha", "backend", "l2", "missing_raw_support"])
def test_v5_rejects_raw_ref_backend_l2_or_identity_mismatch(mutation: str, tmp_path: Path) -> None:
    task_id = v5.TASK_IDS[1]
    raw = _raw(task_id)
    if mutation == "sha":
        raw["data"]["head"]["sha"] = "0" * 40
    elif mutation == "backend":
        raw["data"]["diff"]["content_comparison"]["head_backend"] = "codegraph"
    elif mutation == "l2":
        raw["data"]["diff"]["content_comparison"]["scope"] = "cross_backend"
    else:
        raw["data"]["diff"]["content_comparison"]["changed"] = []

    outcome = v5.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=raw,
    )

    assert not outcome.passed


def test_v5_rejects_hidden_outcome_scoring_or_wrong_source_only_exclusion() -> None:
    manifest = copy.deepcopy(v5.load_manifest())
    manifest["answer_schema"]["scored_model_fields"].append("tool_calls")

    with pytest.raises(v5.V5ContractError, match="answer fields"):
        v5.validate_manifest(manifest)

    manifest = copy.deepcopy(v5.load_manifest())
    manifest["fixture_exclusion_globs"].remove("evals/**")

    with pytest.raises(v5.V5ContractError, match="source-only"):
        v5.validate_manifest(manifest)
