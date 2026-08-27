"""CLI contract tests for the read-only orientation command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from loomgraph.cli import _branch_diff, _indexing
from loomgraph.cli.main import main
from loomgraph.storage import factory


def test_orient_returns_light_json_for_cross_file_task(monkeypatch) -> None:
    monkeypatch.setattr(
        "loomgraph.cli._orientation.check_codeindex", lambda: {"installed": True}
    )

    result = CliRunner().invoke(main, ["orient", "--task-kind", "cross-file"])

    assert result.exit_code == 0
    response = json.loads(result.stdout)
    assert response["success"] is True
    assert response["data"]["recommended_path"] == "light"
    assert response["data"]["availability"] == "conditional"
    assert response["data"]["policy"] == "balanced"


def test_orient_temporal_review_reports_unavailable_when_ref_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "loomgraph.cli._orientation.check_codeindex", lambda: {"installed": True}
    )

    result = CliRunner().invoke(main, ["orient", "--task-kind", "temporal-review"])

    assert result.exit_code == 0
    response = json.loads(result.stdout)
    assert response["success"] is True
    assert response["data"]["availability"] == "unavailable"
    assert response["data"]["fallback"]["reason"] == "comparison_unavailable"


def test_orient_checks_temporal_refs_without_creating_files(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "loomgraph.cli._orientation.check_codeindex", lambda: {"installed": True}
    )
    monkeypatch.setattr("loomgraph.cli._orientation.is_git_repository", lambda _: True)
    monkeypatch.setattr(
        "loomgraph.cli._orientation.resolve_ref", lambda _, ref: f"sha-for-{ref}"
    )
    before = sorted(path.name for path in tmp_path.iterdir())

    with monkeypatch.context() as context:
        context.chdir(tmp_path)
        result = CliRunner().invoke(
            main,
            [
                "orient",
                "--task-kind",
                "temporal-review",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
            ],
        )

    assert result.exit_code == 0
    response = json.loads(result.stdout)
    assert response["data"]["recommended_path"] == "temporal-review"
    assert response["data"]["availability"] == "conditional"
    assert response["data"]["comparison_request"] == {
        "base_ref": "main",
        "base_sha": "sha-for-main",
        "head_ref": "feature",
        "head_sha": "sha-for-feature",
        "execution_constraint": (
            "use resolved SHA values, or verify the branch-diff response SHA values match"
        ),
    }
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_orient_never_provisions_snapshots_indexes_or_storage(monkeypatch, tmp_path: Path) -> None:
    def must_not_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("orient must remain read-only")

    monkeypatch.setattr(
        "loomgraph.cli._orientation.check_codeindex", lambda: {"installed": True}
    )
    monkeypatch.setattr("loomgraph.cli._orientation.is_git_repository", lambda _: True)
    monkeypatch.setattr(
        "loomgraph.cli._orientation.resolve_ref", lambda _, ref: f"sha-for-{ref}"
    )
    monkeypatch.setattr(_branch_diff, "_provision_ref", must_not_run)
    monkeypatch.setattr(_indexing, "_run_export", must_not_run)
    monkeypatch.setattr(factory, "create_graph_store", must_not_run)

    with monkeypatch.context() as context:
        context.chdir(tmp_path)
        result = CliRunner().invoke(
            main,
            [
                "orient",
                "--task-kind",
                "temporal-review",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
            ],
        )

    assert result.exit_code == 0
