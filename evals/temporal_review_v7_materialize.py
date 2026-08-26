"""Materialize an isolated source-only checkout for one V7 review cell."""

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

from evals.temporal_review_v7_fixtures import (  # noqa: E402
    Contract,
    V7ContractError,
    contract,
    load_manifest,
)


class V7MaterializationError(RuntimeError):
    """A frozen V7 source checkout could not be created safely."""


@dataclass(frozen=True)
class MaterializedTemporalReviewV7Fixture:
    task_id: str
    path: Path
    contract: Contract


def _git(path: Path | None, *args: str) -> str:
    command = ["git"]
    if path is not None:
        command.extend(["-C", str(path)])
    result = subprocess.run([*command, *args], capture_output=True, text=True)
    if result.returncode:
        raise V7MaterializationError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _has_commit(path: Path, sha: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(path), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True, text=True
    ).returncode == 0


def _ensure_history(destination: Path, source_repository: Path, item: Contract) -> None:
    missing = [
        item.refs[side]["commit_sha"] for side in ("base", "head")
        if not _has_commit(destination, item.refs[side]["commit_sha"])
    ]
    if not missing:
        return
    try:
        origin = _git(source_repository, "remote", "get-url", "origin")
    except V7MaterializationError as exc:
        raise V7MaterializationError("frozen V7 commits are absent and origin is unavailable") from exc
    _git(destination, "fetch", "--no-tags", origin, *missing)
    if any(not _has_commit(destination, sha) for sha in missing):
        raise V7MaterializationError("could not fetch all frozen V7 commits")


def _validate_checkout(destination: Path, item: Contract) -> None:
    if _git(destination, "status", "--porcelain", "--untracked-files=all"):
        raise V7MaterializationError("materialized V7 checkout must start clean")
    if _git(destination, "rev-parse", "--abbrev-ref", "HEAD") != "HEAD":
        raise V7MaterializationError("materialized V7 checkout must be detached")
    if _git(destination, "rev-parse", "HEAD") != item.refs["head"]["commit_sha"]:
        raise V7MaterializationError("materialized V7 checkout is not at frozen head")
    for side in ("base", "head"):
        if _git(destination, "rev-parse", f"{item.refs[side]['alias']}^{{commit}}") != item.refs[side]["commit_sha"]:
            raise V7MaterializationError(f"V7 alias {item.refs[side]['alias']} is incorrect")
    exclusions = load_manifest().get("fixture_exclusion_globs")
    if not isinstance(exclusions, list):
        raise V7MaterializationError("V7 fixture exclusions are invalid")
    for pattern in exclusions:
        if not isinstance(pattern, str):
            raise V7MaterializationError("V7 fixture exclusions are invalid")
        if (destination / pattern.removesuffix("/**")).exists():
            raise V7MaterializationError(f"oracle-bearing path is visible: {pattern}")


def materialize_temporal_review_v7_fixture(
    task_id: str, destination: Path, *, source_repository: Path
) -> MaterializedTemporalReviewV7Fixture:
    """Create a detached sparse checkout containing only source and config."""
    item = contract(task_id)
    destination, source_repository = destination.resolve(), source_repository.resolve()
    if destination.exists():
        raise V7MaterializationError("destination must not already exist")
    if not (source_repository / ".git").exists():
        raise V7MaterializationError("source_repository is not a Git checkout")
    _git(None, "clone", "--no-local", "--no-checkout", str(source_repository), str(destination))
    _ensure_history(destination, source_repository, item)
    _git(destination, "sparse-checkout", "init", "--no-cone")
    _git(destination, "sparse-checkout", "set", "--no-cone", "/src/", "/.codeindex.yaml")
    _git(destination, "checkout", "--quiet", "--detach", item.refs["head"]["commit_sha"])
    _git(destination, "tag", "-f", item.base_ref, item.refs["base"]["commit_sha"])
    _git(destination, "tag", "-f", item.head_ref, item.refs["head"]["commit_sha"])
    _validate_checkout(destination, item)
    return MaterializedTemporalReviewV7Fixture(task_id, destination, item)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-repository", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        fixture = materialize_temporal_review_v7_fixture(
            args.task_id, args.destination, source_repository=args.source_repository
        )
    except (V7ContractError, V7MaterializationError) as exc:
        parser.error(str(exc))
    print(json.dumps({"task_id": fixture.task_id, "path": str(fixture.path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
