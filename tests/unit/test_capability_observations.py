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


def test_runner_writes_real_cold_and_warm_definition_observations(tmp_path) -> None:
    records = run_task("overlap-definition", tmp_path / "run")

    assert [record["phase"] for record in records] == ["cold", "warm"]
    assert all(record["oracle"]["passed"] is True for record in records)
    assert records[0]["operation"]["reindexed"] is True
    assert records[1]["operation"]["reindexed"] is False
    assert records[0]["rg"]["equivalence"] == "equivalent"


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
