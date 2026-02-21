"""Hybrid retrieval and iterative deep query for LoomGraph.

Provides two key capabilities ported from MatrixoneGraph:

1. hybrid_query() — entity + relation graph traversal + context assembly
2. iterative_deep_query() — LLM-driven multi-round retrieval that
   analyzes context gaps and triggers follow-up searches until the
   context is complete.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Structured query result with entities, relations, and context."""

    query: str = ""
    mode: str = ""
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    context: str = ""
    rounds: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "entities": self.entities,
            "relations": self.relations,
            "context": self.context,
            "rounds": self.rounds,
        }


# ── Hybrid query: entity search + graph BFS + context assembly ──


async def hybrid_query(
    client: Any,
    query: str,
    *,
    top_k: int = 10,
    depth: int = 1,
) -> QueryResult:
    """Hybrid query combining LightRAG search with graph traversal.

    1. Query LightRAG for initial entity matches
    2. Fetch all relations and build adjacency map
    3. BFS-expand matched entities to find neighbors
    4. Assemble structured context text

    Args:
        client: LightRAGClient instance
        query: Natural language query
        top_k: Max entities to return (default: 10)
        depth: Graph traversal depth (default: 1)

    Returns:
        QueryResult with entities, relations, and formatted context
    """
    # Step 1: LightRAG semantic search
    search_result = await client.query(query, mode="hybrid")
    response_text = search_result.get("response", "")

    # Step 2: Fetch graph data for traversal
    try:
        all_entities = await client.get_all_entities()
        all_relations = await client.get_all_relations()
    except Exception:
        # Fallback: return LightRAG response only
        return QueryResult(
            query=query, mode="hybrid",
            context=response_text,
        )

    # Build adjacency map (bidirectional)
    adj: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in all_relations:
        src = r.get("src_id", "")
        tgt = r.get("tgt_id", "")
        if src and tgt:
            adj[src].append({"neighbor": tgt, **r})
            adj[tgt].append({"neighbor": src, **r})

    # Build entity lookup
    entity_map = {e.get("entity_name", ""): e for e in all_entities}

    # Step 3: Find matching entities (name contains query terms)
    query_terms = query.lower().split()
    matched: list[dict[str, Any]] = []
    for name, ent in entity_map.items():
        desc = ent.get("description", "").lower()
        name_lower = name.lower()
        if any(t in name_lower or t in desc for t in query_terms):
            matched.append({"name": name, **ent})
    matched = matched[:top_k]

    # Step 4: BFS expansion
    visited: set[str] = {e["name"] for e in matched}
    neighbor_entities: list[dict[str, Any]] = []
    related_rels: list[dict[str, Any]] = []

    frontier = [e["name"] for e in matched]
    for _ in range(depth):
        next_frontier: list[str] = []
        for name in frontier:
            for edge in adj.get(name, []):
                nb = edge["neighbor"]
                related_rels.append(edge)
                if nb not in visited:
                    visited.add(nb)
                    if nb in entity_map:
                        neighbor_entities.append({"name": nb, **entity_map[nb]})
                        next_frontier.append(nb)
        frontier = next_frontier

    # Step 5: Assemble context
    all_matched = matched + neighbor_entities[:top_k]
    context = _assemble_context(all_matched, related_rels, response_text)

    return QueryResult(
        query=query, mode="hybrid",
        entities=all_matched,
        relations=related_rels[:50],
        context=context,
    )


def _assemble_context(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    llm_response: str = "",
) -> str:
    """Assemble structured context text from entities and relations."""
    parts: list[str] = []

    if entities:
        parts.append("=== Matched Entities ===")
        for e in entities[:20]:
            kind = e.get("entity_type", e.get("kind", ""))
            name = e.get("name", e.get("entity_name", ""))
            fp = e.get("file_path", "")
            desc = e.get("description", "")
            line = f"[{kind}] {name}"
            if fp:
                line += f" ({fp})"
            parts.append(line)
            if desc:
                parts.append(f"  {desc[:200]}")

    # Deduplicate relations
    seen_rels: set[str] = set()
    unique_rels: list[dict[str, Any]] = []
    for r in relations:
        src = r.get("src_id", "")
        tgt = r.get("tgt_id", "")
        kw = r.get("keywords", "")
        key = f"{src}-{kw}-{tgt}"
        if key not in seen_rels:
            seen_rels.add(key)
            unique_rels.append(r)

    if unique_rels:
        parts.append("\n=== Relations ===")
        for r in unique_rels[:30]:
            src = r.get("src_id", "")
            tgt = r.get("tgt_id", "")
            kw = r.get("keywords", "RELATED")
            parts.append(f"  {src} --{kw}--> {tgt}")

    if llm_response:
        parts.append("\n=== LightRAG Response ===")
        parts.append(llm_response[:2000])

    return "\n".join(parts)


