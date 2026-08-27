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
    """Expand the sqlite db_path template (`~` + `{workspace}`).

    Path separators in the workspace name are sanitized (#99): a git branch
    like ``codex/foo`` would otherwise turn into a subdirectory and the DB
    becomes undiscoverable (workspace list scans top-level ``*.db`` only).
    """
    expanded = Path(template).expanduser()
    if "{workspace}" in str(expanded):
        if not workspace:
            # #176: fail loud — silently proceeding created a literal
            # ~/.loomgraph/{workspace}.db shared by every None-caller.
            raise ValueError(
                "db_path template contains {workspace} but no workspace "
                "name was given — resolve the workspace (e.g. "
                "get_auto_workspace) before creating the store"
            )
        safe_workspace = workspace.replace("\\", "/").replace("/", "-")
        expanded = Path(str(expanded).replace("{workspace}", safe_workspace))
    return expanded


def workspace_exists(workspace: str) -> bool:
    """Return whether a workspace database already exists without opening it."""
    if not workspace:
        return False
    settings = get_settings()
    return _resolve_db_path(settings.storage.db_path, workspace).is_file()


async def create_graph_store(workspace: str | None = None) -> GraphStore:
    """Instantiate the SQLite-backed GraphStore.

    Creates the parent directory if missing and awaits `initialize()` so
    the returned store is ready to use. vec0 dimension is read from
    `settings.embedding.dimension`; mismatch with an existing .db raises
    `SqliteDimensionMismatch`.
    """
    settings = get_settings()
    if workspace is None:
        # Discovery handle (#176): in-memory store whose workspace_root is
        # the template's directory — list_workspaces() scans *.db without
        # ever creating a literal {workspace}.db file on disk.
        root = Path(settings.storage.db_path).expanduser().parent
        root.mkdir(parents=True, exist_ok=True)
        store = SqliteGraphStore(
            db_path=":memory:",
            workspace_root=root,
            dimension=settings.embedding.dimension,
        )
        await store.initialize()
        return store
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
    if e.provider == "builtin":
        # #158: local CodeRankEmbed int8 ONNX (needs the [embed] extra);
        # `auto` never reaches here — it resolves sticky in
        # embedding.resolve (needs the store for meta).
        from loomgraph.embedding.builtin import BuiltinEmbeddingClient

        return BuiltinEmbeddingClient()
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
