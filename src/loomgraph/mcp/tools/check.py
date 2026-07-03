"""MCP tool: `check` — index freshness (source_id vs disk).

Wraps `loomgraph.cli._analysis._async_check` directly (no subprocess).
EPIC-014 #62: expose as a standalone MCP primitive so agents can probe
freshness without the full `loomgraph_debt_audit` composite.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._analysis import _async_check
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

TOOL_SPEC = Tool(
    name="loomgraph_check",
    title="Index freshness check",
    description=(
        "Verify indexed entities still reference files on disk. Returns a "
        "freshness ratio plus the list of stale source_ids (files moved or "
        "deleted since indexing). Use to decide whether to run "
        "`loomgraph update` or `loomgraph index --clear`. Side-effect-free read."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "repo_path": {
                "type": "string",
                "description": (
                    "Base path to resolve source_id file paths against. "
                    "Default: cwd."
                ),
                "default": ".",
            },
            "workspace": {
                "type": "string",
                "description": "Override the workspace to query.",
            },
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    repo_path = arguments.get("repo_path", ".")
    workspace = resolve_workspace(arguments)
    return await safe_call(
        lambda: _async_check(repo_path=repo_path, workspace=workspace),
        failure_code="CHECK_FAILED",
        failure_hint="Confirm the workspace is indexed: `loomgraph workspace info`.",
    )
