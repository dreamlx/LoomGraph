"""Backend factory — instantiate GraphStore + LLMClient from settings.

Phase 5 (EPIC-011 / ADR-013): only sqlite is supported. The LightRAG
adapter, client, and config branch were removed in v0.10.0.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loomgraph.core.config import get_settings
from loomgraph.llm.base import LLMClient
from loomgraph.llm.direct import DirectLLMClient
from loomgraph.storage.base import GraphStore
from loomgraph.storage.sqlite_store import SqliteGraphStore

if TYPE_CHECKING:
    from loomgraph.embedding.base import EmbeddingClient


def _resolve_db_path(template: str, workspace: str | None) -> Path:
    """Expand the sqlite db_path template (`~` + `{workspace}`)."""
    expanded = Path(template).expanduser()
    if "{workspace}" in str(expanded) and workspace:
        expanded = Path(str(expanded).replace("{workspace}", workspace))
    return expanded


async def create_graph_store(workspace: str | None = None) -> GraphStore:
    """Instantiate the SQLite-backed GraphStore.

    Creates the parent directory if missing and awaits `initialize()` so
    the returned store is ready to use. vec0 dimension is read from
    `settings.embedding.dimension`; mismatch with an existing .db raises
    `SqliteDimensionMismatch`.
    """
    settings = get_settings()
    path = _resolve_db_path(settings.storage.db_path, workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteGraphStore(
        db_path=path,
        workspace_root=path.parent,
        dimension=settings.embedding.dimension,
    )
    await store.initialize()
    return store


def create_embedding_client() -> EmbeddingClient:
    """Instantiate a `DirectEmbeddingClient` per `settings.embedding`.

    Honors `embedding.enabled` upstream — this helper assumes the caller
    already decided to embed; the caller is responsible for checking
    `settings.embedding.enabled` first to avoid pointless construction.
    """
    from loomgraph.embedding.direct import DirectEmbeddingClient

    settings = get_settings()
    e = settings.embedding
    return DirectEmbeddingClient(
        base_url=e.api_url,
        model=e.model,
        api_key=e.api_key,
        timeout=e.timeout,
        batch_size=e.batch_size,
        dimension=e.dimension,
        max_length=e.max_length,
    )


def create_llm_client(workspace: str | None = None) -> LLMClient:
    """Instantiate the configured LLMClient.

    `workspace` is accepted for API symmetry but ignored — DirectLLMClient
    has no retrieval scope.
    """
    del workspace
    settings = get_settings()
    return DirectLLMClient(
        base_url=settings.llm.api_url,
        model=settings.llm.model,
        api_key=settings.llm.api_key,
        timeout=settings.llm.timeout,
        max_tokens=settings.llm.max_tokens,
        temperature=settings.llm.temperature,
    )
