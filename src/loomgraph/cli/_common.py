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

    # Auto-detect from current directory name (lowercase for LightRAG compatibility)
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
    client: Any,  # LightRAGClient
    allow_fallback: bool = True,
) -> str:
    """Resolve workspace with fallback to main branches.

    Workflow:
    1. Check if target workspace exists (entity_count > 0)
    2. If not and allow_fallback=True, try main/develop/master
    3. Raise error if no valid workspace found

    Args:
        workspace: Target workspace (e.g. "myproject:feature-A")
        client: LightRAG client instance
        allow_fallback: Enable fallback to default branches (default: True)

    Returns:
        Resolved workspace name (may be different from input if fallback occurred)

    Raises:
        click.ClickException: No valid workspace found

    Example:
        >>> ws = await resolve_workspace_with_fallback("myproject:feature-A", client)
        ℹ️  Workspace 'myproject:feature-A' not found, using 'myproject:main'
        >>> ws
        'myproject:main'
    """
    # Check if target workspace has data
    try:
        stats = await client.get_graph_stats()
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
                stats = await client.get_graph_stats()
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
# Client Factory (v0.9.2 — DRY refactor)
# ============================================

def create_client(
    workspace: str | None = None,
    api_url: str | None = None,
) -> Any:
    """Create a LightRAGClient with settings from config.

    Args:
        workspace: Optional workspace name (auto-detected if None)
        api_url: Optional API URL override (uses config if None)

    Returns:
        Configured LightRAGClient instance
    """
    from loomgraph.core.config import get_settings
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    url = api_url or settings.lightrag.api_url
    ws = get_auto_workspace(workspace) if workspace is not None else None

    return LightRAGClient(
        base_url=url,
        timeout=settings.lightrag.api_timeout,
        workspace=ws,
    )


async def prepare_workspace_client(
    workspace: str | None = None,
) -> tuple[str, Any]:
    """Create client and resolve workspace with fallback in one step.

    Replaces the 8-line boilerplate pattern used in query commands.

    Args:
        workspace: Optional workspace name (auto-detected if None)

    Returns:
        Tuple of (resolved_workspace, configured_client)
    """
    from loomgraph.core.config import get_settings
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    ws = get_auto_workspace(workspace)
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=ws,
    )

    ws = await resolve_workspace_with_fallback(ws, client, allow_fallback=True)
    client.workspace = ws

    return ws, client


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
    LIGHTRAG_ERROR = "LIGHTRAG_ERROR"
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
