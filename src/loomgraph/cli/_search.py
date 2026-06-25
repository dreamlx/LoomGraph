"""CLI commands for find, query, and graph queries."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import click

from loomgraph.cli._common import (
    ErrorCode,
    output_error,
    output_success,
    prepare_workspace_store,
)
from loomgraph.cli.main import main


@main.command()
@click.argument("query")
@click.option("--type", "-t", "entity_type", default=None, help="Filter by entity type (e.g. function, class, module)")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option("--limit", "-n", default=20, help="Maximum number of results")
@click.option("--with-relations", is_flag=True, default=False, help="Include callers/callees for each matched entity")
@click.option("--depth", default=1, help="BFS expansion depth for --with-relations (default: 1)")
def find(
    query: str,
    entity_type: str | None,
    workspace: str | None,
    limit: int,
    with_relations: bool,
    depth: int,
) -> None:
    """Find entities in the knowledge graph by name matching.

    QUERY: Search term to match against entity names and descriptions.
    Returns structured entity matches with type, source_id, and relevance score.

    Use --with-relations to include callers/callees for each match (saves N+1 calls).
    """
    try:
        result = asyncio.run(_async_find(query, entity_type, workspace, limit, with_relations, depth))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Find failed: {e}",
            suggestion="Check service status with: loomgraph status",
        )


@main.command(hidden=True)
@click.argument("query")
@click.option("--type", "-t", "entity_type", default=None, help="Filter by entity type")
@click.option("--workspace", "-w", default=None, help="Workspace name")
@click.option("--limit", "-n", default=20, help="Maximum number of results")
def search(query: str, entity_type: str | None, workspace: str | None, limit: int) -> None:
    """[Deprecated] Use 'find' instead."""
    print(
        "WARNING: 'loomgraph search' is deprecated, use 'loomgraph find' instead.",
        file=sys.stderr,
    )
    try:
        result = asyncio.run(_async_find(query, entity_type, workspace, limit))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Search failed: {e}",
            suggestion="Check service status with: loomgraph status",
        )


async def _async_find(
    query: str,
    entity_type: str | None = None,
    workspace: str | None = None,
    limit: int = 20,
    with_relations: bool = False,
    depth: int = 1,
) -> dict[str, Any]:
    """Find entities via graph layer API (structural search).

    When with_relations=True, also fetches relations and attaches
    callers/callees to each matched entity via BFS expansion.
    """
    from difflib import SequenceMatcher

    ws, store = await prepare_workspace_store(workspace)

    entities = await store.get_all_entities()

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

    # Attach relations if requested
    if with_relations and matches:
        relations = await store.get_all_relations()
        _attach_relations(matches, relations, depth)

    return {
        "query": query,
        "total_entities": len(entities),
        "matches_count": len(matches),
        "matches": matches,
    }


def _attach_relations(
    matches: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    depth: int = 1,
) -> None:
    """Attach callers/callees to matched entities via BFS expansion.

    Builds an adjacency list from all relations, then for each matched entity,
    performs BFS up to `depth` layers to collect callers and callees.
    """
    from collections import defaultdict

    # Build adjacency: src→tgt (outgoing) and tgt→src (incoming)
    outgoing: dict[str, list[dict[str, str]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, str]]] = defaultdict(list)

    for rel in relations:
        src = rel.get("src_id", "") or rel.get("source", "")
        tgt = rel.get("tgt_id", "") or rel.get("target", "")
        keywords = rel.get("keywords", "UNKNOWN")

        if src and tgt:
            outgoing[src].append({"entity": tgt, "relation": keywords})
            incoming[tgt].append({"entity": src, "relation": keywords})

    for match in matches:
        entity_name = match["entity"]

        # BFS for callees (outgoing edges)
        callees = _bfs_collect(entity_name, outgoing, depth)
        # BFS for callers (incoming edges)
        callers = _bfs_collect(entity_name, incoming, depth)

        match["callers"] = sorted(callers, key=lambda x: x["entity"])
        match["callees"] = sorted(callees, key=lambda x: x["entity"])


def _bfs_collect(
    start: str,
    adj: dict[str, list[dict[str, str]]],
    depth: int,
) -> list[dict[str, str]]:
    """BFS from start entity along adjacency edges up to given depth.

    Returns deduplicated list of {entity, relation} dicts (excludes start itself).
    """
    visited: set[str] = {start}
    result: list[dict[str, str]] = []
    frontier = [start]

    for _ in range(depth):
        next_frontier: list[str] = []
        for node in frontier:
            for edge in adj.get(node, []):
                neighbor = edge["entity"]
                if neighbor not in visited:
                    visited.add(neighbor)
                    result.append(edge)
                    next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    return result


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
            code=ErrorCode.STORAGE_ERROR,
            message=f"Graph query failed: {e}",
            suggestion="Check service status with: loomgraph status",
        )


async def _async_graph_query(
    entity_name: str,
    direction: str,
    relation_type: str,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run graph traversal via graph layer API (precise structural query)."""
    ws, store = await prepare_workspace_store(workspace)

    relations = await store.get_all_relations()
    entities = await store.get_all_entities()

    # Build entity name → source_id lookup
    source_id_map: dict[str, str] = {}
    for ent in entities:
        name = ent.get("entity_name", "") or ent.get("entity_id", "") or ent.get("id", "")
        if name:
            source_id_map[name] = ent.get("source_id", "")

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
            callers.append({"entity": src, "relation": keywords, "source_id": source_id_map.get(src, "")})
        if src == entity_name:
            callees.append({"entity": tgt, "relation": keywords, "source_id": source_id_map.get(tgt, "")})

    result: dict[str, Any] = {
        "entity": entity_name,
        "source_id": source_id_map.get(entity_name, ""),
    }

    if direction in ("callers", "both"):
        result["callers"] = sorted(callers, key=lambda x: x["entity"])
    if direction in ("callees", "both"):
        result["callees"] = sorted(callees, key=lambda x: x["entity"])

    result["callers_count"] = len(callers) if direction in ("callers", "both") else None
    result["callees_count"] = len(callees) if direction in ("callees", "both") else None

    return result
