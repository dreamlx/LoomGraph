"""Tests for v2 source-only temporal-review checkout materialization."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from evals import temporal_review_v2_materialize as materialize
from evals.temporal_review_v2_materialize import (
    MaterializedTemporalReviewV2Fixture,
    V2MaterializationError,
    materialize_temporal_review_v2_fixture,
)


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def test_materialize_v2_checkout_is_detached_clean_and_source_only(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    destination = tmp_path / "review"

    fixture = materialize_temporal_review_v2_fixture(
        "impact-low-resolution-review",
        destination,
        source_repository=repository,
    )

    assert fixture.path == destination.resolve()
    assert (destination / "src").is_dir()
    assert _git(destination, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert _git(destination, "rev-parse", "HEAD") == fixture.contract.refs["head"]["commit_sha"]
    assert _git(destination, "rev-parse", "review-base^{commit}") == fixture.contract.refs["base"]["commit_sha"]
    assert _git(destination, "rev-parse", "review-head^{commit}") == fixture.contract.refs["head"]["commit_sha"]
    assert _git(destination, "status", "--porcelain", "--untracked-files=all") == ""
    assert not (destination / "CHANGELOG.md").exists()
    assert not (destination / "docs" / "evals").exists()
    assert not (destination / "tests").exists()
    assert not (destination / "evals").exists()


def test_materialize_v2_rejects_existing_destination(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    destination = tmp_path / "existing"
    destination.mkdir()

    with pytest.raises(V2MaterializationError, match="must not already exist"):
        materialize_temporal_review_v2_fixture(
            "impact-low-resolution-review",
            destination,
            source_repository=repository,
        )


def test_materializer_fetches_missing_frozen_history_from_source_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = materialize.contract("impact-low-resolution-review")
    destination = tmp_path / "destination"
    source = tmp_path / "source"
    destination.mkdir()
    source.mkdir()
    calls: list[tuple[Path | None, tuple[str, ...]]] = []
    commit_checks = iter((False, False, True, True))

    def fake_git(path: Path | None, *args: str) -> str:
        calls.append((path, args))
        if path == source and args == ("remote", "get-url", "origin"):
            return "https://example.invalid/loomgraph.git"
        return ""

    monkeypatch.setattr(materialize, "_git", fake_git)
    monkeypatch.setattr(materialize, "_has_commit", lambda _path, _sha: next(commit_checks))

    materialize._ensure_frozen_history(destination, source, item)

    assert (destination, (
        "fetch",
        "--no-tags",
        "https://example.invalid/loomgraph.git",
        item.refs["base"]["commit_sha"],
        item.refs["head"]["commit_sha"],
    )) in calls


def test_materializer_reports_missing_history_without_source_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = materialize.contract("impact-low-resolution-review")
    destination = tmp_path / "destination"
    source = tmp_path / "source"
    destination.mkdir()
    source.mkdir()

    monkeypatch.setattr(materialize, "_has_commit", lambda _path, _sha: False)

    def no_origin(_path: Path | None, *_args: str) -> str:
        raise V2MaterializationError("origin unavailable")

    monkeypatch.setattr(materialize, "_git", no_origin)

    with pytest.raises(V2MaterializationError, match="no readable origin"):
        materialize._ensure_frozen_history(destination, source, item)


def test_direct_cli_serializes_public_materialization_record(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    item = materialize.contract("impact-low-resolution-review")
    fixture = MaterializedTemporalReviewV2Fixture("impact-low-resolution-review", tmp_path / "review", item)
    monkeypatch.setattr(materialize, "materialize_temporal_review_v2_fixture", lambda *_args, **_kwargs: fixture)

    assert materialize.main([
        "--task-id",
        fixture.task_id,
        "--destination",
        str(fixture.path),
        "--source-repository",
        str(tmp_path),
    ]) == 0

    record = json.loads(capsys.readouterr().out)
    assert record == {
        "backend": "codeindex",
        "base": {
            "ref": "review-base",
            "sha": item.refs["base"]["commit_sha"],
        },
        "head": {
            "ref": "review-head",
            "sha": item.refs["head"]["commit_sha"],
        },
        "path": str(fixture.path),
        "source_only": True,
        "task_id": fixture.task_id,
    }


def test_direct_file_entrypoint_has_help() -> None:
    script = Path(__file__).resolve().parents[2] / "evals" / "temporal_review_v2_materialize.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        check=True,
        text=True,
    )
    assert "--task-id" in result.stdout
