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

    Backend-agnostic counterpart to `prepare_workspace_client`. Candidate
    workspaces are checked on disk before opening a store; the first existing
    workspace with entities wins, including the main/develop/master fallback.

    Returns:
        (resolved_workspace, GraphStore)
    """
    from loomgraph.storage.factory import create_graph_store, workspace_exists

    ws = get_auto_workspace(workspace)
    if ws is None:
        ws = ""

    candidates = [ws]
    if ":" in ws:
        project = ws.split(":")[0]
        candidates.extend(
            f"{project}:{branch}"
            for branch in ("main", "develop", "master")
            if f"{project}:{branch}" != ws
        )

    for candidate in candidates:
        # A query must establish that a workspace exists before creating or
        # opening a store: SQLite connect + schema initialization creates a
        # file for a missing workspace (#235).
        if not workspace_exists(candidate):
            continue

        store = await create_graph_store(workspace=candidate)
        try:
            resolved = await resolve_workspace_with_fallback(
                candidate, store, allow_fallback=False
            )
        except click.ClickException:
            close = getattr(store, "close", None)
            if close is not None:
                await close()
            continue

        if resolved != ws:
            click.echo(
                f"ℹ️  Workspace '{ws}' not found, using '{resolved}'",
                err=True,
            )
        return resolved, store

    raise click.ClickException(
        "No workspace found for project. "
        "Index the codebase first: loomgraph index ."
    )


async def read_resolution_metadata(store: Any) -> dict[str, float] | None:
    """Read the complete persisted resolution split, if the store has one."""
    get_meta = getattr(store, "get_meta", None)
    if get_meta is None:
        return None
    values: dict[str, float] = {}
    for key in (
        "resolved_ratio",
        "internal_unresolved_ratio",
        "external_unresolved_ratio",
    ):
        try:
            raw = await get_meta(key)
            if raw is None or raw == "":
                return None
            values[key] = float(raw)
        except Exception:  # noqa: BLE001 - metadata is advisory
            return None
    return values


def create_llm_client_for_workspace(workspace: str | None = None) -> Any:
    """Create an `LLMClient` bound to `workspace`."""
    from loomgraph.storage.factory import create_llm_client

    return create_llm_client(workspace=workspace)


# Re-exported from core so the graph-export ingestion pipeline can share the
# same embedding step without a core→cli import cycle. Callers that import
# `from loomgraph.cli._common import maybe_embed_entities` keep working.
from loomgraph.core.embedding_pipeline import maybe_embed_entities  # noqa: E402,F401

# ============================================
# Error Codes (from CLI_DESIGN.md)
# ============================================

class ErrorCode:
    """Structured error codes for AI Agent parsing."""

    CODEINDEX_NOT_FOUND = "CODEINDEX_NOT_FOUND"
    CODEINDEX_FAILED = "CODEINDEX_FAILED"
    CODEGRAPH_FAILED = "CODEGRAPH_FAILED"
    CODEINDEX_TIMEOUT = "CODEINDEX_TIMEOUT"
    EMBEDDING_SERVICE_UNAVAILABLE = "EMBEDDING_SERVICE_UNAVAILABLE"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    EMBEDDING_NOT_INDEXED = "EMBEDDING_NOT_INDEXED"
    DATABASE_CONNECTION_FAILED = "DATABASE_CONNECTION_FAILED"
    DATABASE_ERROR = "DATABASE_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    DEPENDENCIES_MISSING = "DEPENDENCIES_MISSING"
    GIT_ERROR = "GIT_ERROR"
    NO_CHANGES = "NO_CHANGES"
    GRAPH_EXPORT_EMPTY = "GRAPH_EXPORT_EMPTY"
    HOOK_INSTALL_FAILED = "HOOK_INSTALL_FAILED"


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
