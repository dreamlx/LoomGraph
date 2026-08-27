"""Read-only Claude Code orientation command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import output_success
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.cli.main import main
from loomgraph.core.git import GitError, is_git_repository, resolve_ref
from loomgraph.core.orientation import decide_orientation


def _resolve_temporal_refs(
    repo: Path, base_ref: str | None, head_ref: str | None
) -> dict[str, str] | None:
    """Check explicit temporal refs without provisioning snapshots or storage."""
    if not base_ref or not head_ref:
        return None
    try:
        base_sha = resolve_ref(repo, base_ref)
        head_sha = resolve_ref(repo, head_ref)
    except GitError:
        return None
    return {
        "base_ref": base_ref,
        "base_sha": base_sha,
        "head_ref": head_ref,
        "head_sha": head_sha,
    }


@main.command()
@click.option(
    "--task-kind",
    type=click.Choice(("local", "cross-file", "temporal-review")),
    required=True,
    help="Declared first-step task kind; this command does not infer intent.",
)
@click.option(
    "--policy",
    type=click.Choice(("economy", "balanced", "deep")),
    default="balanced",
    show_default=True,
    help="Explicit evidence budget policy.",
)
@click.option("--base-ref", help="Base Git ref required for temporal-review.")
@click.option("--head-ref", help="Head Git ref required for temporal-review.")
def orient(
    task_kind: str,
    policy: str,
    base_ref: str | None,
    head_ref: str | None,
) -> None:
    """Recommend a smallest read-only code-understanding path for Claude Code."""
    codeindex_available = (
        check_codeindex().get("installed") is True if task_kind != "local" else False
    )
    git_repository = False
    resolved_refs: dict[str, str] | None = None
    if task_kind == "temporal-review":
        repo = Path.cwd()
        git_repository = is_git_repository(repo)
        if git_repository:
            resolved_refs = _resolve_temporal_refs(repo, base_ref, head_ref)
    result: dict[str, Any] = decide_orientation(
        task_kind=task_kind,
        policy=policy,
        codeindex_available=codeindex_available,
        git_repository=git_repository,
        refs_resolved=resolved_refs is not None,
    )
    if task_kind == "temporal-review":
        result["comparison_request"] = resolved_refs or {
            "base_ref": base_ref,
            "head_ref": head_ref,
        }
        if resolved_refs is not None:
            result["comparison_request"]["execution_constraint"] = (
                "use resolved SHA values, or verify the branch-diff response SHA values match"
            )
    output_success(result)
