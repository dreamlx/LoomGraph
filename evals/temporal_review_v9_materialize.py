"""Materialize an isolated source-only checkout for one V9 review cell."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from evals.temporal_review_v9_fixtures import (  # noqa: E402
    Contract,
    V9ContractError,
    contract,
    load_manifest,
)


class V9MaterializationError(RuntimeError):
    """A frozen V9 source checkout could not be created safely."""


@dataclass(frozen=True)
class MaterializedTemporalReviewV9Fixture:
    task_id: str
    path: Path
    contract: Contract


def _git(path: Path | None, *args: str) -> str:
    command = ["git", *(["-C", str(path)] if path is not None else []), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise V9MaterializationError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _has_commit(path: Path, sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(path), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _ensure_history(destination: Path, source: Path, item: Contract) -> None:
    missing = [
        item.refs[side]["commit_sha"]
        for side in ("base", "head")
        if not _has_commit(destination, item.refs[side]["commit_sha"])
    ]
    if missing:
        try:
            origin = _git(source, "remote", "get-url", "origin")
        except V9MaterializationError as exc:
            raise V9MaterializationError(
                "frozen V9 commits are absent and origin is unavailable"
            ) from exc
        _git(destination, "fetch", "--no-tags", origin, *missing)
    if any(not _has_commit(destination, sha) for sha in missing):
        raise V9MaterializationError("could not fetch all frozen V9 commits")


def materialize_temporal_review_v9_fixture(
    task_id: str, destination: Path, *, source_repository: Path
) -> MaterializedTemporalReviewV9Fixture:
    """Create a detached sparse source checkout without oracle-bearing files."""
    item = contract(task_id)
    destination, source_repository = destination.resolve(), source_repository.resolve()
    if destination.exists() or not (source_repository / ".git").exists():
        raise V9MaterializationError(
            "destination exists or source_repository is not a Git checkout"
        )
    _git(None, "clone", "--no-local", "--no-checkout", str(source_repository), str(destination))
    _ensure_history(destination, source_repository, item)
    _git(destination, "sparse-checkout", "init", "--no-cone")
    _git(destination, "sparse-checkout", "set", "--no-cone", "/src/", "/.codeindex.yaml")
    _git(destination, "checkout", "--quiet", "--detach", item.refs["head"]["commit_sha"])
    _git(destination, "tag", "-f", item.base_ref, item.refs["base"]["commit_sha"])
    _git(destination, "tag", "-f", item.head_ref, item.refs["head"]["commit_sha"])
    if (
        _git(destination, "status", "--porcelain", "--untracked-files=all")
        or _git(destination, "rev-parse", "--abbrev-ref", "HEAD") != "HEAD"
        or _git(destination, "rev-parse", "HEAD") != item.refs["head"]["commit_sha"]
        or any(
            _git(destination, "rev-parse", f"{item.refs[side]['alias']}^{{commit}}")
            != item.refs[side]["commit_sha"]
            for side in ("base", "head")
        )
    ):
        raise V9MaterializationError("materialized V9 checkout is not clean at frozen head")
    exclusions = load_manifest().get("fixture_exclusion_globs")
    if not isinstance(exclusions, list) or any(
        not isinstance(value, str) or (destination / value.removesuffix("/**")).exists()
        for value in exclusions
    ):
        raise V9MaterializationError("oracle-bearing path is visible or V9 exclusions are invalid")
    return MaterializedTemporalReviewV9Fixture(task_id, destination, item)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-repository", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        fixture = materialize_temporal_review_v9_fixture(
            args.task_id, args.destination, source_repository=args.source_repository
        )
    except (V9ContractError, V9MaterializationError) as exc:
        parser.error(str(exc))
    print(json.dumps({"task_id": fixture.task_id, "path": str(fixture.path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
