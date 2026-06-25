"""Common helpers shared across CLI submodules."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import click


def _setup_logging(verbose: bool, quiet: bool) -> None:
    """Configure logging to stderr only.

    Ensures JSON output on stdout is never polluted by log messages.
    """
    if quiet:
        logging.disable(logging.CRITICAL)
        return

    level = logging.DEBUG if verbose else logging.WARNING
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logging.root.handlers = [handler]
    logging.root.setLevel(level)


# ============================================
# Workspace Auto-Detection
# ============================================

def get_auto_workspace(workspace: str | None) -> str | None:
    """Get workspace, auto-detecting from current directory if not specified.

    Priority:
    1. Explicit --workspace argument
    2. cwd.name:branch (git repository)
    3. cwd.name (non-git fallback)

    Returns:
        Workspace name or None for default
    """
    if workspace:
        return workspace

    # Auto-detect from current directory name (lowercase — workspace names
    cwd = Path.cwd()
    ws_name = cwd.name.lower()

    try:
        from loomgraph.core.git import get_current_branch, is_git_repository

        if is_git_repository(cwd):
            branch = get_current_branch(cwd)
            ws_name = f"{ws_name}:{branch}"
    except Exception:
        pass  # fallback to dir name only

    return ws_name


async def resolve_workspace_with_fallback(
    workspace: str,
    store: Any,  # GraphStore
    allow_fallback: bool = True,
) -> str:
    """Resolve workspace with fallback to main branches.

    Workflow:
    1. Check if target workspace has data (entity_count > 0)
    2. If not and allow_fallback=True, try main/develop/master
    3. Raise error if no valid workspace found
    """
    # Check if target workspace has data
    try:
        stats = await store.get_graph_stats()
        entity_count = stats.get("entity_count") or stats.get("total_entities", 0)

        if entity_count > 0:
            return workspace
    except Exception:
        # API error - treat as empty workspace
        pass

    # No fallback - raise error immediately
    if not allow_fallback:
        raise click.ClickException(
            f"Workspace '{workspace}' is empty or not found. "
            f"Create it with: loomgraph index ."
        )

    # Try fallback to main branches
    if ":" in workspace:
        project = workspace.split(":")[0]
        for branch in ["main", "develop", "master"]:
            fallback = f"{project}:{branch}"
            if fallback == workspace:
                continue  # skip if already tried

            try:
                stats = await store.get_graph_stats()
                entity_count = stats.get("entity_count") or stats.get("total_entities", 0)
                if entity_count > 0:
                    click.echo(
                        f"ℹ️  Workspace '{workspace}' not found, using '{fallback}'",
                        err=True,
                    )
                    return fallback
            except Exception:
                continue

    # No valid workspace found
    raise click.ClickException(
        "No workspace found for project. "
        "Index the codebase first: loomgraph index ."
    )


# ============================================
# Store / LLM Factory (v0.10.0 — abstraction-only)
# ============================================


async def prepare_workspace_store(
    workspace: str | None = None,
) -> tuple[str, Any]:
    """Create GraphStore + resolve workspace with fallback.

    Backend-agnostic counterpart to `prepare_workspace_client`. The store
    is built per `settings.storage.backend`, then workspace is resolved
    via fallback (re-creating the store if the workspace changed so the
    underlying connection is bound to the right workspace).

    Returns:
        (resolved_workspace, GraphStore)
    """
    from loomgraph.storage.factory import create_graph_store

    ws = get_auto_workspace(workspace)
    if ws is None:
        ws = ""
    store = await create_graph_store(workspace=ws)

    resolved = await resolve_workspace_with_fallback(ws, store, allow_fallback=True)
    if resolved != ws:
        # Re-create store bound to the fallback workspace
        close = getattr(store, "close", None)
        if close is not None:
            await close()
        store = await create_graph_store(workspace=resolved)

    return resolved, store


def create_llm_client_for_workspace(workspace: str | None = None) -> Any:
    """Create an `LLMClient` bound to `workspace`."""
    from loomgraph.storage.factory import create_llm_client

    return create_llm_client(workspace=workspace)


async def maybe_embed_entities(entities: list[dict[str, Any]]) -> int:
    """Attach OpenAI-compatible embeddings to entity dicts in place.

    Gated on `settings.embedding.enabled` (default False) — pipx install
    yields a fully usable LoomGraph with no embedding service running.
    When enabled, embedding failure logs a warning and returns 0 —
    entity rows still write, the vec0 column just stays empty.
    Returns count of embeddings attached.
    """
    import logging

    from loomgraph.core.config import get_settings

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

    try:
        from loomgraph.storage.factory import create_embedding_client

        async with create_embedding_client() as client:
            result = await client.embed(texts)
    except Exception as ex:
        logging.getLogger(__name__).warning(
            "Embedding skipped (%s entities): %s", len(targets), ex
        )
        return 0

    for (i, _entity), emb in zip(targets, result.embeddings, strict=False):
        entities[i]["embedding"] = emb
    return len(targets)


# ============================================
# Error Codes (from CLI_DESIGN.md)
# ============================================

class ErrorCode:
    """Structured error codes for AI Agent parsing."""

    CODEINDEX_NOT_FOUND = "CODEINDEX_NOT_FOUND"
    CODEINDEX_FAILED = "CODEINDEX_FAILED"
    CODEINDEX_TIMEOUT = "CODEINDEX_TIMEOUT"
    EMBEDDING_SERVICE_UNAVAILABLE = "EMBEDDING_SERVICE_UNAVAILABLE"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    DATABASE_CONNECTION_FAILED = "DATABASE_CONNECTION_FAILED"
    DATABASE_ERROR = "DATABASE_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    DEPENDENCIES_MISSING = "DEPENDENCIES_MISSING"
    GIT_ERROR = "GIT_ERROR"
    NO_CHANGES = "NO_CHANGES"


# ============================================
# JSON Output Helpers
# ============================================

def output_success(data: dict[str, Any]) -> None:
    """Output success response in JSON format."""
    response = {"success": True, "data": data}
    click.echo(json.dumps(response, indent=2, ensure_ascii=False))


def output_error(
    code: str,
    message: str,
    suggestion: str | None = None,
    docs: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Output error response in JSON format."""
    error = {"code": code, "message": message}
    if suggestion:
        error["suggestion"] = suggestion
    if docs:
        error["docs"] = docs

    response: dict[str, Any] = {"success": False, "error": error}
    if data:
        response["data"] = data

    click.echo(json.dumps(response, indent=2, ensure_ascii=False))
    sys.exit(1)


def output_partial_error(
    code: str,
    message: str,
    suggestions: list[str],
    data: dict[str, Any],
) -> None:
    """Output partial error (some operations succeeded, some failed)."""
    response = {
        "success": False,
        "data": data,
        "error": {
            "code": code,
            "message": message,
            "suggestions": suggestions,
        },
    }
    click.echo(json.dumps(response, indent=2, ensure_ascii=False))
    sys.exit(1)
