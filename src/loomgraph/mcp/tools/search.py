"""MCP tool: `search` — semantic search over entity-description vectors.

Wraps `loomgraph.cli._search._async_search` directly (no subprocess). The
semantic peer of `loomgraph_find`: use `find` for name matching, `search`
for intent/meaning (EPIC-015 #70 Phase 0 measured intent-query wins where
`find` returned empty).
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._search import VectorsNotIndexedError, _async_search
from loomgraph.mcp.tools._common import (
    error_response,
    resolve_workspace,
    success_response,
)

TOOL_SPEC = Tool(
    name="loomgraph_search",
    title="Search entities by meaning",
    description=(
        "Semantic search over entity descriptions (signature + docstring). "
        "Embeds the query and returns the nearest entities by vector "
        "distance — use this for intent questions like 'where are hotspots "
        "computed' whose words may not appear in any symbol name. "
        "Complementary to `loomgraph_find` (name matching): use find when "
        "you know a symbol name, search when you know what it DOES. "
        "Requires the workspace indexed with embedding enabled."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language intent or descriptive phrase.",
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
    workspace = resolve_workspace(arguments)

    try:
        data = await _async_search(
            query=query,
            entity_type=entity_type,
            limit=limit,
            workspace=workspace,
        )
    except VectorsNotIndexedError as e:
        # Common case (embedding defaults off) — surface a typed code with the
        # actionable enable-embedding suggestion instead of generic SEARCH_FAILED.
        return error_response(
            "EMBEDDING_NOT_INDEXED",
            f"Workspace '{e.workspace}' has no embedded vectors — semantic search unavailable.",
            suggestion=(
                "Index with embedding enabled (LOOMGRAPH_EMBEDDING__ENABLED=true) "
                "then `loomgraph index --clear <path>`. For name-based search use loomgraph_find."
            ),
        )
    except Exception as exc:
        # Embedding service down, store error, etc.
        return error_response(
            "SEARCH_FAILED",
            f"{type(exc).__name__}: {exc}",
            suggestion=(
                "Check the embedding service is reachable: loomgraph status. "
                "For name-based search use loomgraph_find."
            ),
        )
    return success_response(data)
