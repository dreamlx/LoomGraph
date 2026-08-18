"""CLI command: import a codeindex `graph-export` NDJSON artifact.

This wires the codeindex#102 producer to a loomgraph-side consumer
workspace. Mapping rules in `loomgraph.io.export_reader`; this module
handles I/O, CLI argument parsing, and `store.insert_custom_kg`
batching.

Default workspace name pattern (per LoomGraph#30 Q2=A):
  `<basename-without-ext>:imported.db`

The `:imported` suffix isolates imported artifacts from workspaces
produced by `loomgraph index .`, so users can never accidentally
overwrite their own working index with a stale snapshot.

`--clear` defaults to **False** (non-destructive) so an AI agent that
calls this without flags cannot wipe a workspace silently.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, output_error, output_success
from loomgraph.cli.main import main
from loomgraph.core.embedding_pipeline import maybe_embed_entities


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
    default=False,
    help=(
        "Clear existing workspace before import. Default: False "
        "(non-destructive). Pass --clear to nuke and replace."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help=(
        "Read + validate + map but do NOT touch any workspace. Prints the "
        "import summary (counts, qualifier breakdown, schema warnings) "
        "without writing. Useful for inspecting an unknown artifact safely."
    ),
)
def import_export(
    artifact: Path,
    workspace: str | None,
    clear: bool,
    dry_run: bool,
) -> None:
    """Import a codeindex graph-export NDJSON artifact into a workspace.

    Honours `resolution_qualifier` on every edge — `resolved` /
    `ambiguous` are imported with the qualifier preserved in `edge_data`,
    while `unresolved` edges are counted in the summary but skipped from
    storage (they have no real target; inserting a placeholder would
    create a misleading hub entity in topology analytics).

    This is the consumer trust calculus LoomGraph#30 verdict requires.
    """
    if workspace is None:
        workspace = f"{artifact.stem}:imported"

    try:
        result = asyncio.run(
            _async_import_export(artifact, workspace, clear=clear, dry_run=dry_run)
        )
        output_success(result)
    except FileNotFoundError as e:
        output_error(
            code=ErrorCode.FILE_NOT_FOUND,
            message=f"Artifact not found: {e}",
            suggestion="Pass an existing path to the NDJSON file.",
        )
    except ValueError as e:
        # ExportReadError + json.JSONDecodeError pass-through
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=f"Artifact malformed: {e}",
            suggestion=(
                "Validate with: head -1 <file> | python3 -m json.tool. "
                "Expect line 1 to be {\"type\":\"meta\",\"schema_version\":0,...}"
            ),
        )
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Workspace write failed: {e}",
            suggestion="Check workspace state with: loomgraph workspace info",
        )


async def _async_import_export(
    artifact: Path,
    workspace: str,
    *,
    clear: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Async pipeline: read NDJSON → (map →) maybe insert_custom_kg."""
    from loomgraph.io import GraphExportReader

    reader = GraphExportReader(artifact)
    entities, relations, summary = reader.read()

    if dry_run:
        return {
            "workspace": workspace,
            "artifact": str(artifact),
            "dry_run": True,
            "summary": summary.to_dict(),
            "would_write": {
                "entities": len(entities),
                "relations": len(relations),
            },
        }

    from loomgraph.storage.factory import create_graph_store

    store = await create_graph_store(workspace=workspace)
    if clear:
        await store.delete_all()

    # Build the entity dicts once; maybe_embed_entities attaches `embedding`
    # in place (gated on settings.embedding.enabled — no-op when off, so the
    # default install profile is unaffected). Mirrors `loomgraph index`/`update`.
    entity_dicts = [
        {"entity_name": e.entity_name, **e.entity_data} for e in entities
    ]
    relation_dicts = [
        {"src_id": r.src_id, "tgt_id": r.tgt_id, **r.edge_data} for r in relations
    ]
    embedded_count = await maybe_embed_entities(entity_dicts, store)

    # insert_custom_kg signature is (entities, relations, chunks); we have no
    # chunks (codeindex export carries no vector data — sqlite-vec embedding
    # is loomgraph's own concern, applied above).
    await store.insert_custom_kg(entity_dicts, relation_dicts, [])

    # #154/#158 review C1-2: persist the trust ratio on this write path too.
    from loomgraph.core.graph_export_ingest import persist_resolved_ratio

    resolved_ratio = await persist_resolved_ratio(store, entity_dicts, relation_dicts)

    stats = await store.get_graph_stats()

    return {
        "workspace": workspace,
        "artifact": str(artifact),
        "cleared": clear,
        "embedded": embedded_count,
        "resolved_ratio": resolved_ratio,
        "summary": summary.to_dict(),
        "store_stats": stats,
    }
