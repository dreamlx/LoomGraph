"""Module dependency analysis.

Analyzes cross-module dependencies by querying the knowledge graph
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
        client: GraphStore instance
        depth: Starting directory depth for module grouping
        auto_depth: When True (default), if the starting depth collapses the
            graph to a single real module (e.g. a single-package repo
            ``src/<pkg>/*`` where depth=2 merges cli/core/mcp/storage into one
            module), re-run at increasing depth until more than one module
            appears or the deepest source path is exhausted (#106). Set False
            to honor ``depth`` exactly.
    """

    client: Any  # GraphStore
    depth: int = 2
    auto_depth: bool = True

    async def analyze(self) -> DepsResult:
        """Run dependency analysis.

        Algorithm:
            1. Fetch all entities, build entity and module-endpoint mappings
            2. Fetch all relations, map src/tgt to modules
            3. Skip same-module relations and unmapped entities
            4. Aggregate by (src_module, tgt_module)

        With ``auto_depth`` (default), steps 1-4 run at increasing depth until
        the grouping yields more than one real module, so single-package repos
        surface their sub-package dependencies instead of collapsing.

        Returns:
            DepsResult with modules, dependencies, and stats
        """
        entities = await self.client.get_all_entities()
        relations = await self.client.get_all_relations()

        # Cap auto-drill at the deepest directory level present in the graph,
        # so we never recurse past what the data can distinguish.
        max_depth = self.depth
        if self.auto_depth:
            for entity in entities:
                source_id = entity.get("source_id", "")
                if source_id and source_id != "external":
                    dir_count = len(PurePosixPath(source_id).parts) - 1  # drop filename
                    if dir_count > max_depth:
                        max_depth = dir_count

        modules_set: set[str] = set()
        edge_agg: dict[tuple[str, str], dict[str, Any]] = {}
        for d in range(self.depth, max_depth + 1):
            modules_set, _, edge_agg = self._analyze_at_depth(
                entities, relations, d
            )
            # Stop as soon as more than one real module (excluding the root "."
            # bucket) exists — the first depth with real structure. auto_depth
            # off, or exhausted depth, also stops here.
            if not self.auto_depth or len(modules_set - {"."}) > 1 or d == max_depth:
                break

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

    @staticmethod
    def _analyze_at_depth(
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        depth: int,
    ) -> tuple[set[str], dict[str, str], dict[tuple[str, str], dict[str, Any]]]:
        """Group entities/relations into modules at a fixed depth.

        Returns ``(modules_set, entity_module, edge_agg)``. Pure (no I/O) so
        ``analyze`` can re-run it at increasing depths cheaply.
        """
        # Build entity_name → module mapping
        # Handle both injection format (entity_name) and API response format (entity_id/id)
        entity_module: dict[str, str] = {}
        module_endpoint: dict[str, set[str]] = defaultdict(set)
        modules_set: set[str] = set()

        for entity in entities:
            name = entity.get("entity_name", "") or entity.get("entity_id", "") or entity.get("id", "")
            source_id = entity.get("source_id", "")
            entity_type = entity.get("entity_type", "unknown")
            if not name or not source_id:
                continue
            # Skip external stubs — they produce meaningless "." module deps
            if entity_type == "external" or source_id == "external":
                continue
            module = extract_module(source_id, depth)
            entity_module[name] = module
            endpoint, separator, _ = name.rpartition(".")
            if separator:
                module_endpoint[endpoint].add(module)
            modules_set.add(module)

        # Aggregate cross-module relations
        # Key: (from_module, to_module) → {count, types}
        edge_agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "types": defaultdict(int)}
        )

        for relation in relations:
            # Handle both injection format (src_id/tgt_id) and API response format (source/target)
            src_name = relation.get("src_id", "") or relation.get("source", "")
            tgt_name = relation.get("tgt_id", "") or relation.get("target", "")
            rel_type = relation.get("keywords", "UNKNOWN")

            src_module = entity_module.get(src_name)
            tgt_module = entity_module.get(tgt_name)

            # codeindex represents a module-level IMPORTS edge with module ids
            # (for example ``src.cli.handler → src.core.service``), not symbol
            # entity ids. Accept only resolved endpoints that have exactly one
            # source-bearing module mapping.
            # This deliberately leaves external, unresolved and ambiguous
            # imports outside the dependency aggregate.
            if (
                rel_type == "IMPORTS"
                and relation.get("resolution_qualifier") == "resolved"
            ):
                source_modules = module_endpoint.get(src_name, set())
                target_modules = module_endpoint.get(tgt_name, set())
                if src_module is None and len(source_modules) == 1:
                    src_module = next(iter(source_modules))
                if tgt_module is None and len(target_modules) == 1:
                    tgt_module = next(iter(target_modules))

            # Skip if either entity is unmapped (external/no source_id)
            if src_module is None or tgt_module is None:
                continue

            # Skip same-module relations
            if src_module == tgt_module:
                continue

            key = (src_module, tgt_module)
            edge_agg[key]["count"] += 1
            edge_agg[key]["types"][rel_type] += 1

        return modules_set, entity_module, edge_agg
