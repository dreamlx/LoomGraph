"""Shared helpers for MCP tool handlers.

Centralizes:
- JSON response shaping (success / error envelopes matching CLI output)
- Async-core error catching (turn exceptions into structured errors)
- Workspace resolution: per-call → server default → CLI fallback
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.types import TextContent

# Server-level default workspace; can be overridden by env var so users
# starting `loomgraph mcp serve` from a particular project see it
# auto-selected. Per-call `workspace` argument always wins over this.
DEFAULT_WORKSPACE_ENV = "LOOMGRAPH_MCP_DEFAULT_WORKSPACE"


def resolve_workspace(arguments: dict[str, Any]) -> str | None:
    """Per-call workspace argument > server default env var > None (let
    CLI auto-detect from cwd / git branch as today)."""
    ws = arguments.get("workspace")
    if ws:
        return ws
    return os.environ.get(DEFAULT_WORKSPACE_ENV)


def success_response(data: dict[str, Any]) -> list[TextContent]:
    body = json.dumps({"success": True, "data": data}, ensure_ascii=False)
    return [TextContent(type="text", text=body)]


def error_response(
    code: str, message: str, *, suggestion: str | None = None
) -> list[TextContent]:
    err: dict[str, Any] = {"code": code, "message": message}
    if suggestion:
        err["suggestion"] = suggestion
    body = json.dumps({"success": False, "error": err}, ensure_ascii=False)
    return [TextContent(type="text", text=body)]


async def safe_call(
    coro_factory: Any,
    *,
    failure_code: str,
    failure_hint: str | None = None,
) -> list[TextContent]:
    """Run a coroutine factory, wrap any exception into an error envelope.

    Patterns the CLI's `output_error(...)` does at the top of each
    subcommand. The MCP server hands a structured error back to the
    agent so it can recover rather than crashing the entire session.
    """
    try:
        result = await coro_factory()
    except Exception as exc:  # noqa: BLE001 — boundary handler
        return error_response(
            code=failure_code,
            message=f"{type(exc).__name__}: {exc}",
            suggestion=failure_hint,
        )
    return success_response(result)
