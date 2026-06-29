"""MCP tools: `workspace_list` + `workspace_info`."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._workspace import _async_workspace_info, _async_workspace_list
from loomgraph.mcp.tools._common import safe_call

LIST_SPEC = Tool(
    name="loomgraph_workspace_list",
    title="List all workspaces",
    description=(
        "Return every workspace currently stored under `~/.loomgraph/`, "
        "with entity / relation counts. Useful when the agent needs to "
        "discover which projects are queryable before drilling into one."
    ),
    inputSchema={"type": "object", "properties": {}},
)


async def list_handle(arguments: dict[str, Any]) -> list[TextContent]:
    return await safe_call(
        _async_workspace_list,
        failure_code="WORKSPACE_LIST_FAILED",
        failure_hint="Check ~/.loomgraph/ permissions.",
    )


INFO_SPEC = Tool(
    name="loomgraph_workspace_info",
    title="Workspace metadata",
    description=(
        "Detailed stats for a specific workspace: entity / relation "
        "counts by type, db size, last update timestamp. Omit the "
        "`name` argument to inspect the auto-detected current workspace."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Workspace name (e.g. `myproject:main`). Omit to use "
                    "the server's default."
                ),
            },
        },
    },
)


async def info_handle(arguments: dict[str, Any]) -> list[TextContent]:
    name = arguments.get("name")
    return await safe_call(
        lambda: _async_workspace_info(name, None),
        failure_code="WORKSPACE_INFO_FAILED",
        failure_hint=(
            "Run `loomgraph_workspace_list` to discover existing workspace names."
        ),
    )
