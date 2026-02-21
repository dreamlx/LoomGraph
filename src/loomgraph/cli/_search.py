"""CLI commands for search and graph queries."""

from __future__ import annotations

import asyncio
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings


@main.command()
@click.argument("query")
@click.option("--type", "-t", "entity_type", default=None, help="Filter by entity type (e.g. function, class, module)")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option("--limit", "-n", default=20, help="Maximum number of results")
def search(query: str, entity_type: str | None, workspace: str | None, limit: int) -> None:
    """Search entities in the knowledge graph.

    QUERY: Search term to match against entity names and descriptions
    """
    try:
        result = asyncio.run(_async_search(query, entity_type, workspace, limit))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Search failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_search(
    query: str,
    entity_type: str | None = None,
    workspace: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search entities via graph layer API (structural search)."""
    from difflib import SequenceMatcher

    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    entities = await client.get_all_entities()

    query_lower = query.lower()
    scored: list[tuple[float, dict[str, Any]]] = []

    for entity in entities:
        name = entity.get("entity_name", "") or entity.get("entity_id", "") or entity.get("id", "")
        etype = entity.get("entity_type", "")
        description = entity.get("description", "")
        source_id = entity.get("source_id", "")

        if not name:
            continue

        # Apply type filter
        if entity_type and etype.lower() != entity_type.lower():
            continue

        name_lower = name.lower()

        # Scoring: exact substring > prefix > fuzzy
        if query_lower == name_lower:
            score = 1.0
        elif query_lower in name_lower:
            score = 0.9
        elif name_lower.startswith(query_lower):
            score = 0.85
        else:
            # Fuzzy match on name and description
            name_ratio = SequenceMatcher(None, query_lower, name_lower).ratio()
            desc_ratio = 0.0
            if description:
                desc_ratio = SequenceMatcher(None, query_lower, description.lower()).ratio()
            score = max(name_ratio, desc_ratio * 0.7)

        if score >= 0.4:
            scored.append((score, {
                "entity": name,
                "type": etype,
                "source_id": source_id,
                "description": description[:200] if description else "",
                "score": round(score, 3),
            }))

    # Sort by score descending, then by name
    scored.sort(key=lambda x: (-x[0], x[1]["entity"]))
    matches = [item for _, item in scored[:limit]]

    return {
        "query": query,
        "total_entities": len(entities),
        "matches_count": len(matches),
        "matches": matches,
    }


@main.command()
@click.argument("entity_name")
@click.option(
    "--direction",
    type=click.Choice(["callers", "callees", "both"]),
    default="both",
    help="Query direction",
)
@click.option("--depth", default=1, help="Traversal depth")
@click.option(
    "--relation-type",
    type=click.Choice(["CALLS", "INHERITS", "IMPORTS", "all"]),
    default="all",
    help="Relation type filter",
)
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def graph(entity_name: str, direction: str, depth: int, relation_type: str, workspace: str | None) -> None:
    """Query entity relationships in the graph.

    ENTITY_NAME: Name of the entity to query

    Performs precise structural traversal of the knowledge graph,
    returning exact callers and callees from stored relations.
    """
    try:
        result = asyncio.run(_async_graph_query(entity_name, direction, relation_type, workspace))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Graph query failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_graph_query(
    entity_name: str,
    direction: str,
    relation_type: str,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run graph traversal via graph layer API (precise structural query)."""
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    relations = await client.get_all_relations()

    # Filter relations by entity_name (handle both field name variants)
    callers: list[dict[str, str]] = []
    callees: list[dict[str, str]] = []

    for rel in relations:
        src = rel.get("src_id", "") or rel.get("source", "")
        tgt = rel.get("tgt_id", "") or rel.get("target", "")
        keywords = rel.get("keywords", "UNKNOWN")

        # Apply relation type filter
        if relation_type != "all" and keywords != relation_type:
            continue

        if tgt == entity_name:
            callers.append({"entity": src, "relation": keywords})
        if src == entity_name:
            callees.append({"entity": tgt, "relation": keywords})

    result: dict[str, Any] = {"entity": entity_name}

    if direction in ("callers", "both"):
        result["callers"] = sorted(callers, key=lambda x: x["entity"])
    if direction in ("callees", "both"):
        result["callees"] = sorted(callees, key=lambda x: x["entity"])

    result["callers_count"] = len(callers) if direction in ("callers", "both") else None
    result["callees_count"] = len(callees) if direction in ("callees", "both") else None

    return result
