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
    2. cwd.name-branch (git repository, hyphen separator)
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
            ws_name = f"{ws_name}-{branch}"
    except Exception:
        pass  # fallback to dir name only

    return ws_name


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
