"""Embedding attachment for entity dicts (settings-gated).

Lives in `core/` (not `cli/`) so the graph-export ingestion pipeline
(`core/graph_export_ingest.py`) can call it without a core→cli import cycle.
`cli/_common.py` re-exports `maybe_embed_entities` for backwards-compatible
callers (`loomgraph index` / `update` / `import-export`).
"""

from __future__ import annotations

from typing import Any


async def maybe_embed_entities(
    entities: list[dict[str, Any]], store: Any = None
) -> int:
    """Attach embeddings to entity dicts in place.

    Gated on `settings.embedding.enabled` (default False) — pipx install
    yields a fully usable LoomGraph with no embedding service running.
    When enabled, embedding failure logs a warning and returns 0 —
    entity rows still write, the vec0 column just stays empty.

    #158: when a ``store`` is passed and the provider is ``auto`` (default),
    resolution is sticky per workspace (config > ollama-probe > builtin)
    and persists the choice into workspace meta — embedding spaces are
    provider-specific and must never silently mix.
    Returns count of embeddings attached.
    """
    import logging

    from loomgraph.core.config import get_settings

    # Lazy import so tests that patch `loomgraph.storage.factory
    # .create_embedding_client` (the source attribute) are observed —
    # a module-level binding would capture the original at import time.
    from loomgraph.storage.factory import create_embedding_client

    settings = get_settings()
    if not settings.embedding.enabled:
        return 0

    targets: list[tuple[int, dict[str, Any]]] = [
        (i, e)
        for i, e in enumerate(entities)
        if e.get("description") and "embedding" not in e
    ]
    if not targets:
        return 0

    texts = [e["description"] for _, e in targets]

    # Deterministic config/asset errors fail loud (#158 review C1-3):
    # missing [embed] extra, unreachable model sources, sha mismatch,
    # unknown-space workspaces. Swallowing these would report a green
    # index with zero vectors.
    from loomgraph.embedding.builtin import BuiltinEmbeddingError
    from loomgraph.embedding.model_source import ModelDownloadError
    from loomgraph.embedding.resolve import EmbeddingSpaceUnknownError

    try:
        if store is not None and settings.embedding.provider == "auto":
            from loomgraph.embedding.resolve import resolve_embedding_client

            cm = await resolve_embedding_client(store)
            async with cm as (client, _provider):
                result = await client.embed(texts)
        else:
            async with create_embedding_client() as client:
                result = await client.embed(texts)
    except (BuiltinEmbeddingError, ModelDownloadError, EmbeddingSpaceUnknownError):
        raise
    except Exception as ex:
        logging.getLogger(__name__).warning(
            "Embedding skipped (%s entities): %s", len(targets), ex
        )
        return 0

    attached = 0
    for (i, _entity), emb in zip(targets, result.embeddings, strict=False):
        # Skip degenerate (zero/near-zero) vectors — a provider can return
        # 200-OK-but-empty under load, which would poison KNN (every query
        # lands at distance ~1.0). Attach only real vectors to keep vec0 clean.
        if emb and sum(x * x for x in emb) > 0:
            entities[i]["embedding"] = emb
            attached += 1
    return attached
