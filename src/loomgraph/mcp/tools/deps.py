"""MCP tool: `deps` — module-level dependency map."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._analysis import _async_deps
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

DEFAULT_DEPTH = 2

TOOL_SPEC = Tool(
    name="loomgraph_deps",
    title="Module dependency map",
    description=(
        "Cross-module dependency graph aggregated from CALLS / IMPORTS / "
        "INHERITS edges. Returns each module with its inbound + outbound "
        "module dependencies up to N hops. Good for architectural review "
        "or detecting hidden coupling."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "depth": {
                "type": "integer",
                "description": "Module-traversal depth. Default 2.",
                "default": DEFAULT_DEPTH,
                "minimum": 1,
                "maximum": 5,
            },
            "workspace": {"type": "string"},
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    depth = arguments.get("depth", DEFAULT_DEPTH)
    workspace = resolve_workspace(arguments)
    return await safe_call(
        lambda: _async_deps(depth=depth, workspace=workspace),
        failure_code="DEPS_FAILED",
        failure_hint="Confirm the workspace is indexed: `loomgraph workspace info`.",
    )
