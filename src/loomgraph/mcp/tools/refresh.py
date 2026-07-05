"""MCP tool: `refresh` — reactive working-tree re-index (first write tool).

Pull-mode complement to the commit-driven git-hook `update`: an agent that
just edited a file (uncommitted, incl. untracked) can re-index it on demand
instead of waiting for a commit. See ADR-014.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._indexing import _async_refresh
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

TOOL_SPEC = Tool(
    name="loomgraph_refresh",
    title="Refresh graph from working tree",
    description=(
        "Re-index the working tree into the graph on demand. Complementary "
        "to the commit-driven git-hook `update`: refresh captures "
        "*uncommitted* edits including untracked new files, so an agent "
        "that just edited a file can query it without waiting for a commit. "
        "Defaults to a per-file warm-diff over the working tree; pass "
        "`path` to scope to one file/dir, or `force_full` for a cold "
        "rebuild. Shells `codeindex graph-export`, so ai-codeindex must be "
        "installed. See ADR-014."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Optional file or directory prefix to refresh "
                    "(relative to repo root). When omitted, refreshes all "
                    "uncommitted working-tree changes including untracked "
                    "files."
                ),
            },
            "force_full": {
                "type": "boolean",
                "default": False,
                "description": (
                    "If true, perform a cold whole-tree rebuild (clear + "
                    "re-ingest). Slow; use only when incremental refresh "
                    "can't reconcile drift."
                ),
            },
            "workspace": {"type": "string"},
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    workspace = resolve_workspace(arguments)
    path = arguments.get("path")
    force_full = bool(arguments.get("force_full", False))
    return await safe_call(
        lambda: _async_refresh(
            workspace=workspace,
            repo=Path.cwd(),
            path=path,
            force_full=force_full,
        ),
        failure_code="REFRESH_FAILED",
        failure_hint=(
            "refresh runs `codeindex graph-export`; install ai-codeindex "
            ">= 0.28.0 and invoke from the repo root (or pass workspace)."
        ),
    )
