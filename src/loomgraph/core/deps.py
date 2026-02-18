"""Module dependency analysis.

Analyzes cross-module dependencies by querying the LightRAG knowledge graph
and grouping entities by their file path modules.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)


def extract_module(file_path: str, depth: int) -> str:
    """Extract module name from a file path at the given depth.

    Args:
        file_path: Source file path, e.g. "src/auth/service.py"
        depth: Number of directory levels to include

    Returns:
        Module path string, e.g. "src/auth" for depth=2

    Examples:
        >>> extract_module("src/auth/service.py", depth=2)
        'src/auth'
        >>> extract_module("main.py", depth=2)
        '.'
    """
    if not file_path:
        return "."

    parts = PurePosixPath(file_path).parts
    # Remove the filename (last part)
    dir_parts = parts[:-1] if len(parts) > 1 else ()

    if not dir_parts:
        return "."

    # Take up to `depth` directory levels
    module_parts = dir_parts[:depth]
    return "/".join(module_parts)


@dataclass
class DepsResult:
    """Result of dependency analysis."""

    modules: list[str] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "modules": self.modules,
            "dependencies": self.dependencies,
            "stats": self.stats,
        }


@dataclass
class DepsAnalyzer:
    """Analyzes module-level dependencies from the knowledge graph.

    Args:
        client: LightRAG client instance
        depth: Directory depth for module grouping
    """

    client: Any  # LightRAGClient
    depth: int = 2

    async def analyze(self) -> DepsResult:
        """Run dependency analysis.

        Algorithm:
            1. Fetch all entities, build name→module mapping
            2. Fetch all relations, map src/tgt to modules
            3. Skip same-module relations and unmapped entities
            4. Aggregate by (src_module, tgt_module)

        Returns:
            DepsResult with modules, dependencies, and stats
        """
        entities = await self.client.get_all_entities()
        relations = await self.client.get_all_relations()

        # Build entity_name → module mapping
        entity_module: dict[str, str] = {}
        modules_set: set[str] = set()

        for entity in entities:
            name = entity.get("entity_name", "")
            source_id = entity.get("source_id", "")
            if not name or not source_id:
                continue
            module = extract_module(source_id, self.depth)
            entity_module[name] = module
            modules_set.add(module)

        # Aggregate cross-module relations
        # Key: (from_module, to_module) → {count, types}
        edge_agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "types": defaultdict(int)}
        )

        for relation in relations:
            src_name = relation.get("src_id", "")
            tgt_name = relation.get("tgt_id", "")
            rel_type = relation.get("keywords", "UNKNOWN")

            src_module = entity_module.get(src_name)
            tgt_module = entity_module.get(tgt_name)

            # Skip if either entity is unmapped (external/no source_id)
            if src_module is None or tgt_module is None:
                continue

            # Skip same-module relations
            if src_module == tgt_module:
                continue

            key = (src_module, tgt_module)
            edge_agg[key]["count"] += 1
            edge_agg[key]["types"][rel_type] += 1

        # Build sorted results
        sorted_modules = sorted(modules_set)
        dependencies = [
            {
                "from": src,
                "to": tgt,
                "count": agg["count"],
                "types": dict(agg["types"]),
            }
            for (src, tgt), agg in sorted(edge_agg.items())
        ]

        return DepsResult(
            modules=sorted_modules,
            dependencies=dependencies,
            stats={
                "total_modules": len(sorted_modules),
                "total_dependencies": len(dependencies),
                "total_entities": len(entities),
                "total_relations": len(relations),
            },
        )
