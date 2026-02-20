"""Cross-workspace comparison.

Compares entities and relations between two workspaces using
entity name matching (Phase 1).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CompareResult:
    """Result of cross-workspace comparison."""

    ws1: str
    ws2: str
    summary: dict[str, int] = field(default_factory=dict)
    only_in_ws1: list[dict[str, Any]] = field(default_factory=list)
    only_in_ws2: list[dict[str, Any]] = field(default_factory=list)
    relation_changes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "ws1": self.ws1,
            "ws2": self.ws2,
            "summary": self.summary,
            "only_in_ws1": self.only_in_ws1,
            "only_in_ws2": self.only_in_ws2,
            "relation_changes": self.relation_changes,
        }


def _entity_to_info(entity: dict[str, Any]) -> dict[str, str]:
    """Extract summary info from an entity dict."""
    return {
        "name": entity.get("entity_name", ""),
        "type": entity.get("entity_type", ""),
        "source_id": entity.get("source_id", ""),
    }


def _relation_key(rel: dict[str, Any]) -> tuple[str, str, str]:
    """Build a comparable key from a relation dict."""
    return (rel.get("src_id", ""), rel.get("tgt_id", ""), rel.get("keywords", ""))


def _build_entity_relations(
    relations: list[dict[str, Any]], shared_names: set[str]
) -> dict[str, set[tuple[str, str, str]]]:
    """Group relation keys by entity name (both src and tgt)."""
    entity_rels: dict[str, set[tuple[str, str, str]]] = {}
    for rel in relations:
        key = _relation_key(rel)
        src = rel.get("src_id", "")
        tgt = rel.get("tgt_id", "")
        # Only track relations involving shared entities
        if src in shared_names:
            entity_rels.setdefault(src, set()).add(key)
        if tgt in shared_names:
            entity_rels.setdefault(tgt, set()).add(key)
    return entity_rels


@dataclass
class CompareAnalyzer:
    """Compares entities and relations between two workspaces.

    Args:
        client1: LightRAG client for workspace 1
        client2: LightRAG client for workspace 2
        ws1: Name of workspace 1
        ws2: Name of workspace 2
    """

    client1: Any  # LightRAGClient
    client2: Any  # LightRAGClient
    ws1: str = "ws1"
    ws2: str = "ws2"

    async def analyze(self) -> CompareResult:
        """Run cross-workspace comparison.

        Algorithm:
            1. Concurrently fetch entities + relations from both workspaces
            2. Set diff on entity names → only_in_ws1, only_in_ws2, shared
            3. For shared entities, compare relation sets
            4. Build CompareResult

        Returns:
            CompareResult with entity diffs and relation changes
        """
        # Concurrent fetch (4 requests in parallel)
        ws1_entities, ws1_relations, ws2_entities, ws2_relations = await asyncio.gather(
            self.client1.get_all_entities(),
            self.client1.get_all_relations(),
            self.client2.get_all_entities(),
            self.client2.get_all_relations(),
        )

        # Build name→entity mappings
        ws1_map = {e.get("entity_name", ""): e for e in ws1_entities}
        ws2_map = {e.get("entity_name", ""): e for e in ws2_entities}

        ws1_names = set(ws1_map.keys())
        ws2_names = set(ws2_map.keys())

        only1 = ws1_names - ws2_names
        only2 = ws2_names - ws1_names
        shared = ws1_names & ws2_names

        only_in_ws1 = sorted(
            [_entity_to_info(ws1_map[n]) for n in only1],
            key=lambda x: x["name"],
        )
        only_in_ws2 = sorted(
            [_entity_to_info(ws2_map[n]) for n in only2],
            key=lambda x: x["name"],
        )

        # Compare relations for shared entities
        ws1_ent_rels = _build_entity_relations(ws1_relations, shared)
        ws2_ent_rels = _build_entity_relations(ws2_relations, shared)

        relation_changes: list[dict[str, Any]] = []
        all_rel_entities = set(ws1_ent_rels.keys()) | set(ws2_ent_rels.keys())

        for entity_name in sorted(all_rel_entities):
            rels1 = ws1_ent_rels.get(entity_name, set())
            rels2 = ws2_ent_rels.get(entity_name, set())

            if rels1 == rels2:
                continue

            added = rels2 - rels1
            removed = rels1 - rels2

            relation_changes.append({
                "entity": entity_name,
                "ws1_count": len(rels1),
                "ws2_count": len(rels2),
                "added": [
                    {"src": r[0], "tgt": r[1], "keywords": r[2]} for r in sorted(added)
                ],
                "removed": [
                    {"src": r[0], "tgt": r[1], "keywords": r[2]} for r in sorted(removed)
                ],
            })

        return CompareResult(
            ws1=self.ws1,
            ws2=self.ws2,
            summary={
                "only_in_ws1": len(only1),
                "only_in_ws2": len(only2),
                "in_both": len(shared),
                "relations_diff": len(relation_changes),
            },
            only_in_ws1=only_in_ws1,
            only_in_ws2=only_in_ws2,
            relation_changes=relation_changes,
        )
