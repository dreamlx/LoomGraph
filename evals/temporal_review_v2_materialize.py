"""Materialize a source-only historical checkout for the v2 review contract."""

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

from evals.temporal_review_v2_fixtures import (  # noqa: E402
    Contract,
    V2ContractError,
    contract,
    load_manifest,
)


class V2MaterializationError(RuntimeError):
    """A v2 historical review checkout could not be created safely."""


@dataclass(frozen=True)
class MaterializedTemporalReviewV2Fixture:
    """The source-only checkout and frozen v2 task identity used by one run."""

    task_id: str
    path: Path
    contract: Contract


def _git(path: Path | None, *args: str) -> str:
    command = ["git"]
    if path is not None:
        command.extend(["-C", str(path)])
    command.extend(args)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise V2MaterializationError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _has_commit(path: Path, sha: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _ensure_frozen_history(
    destination: Path,
    source_repository: Path,
    item: Contract,
) -> None:
    """Fetch missing frozen objects from the source's origin when needed."""
    missing = [
        item.refs[side]["commit_sha"]
        for side in ("base", "head")
        if not _has_commit(destination, item.refs[side]["commit_sha"])
    ]
    if not missing:
        return

    try:
        source_origin = _git(source_repository, "remote", "get-url", "origin")
    except V2MaterializationError as exc:
        raise V2MaterializationError(
            "frozen v2 review commits are absent and source has no readable origin"
        ) from exc
    _git(destination, "fetch", "--no-tags", source_origin, *missing)
    if any(not _has_commit(destination, sha) for sha in missing):
        raise V2MaterializationError("could not fetch all frozen v2 review commits from source origin")


def _excluded_paths(destination: Path) -> tuple[str, ...]:
    manifest = load_manifest()
    values = manifest.get("fixture_exclusion_globs")
    if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
        raise V2MaterializationError("v2 fixture exclusion globs are invalid")
    return tuple(values)


def _validate_checkout(destination: Path, item: Contract) -> None:
    if _git(destination, "status", "--porcelain", "--untracked-files=all"):
        raise V2MaterializationError("materialized v2 checkout must start clean")
    if _git(destination, "rev-parse", "--abbrev-ref", "HEAD") != "HEAD":
        raise V2MaterializationError("materialized v2 checkout must have a detached HEAD")
    if _git(destination, "rev-parse", "HEAD") != item.refs["head"]["commit_sha"]:
        raise V2MaterializationError("materialized v2 checkout is not at the frozen head commit")
    for side in ("base", "head"):
        alias = item.refs[side]["alias"]
        expected = item.refs[side]["commit_sha"]
        if _git(destination, "rev-parse", f"{alias}^{{commit}}") != expected:
            raise V2MaterializationError(f"v2 alias {alias} does not resolve to its frozen commit")

    for pattern in _excluded_paths(destination):
        root = pattern.removesuffix("/**")
        if (destination / root).exists():
            raise V2MaterializationError(f"oracle-bearing path is visible: {root}")


def materialize_temporal_review_v2_fixture(
    task_id: str,
    destination: Path,
    *,
    source_repository: Path,
) -> MaterializedTemporalReviewV2Fixture:
    """Clone a clean, sparse, detached v2 checkout without oracle-bearing files."""
    item = contract(task_id)
    destination = destination.resolve()
    source_repository = source_repository.resolve()
    if destination.exists():
        raise V2MaterializationError("destination must not already exist")
    if not (source_repository / ".git").exists():
        raise V2MaterializationError("source_repository is not a Git checkout")

    _git(None, "clone", "--no-local", "--no-checkout", str(source_repository), str(destination))
    _ensure_frozen_history(destination, source_repository, item)
    _git(destination, "sparse-checkout", "init", "--no-cone")
    _git(destination, "sparse-checkout", "set", "--no-cone", "/src/", "/.codeindex.yaml")
    _git(destination, "checkout", "--quiet", "--detach", item.refs["head"]["commit_sha"])
    _git(destination, "tag", "-f", item.base_ref, item.refs["base"]["commit_sha"])
    _git(destination, "tag", "-f", item.head_ref, item.refs["head"]["commit_sha"])
    _validate_checkout(destination, item)
    return MaterializedTemporalReviewV2Fixture(task_id, destination, item)


# Keep the short spelling discoverable for callers that mirror agent_use_v2_fixtures.
materialize_v2_temporal_review_fixture = materialize_temporal_review_v2_fixture


def _record(fixture: MaterializedTemporalReviewV2Fixture) -> dict[str, object]:
    return {
        "task_id": fixture.task_id,
        "path": str(fixture.path),
        "base": {
            "ref": fixture.contract.base_ref,
            "sha": fixture.contract.refs["base"]["commit_sha"],
        },
        "head": {
            "ref": fixture.contract.head_ref,
            "sha": fixture.contract.refs["head"]["commit_sha"],
        },
        "backend": fixture.contract.backend,
        "source_only": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-repository", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        fixture = materialize_temporal_review_v2_fixture(
            args.task_id,
            args.destination,
            source_repository=args.source_repository,
        )
    except (V2ContractError, V2MaterializationError) as exc:
        parser.error(str(exc))
    print(json.dumps(_record(fixture), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
