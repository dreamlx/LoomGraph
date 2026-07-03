"""CLI commands for indexing, embedding, and injection."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings
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
@click.argument("input_json", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option("--batch-size", default=32, help="Batch size for embedding")
def embed(input_json: str, output: str | None, batch_size: int) -> None:
    """Generate embeddings from ParseResult JSON.

    INPUT_JSON: codeindex scan output JSON file
    """
    # Load input
    try:
        with open(input_json) as f:
            parse_results = json.load(f)
    except json.JSONDecodeError as e:
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=f"Invalid JSON: {e}",
            suggestion="Ensure input is valid codeindex JSON output",
        )
        return
    except FileNotFoundError:
        output_error(
            code=ErrorCode.FILE_NOT_FOUND,
            message=f"File not found: {input_json}",
        )
        return

    # Run embedding
    try:
        result = asyncio.run(_async_embed(parse_results, batch_size))
    except Exception as e:
        output_error(
            code=ErrorCode.EMBEDDING_FAILED,
            message=f"Embedding failed: {e}",
            suggestion="Check embedding service status with: loomgraph status",
        )
        return

    # Output
    if output:
        with open(output, "w") as f:
            json.dump({"success": True, "data": result}, f, indent=2)
        output_success({"output_file": output, "count": result["count"]})
    else:
        output_success(result)


async def _async_embed(parse_results: dict[str, Any], batch_size: int) -> dict[str, Any]:
    """Run async embedding."""
    from loomgraph.embedding.jina import JinaEmbeddingClient

    settings = get_settings()
    settings.embedding.batch_size = batch_size
    client = JinaEmbeddingClient(settings.embedding)

    # Collect all symbols
    texts: list[str] = []
    names: list[str] = []

    for file_result in parse_results.get("results", []):
        for symbol in file_result.get("symbols", []):
            name = symbol.get("name", "")
            signature = symbol.get("signature", name)
            texts.append(signature)
            names.append(name)

    if not texts:
        return {
            "embeddings": {},
            "model": settings.embedding.model,
            "dimension": settings.embedding.dimension,
            "count": 0,
        }

    # Generate embeddings
    result = await client.embed(texts)

    # Build output
    embeddings = dict(zip(names, result.embeddings, strict=False))

    return {
        "embeddings": embeddings,
        "model": result.model,
        "dimension": len(result.embeddings[0]) if result.embeddings else 0,
        "count": len(embeddings),
    }


@main.command()
@click.argument("parse_json", type=click.Path(exists=True))
@click.argument("embeddings_json", type=click.Path(exists=True))
@click.option("--clear/--no-clear", default=False, help="Clear old data first")
def inject(parse_json: str, embeddings_json: str, clear: bool) -> None:
    """Inject ParseResult + Embeddings into knowledge graph.

    PARSE_JSON: codeindex scan output
    EMBEDDINGS_JSON: embed command output
    """
    # Load inputs
    try:
        with open(parse_json) as f:
            parse_results = json.load(f)
        with open(embeddings_json) as f:
            embeddings_data = json.load(f)
    except json.JSONDecodeError as e:
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=f"Invalid JSON: {e}",
        )
        return
    except FileNotFoundError as e:
        output_error(
            code=ErrorCode.FILE_NOT_FOUND,
            message=f"File not found: {e}",
        )
        return

    # Extract embeddings
    embeddings = embeddings_data.get("data", {}).get("embeddings", {})
    if not embeddings and "embeddings" in embeddings_data:
        embeddings = embeddings_data["embeddings"]

    # Run injection
    try:
        result = asyncio.run(_async_inject(parse_results, embeddings, clear))
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Injection failed: {e}",
            suggestion="Check database connection with: loomgraph status",
        )
        return

    output_success(result)


async def _async_inject(
    parse_results: dict[str, Any],
    embeddings: dict[str, list[float]],
    clear: bool,
) -> dict[str, Any]:
    """Run async injection into knowledge graph."""
    import time

    start_time = time.time()

    # Note: Full SQLite integration via storage abstraction
    # For now, count what would be injected
    entities_created = 0
    relations_created = 0
    entities_updated = 0

    for file_result in parse_results.get("results", []):
        symbols = file_result.get("symbols", [])
        calls = file_result.get("calls", [])
        inheritances = file_result.get("inheritances", [])
        imports = file_result.get("imports", [])

        entities_created += len(symbols)
        relations_created += len(calls) + len(inheritances) + len(imports)

    duration = time.time() - start_time

    return {
        "entities_created": entities_created,
        "relations_created": relations_created,
        "entities_updated": entities_updated,
        "duration_seconds": round(duration, 2),
    }


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
