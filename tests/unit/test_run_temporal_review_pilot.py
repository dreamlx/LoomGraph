"""Tests for the temporal-review pilot driver without invoking a model."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from evals import run_temporal_review_pilot as pilot
from evals.temporal_review_fixtures import load_temporal_review_contract
from evals.temporal_review_materialize import MaterializedTemporalReviewFixture


def test_condition_order_is_counterbalanced() -> None:
    assert pilot._condition_order(1) == ("baseline", "treatment")
    assert pilot._condition_order(2) == ("treatment", "baseline")


def test_driver_writes_counterbalanced_auditable_records(tmp_path: Path, monkeypatch) -> None:
    task_id = "impact-low-resolution-review"
    contract = load_temporal_review_contract(task_id)

    def fake_materialize(
        task: str, destination: Path, *, source_repository: Path
    ) -> MaterializedTemporalReviewFixture:
        assert task == task_id
        destination.mkdir(parents=True)
        return MaterializedTemporalReviewFixture(task, destination, contract)

    warm_environments: list[dict[str, str] | None] = []

    def fake_run(
        command: list[str], *, cwd: Path, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["loomgraph", "branch-diff"]:
            warm_environments.append(env)
            raw = {
                "success": True,
                "data": {
                    "base": {"provisioned": "reused"},
                    "head": {"provisioned": "reused"},
                },
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(raw), "")
        return subprocess.CompletedProcess(command, 0, "{}", "")

    monkeypatch.setattr(pilot, "materialize_temporal_review_fixture", fake_materialize)
    monkeypatch.setattr(pilot, "_run", fake_run)

    result = pilot.run_pilot(
        source_repository=tmp_path / "source-repository",
        output_root=tmp_path / "output",
        task_ids=(task_id,),
        replicates=2,
        model="sonnet",
        loomgraph_binary="loomgraph",
        max_budget_usd="0.50",
    )

    assert [record["condition"] for record in result["runs"]] == [
        "baseline",
        "treatment",
        "treatment",
        "baseline",
    ]
    assert all(record["source_clean"] is True for record in result["runs"])
    assert all(record["environment_path"] == str(tmp_path / "output" / "environment.json") for record in result["runs"])
    assert sum("warm_repeat" in record for record in result["runs"]) == 2
    assert all(
        env is not None
        and env["LOOMGRAPH_STORAGE__DB_PATH"]
        == str(tmp_path / "output" / task_id / f"rep-{index:02d}" / "treatment" / "output" / "loomgraph-storage" / "{workspace}.db")
        for index, env in enumerate(warm_environments, start=1)
    )
    environment = json.loads((tmp_path / "output" / "environment.json").read_text())
    assert environment["claude"]["command"] == ["claude", "--version"]
    assert environment["loomgraph"]["command"] == ["loomgraph", "--version"]
    assert (tmp_path / "output" / "pilot-results.json").is_file()
