"""Backend factory — instantiate GraphStore + LLMClient from settings.

Encapsulates the LightRAG vs SQLite branch so CLI/core code doesn't have
to know which backend it's running against (EPIC-011 / ADR-013).
"""

from __future__ import annotations

from pathlib import Path

from loomgraph.core.config import get_settings
from loomgraph.core.lightrag_client import LightRAGClient
from loomgraph.llm.base import LLMClient
from loomgraph.llm.lightrag_llm import LightRAGLLMClient
from loomgraph.storage.base import GraphStore
from loomgraph.storage.lightrag_store import LightRAGGraphStore
from loomgraph.storage.sqlite_store import SqliteGraphStore


def _resolve_db_path(template: str, workspace: str | None) -> Path:
    """Expand the sqlite db_path template (`~` + `{workspace}`)."""
    expanded = Path(template).expanduser()
    if "{workspace}" in str(expanded) and workspace:
        expanded = Path(str(expanded).replace("{workspace}", workspace))
    return expanded


async def create_graph_store(workspace: str | None = None) -> GraphStore:
    """Instantiate a GraphStore per `settings.storage.backend`.

    For `sqlite`, the database file is created if missing and `initialize()`
    is awaited so the returned store is ready to use. For `lightrag`, the
    backing HTTPClient is constructed with the configured base_url/timeout/
    workspace.
    """
    settings = get_settings()
    backend = settings.storage.backend

    if backend == "lightrag":
        client = LightRAGClient(
            base_url=settings.lightrag.api_url,
            timeout=settings.lightrag.api_timeout,
            workspace=workspace,
        )
        return LightRAGGraphStore(client)

    if backend == "sqlite":
        path = _resolve_db_path(settings.storage.db_path, workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        store = SqliteGraphStore(
            db_path=path,
            workspace_root=path.parent,
        )
        await store.initialize()
        return store

    raise ValueError(f"Unknown storage.backend: {backend!r}")


def create_llm_client(workspace: str | None = None) -> LLMClient:
    """Instantiate an LLMClient.

    Phase 1 only ships the LightRAG adapter (mode=local for overview/impact
    compatibility). Phase 4 adds DirectLLMClient that bypasses LightRAG.
    """
    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=workspace,
    )
    return LightRAGLLMClient(client)
