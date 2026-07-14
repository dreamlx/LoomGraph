"""CLI commands for indexing and updating the knowledge graph."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.cli.main import main
from loomgraph.core.git import (
    get_changed_files,
    get_working_tree_files,
    is_git_repository,
)
from loomgraph.core.graph_export_ingest import (
    GraphExportError,
    ingest,
    ingest_incremental,
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
        entities, relations, summary, warnings = run_graph_export(repo)
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

    # codeindex's partial-graph warnings (#131) — e.g. a non-Python repo
    # indexed with default languages:[python] yields a few stray entities and
    # a "WARNING: partial graph" line. Surface it so a misconfigured repo
    # doesn't index as a silent success (#108).
    for line in warnings:
        click.echo(f"⚠️  {line}", err=True)

    # 0 entities is almost always a languages/grammar mismatch (#93) — warn
    # loudly instead of letting it sail through as a silent success. Kept as a
    # warning (exit 0): an empty repo legitimately indexes to 0.
    # warning (exit 0): an empty repo legitimately indexes to 0.
    zero_warning = (
        _zero_entities_warning(repo, warnings) if summary.entity_count == 0 else None
    )
    if zero_warning is not None:
        click.echo(f"⚠️  WARNING: {zero_warning}", err=True)

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

    if zero_warning is not None:
        result["warning"] = zero_warning
    elif warnings:
        result["warning"] = "; ".join(warnings)

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


def _zero_entities_warning(repo: Path, warnings: list[str] | None = None) -> str:
    """Diagnose a 0-entity graph-export for the user/agent (#93, #96, #118).

    ``codeindex graph-export`` returned nothing — almost always a
    ``.codeindex.yaml`` languages mismatch (codeindex defaults to python)
    or a missing tree-sitter grammar. Return an actionable hint rather than
    a bare count. Java/TypeScript/Swift get a specific pointer to their
    extra; the general case points at the languages config or — when
    codeindex reported a grammar/parser problem on stderr — surfaces that.
    """
    if warnings:
        # codeindex already told us the root cause on stderr (#118): a missing
        # tree-sitter grammar (``Parser library not installed for <lang>``) or a
        # languages-mismatch (``no indexable directories`` + ``Top extensions``).
        # Prefer the codeindex diagnostic over file-suffix guessing — it names
        # the exact missing language even for PHP/objc/JS (no extra / no suffix
        # branch here yet) and cites the config vs file-extension gap directly.
        # The raw WARNING lines are already echoed verbatim above; fold the
        # multi-line hint into its leading sentence (keep the missing-language
        # name + file-extension evidence, drop the per-file path noise).
        first_lines: list[str] = []
        for w in warnings:
            first_lines.append(w.split("\n")[0].rstrip())
        joined = "; ".join(first_lines)
        return (
            f"graph-export returned 0 entities; codeindex reports: {joined}. "
            "Install the matching `loomgraph[<lang>]` extra and ensure that "
            "language is listed under `languages` in .codeindex.yaml"
        )
    if next(repo.rglob("*.java"), None) is not None:
        return (
            "graph-export returned 0 entities; found .java files — install "
            "Java support with `pipx install loomgraph[java]` and ensure "
            "'java' is listed under languages in .codeindex.yaml"
        )
    if next(repo.rglob("*.tsx"), None) is not None or next(repo.rglob("*.ts"), None) is not None:
        return (
            "graph-export returned 0 entities; found .ts/.tsx files — install "
            "TypeScript support with `pipx install loomgraph[typescript]` and "
            "ensure 'typescript' is listed under languages in .codeindex.yaml"
        )
    if next(repo.rglob("*.swift"), None) is not None:
        return (
            "graph-export returned 0 entities; found .swift files — install "
            "Swift support with `pipx install loomgraph[swift]` and ensure "
            "'swift' is listed under languages in .codeindex.yaml"
        )
    return (
        "graph-export returned 0 entities; check that .codeindex.yaml "
        "languages matches this repository's code"
    )


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
    """Update the knowledge graph (per-file warm-diff via git, 路 B).

    In a git repo: re-export the whole tree, then re-embed/re-inject only
    the files that changed since ``--since`` (default ``HEAD~1``) and
    garbage-collect symbols deleted since the last index. Unchanged files
    cost zero embed calls (the expensive part, per codeindex#110).

    Non-git repo, or ``--files`` set: falls back to whole-tree upsert
    (``clear=False``) — additions/modifications converge, but deleted
    symbols are NOT GC'd; run ``index --clear .`` for a fully clean state.

    ``--use-affected`` / ``--embedding-url`` are accepted but inert (kept
    for CI-script / muscle-memory compat). ``--files`` path-existence is
    validated (CI scripts may gate on the exit code) and forces the
    whole-tree fallback.
    """
    import time

    start_time = time.time()

    # Inert flags (compat) — note: --since is now ACTIVE (git diff ref).
    inert: list[str] = []
    if use_affected:
        inert.append("--use-affected")
    if embedding_url:
        inert.append("--embedding-url=…")
    if inert:
        click.echo(f"note: ignoring inert flags ({', '.join(inert)}).", err=True)

    # --files path validation (CI gate compat) → forces whole-tree fallback.
    forced_whole_tree = False
    if files:
        for f in [s.strip() for s in files.split(",") if s.strip()]:
            if not Path(f).exists():
                output_error(
                    code=ErrorCode.INVALID_INPUT,
                    message=f"File not found: {f}",
                    suggestion="Check file paths and ensure they exist",
                )
                return
        forced_whole_tree = True

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
        entities, relations, summary, warnings = run_graph_export(repo)
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
    # Surface codeindex partial-graph warnings (#108) — same as `index`.
    for line in warnings:
        click.echo(f"⚠️  {line}", err=True)

    # Step 3: Incremental (git) or whole-tree upsert (non-git / --files)
    click.echo("[3/3] Updating knowledge graph...", err=True)
    try:
        result = asyncio.run(
            _async_update(entities, relations, workspace, repo, since, forced_whole_tree)
        )
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Pipeline error: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["repo_path"] = str(repo)
    click.echo(f"       Done in {result['duration_seconds']}s ({result['mode']}).", err=True)

    if warnings:
        result["warning"] = "; ".join(warnings)

    output_success(result)


async def _async_update(
    entities: list[Any],
    relations: list[Any],
    workspace: str | None,
    repo: Path,
    since: str,
    forced_whole_tree: bool,
) -> dict[str, Any]:
    """Branch update into per-file incremental (git) or whole-tree upsert.

    - git repo and not ``forced_whole_tree``: ``ingest_incremental`` over the
      ``get_changed_files(since)`` subset (路 B).
    - otherwise: ``ingest(clear=False)`` whole-tree upsert (non-git fallback,
      or explicit ``--files``).
    """
    from loomgraph.storage.factory import create_graph_store

    ws = get_auto_workspace(workspace)
    store = await create_graph_store(workspace=ws)

    def _progress(phase: str, n_entities: int, n_relations: int) -> None:
        click.echo(
            f"       {phase}: {n_entities} entities, {n_relations} relations",
            err=True,
        )

    use_incremental = (not forced_whole_tree) and is_git_repository(repo)
    if use_incremental:
        changed_paths = get_changed_files(since=since, repo_path=repo)
        changed_files = {p.as_posix() for p in changed_paths}
        result = await ingest_incremental(
            entities,
            relations,
            store,
            changed_files=changed_files,
            on_progress=_progress,
        )
        result["mode"] = "warm_incremental"
    else:
        result = await ingest(
            entities, relations, store, clear=False, on_progress=_progress
        )
        result["mode"] = "whole_tree_upsert"

    result["workspace"] = ws
    return result


def _expand_path(path: str, repo: Path) -> set[str]:
    """Expand a path arg (file or dir prefix) to repo-relative posix paths.

    - file → ``{that file}``
    - dir  → all existing files under it (rglob)
    - missing → ``ValueError`` (the MCP handle's ``safe_call`` surfaces this
      as a ``REFRESH_FAILED`` envelope)
    """
    target = (repo / path).resolve()
    base = repo.resolve()
    if target.is_file():
        return {target.relative_to(base).as_posix()}
    if target.is_dir():
        return {
            f.relative_to(base).as_posix()
            for f in target.rglob("*")
            if f.is_file()
        }
    raise ValueError(f"path not found: {path}")


async def _async_refresh(
    workspace: str | None,
    repo: Path,
    path: str | None,
    force_full: bool,
) -> dict[str, Any]:
    """MCP-driven reactive re-index of the working tree (pull-mode).

    Complementary to :func:`_async_update` (committed ``HEAD~1..HEAD`` via the
    git hook): refresh targets the **working tree** — uncommitted edits
    including untracked new files — so an agent that just edited a file can
    see it in the graph without committing first.

    Branching:

    - ``force_full=True`` → ``ingest(clear=True)`` cold rebuild (like
      ``index --clear``).
    - ``path`` given → ``ingest_incremental`` over the expanded path set.
    - git repo, no path → ``ingest_incremental`` over ``get_working_tree_files``.
    - non-git, no path → ``ingest(clear=False)`` whole-tree upsert.
    - incremental resolves to zero changed files → ``{"mode": "noop"}``,
      skipping the codeindex export entirely.
    """
    from loomgraph.storage.factory import create_graph_store

    ws = get_auto_workspace(workspace)
    store = await create_graph_store(workspace=ws)

    if force_full:
        entities, relations, _, _ = run_graph_export(repo)
        result = await ingest(entities, relations, store, clear=True)
        result["mode"] = "cold_rebuild"
        result["workspace"] = ws
        return result

    # Determine the changed-files set + strategy.
    if path is not None:
        changed_files = _expand_path(path, repo)
        strategy = "incremental"
    elif is_git_repository(repo):
        changed_files = {
            p.as_posix() for p in get_working_tree_files(repo_path=repo)
        }
        strategy = "incremental"
    else:
        changed_files = set()
        strategy = "whole_tree"

    if strategy == "incremental" and not changed_files:
        return {"mode": "noop", "changed_files": [], "workspace": ws}

    entities, relations, _, _ = run_graph_export(repo)
    if strategy == "incremental":
        result = await ingest_incremental(
            entities, relations, store, changed_files=changed_files
        )
        result["mode"] = "warm_incremental"
    else:
        result = await ingest(entities, relations, store, clear=False)
        result["mode"] = "whole_tree_upsert"

    result["workspace"] = ws
    return result
