"""MCP tool: `loomgraph_git_metrics` — git hotspots / bus factor.

Exposes the git dimension `loomgraph_debt_audit` computes, as a standalone
primitive. Side-effect-free read; auto-degrades if the path isn't a git
repo. `gather()` is shared by this primitive and the composite (#62).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.mcp.tools._common import safe_call


async def gather(source_path: str, since: str) -> dict[str, Any]:
    """Run the sync GitMetricsAnalyzer in a thread; return serialized dict.

    Shared by this primitive and the `loomgraph_debt_audit` composite so
    the two stay in sync without one importing the other's handler.
    """
    from loomgraph.core.git_metrics import GitMetricsAnalyzer

    def _run() -> dict[str, Any]:
        result = GitMetricsAnalyzer(Path(source_path), since=since).analyze()
        return {
            "repo_path": str(result.repo_path),
            "since": result.since,
            "analyzed_at": result.analyzed_at.isoformat(),
            "summary": result.summary,
            "hotspots": [
                {
                    "file": h.file,
                    "change_freq": h.change_freq,
                    "hotspot_score": h.hotspot_score,
                    "rank": h.rank,
                }
                for h in result.hotspots
            ],
            "bus_factor": [
                {
                    "file": bf.file,
                    "owner": bf.owner,
                    "contributors": bf.contributors,
                    "risk_level": bf.risk_level,
                }
                for bf in result.bus_factor
            ],
        }

    return await asyncio.to_thread(_run)


TOOL_SPEC = Tool(
    name="loomgraph_git_metrics",
    title="Git hotspots & bus factor",
    description=(
        "Compute git-history dimensions: change-frequency hotspots, bus "
        "factor (single-owner files), defect magnets. This is the `git` "
        "dimension of `loomgraph_debt_audit` as a standalone primitive. "
        "Errors cleanly if the path isn't a git repo."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to the git repo (default: cwd).",
                "default": ".",
            },
            "since": {
                "type": "string",
                "description": "History window (default: '3 months').",
                "default": "3 months",
            },
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    return await safe_call(
        lambda: gather(
            source_path=arguments.get("source_path", "."),
            since=arguments.get("since", "3 months"),
        ),
        failure_code="GIT_METRICS_FAILED",
        failure_hint="Confirm source_path is a git repo (has a .git dir).",
    )
