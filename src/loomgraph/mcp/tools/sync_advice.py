"""MCP composite tool: `loomgraph_sync_advice` — upstream/downstream sync analysis.

Replaces the `/loomgraph-sync-advisor` skill: given upstream + downstream
workspaces, return structural diff, debt-with-git on both sides, and
optional trend comparison. Agent synthesizes the merge advice + conflict
prediction.

Returns:
    {
        "upstream": "<ws>",
        "downstream": "<ws>",
        "compare": {data, error},           # structural diff
        "upstream_debt": {data, error},     # debt with git
        "downstream_debt": {data, error},
        "module_impacts": [...],            # graph callers for hot entities
    }
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._debt import _async_debt
from loomgraph.cli._search import _async_graph_query
from loomgraph.cli._workspace import _async_compare
from loomgraph.mcp.tools._common import error_response, success_response

TOOL_SPEC = Tool(
    name="loomgraph_sync_advice",
    title="Upstream/downstream sync advisor",
    description=(
        "Compose merge advice + conflict prediction for syncing changes "
        "from one workspace into another (e.g. upstream main → downstream "
        "feature branch / fork). Combines: workspace `compare`, three-"
        "dimensional `debt --with-git` on both sides, per-entity `graph` "
        "lookups for the most-impacted entities.\n\n"
        "Replaces the multi-step `/loomgraph-sync-advisor` skill. Returns "
        "structured data; agent generates the prose recommendation."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "upstream": {
                "type": "string",
                "description": "Upstream workspace name (the source of changes).",
            },
            "downstream": {
                "type": "string",
                "description": "Downstream workspace name (the merge target).",
            },
            "module": {
                "type": "string",
                "description": (
                    "Optional module path to scope debt analysis to "
                    "(e.g. `src/loomgraph/cli`). Default: whole workspace."
                ),
            },
            "git_since": {
                "type": "string",
                "description": "Git history window for debt --with-git.",
                "default": "3 months",
            },
            "impact_entities": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Specific entities to query for impact in the "
                    "downstream workspace (callers/callees). Pass the "
                    "entities the agent identified as 'changed in upstream' "
                    "from a prior compare call."
                ),
                "default": [],
            },
        },
        "required": ["upstream", "downstream"],
    },
)


async def _safe(coro: Any) -> dict[str, Any]:
    try:
        return {"data": await coro, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"data": None, "error": f"{type(exc).__name__}: {exc}"}


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    upstream: str = arguments["upstream"]
    downstream: str = arguments["downstream"]
    module: str | None = arguments.get("module")
    git_since: str = arguments.get("git_since", "3 months")
    impact_entities: list[str] = list(arguments.get("impact_entities") or [])

    if upstream == downstream:
        return error_response(
            code="INVALID_INPUT",
            message="upstream and downstream must be different workspaces.",
        )

    # All four dimensions in parallel
    compare_task = _safe(_async_compare(ws1=upstream, ws2=downstream))
    up_debt_task = _safe(_async_debt(
        codeindex_data_path=None, output_format="json", workspace=upstream,
        module=module, scope=None, skip_topology=False, with_git=True,
        git_since=git_since,
    ))
    down_debt_task = _safe(_async_debt(
        codeindex_data_path=None, output_format="json", workspace=downstream,
        module=module, scope=None, skip_topology=False, with_git=True,
        git_since=git_since,
    ))
    impact_tasks = [
        _safe(_async_graph_query(
            entity_name=e, direction="callers", relation_type="all", workspace=downstream,
        ))
        for e in impact_entities
    ]

    compare_res, up_debt, down_debt, *impact_results = await asyncio.gather(
        compare_task, up_debt_task, down_debt_task, *impact_tasks,
    )

    impacts = [
        {"entity": impact_entities[i], **impact_results[i]}
        for i in range(len(impact_entities))
    ]

    # Crude advice signal: count how many of the four dimensions succeeded
    succeeded = sum(
        1 for r in (compare_res, up_debt, down_debt) if r["error"] is None
    )
    if succeeded == 0:
        return error_response(
            code="SYNC_ADVICE_FAILED",
            message="Neither workspace produced data — check `loomgraph workspace info`.",
            suggestion=f"Verify both workspaces exist: `{upstream}` and `{downstream}`.",
        )

    return success_response({
        "upstream": upstream,
        "downstream": downstream,
        "compare": compare_res,
        "upstream_debt": up_debt,
        "downstream_debt": down_debt,
        "module_impacts": impacts,
        "summary": {
            "dimensions_succeeded": succeeded,
            "impact_entities_queried": len(impacts),
            "impact_entities_with_data": sum(
                1 for i in impacts if i["error"] is None
            ),
        },
    })
