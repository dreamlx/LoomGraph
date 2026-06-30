"""MCP composite tool: `loomgraph_evolution_track` — cross-workspace entity tracking.

Replaces the `/loomgraph-evolution` skill: given an entity name and a
list of workspaces (each is a branch / version snapshot), find the
entity in every workspace, do pairwise structural diffs, return the
graph context per workspace.

Returns:
    {
        "entity": "<original query>",
        "workspaces_checked": [...],
        "similar": {data, error},           # cross-workspace similar
        "pairwise_compare": [{ws1, ws2, data, error}, ...],
        "per_workspace_graph": [{workspace, entity_matched, data, error}, ...],
    }
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._search import _async_graph_query
from loomgraph.cli._workspace import _async_compare, _async_similar
from loomgraph.mcp.tools._common import error_response, success_response

TOOL_SPEC = Tool(
    name="loomgraph_evolution_track",
    title="Track entity evolution across workspaces",
    description=(
        "Trace how a single code entity has diverged across N workspace "
        "snapshots (e.g. `myproject:main`, `myproject:fork-a`, "
        "`myproject:v0.9`). Composite of: cross-workspace `similar`, "
        "pairwise `compare` for adjacent versions, per-workspace `graph` "
        "callers/callees lookup.\n\n"
        "Replaces the multi-step `/loomgraph-evolution` skill. Returns "
        "structured data per stage; agent composes the divergence "
        "narrative + convergence recommendations."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "entity": {
                "type": "string",
                "description": "Entity name to track (e.g. `AuthService`).",
            },
            "workspaces": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Workspaces to compare (≥2). E.g. "
                    "`[\"proj:main\", \"proj:fork-a\", \"proj:v0.9\"]`. "
                    "Pairwise compares adjacent pairs in order."
                ),
                "minItems": 2,
            },
        },
        "required": ["entity", "workspaces"],
    },
)


async def _safe(coro: Any) -> dict[str, Any]:
    try:
        return {"data": await coro, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"data": None, "error": f"{type(exc).__name__}: {exc}"}


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    entity: str = arguments["entity"]
    workspaces: list[str] = list(arguments["workspaces"])
    if len(workspaces) < 2:
        return error_response(
            code="INVALID_INPUT",
            message="evolution_track requires ≥2 workspaces to compare.",
        )

    # 1. cross-workspace similar — finds the entity in each ws even with
    #    renames / signature drift
    similar_task = _safe(
        _async_similar(entity=entity, workspaces=",".join(workspaces))
    )

    # 2. pairwise compare for adjacent workspaces
    pair_tasks = [
        _safe(_async_compare(ws1=workspaces[i], ws2=workspaces[i + 1]))
        for i in range(len(workspaces) - 1)
    ]

    # 3. per-workspace graph context for the original entity name
    graph_tasks = [
        _safe(_async_graph_query(
            entity_name=entity, direction="both", relation_type="all", workspace=ws,
        ))
        for ws in workspaces
    ]

    similar_res, pair_results, graph_results = await asyncio.gather(
        similar_task,
        asyncio.gather(*pair_tasks),
        asyncio.gather(*graph_tasks),
    )

    pairwise = [
        {
            "ws1": workspaces[i],
            "ws2": workspaces[i + 1],
            **pair_results[i],
        }
        for i in range(len(workspaces) - 1)
    ]
    per_ws = [
        {"workspace": workspaces[i], "entity_query": entity, **graph_results[i]}
        for i in range(len(workspaces))
    ]

    return success_response({
        "entity": entity,
        "workspaces_checked": workspaces,
        "similar": similar_res,
        "pairwise_compare": pairwise,
        "per_workspace_graph": per_ws,
        "summary": {
            "pairs_compared": len(pairwise),
            "workspaces_with_graph_data": sum(
                1 for w in per_ws if w["error"] is None
            ),
        },
    })
