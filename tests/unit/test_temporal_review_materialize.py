"""Tests for source-only temporal-review checkout materialization."""

from __future__ import annotations

from pathlib import Path

import pytest
from evals import temporal_review_materialize as materialize
from evals.temporal_review_materialize import (
    MaterializationError,
    materialize_temporal_review_fixture,
)


def test_materialize_review_checkout_is_clean_and_hides_oracles(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    destination = tmp_path / "review"

    fixture = materialize_temporal_review_fixture(
        "impact-low-resolution-review",
        destination,
        source_repository=repository,
    )

    assert fixture.path == destination.resolve()
    assert (destination / "src").is_dir()
    assert not (destination / "CHANGELOG.md").exists()
    assert not (destination / "docs" / "evals").exists()
    assert not (destination / "tests").exists()
    assert not (destination / "evals").exists()


def test_materialize_rejects_existing_destination(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    destination = tmp_path / "existing"
    destination.mkdir()

    with pytest.raises(MaterializationError, match="must not already exist"):
        materialize_temporal_review_fixture(
            "impact-low-resolution-review",
            destination,
            source_repository=repository,
        )


def test_materializer_fetches_missing_frozen_history_from_source_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = materialize.load_temporal_review_contract("impact-low-resolution-review")
    destination = tmp_path / "destination"
    source = tmp_path / "source"
    destination.mkdir()
    source.mkdir()
    fetched: list[tuple[Path | None, tuple[str, ...]]] = []
    commit_checks = iter((False, False, True, True))

    def fake_git(path: Path | None, *args: str) -> str:
        fetched.append((path, args))
        if path == source and args == ("remote", "get-url", "origin"):
            return "https://example.invalid/loomgraph.git"
        return ""

    monkeypatch.setattr(materialize, "_git", fake_git)
    monkeypatch.setattr(materialize, "_has_commit", lambda _path, _sha: next(commit_checks))

    materialize._ensure_frozen_history(destination, source, contract)

    assert (destination, ("fetch", "--no-tags", "https://example.invalid/loomgraph.git", *[
        contract.refs["base"]["commit_sha"], contract.refs["head"]["commit_sha"]
    ])) in fetched
