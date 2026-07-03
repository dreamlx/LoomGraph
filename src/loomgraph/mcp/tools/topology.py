"""MCP tool: `topology` — graph topology smells (orphans / hubs / god functions)."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._analysis import _async_topology
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

DEFAULT_HUB_THRESHOLD = 10
DEFAULT_GOD_THRESHOLD = 10

TOOL_SPEC = Tool(
    name="loomgraph_topology",
    title="Graph topology smells",
    description=(
        "Surface structural smells across the workspace: orphan entities "
        "(no callers AND no callees), hub entities (many incoming edges), "
        "god functions (many outgoing edges). Optionally scope to a "
        "module by source_id prefix. Useful for debt audits and "
        "architecture reviews."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "hub_threshold": {
                "type": "integer",
                "description": "Min incoming edges to flag as hub.",
                "default": DEFAULT_HUB_THRESHOLD,
                "minimum": 1,
            },
            "god_threshold": {
                "type": "integer",
                "description": "Min outgoing edges to flag as god function.",
                "default": DEFAULT_GOD_THRESHOLD,
                "minimum": 1,
            },
            "module": {
                "type": "string",
                "description": (
                    "[deprecated, use scope] Optional source_id prefix filter."
                ),
            },
            "scope": {
                "type": "string",
                "description": (
                    "Absolute source_id path prefix to scope to "
                    "(e.g. `src/`, `src/loomgraph/cli/`). Filters "
                    "orphans/hubs/gods + coupling. Recommended over module."
                ),
            },
            "workspace": {"type": "string"},
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    hub = arguments.get("hub_threshold", DEFAULT_HUB_THRESHOLD)
    god = arguments.get("god_threshold", DEFAULT_GOD_THRESHOLD)
    module = arguments.get("module")
    scope = arguments.get("scope")
    workspace = resolve_workspace(arguments)
    return await safe_call(
        lambda: _async_topology(
            hub_threshold=hub,
            god_threshold=god,
            module=module,
            workspace=workspace,
            scope=scope,
        ),
        failure_code="TOPOLOGY_FAILED",
        failure_hint="Confirm the workspace is indexed: `loomgraph workspace info`.",
    )
