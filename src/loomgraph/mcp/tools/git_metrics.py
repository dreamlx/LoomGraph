"""MCP tool: `git_metrics` — git-history hotspots / bus factor / defect magnets.

Wraps `loomgraph.cli._analysis._async_git_metrics` directly (no subprocess).
EPIC-014 #62: expose as a standalone MCP primitive so agents can pull git
metrics ad-hoc without the full `loomgraph_debt_audit` composite.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._analysis import _async_git_metrics
from loomgraph.mcp.tools._common import safe_call

TOOL_SPEC = Tool(
    name="loomgraph_git_metrics",
    title="Git history metrics (hotspots, bus factor)",
    description=(
        "Compute change-frequency hotspots, bus factor, and defect magnets "
        "from git history over a time window. Identifies fragile files "
        "(frequently churned) and knowledge silos (single-owner code). No "
        "workspace needed — operates on the git repo at `path`. "
        "Side-effect-free read."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository path to analyze. Default: cwd.",
                "default": ".",
            },
            "since": {
                "type": "string",
                "description": "Git history window (default: '3 months').",
                "default": "3 months",
            },
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    path = arguments.get("path", ".")
    since = arguments.get("since", "3 months")
    return await safe_call(
        lambda: _async_git_metrics(path=path, since=since),
        failure_code="GIT_METRICS_FAILED",
        failure_hint="Confirm the path is a git repo, or widen `since`.",
    )
