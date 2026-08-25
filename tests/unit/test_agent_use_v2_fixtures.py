"""Contract tests for the independent agent-use v2 temporal fixture."""

from __future__ import annotations

import json

import pytest
from evals.agent_use_v2_fixtures import (
    V2_FIXTURE_ID,
    V2_TASK_ID,
    FixtureContractError,
    evaluate_baseline_answer,
    evaluate_finding_answer,
    evaluate_raw_branch_diff_response,
    evaluate_treatment_answer,
    load_v2_fixture_manifest,
    materialize_v2_fixture,
    task_instruction,
    validate_v2_fixture_manifest,
)
from evals.capability_fixtures import _git


def _finding(*, evidence: str = "base to head evidence") -> dict[str, object]:
    return {
        "kind": "broken_chain",
        "src": "app.handlers.keep_legacy",
        "tgt": "app.auth.legacy_token",
        "relation": "CALLS",
        "evidence": evidence,
    }


def _comparison(
    *,
    content_status: str = "available",
    reason: object = None,
) -> dict[str, object]:
    return {
        "base_ref": "base",
        "head_ref": "head",
        "base_backend": "codeindex",
        "head_backend": "codeindex",
        "base_provisioned": "created",
        "head_provisioned": "reused",
        "content_comparison": {"status": content_status, "reason": reason},
    }


def _treatment_answer() -> dict[str, object]:
    return {
        "findings": [_finding()],
        "trust": {"availability": "available", "comparison": _comparison()},
    }


def _baseline_answer() -> dict[str, object]:
    return {
        "findings": [_finding()],
        "trust": {"availability": "unavailable", "comparison": None},
    }


def _raw_response(*, status: str = "available") -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "base": {
                "ref": "base",
                "sha": "11d6876d51425f64ac97ce2a52644c840b629917",
                "workspace": "python-history:base",
                "provisioned": "created",
            },
            "head": {
                "ref": "head",
                "sha": "a270de36ee2af15d13b37fc14395cfae0d3435aa",
                "workspace": "python-history:head",
                "provisioned": "reused",
            },
            "diff": {
                "broken_chains": [
                    {
                        "src": "app.handlers.keep_legacy",
                        "tgt": "app.auth.legacy_token",
                        "keywords": "CALLS",
                    }
                ],
                "content_comparison": {
                    "status": status,
                    "base_backend": "codeindex",
                    "head_backend": "codeindex",
                    "reason": None if status == "available" else "missing_per_entity_content_hash",
                },
            },
        },
    }


def test_manifest_freezes_python_history_refs_content_and_oracle() -> None:
    manifest = load_v2_fixture_manifest()
    validate_v2_fixture_manifest(manifest)

    assert manifest["schema_version"] == 1
    assert manifest["fixture_id"] == V2_FIXTURE_ID == "python-history"
    assert manifest["task"]["id"] == V2_TASK_ID == "python-history-branch-diff-contract"
    assert manifest["content_sha"] == (
        "52a552f4426ed6773b3711f63a8024e382b11eb2b70ff8e15c585763d94e7667"
    )
    assert manifest["refs"] == {
        "base": {
            "tag": "base",
            "commit_sha": "11d6876d51425f64ac97ce2a52644c840b629917",
        },
        "head": {
            "tag": "head",
            "commit_sha": "a270de36ee2af15d13b37fc14395cfae0d3435aa",
        },
    }
    assert manifest["oracle"]["finding"] == {
        "kind": "broken_chain",
        "src": "app.handlers.keep_legacy",
        "tgt": "app.auth.legacy_token",
        "relation": "CALLS",
    }
    assert manifest["oracle"]["content_comparison"] == {
        "status": "available",
        "reason": None,
        "base_backend": "codeindex",
        "head_backend": "codeindex",
    }


def test_materialize_v2_fixture_rechecks_tags_commits_and_content_sha(tmp_path) -> None:
    fixture = materialize_v2_fixture(tmp_path / "fixture")

    assert fixture.fixture_id == "python-history"
    assert fixture.sha == "52a552f4426ed6773b3711f63a8024e382b11eb2b70ff8e15c585763d94e7667"
    assert fixture.refs == {"base", "head"}
    assert _git(fixture.path, "rev-parse", "base") == (
        "11d6876d51425f64ac97ce2a52644c840b629917"
    )
    assert _git(fixture.path, "rev-parse", "head") == (
        "a270de36ee2af15d13b37fc14395cfae0d3435aa"
    )


