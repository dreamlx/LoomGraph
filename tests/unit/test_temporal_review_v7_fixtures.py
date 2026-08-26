"""Contract tests for the independently preregistered v7 cohort."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from evals import temporal_review_v7_fixtures as v7


def _source_root(tmp_path: Path) -> Path:
    analyzer = tmp_path / "src/loomgraph/core/impact/analyzer.py"
    git = tmp_path / "src/loomgraph/core/git.py"
    analyzer.parent.mkdir(parents=True, exist_ok=True)
    analyzer.write_text(
        "class ImpactAnalyzer:\n    async def _find_callers(self):\n        return []\n",
        encoding="utf-8",
    )
    git.write_text("def get_changed_files():\n    return []\n", encoding="utf-8")
    return tmp_path


def _raw(task_id: str) -> dict[str, Any]:
    item = v7.contract(task_id)
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
    item = v7.contract(task_id)
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


def test_v7_manifest_declares_independent_archive_only_v6_lineage() -> None:
    manifest = v7.load_manifest()

    assert manifest["schema_version"] == 7
    assert manifest["manifest_id"] == "loomgraph-temporal-review-v7-primary-navigation-evidence"
    assert manifest["cohort_lineage"] == {
        "cohort_id": "temporal-review-v7",
        "independent_from": "loomgraph-temporal-review-v6-primary-navigation-evidence",
        "source_comparisons": "same_frozen_history_independent_same-source-contrast",
        "predecessor_evidence": "archive_only_not_rerun_rescored_or_pooled",
    }
    assert manifest["selection_preflight_sha256"] == v7.selection_preflight_sha256()
    assert manifest["answer_schema"]["scored_model_fields"] == [
        "decision.boundary",
        "review_locus.path",
        "review_locus.qualname",
    ]
    for task_id in v7.TASK_IDS:
        instruction = v7.load_instruction(task_id)
        assert '"review_loci"' not in instruction
        assert '"review_locus"' in instruction
        assert "只选择一个主要位置" in instruction
        assert "不要列替代项" in instruction
        assert v7.contract(task_id).refs["head"]["commit_sha"] not in instruction


def test_v7_selection_artifacts_are_fresh_and_not_prior_cohort_bytes() -> None:
    preflight = v7.load_manifest()
    hashes = {
        artifact["raw_sha256"]
        for artifact in json.loads(
            v7.SELECTION_PREFLIGHT_PATH.read_text(encoding="utf-8")
        )["artifacts"]
    }

    assert hashes.isdisjoint(v7._PRIOR_SELECTION_RAW_SHA256)
    assert preflight["selection_preflight_sha256"] == v7.selection_preflight_sha256()


@pytest.mark.parametrize("task_id", v7.TASK_IDS)
def test_v7_accepts_one_ast_identity_and_raw_comparison_trust(task_id: str, tmp_path: Path) -> None:
    assert v7.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed


def test_v7_rejects_extra_or_nonresolving_review_locus(tmp_path: Path) -> None:
    task_id = v7.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["review_loci"] = []
    assert not v7.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed

    answer = _answer(task_id, "treatment")
    answer["review_locus"]["qualname"] = "ImpactAnalyzer.not_real"
    outcome = v7.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )
    assert not outcome.passed
    assert any("frozen head AST" in failure for failure in outcome.failures)


@pytest.mark.parametrize("mutation", ["sha", "backend", "l2", "missing_raw_support"])
def test_v7_rejects_raw_ref_backend_l2_or_identity_mismatch(mutation: str, tmp_path: Path) -> None:
    task_id = v7.TASK_IDS[1]
    raw = _raw(task_id)
    if mutation == "sha":
        raw["data"]["head"]["sha"] = "0" * 40
    elif mutation == "backend":
        raw["data"]["diff"]["content_comparison"]["head_backend"] = "codegraph"
    elif mutation == "l2":
        raw["data"]["diff"]["content_comparison"]["scope"] = "cross_backend"
    else:
        raw["data"]["diff"]["content_comparison"]["changed"] = []
    assert not v7.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=raw,
    ).passed


def test_v7_rejects_manifest_without_v6_archive_only_lineage_or_fresh_selection() -> None:
    manifest = copy.deepcopy(v7.load_manifest())
    manifest["cohort_lineage"]["predecessor_evidence"] = "pooled"
    with pytest.raises(v7.V7ContractError, match="independence"):
        v7.validate_manifest(manifest)

    manifest = copy.deepcopy(v7.load_manifest())
    manifest["selection_preflight_sha256"] = "0" * 64
    with pytest.raises(v7.V7ContractError, match="selection preflight"):
        v7.validate_manifest(manifest)
