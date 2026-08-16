"""CLI command: embed-backfill — populate vec_node_descriptions for
an already-indexed workspace.

EPIC-015 Phase 3 (#70). For a workspace that has entities but no
embedding vectors (e.g. an import-export workspace, which on import
carries no vector data), this command embeds entity descriptions and
writes them to vec_node_descriptions WITHOUT triggering a full reindex.
It does NOT re-parse or re-inject — it only embeds existing entities.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import click

from loomgraph.cli._common import (
    ErrorCode,
    output_error,
    output_success,
    prepare_workspace_store,
)
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings

logger = logging.getLogger(__name__)


@main.command("embed-backfill")
@click.option(
    "--workspace", "-w",
    default=None,
    help="Workspace name (default: auto-detected from current directory)",
)
def embed_backfill(workspace: str | None) -> None:
    """Populate vector embeddings for an already-indexed workspace.

    Embeds entity descriptions that were stored without vectors
    (e.g. workspaces created via `import-export`) and writes them
    to vec_node_descriptions. Does NOT re-parse or re-inject — the
    workspace must already contain entities.

    Idempotent: if the workspace already has vectors, exits cleanly
    without re-embedding.

    Requires LOOMGRAPH_EMBEDDING__ENABLED=true and a configured
    OpenAI-compatible embedding provider.
    """
    try:
        result = asyncio.run(_async_embed_backfill(workspace))
        output_success(result)
    except click.ClickException as e:
        # Workspace not found / empty — same user action as "not indexed"
        output_error(
            code=ErrorCode.EMBEDDING_NOT_INDEXED,
            message=str(e.message),
            suggestion=(
                "Index first: loomgraph index <path>  "
                "(with LOOMGRAPH_EMBEDDING__ENABLED=true for semantic search)."
            ),
        )
    except Exception as e:
        output_error(
            code=ErrorCode.EMBEDDING_FAILED,
            message=f"Embed backfill failed: {e}",
            suggestion=(
                "Check the embedding service is reachable: loomgraph status. "
                "For non-semantic search use: loomgraph find <query>."
            ),
        )


async def _async_embed_backfill(
    workspace: str | None = None,
) -> dict[str, Any]:
    """Core: embed existing entity descriptions, write vectors to vec0.

    Idempotency gate: if ``store.vector_count() > 0``, returns immediately
    with ``"skipped": true`` — no re-embedding, no error.

    Raises ``click.ClickException`` when the workspace has no entities
    (not an embedding issue — the workspace itself is empty/missing).
    """
    ws, store = await prepare_workspace_store(workspace)

    # ---- Idempotency: already embedded ----
    vc = await store.vector_count()
    if vc > 0:
        entities = await store.get_all_entities()
        return {
            "workspace": ws,
            "skipped": True,
            "reason": "workspace already embedded",
            "vector_count": vc,
            "total_entities": len(entities),
        }

    # ---- Embedding must be enabled ----
    settings = get_settings()
    if not settings.embedding.enabled:
        raise click.ClickException(
            "Embedding is not enabled. Set LOOMGRAPH_EMBEDDING__ENABLED=true "
            "and configure LOOMGRAPH_EMBEDDING__API_URL to an OpenAI-compatible "
            "endpoint, then retry."
        )

    # ---- Gather entities with descriptions ----
    entities = await store.get_all_entities()
    if not entities:
        raise click.ClickException(
            f"Workspace '{ws}' has no entities. "
            "Index the codebase first: loomgraph index <path>"
        )

    targets: list[tuple[str, str | None, str]] = []
    for e in entities:
        name = e.get("entity_name", "")
        desc = e.get("description", "")
        if name and desc:
            targets.append((name, e.get("source_id"), desc))

    if not targets:
        return {
            "workspace": ws,
            "embedded": 0,
            "total_entities": len(entities),
            "skipped_reason": "no entities with descriptions",
        }

    # ---- Embed ----
    # #158: sticky resolution for the auto provider (same space as index).
    from loomgraph.embedding.resolve import resolve_embedding_client
    from loomgraph.storage.factory import create_embedding_client

    texts = [t[2] for t in targets]
    try:
        if settings.embedding.provider == "auto":
            cm = await resolve_embedding_client(store)
            async with cm as (client, _provider):
                result = await client.embed(texts)
        else:
            async with create_embedding_client() as client:
                result = await client.embed(texts)
    except Exception:
        logger.warning(
            "Embedding failed for %d entities in workspace '%s'",
            len(targets), ws, exc_info=True,
        )
        raise

    # ---- Write vectors ----
    embedding_tuples: list[tuple[str, str | None, list[float]]] = [
        (name, sid, emb)
        for (name, sid, _desc), emb in zip(targets, result.embeddings, strict=False)
    ]
    written = await store.write_embeddings(embedding_tuples)

    return {
        "workspace": ws,
        "embedded": written,
        "total_entities": len(entities),
        "model": result.model,
    }
