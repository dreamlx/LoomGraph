"""LoomGraph MCP server.

Exposes loomgraph's read-side query surface as MCP tools so AI agents
(Claude Code, Codex, Cursor) can call `find` / `graph` / `topology` /
`impact` / `deps` / `overview` / `workspace_*` as native tools without
the ~250ms Python-startup penalty per CLI subprocess invocation.

Read tools stay dependency-light (no codeindex needed). `refresh`
(`loomgraph_refresh`) is the sole write tool: it shells codeindex to
re-ingest the working tree on agent demand (pull-mode complement to the
commit-driven git-hook `update`), so the MCP server now requires codeindex
*only when refresh is invoked* — query-only deployments still work without
it. See ADR-014 and docs/api/MCP_DESIGN.md for the contract.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from loomgraph import __version__
from loomgraph.mcp.tools import branch_diff as t_branch_diff
from loomgraph.mcp.tools import check as t_check
from loomgraph.mcp.tools import debt as t_debt
from loomgraph.mcp.tools import debt_audit as t_debt_audit
from loomgraph.mcp.tools import deps as t_deps
from loomgraph.mcp.tools import evolution_track as t_evolution_track
from loomgraph.mcp.tools import find as t_find
from loomgraph.mcp.tools import git_metrics as t_git_metrics
from loomgraph.mcp.tools import graph as t_graph
from loomgraph.mcp.tools import impact as t_impact
from loomgraph.mcp.tools import overview as t_overview
from loomgraph.mcp.tools import refresh as t_refresh
from loomgraph.mcp.tools import search as t_search
from loomgraph.mcp.tools import sync_advice as t_sync_advice
from loomgraph.mcp.tools import topology as t_topology
from loomgraph.mcp.tools import workspace as t_workspace

logger = logging.getLogger(__name__)

SERVER_NAME = "loomgraph"
SERVER_INSTRUCTIONS = (
    "LoomGraph is for structure and time, not line-oriented lookup. Use it for "
    "cross-file relationships, caller/callee or change impact, module dependencies "
    "and topology, or branch/history comparison. Use loomgraph_find to resolve an "
    "entity before loomgraph_graph. Use ordinary text tools for an exact text, string, "
    "or single-file lookup. Check freshness when the working tree may have changed, "
    "and report any trust or uncertainty fields returned by the tool. Do not treat an "
    "empty, failed, stale, or partial graph result as evidence that no relationship exists."
)

# Registry of available tools. Each entry: (Tool spec, async handler).
# When adding a new tool, add its module to loomgraph.mcp.tools and
# register it here.
_TOOL_HANDLERS: dict[str, Any] = {}
_TOOL_SPECS: list[Tool] = []


def _register(spec: Tool, handler: Any) -> None:
    _TOOL_SPECS.append(spec)
    _TOOL_HANDLERS[spec.name] = handler


_register(t_find.TOOL_SPEC, t_find.handle)
_register(t_search.TOOL_SPEC, t_search.handle)
_register(t_graph.TOOL_SPEC, t_graph.handle)
_register(t_topology.TOOL_SPEC, t_topology.handle)
_register(t_impact.TOOL_SPEC, t_impact.handle)
_register(t_deps.TOOL_SPEC, t_deps.handle)
_register(t_overview.TOOL_SPEC, t_overview.handle)
# Debt-surface read primitives (#62) — each dimension also reachable via
# the loomgraph_debt_audit composite; exposed standalone so sessions
# without the composite loaded can still reach them.
_register(t_debt.TOOL_SPEC, t_debt.handle)
_register(t_check.TOOL_SPEC, t_check.handle)
_register(t_git_metrics.TOOL_SPEC, t_git_metrics.handle)
# Write tools (see ADR-014 and EPIC-016 #191)
_register(t_refresh.TOOL_SPEC, t_refresh.handle)
_register(t_branch_diff.TOOL_SPEC, t_branch_diff.handle)
_register(t_workspace.LIST_SPEC, t_workspace.list_handle)
_register(t_workspace.INFO_SPEC, t_workspace.info_handle)
# Composite tools (v0.12.1) — multi-dimension reports
_register(t_debt_audit.TOOL_SPEC, t_debt_audit.handle)
_register(t_evolution_track.TOOL_SPEC, t_evolution_track.handle)
_register(t_sync_advice.TOOL_SPEC, t_sync_advice.handle)


# Tools that overlap codegraph's `codegraph_explore` (single-tool structural
# queries, fresh per-call). On a codegraph-backed workspace these are unlisted
# so an agent picks the narrower, fresher codegraph tool instead of diluting
# its salience across two near-identical query surfaces (#152 adaptive surface).
# Unlisted ≠ removed: call_tool still serves them, and LOOMGRAPH_MCP_TOOLS=all
# forces the full list (parity with codegraph's CODEGRAPH_MCP_TOOLS philosophy).
_CODEGRAPH_OVERLAP_TOOLS = {"loomgraph_find", "loomgraph_graph"}
ALL_TOOLS_ENV = "LOOMGRAPH_MCP_TOOLS"
ALLOWED_TOOLS_ENV = "LOOMGRAPH_MCP_ALLOWED_TOOLS"


def _allowed_tool_names() -> set[str] | None:
    """Return an optional fail-closed server allowlist from the environment."""
    import os

    raw = os.environ.get(ALLOWED_TOOLS_ENV)
    if raw is None:
        return None
    return {name.strip() for name in raw.split(",") if name.strip()} & set(_TOOL_HANDLERS)


def _tool_is_allowed(name: str) -> bool:
    allowed = _allowed_tool_names()
    return allowed is None or name in allowed


def build_server() -> Server:
    """Construct the MCP Server instance with all tools registered.

    Factored out so tests can introspect the server without starting
    stdio I/O.
    """

    async def list_tools(ctx: Any, params: Any) -> ListToolsResult:
        return ListToolsResult(tools=_visible_tool_specs())

    async def call_tool(ctx: Any, params: Any) -> CallToolResult:
        name = params.name
        arguments = params.arguments or {}
        if not _tool_is_allowed(name):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "success": False,
                                "error": {
                                    "code": "TOOL_NOT_ALLOWED",
                                    "message": f"Tool {name!r} is not enabled for this server.",
                                },
                            }
                        ),
                    )
                ]
            )
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "success": False,
                                "error": {
                                    "code": "UNKNOWN_TOOL",
                                    "message": f"No tool registered as {name!r}.",
                                    "known_tools": sorted(_TOOL_HANDLERS),
                                },
                            }
                        ),
                    )
                ]
            )
        content = await handler(arguments)
        return CallToolResult(content=content)

    # mcp 2.0: handlers are constructor params (on_*), not decorators.
    return Server(
        SERVER_NAME,
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def _visible_tool_specs() -> list[Tool]:
    """The tool list an agent sees, minus codegraph-overlap tools when the
    active workspace is codegraph-backed (#152).

    Detection reads the workspace's ``extraction_backend`` meta (the same
    signal `update`/`refresh` route on) — NOT cwd/``which codegraph``, which
    are unreliable (serve cwd ≠ queried workspace; installed-for-another-
    project would hide tools on every codeindex workspace). LOOMGRAPH_MCP_TOOLS
    =all forces the full list. Falls back to the full list when the workspace
    can't be opened (no workspace yet, or non-codegraph) — the default stays
    the full list until a codegraph workspace is actually queried.

    NOTE: callers may be sync (tests) or async (the real ``list_tools``
    handler runs inside the MCP event loop). The event-loop case is why this
    returns a non-coroutine but defers the meta read to a thread —
    ``asyncio.run()`` inside an active loop raises ``RuntimeError``, which
    the bare ``except`` would swallow, silently defeating the unlist (codex
    review #172).
    """
    import os

    allowed = _allowed_tool_names()
    if allowed is not None:
        return [tool for tool in _TOOL_SPECS if tool.name in allowed]
    if os.environ.get(ALL_TOOLS_ENV, "").lower() == "all":
        return list(_TOOL_SPECS)
    if not _active_workspace_is_codegraph():
        return list(_TOOL_SPECS)
    return [t for t in _TOOL_SPECS if t.name not in _CODEGRAPH_OVERLAP_TOOLS]


def _active_workspace_is_codegraph() -> bool:
    """True when the active workspace's recorded extraction_backend is codegraph.

    Resolves the workspace the same way the query tools do (per-call arg >
    server default env > CLI auto-detect from cwd/git), opens it, and reads
    the meta. Any failure (no workspace, unreadable, no meta) → False (the
    default full list is the safe fallback).

    The SQLite read runs via ``asyncio.run``. When ``list_tools`` is already
    inside the MCP event loop, ``asyncio.run`` raises ``RuntimeError``; we
    catch that and run the peek in a worker thread (which has no event loop,
    so ``asyncio.run`` works there). Without this the RuntimeError was
    swallowed → codegraph workspaces always saw the full list (codex review
    #172 — adaptive unlist was nonfunctional).
    """
    import os

    from loomgraph.cli._common import get_auto_workspace
    from loomgraph.mcp.tools._common import DEFAULT_WORKSPACE_ENV

    ws_arg = os.environ.get(DEFAULT_WORKSPACE_ENV)
    ws = ws_arg or get_auto_workspace(None)
    if not ws:
        return False
    return _detect_backend_sync(ws) == "codegraph"


def _detect_backend_sync(ws: str) -> str | None:
    """Run the meta peek, handling the nested-event-loop case by thread-fallback.

    When the MCP ``list_tools`` handler is already inside the event loop,
    ``asyncio.run`` would raise (and the already-created coroutine would
    warn "never awaited"). Detect the running loop first and route to a
    worker thread up front (codex review #172)."""
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False

    if not in_loop:
        try:
            return asyncio.run(_peek_backend_meta(ws))
        except Exception:
            return None

    # We're inside the MCP event loop — run in a worker thread (which has
    # no loop, so asyncio.run works there).
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(
            lambda: asyncio.run(_peek_backend_meta(ws))
        ).result()


async def _peek_backend_meta(ws: str) -> str | None:
    """Open ``ws`` and return its recorded extraction_backend meta (or None)."""
    from loomgraph.storage.factory import create_graph_store

    store = await create_graph_store(workspace=ws)
    try:
        get_meta = getattr(store, "get_meta", None)
        if get_meta is None:
            return None
        recorded = await get_meta("extraction_backend")
        return str(recorded) if recorded else None
    finally:
        close = getattr(store, "close", None)
        if close is not None:
            await close()


async def serve_stdio() -> None:
    """Entry point: serve over stdio. Used by `loomgraph mcp serve`."""
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
