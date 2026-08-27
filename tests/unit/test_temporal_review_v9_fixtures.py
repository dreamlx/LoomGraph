"""Contract tests for the independently preregistered V9 cohort."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from evals import temporal_review_v9_fixtures as v9


def _source_root(tmp_path: Path) -> Path:
    ingest = tmp_path / "src/loomgraph/core/graph_export_ingest.py"
    risk = tmp_path / "src/loomgraph/core/impact/risk.py"
    ingest.parent.mkdir(parents=True, exist_ok=True)
    risk.parent.mkdir(parents=True, exist_ok=True)
    ingest.write_text("async def persist_resolved_ratio():\n    return None\n", encoding="utf-8")
    risk.write_text("class RiskAssessor:\n    def assess(self):\n        return None\n", encoding="utf-8")
    return tmp_path


def _raw(task_id: str) -> dict[str, object]:
    item = v9.contract(task_id)
    locus = item.oracle["required_review_locus"]
    return {
        "success": True,
        "data": {
            "base": {"ref": item.base_ref, "sha": item.refs["base"]["commit_sha"], "workspace": "base", "provisioned": "created"},
            "head": {"ref": item.head_ref, "sha": item.refs["head"]["commit_sha"], "workspace": "head", "provisioned": "reused"},
            "diff": {"content_comparison": {"version": 1, "scope": "same_backend_only", "status": "available", "reason": None, "base_backend": "codeindex", "head_backend": "codeindex", "changed": [{"source_id": f"{locus['path']}:1", "name": f"src.loomgraph.{locus['qualname']}"}]}},
        },
    }


def _answer(task_id: str, condition: str) -> dict[str, object]:
    item = v9.contract(task_id)
    locus = item.oracle["required_review_locus"]
    return {
        "decision": {"boundary": item.oracle["boundary"][condition], "rationale": "Comparison boundary is separate from adapter-owned raw evidence."},
        "review_locus": {"path": locus["path"], "qualname": locus["qualname"], "rationale": "Review this identity."},
    }


def test_v9_manifest_declares_independent_flash_literal_identity_and_calibration_closure() -> None:
    manifest = v9.load_manifest()

    assert manifest["schema_version"] == 9
    assert manifest["runtime_identity"]["requested_model_literal"] == "glm-5.3-flash"
    assert manifest["cohort_lineage"]["predecessor_evidence"] == "archive_only_not_rerun_rescored_or_pooled"
    assert manifest["selection_preflight_sha256"] == v9.selection_preflight_sha256()
    assert set(manifest["runtime_identity"]["required_persisted_fields"]) == v9._REQUIRED_IDENTITY_FIELDS
    assert manifest["runtime_identity"]["model_categories_valid"] is True
    assert manifest["runtime_identity"]["identity_mode"] == "runtime-specific-only"
    assert manifest["runtime_identity"]["assistant_attribution"] == "canonical_must_equal_requested_model_literal"
    assert manifest["runtime_identity"]["raw_categories"] == "all_nonempty_exact_strings"
    assert manifest["calibration"] == {
        "protocol": v9.CALIBRATION_PROTOCOL,
        "required_before_pilot": True,
        "mode": "voluntary",
        "scored": False,
        "target_manifest_access": "forbidden",
        "solution_or_gold_patch_access": "forbidden",
        "prompt": "no_target_runtime_calibration_only",
        "command_surface": "same_claude_orientation_command_as_pilot_except_no_target_prompt",
        "tool_surface": {"baseline": [], "treatment": ["loomgraph_branch_diff"]},
        "fixed_max_budget_usd": "0.50",
        "command_surface_fingerprint": {
            "algorithm": "sha256_canonical_json",
            "payload": "normalized_outer_and_inner_claude_commands",
            "comparison": "exact_per_condition_across_calibration_replicates_and_pilot_cells",
            "normalization": {
                "outer_values": ["--source-dir", "--instruction-file", "--output-dir", "--task-id"],
                "outer_markers": ["--temporal-review-v9-calibration", "--temporal-review-v9-contract"],
                "inner_values": ["terminal_instruction"],
                "mcp_storage_value": "LOOMGRAPH_STORAGE__DB_PATH",
            },
        },
        "content_integrity": {
            "source_path": "calibration-source/src/calibration.py",
            "source_sha256": "4ecef8c92de9e16713cff66da3f5e80c72c05097978984520578084824779490",
            "instruction_path": "calibration-instruction.md",
            "instruction_sha256": "d3fdd39f6d6168253a56155fe22d92a234b084ff5d62f8b19e01ed547d712191",
            "no_target_leakage_proof": "casefolded_source_and_instruction_forbidden_token_scan",
            "forbidden_casefolded_terms": ["manifest", "oracle", "target", "solution", "gold", "v9-resolution", "v9-sparse"],
        },
        "treatment_environment": {
            "allowed_keys": ["LOOMGRAPH_MCP_ALLOWED_TOOLS", "LOOMGRAPH_STORAGE__DB_PATH"],
            "LOOMGRAPH_MCP_ALLOWED_TOOLS": "loomgraph_branch_diff",
            "additional_keys": "forbidden",
        },
        "conditions": ["baseline", "treatment"],
        "replicates": [1, 2],
        "execution_order": [
            {"replicate": 1, "condition": "baseline"},
            {"replicate": 1, "condition": "treatment"},
            {"replicate": 2, "condition": "treatment"},
            {"replicate": 2, "condition": "baseline"},
        ],
        "identity_comparison": "all_three_category_canonical_sets_must_agree",
        "raw_occurrences": "retain_and_rebuild_from_each_stream_not_cross_run_order_compared",
    }
    for task_id in v9.TASK_IDS:
        instruction = v9.load_instruction(task_id)
        assert '"review_loci"' not in instruction
        assert '"review_locus"' in instruction
        assert "只选择一个主要位置" in instruction
        assert v9.contract(task_id).refs["head"]["commit_sha"] not in instruction


def test_v9_selection_artifacts_are_fresh_and_reject_prior_hashes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = v9.load_manifest()
    hashes = {artifact["raw_sha256"] for artifact in json.loads(v9.SELECTION_PREFLIGHT_PATH.read_text(encoding="utf-8"))["artifacts"]}
    assert hashes.isdisjoint(v9._PRIOR_SELECTION_RAW_SHA256)

    preflight = json.loads(v9.SELECTION_PREFLIGHT_PATH.read_text(encoding="utf-8"))
    preflight["artifacts"][0]["raw_sha256"] = next(iter(v9._PRIOR_SELECTION_RAW_SHA256))
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(preflight), encoding="utf-8")
    monkeypatch.setattr(v9, "SELECTION_PREFLIGHT_PATH", path)
    with pytest.raises(v9.V9ContractError, match="artifact metadata"):
        v9.selection_preflight_sha256(manifest["tasks"])


@pytest.mark.parametrize("task_id", v9.TASK_IDS)
def test_v9_accepts_one_ast_identity_and_raw_comparison_trust(task_id: str, tmp_path: Path) -> None:
    assert v9.parse_raw_response(task_id, _raw(task_id))["valid"] is True
    assert v9.evaluate_answer(task_id, _answer(task_id, "treatment"), condition="treatment", source_root=_source_root(tmp_path), raw_response=_raw(task_id)).passed


def test_v9_rejects_sha_instead_of_runtime_ref_alias() -> None:
    task_id = v9.TASK_IDS[0]
    raw = _raw(task_id)
    raw["data"]["base"]["ref"] = v9.contract(task_id).refs["base"]["commit_sha"]  # type: ignore[index]
    assert v9.parse_raw_response(task_id, raw) == {"valid": False, "reason": "base_ref_or_sha_mismatch"}


def test_v9_rejects_extra_or_nonresolving_review_locus(tmp_path: Path) -> None:
    task_id = v9.TASK_IDS[0]
    answer = _answer(task_id, "treatment")
    answer["review_loci"] = []
    assert not v9.evaluate_answer(task_id, answer, condition="treatment", source_root=_source_root(tmp_path), raw_response=_raw(task_id)).passed

    answer = _answer(task_id, "treatment")
    answer["review_locus"]["qualname"] = "not_real"  # type: ignore[index]
    outcome = v9.evaluate_answer(task_id, answer, condition="treatment", source_root=_source_root(tmp_path), raw_response=_raw(task_id))
    assert not outcome.passed
    assert any("frozen head AST" in failure for failure in outcome.failures)


@pytest.mark.parametrize("mutation", ["sha", "backend", "l2", "missing_raw_support"])
def test_v9_rejects_raw_ref_backend_l2_or_identity_mismatch(mutation: str, tmp_path: Path) -> None:
    task_id = v9.TASK_IDS[1]
    raw = _raw(task_id)
    content = raw["data"]["diff"]["content_comparison"]  # type: ignore[index]
    if mutation == "sha":
        raw["data"]["head"]["sha"] = "0" * 40  # type: ignore[index]
    elif mutation == "backend":
        content["head_backend"] = "codegraph"
    elif mutation == "l2":
        content["scope"] = "cross_backend"
    else:
        content["changed"] = []
    assert not v9.evaluate_answer(task_id, _answer(task_id, "treatment"), condition="treatment", source_root=_source_root(tmp_path), raw_response=raw).passed


def test_v9_rejects_alias_literal_or_identity_closure_drift() -> None:
    manifest = copy.deepcopy(v9.load_manifest())
    manifest["runtime_identity"]["requested_model_literal"] = "sonnet"
    with pytest.raises(v9.V9ContractError, match="model-category"):
        v9.validate_manifest(manifest)

    manifest = copy.deepcopy(v9.load_manifest())
    manifest["runtime_identity"]["identity_mode"] = "model-specific"
    with pytest.raises(v9.V9ContractError, match="model-category"):
        v9.validate_manifest(manifest)

    manifest = copy.deepcopy(v9.load_manifest())
    manifest["calibration"]["scored"] = True
    with pytest.raises(v9.V9ContractError, match="calibration"):
        v9.validate_manifest(manifest)

    manifest = copy.deepcopy(v9.load_manifest())
    manifest["calibration"]["target_manifest_access"] = "allowed"
    with pytest.raises(v9.V9ContractError, match="calibration"):
        v9.validate_manifest(manifest)

    manifest = copy.deepcopy(v9.load_manifest())
    manifest["calibration"]["fixed_max_budget_usd"] = "0.05"
    with pytest.raises(v9.V9ContractError, match="calibration"):
        v9.validate_manifest(manifest)

    manifest = copy.deepcopy(v9.load_manifest())
    manifest["calibration"]["treatment_environment"]["additional_keys"] = "allowed"
    with pytest.raises(v9.V9ContractError, match="calibration"):
        v9.validate_manifest(manifest)

    manifest = copy.deepcopy(v9.load_manifest())
    manifest["runtime_identity"]["model_categories_valid"] = False
    with pytest.raises(v9.V9ContractError, match="model-category"):
        v9.validate_manifest(manifest)
