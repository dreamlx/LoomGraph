"""Contract tests for the independently preregistered v8 cohort."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from evals import temporal_review_v8_fixtures as v8


def _source_root(tmp_path: Path) -> Path:
    ingest = tmp_path / "src/loomgraph/core/graph_export_ingest.py"
    risk = tmp_path / "src/loomgraph/core/impact/risk.py"
    ingest.parent.mkdir(parents=True, exist_ok=True)
    risk.parent.mkdir(parents=True, exist_ok=True)
    ingest.write_text("async def persist_resolved_ratio():\n    return None\n", encoding="utf-8")
    risk.write_text("class RiskAssessor:\n    def assess(self):\n        return None\n", encoding="utf-8")
    return tmp_path


def _raw(task_id: str) -> dict[str, Any]:
    item = v8.contract(task_id)
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
    item = v8.contract(task_id)
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


def test_v8_manifest_declares_independent_archive_only_lineage_and_identity_closure() -> None:
    manifest = v8.load_manifest()

    assert manifest["schema_version"] == 8
    assert manifest["cohort_lineage"] == {
        "cohort_id": "temporal-review-v8",
        "independent_from": "loomgraph-temporal-review-v7-primary-navigation-evidence",
        "source_comparisons": "same_frozen_history_independent_same-source-contrast",
        "predecessor_evidence": "archive_only_not_rerun_rescored_or_pooled",
    }
    assert manifest["selection_preflight_sha256"] == v8.selection_preflight_sha256()
    assert set(manifest["runtime_identity"]["required_persisted_fields"]) == v8._REQUIRED_IDENTITY_FIELDS
    assert manifest["runtime_identity"]["model_categories_valid"] is True
    for task_id in v8.TASK_IDS:
        instruction = v8.load_instruction(task_id)
        assert '"review_loci"' not in instruction
        assert '"review_locus"' in instruction
        assert "只选择一个主要位置" in instruction
        assert v8.contract(task_id).refs["head"]["commit_sha"] not in instruction


def test_v8_selection_artifacts_are_fresh_and_reject_prior_hashes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = v8.load_manifest()
    hashes = {
        artifact["raw_sha256"]
        for artifact in json.loads(v8.SELECTION_PREFLIGHT_PATH.read_text(encoding="utf-8"))["artifacts"]
    }
    assert hashes.isdisjoint(v8._PRIOR_SELECTION_RAW_SHA256)

    preflight = json.loads(v8.SELECTION_PREFLIGHT_PATH.read_text(encoding="utf-8"))
    preflight["artifacts"][0]["raw_sha256"] = next(iter(v8._PRIOR_SELECTION_RAW_SHA256))
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(preflight), encoding="utf-8")
    monkeypatch.setattr(v8, "SELECTION_PREFLIGHT_PATH", path)
    with pytest.raises(v8.V8ContractError, match="artifact metadata"):
        v8.selection_preflight_sha256(manifest["tasks"])


@pytest.mark.parametrize("task_id", v8.TASK_IDS)
def test_v8_accepts_one_ast_identity_and_raw_comparison_trust(task_id: str, tmp_path: Path) -> None:
    assert v8.parse_raw_response(task_id, _raw(task_id))["valid"] is True
    assert v8.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed


def test_v8_rejects_sha_instead_of_runtime_ref_alias() -> None:
    task_id = v8.TASK_IDS[0]
    raw = _raw(task_id)
    raw["data"]["base"]["ref"] = v8.contract(task_id).refs["base"]["commit_sha"]

    assert v8.parse_raw_response(task_id, raw) == {
        "valid": False,
        "reason": "base_ref_or_sha_mismatch",
    }


def test_v8_rejects_extra_or_nonresolving_review_locus(tmp_path: Path) -> None:
    task_id = v8.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["review_loci"] = []
    assert not v8.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    ).passed

    answer = _answer(task_id, "treatment")
    answer["review_locus"]["qualname"] = "not_real"
    outcome = v8.evaluate_answer(
        task_id,
        answer,
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=_raw(task_id),
    )
    assert not outcome.passed
    assert any("frozen head AST" in failure for failure in outcome.failures)


@pytest.mark.parametrize("mutation", ["sha", "backend", "l2", "missing_raw_support"])
def test_v8_rejects_raw_ref_backend_l2_or_identity_mismatch(mutation: str, tmp_path: Path) -> None:
    task_id = v8.TASK_IDS[1]
    raw = _raw(task_id)
    if mutation == "sha":
        raw["data"]["head"]["sha"] = "0" * 40
    elif mutation == "backend":
        raw["data"]["diff"]["content_comparison"]["head_backend"] = "codegraph"
    elif mutation == "l2":
        raw["data"]["diff"]["content_comparison"]["scope"] = "cross_backend"
    else:
        raw["data"]["diff"]["content_comparison"]["changed"] = []
    assert not v8.evaluate_answer(
        task_id,
        _answer(task_id, "treatment"),
        condition="treatment",
        source_root=_source_root(tmp_path),
        raw_response=raw,
    ).passed


def test_v8_rejects_manifest_without_archive_only_lineage_or_model_categories_closure() -> None:
    manifest = copy.deepcopy(v8.load_manifest())
    manifest["cohort_lineage"]["predecessor_evidence"] = "pooled"
    with pytest.raises(v8.V8ContractError, match="independence"):
        v8.validate_manifest(manifest)

    manifest = copy.deepcopy(v8.load_manifest())
    manifest["runtime_identity"]["model_categories_valid"] = False
    with pytest.raises(v8.V8ContractError, match="model-category"):
        v8.validate_manifest(manifest)
