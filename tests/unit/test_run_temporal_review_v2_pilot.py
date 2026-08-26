"""Tests for the dormant temporal-review v2 pilot driver."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from evals import run_temporal_review_v2_pilot as pilot
from evals.temporal_review_v2_fixtures import contract
from evals.temporal_review_v2_materialize import MaterializedTemporalReviewV2Fixture


def test_condition_order_is_counterbalanced() -> None:
    assert pilot._condition_order(1) == ("baseline", "treatment")
    assert pilot._condition_order(2) == ("treatment", "baseline")


def test_valid_raw_comparison_drives_warm_repeat_even_after_semantic_exclusion(tmp_path: Path, monkeypatch) -> None:
    task_id = "impact-low-resolution-review"
    item = contract(task_id)

    def fake_materialize(task: str, destination: Path, *, source_repository: Path) -> MaterializedTemporalReviewV2Fixture:
        assert task == task_id
        destination.mkdir(parents=True)
        return MaterializedTemporalReviewV2Fixture(task, destination, item)

    warm_environments: list[dict[str, str] | None] = []

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["loomgraph", "branch-diff"]:
            warm_environments.append(env)
            return subprocess.CompletedProcess(command, 0, '{"success": true}', "")
        if "--output-dir" in command:
            output_dir = Path(command[command.index("--output-dir") + 1])
            output_dir.mkdir(parents=True)
            condition = command[command.index("--condition") + 1]
            (output_dir / "orientation.json").write_text(json.dumps({
                "status": "task_review_oracle_failed" if condition == "treatment" else "complete",
                "invalid_reason": "task_specific_oracle_mismatch" if condition == "treatment" else None,
                "semantic_packet": condition == "baseline",
                "trust_observation": {"valid_raw_branch_diff_count": 1 if condition == "treatment" else 0},
            }))
        return subprocess.CompletedProcess(command, 0, "{}", "")

    monkeypatch.setattr(pilot, "materialize_temporal_review_v2_fixture", fake_materialize)
    monkeypatch.setattr(pilot, "_run", fake_run)

    result = pilot.run_pilot(
        source_repository=tmp_path / "source", output_root=tmp_path / "output", task_ids=(task_id,),
        replicates=2, model="sonnet", loomgraph_binary="loomgraph", max_budget_usd="0.50",
    )

    assert result["protocol"] == "temporal-review-v2-pilot"
    assert [record["condition"] for record in result["runs"]] == ["baseline", "treatment", "treatment", "baseline"]
    assert sum("warm_repeat" in record for record in result["runs"]) == 2
    assert all(record["tool_surface"] == pilot.SURFACE for record in result["runs"] if record["condition"] == "treatment")
    assert all(record["source_clean"] is True for record in result["runs"])
    assert all(env is not None and env["LOOMGRAPH_STORAGE__DB_PATH"].endswith("/output/loomgraph-storage/{workspace}.db") for env in warm_environments)
    assert (tmp_path / "output" / "pilot-results.json").is_file()


def test_warm_repeat_requires_retained_raw_evidence() -> None:
    assert pilot._has_valid_raw_comparison(None) is False
    assert pilot._has_valid_raw_comparison({"valid_raw_branch_diff_count": 0}) is False
    assert pilot._has_valid_raw_comparison({"valid_raw_branch_diff_count": 1}) is True
