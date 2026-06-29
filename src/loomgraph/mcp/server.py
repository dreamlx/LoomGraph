"""LoomGraph MCP server.

Exposes loomgraph's read-side query surface as MCP tools so AI agents
(Claude Code, Codex, Cursor) can call `find` / `graph` / `topology` /
`impact` / `deps` / `overview` / `workspace_*` as native tools without
the ~250ms Python-startup penalty per CLI subprocess invocation.

Write tools (`index`, `update`, `import-export`) are intentionally
NOT exposed via MCP — they're slow, mutating, and require codeindex.
Keeping them CLI-only lets the MCP server runtime dependency tree
stay small (no codeindex required for query-only users).

See docs/api/MCP_DESIGN.md for the contract.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from loomgraph.mcp.tools import find as t_find
from loomgraph.mcp.tools import graph as t_graph

logger = logging.getLogger(__name__)

SERVER_NAME = "loomgraph"
SERVER_VERSION = "0.12.0"

# Registry of available tools. Each entry: (Tool spec, async handler).
# When adding a new tool, add its module to loomgraph.mcp.tools and
# register it here.
_TOOL_HANDLERS: dict[str, Any] = {}
_TOOL_SPECS: list[Tool] = []


def _register(spec: Tool, handler: Any) -> None:
    _TOOL_SPECS.append(spec)
    _TOOL_HANDLERS[spec.name] = handler


_register(t_find.TOOL_SPEC, t_find.handle)
_register(t_graph.TOOL_SPEC, t_graph.handle)


def build_server() -> Server:
    """Construct the MCP Server instance with all tools registered.

    Factored out so tests can introspect the server without starting
    stdio I/O.
    """
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return list(_TOOL_SPECS)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return [
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
        return await handler(arguments or {})

    return server


async def serve_stdio() -> None:
    """Entry point: serve over stdio. Used by `loomgraph mcp serve`."""
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