def test_instruction_only_exposes_task_refs_and_backend() -> None:
    instruction = task_instruction()

    assert "base" in instruction and "head" in instruction and "codeindex" in instruction
    for secret in (
        "app.handlers.keep_legacy",
        "app.auth.legacy_token",
        "broken_chain",
        "content_comparison",
        "fixture-manifest",
        "52a552f4",
    ):
        assert secret not in instruction


def test_finding_oracle_is_independent_and_accepts_only_exact_v2_finding() -> None:
    result = evaluate_finding_answer({"findings": [_finding()]})
    assert result.passed is True
    assert result.failures == ()

    wrong_relation = {"findings": [_finding()]}
    wrong_relation["findings"][0]["relation"] = "REFERENCES"
    result = evaluate_finding_answer(wrong_relation)
    assert result.passed is False
    assert "finding" in " ".join(result.failures)


def test_finding_oracle_rejects_missing_or_extra_findings() -> None:
    assert not evaluate_finding_answer({"findings": []}).passed
    assert not evaluate_finding_answer({"findings": [_finding(), _finding()]}).passed
    assert not evaluate_finding_answer({"findings": [_finding(evidence="")]}).passed
    assert not evaluate_finding_answer({"findings": "not-a-list"}).passed


def test_treatment_oracle_requires_available_comparison_trust() -> None:
    assert evaluate_treatment_answer(_treatment_answer()).passed is True

    unavailable = _treatment_answer()
    unavailable["trust"]["comparison"]["content_comparison"]["status"] = "unavailable"
    assert not evaluate_treatment_answer(unavailable).passed

    wrong_ref = _treatment_answer()
    wrong_ref["trust"]["comparison"]["head_ref"] = "main"
    assert not evaluate_treatment_answer(wrong_ref).passed

    missing_reason = _treatment_answer()
    del missing_reason["trust"]["comparison"]["content_comparison"]["reason"]
    assert not evaluate_treatment_answer(missing_reason).passed


def test_baseline_oracle_requires_unavailable_comparison_without_fabricated_value() -> None:
    assert evaluate_baseline_answer(_baseline_answer()).passed is True

    fabricated = _baseline_answer()
    fabricated["trust"]["comparison"] = _comparison()
    assert not evaluate_baseline_answer(fabricated).passed

    missing = _baseline_answer()
    del missing["trust"]["comparison"]
    assert not evaluate_baseline_answer(missing).passed


def test_raw_oracle_requires_successful_fixed_ref_diff_and_available_l2() -> None:
    assert evaluate_raw_branch_diff_response(_raw_response()).passed is True

    wrong_chain = _raw_response()
    wrong_chain["data"]["diff"]["broken_chains"][0]["tgt"] = "app.auth.validate_token"
    assert not evaluate_raw_branch_diff_response(wrong_chain).passed

    unavailable = _raw_response(status="unavailable")
    assert not evaluate_raw_branch_diff_response(unavailable).passed


@pytest.mark.parametrize(
    "field",
    ["fixture_id", "content_sha", "refs", "oracle"],
)
def test_manifest_validation_rejects_mutated_contract(field: str) -> None:
    manifest = load_v2_fixture_manifest()
    if field == "fixture_id":
        manifest[field] = "other"
    elif field == "content_sha":
        manifest[field] = "0" * 64
    elif field == "refs":
        manifest[field]["head"]["tag"] = "main"
    else:
        manifest[field]["content_comparison"]["status"] = "unavailable"

    with pytest.raises(FixtureContractError):
        validate_v2_fixture_manifest(manifest)


def test_materialize_v2_fixture_fails_loud_if_fixture_drifted(tmp_path, monkeypatch) -> None:
    from evals import agent_use_v2_fixtures as module

    original = module.materialize_fixture

    def drifted(fixture_id, path):
        fixture = original(fixture_id, path)
        (fixture.path / "app" / "auth.py").write_text("drifted\n")
        return fixture

    monkeypatch.setattr(module, "materialize_fixture", drifted)
    with pytest.raises(FixtureContractError, match="content SHA"):
        module.materialize_v2_fixture(tmp_path / "drifted")


def test_raw_oracle_rejects_error_envelope() -> None:
    response = _raw_response()
    response["success"] = False
    response["error"] = {"code": "BRANCH_DIFF_FAILED"}

    result = evaluate_raw_branch_diff_response(response)
    assert result.passed is False
    assert result.failures


def test_manifest_is_valid_json_artifact() -> None:
    manifest = load_v2_fixture_manifest()
    assert json.dumps(manifest, sort_keys=True)
