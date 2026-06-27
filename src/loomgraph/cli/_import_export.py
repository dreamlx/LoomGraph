"""CLI command: import a codeindex `graph-export` NDJSON artifact.

This wires the codeindex#102 producer to a loomgraph-side consumer
workspace. Mapping rules in `loomgraph.io.export_reader`; this module
only handles I/O, CLI argument parsing, and `store.insert_custom_kg`
batching.

Default workspace name pattern (per LoomGraph#30 Q2=A):
  `<basename-without-ext>:imported.db`

The `:imported` suffix isolates imported artifacts from workspaces
produced by `loomgraph index .`, so users can never accidentally
overwrite their own working index with a stale snapshot.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, output_error, output_success
from loomgraph.cli.main import main


@main.command("import-export")
@click.argument(
    "artifact",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--workspace",
    "-w",
    default=None,
    help=(
        "Workspace name to write into. Default: "
        "`<artifact-basename>:imported`. The `:imported` suffix prevents "
        "collision with `loomgraph index .` output."
    ),
)
@click.option(
    "--clear/--no-clear",
    default=True,
    help="Clear existing workspace before import (default: True).",
)
def import_export(
    artifact: Path,
    workspace: str | None,
    clear: bool,
) -> None:
    """Import a codeindex graph-export NDJSON artifact into a workspace.

    Honours `resolution_qualifier` on every edge — `resolved` /
    `ambiguous` / `unresolved` are all imported with the qualifier
    preserved in `edge_data`, so downstream `loomgraph graph` / `find`
    queries can filter on it. This is the consumer trust calculus
    LoomGraph#30 verdict requires.
    """
    if workspace is None:
        workspace = f"{artifact.stem}:imported"

    try:
        result = asyncio.run(
            _async_import_export(artifact, workspace, clear=clear)
        )
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Import failed: {e}",
            suggestion=(
                "Check artifact format with: head -1 <file> | python3 -m json.tool"
            ),
        )


async def _async_import_export(
    artifact: Path,
    workspace: str,
    *,
    clear: bool,
) -> dict[str, Any]:
    """Async pipeline: read NDJSON → map → insert_custom_kg."""
    from loomgraph.io import GraphExportReader
    from loomgraph.storage.factory import create_graph_store

    reader = GraphExportReader(artifact)
    entities, relations, summary = reader.read()

    store = await create_graph_store(workspace=workspace)
    if clear:
        await store.delete_all()

    # insert_custom_kg signature is (entities, relations, chunks);
    # we have no chunks (codeindex export doesn't carry vector data —
    # by design, sqlite-vec embedding is loomgraph's own concern).
    await store.insert_custom_kg(
        [
            {"entity_name": e.entity_name, **e.entity_data}
            for e in entities
        ],
        [
            {"src_id": r.src_id, "tgt_id": r.tgt_id, **r.edge_data}
            for r in relations
        ],
        [],
    )

    # Final stats from the live store (sanity-check insert)
    stats = await store.get_graph_stats()

    return {
        "workspace": workspace,
        "artifact": str(artifact),
        "cleared": clear,
        "summary": summary.to_dict(),
        "store_stats": stats,
    }
