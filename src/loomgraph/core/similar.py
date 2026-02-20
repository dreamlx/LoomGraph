"""Cross-workspace entity similarity search.

Finds similar entities across workspaces using exact and fuzzy
name matching (Phase 1: stdlib SequenceMatcher).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.7


@dataclass
class SimilarResult:
    """Result of cross-workspace similarity search."""

    query_entity: str
    matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "query_entity": self.query_entity,
            "matches": self.matches,
        }


def _count_entity_relations(
    entity_name: str, relations: list[dict[str, Any]]
) -> int:
    """Count relations involving the given entity (as src or tgt)."""
    count = 0
    for rel in relations:
        if rel.get("src_id") == entity_name or rel.get("tgt_id") == entity_name:
            count += 1
    return count


@dataclass
class SimilarAnalyzer:
    """Finds similar entities across multiple workspaces.

    Args:
        clients: List of LightRAG clients, each bound to a workspace
        workspace_names: Corresponding workspace names
    """

    clients: list[Any]  # list[LightRAGClient]
    workspace_names: list[str]

    async def analyze(self, entity_name: str) -> SimilarResult:
        """Search for similar entities across all workspaces.

        Algorithm:
            1. Concurrently fetch entities + relations from all workspaces
            2. Phase 1: exact name match
            3. Phase 1: fuzzy name match (SequenceMatcher, ratio > 0.7)
            4. Count relations for each match

        Args:
            entity_name: Entity name to search for

        Returns:
            SimilarResult with matched entities and metadata
        """
        # Concurrent fetch: entities + relations for each workspace
        coros = []
        for client in self.clients:
            coros.append(client.get_all_entities())
            coros.append(client.get_all_relations())

        results = await asyncio.gather(*coros)

        # Unpack: results[0]=entities_ws0, results[1]=relations_ws0, results[2]=entities_ws1, ...
        matches: list[dict[str, Any]] = []
        query_lower = entity_name.lower()

        for i, ws_name in enumerate(self.workspace_names):
            entities = results[i * 2]
            relations = results[i * 2 + 1]

            for entity in entities:
                name = entity.get("entity_name", "")
                if not name:
                    continue

                # Exact match
                if name == entity_name:
                    rel_count = _count_entity_relations(name, relations)
                    matches.append({
                        "workspace": ws_name,
                        "entity": name,
                        "match_type": "exact",
                        "relations_count": rel_count,
                    })
                    continue

                # Fuzzy match (case-insensitive)
                ratio = SequenceMatcher(
                    None, query_lower, name.lower()
                ).ratio()
                if ratio > FUZZY_THRESHOLD:
                    rel_count = _count_entity_relations(name, relations)
                    matches.append({
                        "workspace": ws_name,
                        "entity": name,
                        "match_type": "fuzzy",
                        "relations_count": rel_count,
                    })

        return SimilarResult(
            query_entity=entity_name,
            matches=matches,
        )
