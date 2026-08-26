"""Contract tests for the independently preregistered v6 cohort."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from evals import temporal_review_v6_fixtures as v6


def _source_root(tmp_path: Path) -> Path:
    analyzer = tmp_path / "src/loomgraph/core/impact/analyzer.py"
    git = tmp_path / "src/loomgraph/core/git.py"
    analyzer.parent.mkdir(parents=True)
    analyzer.write_text(
        "class ImpactAnalyzer:\n    async def _find_callers(self):\n        return []\n",
        encoding="utf-8",
    )
    git.write_text(
        "def get_changed_files():\n    return []\n",
        encoding="utf-8",
    )
    return tmp_path


def _raw(task_id: str) -> dict[str, Any]:
    item = v6.contract(task_id)
    locus = item.oracle["required_review_locus"]
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
                    "changed": [
                        {
                            "source_id": f"{locus['path']}:1",
                            "name": f"src.loomgraph.{locus['qualname']}",
                        }
                    ],
                }
            },
        },
    }


def _answer(task_id: str, condition: str) -> dict[str, Any]:
    item = v6.contract(task_id)
    locus = item.oracle["required_review_locus"]
    return {
        "decision": {
            "boundary": item.oracle["boundary"][condition],
            "rationale": "Comparison boundary is separate from adapter-owned raw evidence.",
        },
        "review_locus": {
            "path": locus["path"],
            "qualname": locus["qualname"],
            "rationale": "Review this identity.",
        },
    }


def test_v6_manifest_declares_independent_same_source_non_pooled_cohort() -> None:
    manifest = v6.load_manifest()

    assert manifest["schema_version"] == 6
    assert manifest["manifest_id"] != "loomgraph-temporal-review-v5-navigation-evidence"
    assert (
        manifest["cohort_lineage"]["predecessor_evidence"] == "archive_only_not_pooled_or_rescored"
    )
    assert manifest["selection_preflight_sha256"] == v6.selection_preflight_sha256()
    preflight = v6.SELECTION_PREFLIGHT_PATH.read_text(encoding="utf-8")
    assert not any(digest in preflight for digest in v6._V5_SELECTION_RAW_SHA256)
    assert manifest["answer_schema"]["scored_model_fields"] == [
        "decision.boundary",
        "review_locus.path",
        "review_locus.qualname",
    ]
    for task_id in v6.TASK_IDS:
        instruction = v6.load_instruction(task_id)
        assert '"review_loci"' not in instruction
        assert '"review_locus"' in instruction
        assert "只选择一个主要位置" in instruction
        assert "不要列替代项" in instruction
        assert v6.contract(task_id).refs["head"]["commit_sha"] not in instruction


@pytest.mark.parametrize("task_id", v6.TASK_IDS)
def test_v6_accepts_exactly_one_public_ast_identity_and_adapter_raw(
    task_id: str, tmp_path: Path
) -> None:
    assert v6.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed


def test_v6_baseline_requires_only_public_not_observed_boundary(tmp_path: Path) -> None:
    task_id = v6.TASK_IDS[0]

    assert v6.evaluate_answer(
        task_id,
        _answer(task_id, "baseline"),
        condition="baseline",
        source_root=_source_root(tmp_path),
    ).passed


@pytest.mark.parametrize("field", ["outcome", "trust", "comparison", "evidence_kind"])
def test_v6_rejects_non_public_model_fields(field: str, tmp_path: Path) -> None:
    task_id = v6.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    if field == "outcome":
        answer["decision"][field] = "review_required"
    elif field == "evidence_kind":
        answer["review_locus"][field] = "content_delta"
    else:
        answer[field] = {"value": "not adapter evidence"}

    assert not v6.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed


@pytest.mark.parametrize(
    "extra_locus",
    [
        [
            {
                "path": "src/loomgraph/core/git.py",
                "qualname": "get_changed_files",
                "rationale": "extra",
            }
        ],
        {
            "path": "src/loomgraph/core/git.py",
            "qualname": "get_changed_files",
            "rationale": "extra",
        },
    ],
)
def test_v6_rejects_any_extra_or_list_review_locus(extra_locus: object, tmp_path: Path) -> None:
    task_id = v6.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["review_loci"] = extra_locus

    outcome = v6.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not outcome.passed
    assert "answer top-level fields are invalid" in outcome.failures


def test_v6_rejects_a_list_in_the_singular_review_locus_field(tmp_path: Path) -> None:
    task_id = v6.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["review_locus"] = [answer["review_locus"]]

    outcome = v6.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not outcome.passed
    assert "review locus fields are invalid" in outcome.failures


def test_v6_rejects_non_resolving_or_non_primary_identity(tmp_path: Path) -> None:
    task_id = v6.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["review_locus"]["qualname"] = "ImpactAnalyzer.not_real"

    outcome = v6.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )

    assert not outcome.passed
    assert any("frozen head AST" in failure for failure in outcome.failures)
    assert any("v6 review identity is missing" in failure for failure in outcome.failures)


def test_v6_treats_trace_tool_count_as_outside_contract_validity(tmp_path: Path) -> None:
    task_id = v6.TASK_IDS[0]
    raw = _raw(task_id)
    raw["trace_metadata"] = {"tool_calls": 999}

    assert v6.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=raw,
    ).passed


@pytest.mark.parametrize("mutation", ["sha", "backend", "l2", "missing_raw_support"])
def test_v6_rejects_raw_ref_backend_l2_or_identity_mismatch(mutation: str, tmp_path: Path) -> None:
    task_id = v6.TASK_IDS[1]
    raw = _raw(task_id)
    if mutation == "sha":
        raw["data"]["head"]["sha"] = "0" * 40
    elif mutation == "backend":
        raw["data"]["diff"]["content_comparison"]["head_backend"] = "codegraph"
    elif mutation == "l2":
        raw["data"]["diff"]["content_comparison"]["scope"] = "cross_backend"
    else:
        raw["data"]["diff"]["content_comparison"]["changed"] = []

    assert not v6.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=raw,
    ).passed


def test_v6_rejects_schema_that_restores_multiple_loci_or_outcome_scoring() -> None:
    manifest = copy.deepcopy(v6.load_manifest())
    manifest["answer_schema"]["top_level_fields"][1] = "review_loci"

    with pytest.raises(v6.V6ContractError, match="answer fields"):
        v6.validate_manifest(manifest)

    manifest = copy.deepcopy(v6.load_manifest())
    manifest["answer_schema"]["scored_model_fields"].append("tool_calls")

    with pytest.raises(v6.V6ContractError, match="answer fields"):
        v6.validate_manifest(manifest)