# ── Iterative deep query: LLM-driven multi-round retrieval ──

DEEP_QUERY_SYSTEM = """You are a code knowledge graph retrieval planner. Your task is to ensure the collected context fully answers the user's question.

## Steps

1. **Decompose**: Break the user's question into specific sub-questions.
2. **Check coverage**: For each sub-question, check if the existing context contains enough code details (function implementations, call chains, parameters). Just seeing a function name doesn't count — you need actual logic or implementation details.
3. **Generate follow-up queries**: For uncovered sub-questions, extract precise query terms (function names, class names, file names, module names). Prefer identifiers that appear in the existing context but haven't been expanded.

## Rules

- If missing is non-empty, queries must also be non-empty.
- Always try to query — don't assume the knowledge graph lacks information.
- Extract clues from existing context: if a class/function name appears but isn't expanded, use it as a query term.

## Output

Return only JSON:
```json
{
  "sub_questions": ["sub-question 1", "sub-question 2"],
  "covered": ["covered sub-questions"],
  "missing": ["uncovered sub-questions"],
  "queries": ["query_term_1", "query_term_2"],
  "reason": "brief explanation"
}
```

If all sub-questions are covered:
```json
{"sub_questions": [...], "covered": [...], "missing": [], "queries": [], "reason": "Context fully covers all sub-questions"}
```"""


async def iterative_deep_query(
    client: Any,
    query: str,
    initial_context: str,
    *,
    max_rounds: int = 2,
    llm_fn: Any = None,
) -> QueryResult:
    """Perform iterative deep queries — LLM analyzes gaps and triggers follow-ups.

    Args:
        client: LightRAGClient instance
        query: Original user query
        initial_context: Context from initial hybrid_query
        max_rounds: Maximum follow-up rounds (default: 2)
        llm_fn: Async function(messages) -> str for LLM calls.
                 If None, uses client.query() as fallback.

    Returns:
        QueryResult with accumulated context from all rounds
    """
    accumulated = initial_context
    total_rounds = 1
    all_entities: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []

    for round_idx in range(max_rounds):
        # Ask LLM what additional info is needed
        follow_ups = await _plan_follow_ups(
            query, accumulated, llm_fn=llm_fn, client=client,
        )
        if not follow_ups:
            break

        # Execute follow-up queries
        total_rounds += 1
        for q in follow_ups[:3]:
            try:
                result = await hybrid_query(client, q, top_k=5, depth=1)
                if result.context:
                    accumulated += f"\n\n## Follow-up: {q}\n{result.context}"
                    all_entities.extend(result.entities)
                    all_relations.extend(result.relations)
            except Exception as exc:
                logger.warning("Follow-up query '%s' failed: %s", q, exc)

    return QueryResult(
        query=query, mode="deep",
        entities=all_entities,
        relations=all_relations,
        context=accumulated,
        rounds=total_rounds,
    )


async def _plan_follow_ups(
    query: str,
    context: str,
    *,
    llm_fn: Any = None,
    client: Any = None,
) -> list[str]:
    """Use LLM to analyze context gaps and return follow-up query terms."""
    plan_prompt = f"## User Question\n{query}\n\n## Existing Context\n{context}"

    try:
        if llm_fn:
            messages = [
                {"role": "system", "content": DEEP_QUERY_SYSTEM},
                {"role": "user", "content": plan_prompt},
            ]
            text = await llm_fn(messages)
        else:
            # Fallback: use LightRAG query to simulate planning
            result = await client.query(
                f"What additional information is needed to answer: {query}",
                mode="local",
            )
            text = result.get("response", "")

        # Parse JSON from response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
        else:
            return []

        follow_ups = parsed.get("queries", [])
        missing = parsed.get("missing", [])

        # Fallback: if LLM reports missing but no queries, extract from missing
        if not follow_ups and missing:
            follow_ups = [m.split("(")[0].strip() for m in missing[:3]]

        return follow_ups

    except Exception as exc:
        logger.warning("Deep query planning failed: %s", exc)
        return []

