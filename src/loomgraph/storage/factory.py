"""Backend factory — instantiate GraphStore + LLMClient from settings.

Phase 5 (EPIC-011 / ADR-013): only sqlite is supported. The LightRAG
adapter, client, and config branch were removed in v0.10.0.
"""

from __future__ import annotations

from pathlib import Path

from loomgraph.core.config import get_settings
from loomgraph.llm.base import LLMClient
from loomgraph.llm.direct import DirectLLMClient
from loomgraph.storage.base import GraphStore
from loomgraph.storage.sqlite_store import SqliteGraphStore


def _resolve_db_path(template: str, workspace: str | None) -> Path:
    """Expand the sqlite db_path template (`~` + `{workspace}`)."""
    expanded = Path(template).expanduser()
    if "{workspace}" in str(expanded) and workspace:
        expanded = Path(str(expanded).replace("{workspace}", workspace))
    return expanded


async def create_graph_store(workspace: str | None = None) -> GraphStore:
    """Instantiate the SQLite-backed GraphStore.

    Creates the parent directory if missing and awaits `initialize()` so
    the returned store is ready to use.
    """
    settings = get_settings()
    path = _resolve_db_path(settings.storage.db_path, workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteGraphStore(
        db_path=path,
        workspace_root=path.parent,
    )
    await store.initialize()
    return store


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
