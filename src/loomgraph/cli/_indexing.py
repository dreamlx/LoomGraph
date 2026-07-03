"""CLI commands for indexing and updating the knowledge graph."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.cli.main import main
from loomgraph.core.graph_export_ingest import (
    GraphExportError,
    ingest,
    run_graph_export,
)


@main.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--clear/--no-clear", default=True, help="Clear old data before indexing")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def index(repo_path: str, clear: bool, workspace: str | None) -> None:
    """Index a code repository (one-step pipeline).

    Calls: codeindex graph-export → embed → inject (module-qualified entity
    ids — fixes the cross-module same-name collision, #66).

    REPO_PATH: Directory path to index
    """
    import time

    start_time = time.time()
    repo = Path(repo_path).resolve()

    # Step 1: Check codeindex
    click.echo("[1/3] Checking codeindex installation...", err=True)
    codeindex_status = check_codeindex()
    if not codeindex_status.get("installed"):
        output_error(
            code=ErrorCode.CODEINDEX_NOT_FOUND,
            message="codeindex command not found in PATH",
            suggestion="Install codeindex: pip install ai-codeindex",
            docs="https://github.com/dreamlx/codeindex#installation",
        )
        return

    # Step 2: Run codeindex graph-export (qualified entity ids + edges)
    click.echo(f"[2/3] Exporting {repo.name}/ with codeindex graph-export...", err=True)
    try:
        entities, relations, summary = run_graph_export(repo)
    except GraphExportError as e:
        output_error(
            code=ErrorCode.CODEINDEX_FAILED,
            message=str(e),
            suggestion="Check codeindex logs; ensure ai-codeindex >= 0.28.0",
        )
        return
    click.echo(
        f"       Export complete: {summary.entity_count} entities, "
        f"{summary.relation_count} relations.",
        err=True,
    )

    # Step 3: Embed + inject asynchronously
    click.echo("[3/3] Injecting into knowledge graph...", err=True)
    try:
        result = asyncio.run(_async_index(entities, relations, workspace, clear))
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Pipeline error: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["repo_path"] = str(repo)
    click.echo(f"       Done in {result['duration_seconds']}s.", err=True)

    output_success(result)


async def _async_index(
    entities: list[Any],
    relations: list[Any],
    workspace: str | None,
    clear: bool,
) -> dict[str, Any]:
    """Resolve workspace, build the store, run the shared ingest pipeline.

    Receives already-mapped entities/relations from ``run_graph_export``
    (module-qualified ids — fixes the cross-module same-name collision, #66).
    Delegates embed + insert to :func:`ingest`.
    """
    from loomgraph.storage.factory import create_graph_store

    ws = get_auto_workspace(workspace)
    store = await create_graph_store(workspace=ws)

    def _progress(phase: str, n_entities: int, n_relations: int) -> None:
        click.echo(
            f"       {phase}: {n_entities} entities, {n_relations} relations",
            err=True,
        )

    result = await ingest(
        entities, relations, store, clear=clear, on_progress=_progress
    )
    result["workspace"] = ws
    result["mode"] = "cold_rebuild" if clear else "append"
    return result


@main.command()
@click.option("--since", default="HEAD~1", help="Git ref to compare from (default: HEAD~1)")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option("--files", default=None, help="Comma-separated list of files to update (skips git detection)")
@click.option("--embedding-url", default=None, help="Override embedding API URL from config")
@click.option("--use-affected", is_flag=True, help="Use 'codeindex affected' instead of 'git diff' (smarter detection)")
def update(
    since: str,
    workspace: str | None,
    files: str | None,
    embedding_url: str | None,
    use_affected: bool,
) -> None:
    """Update the knowledge graph (whole-tree re-export, #66).

    Previously a per-file warm update via ``codeindex parse <file>`` + git diff.
    Now: whole-tree ``codeindex graph-export`` + upsert — converges with
    ``index`` minus ``--clear`` for additions/modifications. Deleted symbols
    are NOT garbage-collected (upsert overwrites same-id, never removes); run
    ``index --clear`` for a fully clean state. Warm-incrementality will be
    restored via a content_hash-based diff (EPIC-015 follow-up).

    ``--since`` / ``--files`` / ``--use-affected`` / ``--embedding-url`` are
    accepted but inert (a deprecation note is emitted when any non-default is
    set). ``--files`` path-existence is still validated, for CI scripts that
    gate on the exit code.
    """
    import time

    start_time = time.time()

    # Inert-flag detection (kept for CI-script + muscle-memory compatibility).
    inert: list[str] = []
    if since != "HEAD~1":
        inert.append(f"--since={since}")
    if use_affected:
        inert.append("--use-affected")
    if embedding_url:
        inert.append("--embedding-url=…")
    if files:
        # Validate paths exist (CI scripts may gate on the exit code) — then drop.
        for f in [s.strip() for s in files.split(",") if s.strip()]:
            if not Path(f).exists():
                output_error(
                    code=ErrorCode.INVALID_INPUT,
                    message=f"File not found: {f}",
                    suggestion="Check file paths and ensure they exist",
                )
                return
        inert.append("--files=…")
    if inert:
        click.echo(
            "note: update now does whole-tree graph-export re-export; "
            f"ignoring inert flags ({', '.join(inert)}). "
            "Warm-incremental restoration tracked in EPIC-015 follow-up.",
            err=True,
        )

    repo = Path(".").resolve()

    # Step 1: Check codeindex
    click.echo("[1/3] Checking codeindex installation...", err=True)
    codeindex_status = check_codeindex()
    if not codeindex_status.get("installed"):
        output_error(
            code=ErrorCode.CODEINDEX_NOT_FOUND,
            message="codeindex command not found in PATH",
            suggestion="Install codeindex: pip install ai-codeindex",
            docs="https://github.com/dreamlx/codeindex#installation",
        )
        return

    # Step 2: Run codeindex graph-export (whole tree)
    click.echo("[2/3] Exporting whole tree with codeindex graph-export...", err=True)
    try:
        entities, relations, summary = run_graph_export(repo)
    except GraphExportError as e:
        output_error(
            code=ErrorCode.CODEINDEX_FAILED,
            message=str(e),
            suggestion="Check codeindex logs; ensure ai-codeindex >= 0.28.0",
        )
        return
    click.echo(
        f"       Export complete: {summary.entity_count} entities, "
        f"{summary.relation_count} relations.",
        err=True,
    )

    # Step 3: Embed + upsert (clear=False → no delete_all)
    click.echo("[3/3] Upserting into knowledge graph...", err=True)
    try:
        result = asyncio.run(_async_index(entities, relations, workspace, False))
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Pipeline error: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["repo_path"] = str(repo)
    click.echo(f"       Done in {result['duration_seconds']}s.", err=True)

    output_success(result)
