"""MCP tool: `find` — fuzzy entity name match.

Wraps `loomgraph.cli._search._async_find` directly (no subprocess) so
each call costs the SQL round-trip only, not Python startup.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._search import _async_find
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

TOOL_SPEC = Tool(
    name="loomgraph_find",
    title="Find entities by name",
    description=(
        "Fuzzy-match entities (functions, classes, methods, modules) by name "
        "in the loomgraph workspace. Returns up to `limit` matches each with "
        "entity name, type, source_id (file:line), and a relevance score. "
        "Use this FIRST to discover the exact qualified name of an entity "
        "before walking the call graph with `loomgraph_graph`."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Name fragment to fuzzy-match.",
            },
            "entity_type": {
                "type": "string",
                "description": "Optional filter — one of: class | function | method | module.",
                "enum": ["class", "function", "method", "module"],
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of matches to return (default 20).",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
            "with_relations": {
                "type": "boolean",
                "description": (
                    "If true, also include callers + callees for each match. "
                    "Default false to keep responses small."
                ),
                "default": False,
            },
            "workspace": {
                "type": "string",
                "description": (
                    "Override the workspace to query. Default: server's "
                    "configured default or auto-detected from cwd."
                ),
            },
        },
        "required": ["query"],
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    query = arguments["query"]
    entity_type = arguments.get("entity_type")
    limit = arguments.get("limit", 20)
    with_relations = arguments.get("with_relations", False)
    workspace = resolve_workspace(arguments)

    return await safe_call(
        lambda: _async_find(
            query=query,
            entity_type=entity_type,
            limit=limit,
            with_relations=with_relations,
            workspace=workspace,
        ),
        failure_code="FIND_FAILED",
        failure_hint=(
            "Check the workspace is indexed: "
            "`loomgraph workspace info` or `loomgraph index <path>`."
        ),
    )
