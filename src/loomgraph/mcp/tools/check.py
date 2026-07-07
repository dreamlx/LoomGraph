"""MCP tool: `loomgraph_check` — index freshness (source_id vs disk).

Side-effect-free read; same dimension `loomgraph_debt_audit` exposes as
its `check` entry, now also reachable as a standalone primitive (#62).
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
        "Verify index freshness: compare each indexed source_id against the "
        "filesystem. Reports valid / stale / missing counts and the stale "
        "files. Useful before an audit to confirm the graph matches the "
        "working tree."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "repo_path": {
                "type": "string",
                "description": "Base path on disk to resolve source_ids against.",
                "default": ".",
            },
            "workspace": {"type": "string"},
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    workspace = resolve_workspace(arguments)
    return await safe_call(
        lambda: _async_check(
            repo_path=arguments.get("repo_path", "."),
            workspace=workspace,
        ),
        failure_code="CHECK_FAILED",
        failure_hint="Confirm repo_path exists and the workspace is indexed.",
    )
