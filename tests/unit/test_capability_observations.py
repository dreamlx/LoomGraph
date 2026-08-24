"""Guards for raw structural-capability observation records (#206)."""

from __future__ import annotations

import json

import pytest
from evals.capability_fixtures import materialize_fixture
from evals.run_capability_observations import (
    ObservationValidationError,
    run_task,
    validate_observation,
    write_observations,
)


def _record(phase: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "fixture": {"id": "python-core", "sha": "a" * 64, "git_ref": "HEAD"},
        "task_id": "overlap-definition",
        "phase": phase,
        "toolchain": {
            "loomgraph_version": "0.22.0",
            "codeindex_version": "0.40.1",
            "parser_versions": {"python": "0.23.0"},
            "backend": "codeindex",
        },
        "operation": {
            "index_command": ["loomgraph", "index", "."],
            "query_command": ["loomgraph", "find", "AuthService"],
            "index_clear_wall_ms": 1 if phase == "cold" else None,
            "query_wall_ms": 1,
            "reindexed": phase == "cold",
            "exit_code": 0,
            "raw_stdout": '{"success": true}',
            "raw_stderr": "",
        },
        "answer": {"status": "complete"},
        "trust": {"workspace": "capability-a1", "partial": False},
        "oracle": {"passed": True, "failures": []},
        "rg": {"equivalence": "equivalent", "command": ["rg", "AuthService"]},
    }


def test_validates_independent_cold_and_warm_records() -> None:
    cold = _record("cold")
    warm = _record("warm")

    validate_observation(cold)
    validate_observation(warm)


def test_rejects_warm_record_that_reindexed() -> None:
    warm = _record("warm")
    operation = warm["operation"]
    assert isinstance(operation, dict)
    operation["reindexed"] = True

    with pytest.raises(ObservationValidationError, match="warm.*reindexed"):
        validate_observation(warm)


def test_rejects_a_claim_without_raw_answer_or_trust() -> None:
    cold = _record("cold")
    operation = cold["operation"]
    assert isinstance(operation, dict)
    operation["raw_stdout"] = ""

    with pytest.raises(ObservationValidationError, match="raw_stdout"):
        validate_observation(cold)


def test_materialized_fixture_has_stable_refs_and_content_hash(tmp_path) -> None:
    fixture = materialize_fixture("python-history", tmp_path / "fixture")

    assert fixture.sha == materialize_fixture("python-history", tmp_path / "other").sha
    assert fixture.refs == {"base", "head"}
    assert (fixture.path / "app" / "auth.py").is_file()


def test_topology_debt_fixture_has_a_deterministic_hub_and_history(tmp_path) -> None:
    fixture = materialize_fixture("topology-debt-git", tmp_path / "fixture")

    hub = (fixture.path / "app" / "hub.py").read_text()
    assert "def HubFunc" in hub
    assert "revision = 12" in hub


def test_typescript_adversary_fixture_contains_a_real_path_alias(tmp_path) -> None:
    fixture = materialize_fixture("ts-barrel-alias", tmp_path / "fixture")

    assert '"@models/*": ["src/*"]' in (fixture.path / "tsconfig.json").read_text()
    assert 'from "@models/models"' in (fixture.path / "src" / "alias_consumer.ts").read_text()


def test_runner_writes_real_cold_and_warm_definition_observations(tmp_path) -> None:
    records = run_task("overlap-definition", tmp_path / "run")

    assert [record["phase"] for record in records] == ["cold", "warm"]
    assert all(record["oracle"]["passed"] is True for record in records)
    assert records[0]["operation"]["reindexed"] is True
    assert records[1]["operation"]["reindexed"] is False
    assert records[0]["rg"]["equivalence"] == "equivalent"


def test_runner_requires_the_fixed_git_hotspot_oracle(tmp_path) -> None:
    records = run_task("structural-topology-debt-git", tmp_path / "debt")

    for record in records:
        data = json.loads(record["operation"]["raw_stdout"])["data"]
        assert any(
            issue.get("category") == "critical_hotspot"
            and issue.get("severity") == "P0"
            and issue.get("entity") == "app/hub.py"
            for issue in data["issues"]
        )
        topology = json.loads(record["supplemental"]["raw_stdout"])["data"]
        assert len(topology["callers"]) == 8
        assert record["supplemental"]["oracle"]["passed"] is True


def test_runner_requires_the_fixed_multihop_impact_chain(tmp_path) -> None:
    records = run_task("structural-multihop-impact", tmp_path / "impact")

    for record in records:
        data = json.loads(record["operation"]["raw_stdout"])["data"]["impact_analysis"]
        assert "app.handlers.handle_login" in {
            caller["name"] for caller in data["direct_callers"]
        }
        assert "app.api.dispatch" in {
            caller["name"] for caller in data["indirect_callers"]
        }


@pytest.mark.parametrize(
    "task_id",
    [
        "structural-multihop-impact",
        "structural-topology-debt-git",
        "trust-annotated-factory-receiver",
    ],
)
def test_runner_records_the_resolution_split_for_trust_sensitive_tasks(tmp_path, task_id) -> None:
    records = run_task(task_id, tmp_path / task_id)

    for record in records:
        resolution = record["trust"]["resolution"]
        assert set(resolution) >= {
            "resolved_ratio",
            "internal_unresolved_ratio",
            "external_unresolved_ratio",
        }


def test_runner_exercises_the_tsconfig_path_alias(tmp_path) -> None:
    records = run_task("trust-alias-barrel", tmp_path / "alias")

    for record in records:
        assert "src.alias_consumer" in record["operation"]["query_command"]
        assert "src.consumer" in record["supplemental"]["command"]
        assert record["supplemental"]["oracle"]["passed"] is True


def test_branch_diff_records_the_codegraph_variant_without_mislabeling_l2(tmp_path) -> None:
    records = run_task("structural-branch-diff", tmp_path / "branch-diff")

    for record in records:
        comparison = record["comparison"]
        assert comparison["backend"] == "codegraph"
        if comparison["availability"] == "available":
            assert comparison["oracle"]["passed"] is True
            assert record["trust"]["comparison"]["content_comparison_status"] == "unavailable"
        else:
            assert comparison["availability"] == "infrastructure_unavailable"
            assert "infrastructure_error" in comparison


@pytest.mark.parametrize(
    "task_id",
    [
        "overlap-direct-static-call",
        "structural-multihop-impact",
        "structural-typed-deps",
        "structural-branch-diff",
        "structural-topology-debt-git",
        "trust-annotated-factory-receiver",
        "trust-alias-barrel",
    ],
)
def test_runner_writes_real_observations_for_shared_python_tasks(tmp_path, task_id) -> None:
    records = run_task(task_id, tmp_path / task_id)

    assert [record["phase"] for record in records] == ["cold", "warm"]
    assert all(record["oracle"]["passed"] is True for record in records)


def test_writer_emits_one_raw_json_row_per_observation(tmp_path) -> None:
    output = tmp_path / "records.jsonl"
    records = [_record("cold"), _record("warm")]

    write_observations(records, output)

    assert [line["phase"] for line in map(json.loads, output.read_text().splitlines())] == [
        "cold", "warm"
    ]
