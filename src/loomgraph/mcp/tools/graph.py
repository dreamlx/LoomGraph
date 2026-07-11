"""MCP tool: `graph` — walk callers / callees of a known entity.

Wraps `loomgraph.cli._search._async_graph_query` directly.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._search import _async_graph_query
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

TOOL_SPEC = Tool(
    name="loomgraph_graph",
    title="Walk graph relations from an entity",
    description=(
        "Walk CALLS / INHERITS / IMPORTS edges of a SPECIFIC entity in the "
        "loomgraph workspace. Returns callers (who calls this) and/or "
        "callees (who this calls). Use AFTER `loomgraph_find` so you have "
        "the exact qualified entity name. Direction defaults to `both`; "
        "relation type defaults to `all`."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "entity_name": {
                "type": "string",
                "description": (
                    "Qualified entity name (e.g. `module.Class.method` or "
                    "`function_name`). Use `loomgraph_find` first if unsure."
                ),
            },
            "direction": {
                "type": "string",
                "enum": ["callers", "callees", "both"],
                "description": "Which side of the graph to walk. Default both.",
                "default": "both",
            },
            "relation_type": {
                "type": "string",
                "enum": ["CALLS", "INHERITS", "IMPORTS", "all"],
                "description": "Filter by relation type. Default all.",
                "default": "all",
            },
            "include_unresolved": {
                "type": "boolean",
                "description": (
                    "Include unresolved/ambiguous low-trust edges. Their "
                    "targets are call expressions (dst_raw) that may not be "
                    "in-repo entities, so they surface as phantom callees/"
                    "callers with source_id=\"\". Default false (resolved only)."
                ),
                "default": False,
            },
            "workspace": {
                "type": "string",
                "description": "Override the workspace to query.",
            },
        },
        "required": ["entity_name"],
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    entity_name = arguments["entity_name"]
    direction = arguments.get("direction", "both")
    relation_type = arguments.get("relation_type", "all")
    include_unresolved = arguments.get("include_unresolved", False)
    workspace = resolve_workspace(arguments)

    return await safe_call(
        lambda: _async_graph_query(
            entity_name=entity_name,
            direction=direction,
            relation_type=relation_type,
            workspace=workspace,
            include_unresolved=include_unresolved,
        ),
        failure_code="GRAPH_FAILED",
        failure_hint=(
            "If `callers_count` is 0 but you expect callers, try "
            "`loomgraph_find` to confirm the exact entity name "
            "(qualified names like `module.Class.method` are required)."
        ),
    )
