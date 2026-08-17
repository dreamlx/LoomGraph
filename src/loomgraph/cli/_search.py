"""CLI commands for find, query, and graph queries."""

from __future__ import annotations

import asyncio
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


class VectorsNotIndexedError(RuntimeError):
    """Workspace has no embedded vectors — semantic search unavailable.

    Raised by `_async_search` when `store.vector_count() == 0` so the CLI
    can emit `EMBEDDING_NOT_INDEXED` with a targeted suggestion rather than
    a generic storage error (and rather than relying on sqlite-vec's
    version-dependent empty-table KNN behaviour).
    """

    def __init__(self, workspace: str) -> None:
        super().__init__(workspace)
        self.workspace = workspace


@main.command()
@click.argument("query")
@click.option("--type", "-t", "entity_type", default=None, help="Filter by entity type (e.g. function, class, method)")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: auto-detected)")
@click.option("--limit", "-n", default=20, help="Maximum number of results")
def search(query: str, entity_type: str | None, workspace: str | None, limit: int) -> None:
    """Semantic search over entity descriptions (by meaning, not name).

    QUERY: Natural-language intent or descriptive phrase. Embedded and
    matched against entity-description vectors (signature + docstring) via
    KNN. Complementary to `find` (name matching): use `find` when you know
    a symbol name, `search` when you know what something *does*.

    Requires the workspace to have been indexed with embedding enabled
    (LOOMGRAPH_EMBEDDING__ENABLED=true). Returns EMBEDDING_NOT_INDEXED
    otherwise.
    """
    try:
        result = asyncio.run(_async_search(query, entity_type, workspace, limit))
        output_success(result)
    except VectorsNotIndexedError as e:
        output_error(
            code=ErrorCode.EMBEDDING_NOT_INDEXED,
            message=(
                f"Workspace '{e.workspace}' has no embedded vectors — "
                "semantic search is unavailable."
            ),
            suggestion=(
                "Index with embedding enabled: set LOOMGRAPH_EMBEDDING__ENABLED=true "
                "(and LOOMGRAPH_EMBEDDING__API_URL to an OpenAI-compatible endpoint), "
                "then `loomgraph index --clear <path>`. See EPIC-015 (#70)."
            ),
        )
    except click.ClickException as e:
        # Most commonly: no workspace found at all (first-time user, nothing
        # indexed yet). Same user action as "not indexed" → same code, so a
        # client doesn't mistake it for an embedding-service outage.
        output_error(
            code=ErrorCode.EMBEDDING_NOT_INDEXED,
            message=str(e.message),
            suggestion="Index first: loomgraph index <path>  (with LOOMGRAPH_EMBEDDING__ENABLED=true for semantic search).",
        )
    except Exception as e:
        output_error(
            code=ErrorCode.EMBEDDING_FAILED,
            message=f"Semantic search failed: {e}",
            suggestion=(
                "Check the embedding service is reachable: loomgraph status. "
                "For name-based search use: loomgraph find <query>."
            ),
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


async def _async_search(
    query: str,
    entity_type: str | None = None,
    workspace: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Semantic search: embed the query, KNN over entity-description vectors.

    Complementary to `_async_find` (name fuzzy match) — use this when the
    query is an intent/phrase whose words may not appear in any symbol name.
    Phase 0 (EPIC-015 #70) measured intent-query wins where `find` returned
    empty.

    Raises ``VectorsNotIndexedError`` if the workspace has no vectors — the
    CLI translates that to ``EMBEDDING_NOT_INDEXED``.
    """
    ws, store = await prepare_workspace_store(workspace)

    vc = await store.vector_count()
    if vc == 0:
        raise VectorsNotIndexedError(ws)

    # Embed the query into the same vector space as the entity descriptions.
    # #158: sticky provider resolution (auto → config > ollama-probe >
    # builtin) and the query-side task prefix for CodeRankEmbed. Single
    # construction entry (pruner) — deterministic errors propagate to the
    # CLI's typed-error translation.
    from loomgraph.embedding.resolve import client_for_store

    cm = await client_for_store(store)
    async with cm as (client, _provider):
        emb = await client.embed_query(query)

    # Over-fetch when filtering by type so a sparse type doesn't get starved
    # by the KNN cut (same heuristic search_similar uses for source_prefix).
    k = limit * 5 if entity_type else limit
    raw_hits = await store.search_similar(emb, k=k)

    # Hydrate with entity metadata (type/description/source_id) for display.
    entities = await store.get_all_entities()
    meta_by_name: dict[str, dict[str, Any]] = {}
    for e in entities:
        nm = e.get("entity_name") or e.get("id") or ""
        if nm and nm not in meta_by_name:
            meta_by_name[nm] = e

    matches: list[dict[str, Any]] = []
    for hit in raw_hits:
        nm = hit["entity_name"]
        meta = meta_by_name.get(nm, {})
        etype = meta.get("entity_type", "")
        if entity_type and etype.lower() != entity_type.lower():
            continue
        distance = float(hit.get("distance", 0.0))
        matches.append({
            "entity": nm,
            "type": etype,
            "source_id": hit.get("source_id") or meta.get("source_id", ""),
            "description": (meta.get("description") or "")[:200],
            # vec0 returns L2 distance over unit vectors (range [0,2]);
            # convert to cosine similarity — scale-free across embedding
            # models (#158: CodeRankEmbed's absolute cos is lower than
            # nomic-text's, so `1 - distance` floored everything at 0).
            # Note (#158 review C2-4): exact only for unit vectors — builtin
            # normalizes; Direct providers that return unnormalized vectors
            # keep ranking but the absolute score is approximate.
            "score": round(max(0.0, 1.0 - (distance ** 2) / 2.0), 3),
        })
        if len(matches) >= limit:
            break

    return {
        "query": query,
        "mode": "semantic",
        "workspace": ws,
        "vector_count": vc,
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

        # #113: skip low-trust (unresolved/ambiguous) edges so phantom callees
        # don't leak into --with-relations output. find gives no escape hatch —
        # use `graph --include-unresolved` to inspect raw call expressions.
        if not _edge_is_trusted(rel, include_unresolved=False):
            continue

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


def _edge_is_trusted(rel: dict[str, Any], include_unresolved: bool) -> bool:
    """#113: unresolved/ambiguous edges target a call expression (dst_raw), not
    an in-repo entity — surfacing them yields phantom callees/callers
    (``source_id=""``). Default to trusted-only (resolved). ``include_unresolved``
    keeps them for raw-call inspection. A relation missing the field is treated
    as resolved (old data / pre-#113 fixtures never get filtered)."""
    if include_unresolved:
        return True
    qualifier = str(rel.get("resolution_qualifier", "resolved"))
    return qualifier == "resolved"


def _resolve_simple_name(
    entity_name: str, source_id_map: dict[str, str]
) -> str:
    """Resolve a simple name to a stored FQN (#98), trying both `.` and `::`
    separators so the codegraph backend (`Class::method`) isn't blind (#152).

    Exact-match caller responsibility: unique dotted/`::`-suffix match wins;
    ambiguous/none returns the name unchanged (empty result, no worse than
    before)."""
    for sep in (".", "::"):
        suffix = sep + entity_name
        matches = [n for n in source_id_map if n.endswith(suffix)]
        if len(matches) == 1:
            return matches[0]
    return entity_name


def _class_methods(class_name: str, source_id_map: dict[str, str]) -> list[str]:
    """Names that are methods of ``class_name`` — ``Class.method`` (#105) and
    ``Class::method`` (codegraph, #152)."""
    out: list[str] = []
    for sep in (".", "::"):
        prefix = class_name + sep
        out.extend(n for n in source_id_map if n.startswith(prefix))
    return out


@main.command()
@click.argument("entity_name")
@click.option(
    "--direction",
    type=click.Choice(["callers", "callees", "both"]),
    default="both",
    help="Query direction",
)
@click.option("--depth", default=1, help="Traversal depth")
@click.option("--relation-type",
    type=click.Choice(["CALLS", "INHERITS", "IMPORTS", "REFERENCES", "all"]),
    default="all",
    help="Relation type filter",
)
@click.option("--include-unresolved", is_flag=True, default=False,
    help="Include unresolved/ambiguous edges (phantom targets not in repo)")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def graph(entity_name: str, direction: str, depth: int, relation_type: str, include_unresolved: bool, workspace: str | None) -> None:
    """Query entity relationships in the graph.

    ENTITY_NAME: Name of the entity to query

    Performs precise structural traversal of the knowledge graph,
    returning exact callers and callees from stored relations.
    """
    try:
        result = asyncio.run(_async_graph_query(entity_name, direction, relation_type, workspace, depth, include_unresolved))
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
    depth: int = 1,
    include_unresolved: bool = False,
) -> dict[str, Any]:
    """Run graph traversal via graph layer API (precise structural query)."""
    ws, store = await prepare_workspace_store(workspace)

    relations = await store.get_all_relations()
    entities = await store.get_all_entities()

    # Build entity name → source_id lookup
    source_id_map: dict[str, str] = {}
    entity_type_map: dict[str, str] = {}
    for ent in entities:
        name = ent.get("entity_name", "") or ent.get("entity_id", "") or ent.get("id", "")
        if name:
            source_id_map[name] = ent.get("source_id", "")
            entity_type_map[name] = ent.get("entity_type", "")

    # Resolve simple name → stored FQN (#98): a caller passing
    # `downstreamBlockers` must hit `src.lib.api.queries.downstreamBlockers`.
    # Exact wins; else a unique dotted-suffix match resolves; ambiguous/none
    # leaves the name as-is (empty result, no worse than before).
    # #152: codegraph names use `::` separators (MigrationManager::constructor)
    # rather than `.` — try both so the codegraph backend isn't blind to
    # simple-name queries (#98 feature dead for a whole backend otherwise).
    resolved = entity_name
    if entity_name not in source_id_map:
        resolved = _resolve_simple_name(entity_name, source_id_map)

    # Build relation_type-filtered adjacency and BFS up to `depth` layers
    # (#103): previously `--depth` was a no-op (graph() dropped it before
    # calling here). depth=1 == direct neighbours (prior behaviour); depth>1
    # expands callers/callees transitively, deduped, never revisiting start.
    from collections import defaultdict

    outgoing: dict[str, list[dict[str, str]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, str]]] = defaultdict(list)
    for rel in relations:
        src = rel.get("src_id", "") or rel.get("source", "")
        tgt = rel.get("tgt_id", "") or rel.get("target", "")
        keywords = rel.get("keywords", "UNKNOWN")
        if relation_type != "all" and keywords != relation_type:
            continue
        # #113: skip low-trust (unresolved/ambiguous) edges by default — their
        # tgt is a call expression (dst_raw), not an in-repo entity, so they'd
        # surface as phantom callees/callers with source_id="". --include-unresolved
        # brings them back for raw-call inspection.
        if not _edge_is_trusted(rel, include_unresolved):
            continue
        if not (src and tgt):
            continue
        outgoing[src].append({"entity": tgt, "relation": keywords,
                              "source_id": source_id_map.get(tgt, "")})
        incoming[tgt].append({"entity": src, "relation": keywords,
                              "source_id": source_id_map.get(src, "")})

    callees = _bfs_collect(resolved, outgoing, depth)
    callers = _bfs_collect(resolved, incoming, depth)

    # #105: a class entity owns no outgoing edges itself — the calls live on
    # its methods (Class.method). So `graph SomeClass` saw 0 callees even
    # though every method was calling things. When the resolved entity is a
    # class, fold its methods' callees in (additive over any direct edges the
    # class already has, e.g. REFERENCES; deduped by target). callers are
    # unaffected — constructor edges land on the class via codeindex #132.
    # #152: codegraph uses `Class::method` — try both separators.
    if entity_type_map.get(resolved) == "class":
        seen_callees = {c["entity"] for c in callees}
        for method_name in _class_methods(resolved, source_id_map):
            for edge in _bfs_collect(method_name, outgoing, depth):
                if edge["entity"] not in seen_callees:
                    seen_callees.add(edge["entity"])
                    callees.append(edge)

    result: dict[str, Any] = {
        "entity": resolved,
        "source_id": source_id_map.get(resolved, ""),
    }

    if direction in ("callers", "both"):
        result["callers"] = sorted(callers, key=lambda x: x["entity"])
    if direction in ("callees", "both"):
        result["callees"] = sorted(callees, key=lambda x: x["entity"])

    result["callers_count"] = len(callers) if direction in ("callers", "both") else None
    result["callees_count"] = len(callees) if direction in ("callees", "both") else None

    return result
