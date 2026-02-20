"""Project module overview analysis.

Generates a high-level view of all modules in the knowledge graph,
with entity statistics, top entities, and optional LLM summaries.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from loomgraph.core.deps import DepsAnalyzer, extract_module

logger = logging.getLogger(__name__)


@dataclass
class OverviewResult:
    """Result of overview analysis."""

    modules: list[dict[str, Any]] = field(default_factory=list)
    dependency_graph: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "modules": self.modules,
            "dependency_graph": self.dependency_graph,
        }


@dataclass
class OverviewAnalyzer:
    """Generates a project module overview from the knowledge graph.

    Args:
        client: LightRAG client instance
        depth: Directory depth for module grouping
    """

    client: Any  # LightRAGClient
    depth: int = 2

    async def analyze(self, no_summary: bool = False) -> OverviewResult:
        """Run overview analysis.

        Args:
            no_summary: If True, skip LLM-generated module summaries

        Returns:
            OverviewResult with module details and dependency graph
        """
        entities = await self.client.get_all_entities()
        relations = await self.client.get_all_relations()

        # Group entities by module
        # module -> {entities: [], entity_types: Counter, files: set}
        module_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"entities": [], "entity_types": defaultdict(int), "files": set()}
        )

        entity_module: dict[str, str] = {}

        for entity in entities:
            # Handle both injection format (entity_name) and API response format (entity_id/id)
            name = entity.get("entity_name", "") or entity.get("entity_id", "") or entity.get("id", "")
            source_id = entity.get("source_id", "")
            entity_type = entity.get("entity_type", "unknown")

            if not name or not source_id:
                continue

            module = extract_module(source_id, self.depth)
            entity_module[name] = module

            md = module_data[module]
            md["entities"].append(name)
            md["entity_types"][entity_type] += 1
            # Extract just the filename
            filename = PurePosixPath(source_id).name
            md["files"].add(filename)

        # Count relations per entity for ranking
        entity_relation_count: dict[str, int] = defaultdict(int)
        for relation in relations:
            # Handle both injection format (src_id/tgt_id) and API response format (source/target)
            src = relation.get("src_id", "") or relation.get("source", "")
            tgt = relation.get("tgt_id", "") or relation.get("target", "")
            if src:
                entity_relation_count[src] += 1
            if tgt:
                entity_relation_count[tgt] += 1

        # Build module results
        modules_list: list[dict[str, Any]] = []
        for module_name in sorted(module_data.keys()):
            md = module_data[module_name]
            # Sort entities by relation count (descending)
            top_entities = sorted(
                md["entities"],
                key=lambda e: entity_relation_count.get(e, 0),
                reverse=True,
            )[:10]  # Top 10

            module_info: dict[str, Any] = {
                "name": module_name,
                "entity_count": len(md["entities"]),
                "entities_by_type": dict(md["entity_types"]),
                "top_entities": top_entities,
                "files": sorted(md["files"]),
                "summary": "",
            }
            modules_list.append(module_info)

        # Generate LLM summaries if requested
        if not no_summary:
            for module_info in modules_list:
                try:
                    prompt = (
                        f"Briefly describe the module '{module_info['name']}' "
                        f"which contains {module_info['entity_count']} entities: "
                        f"{', '.join(module_info['top_entities'][:5])}. "
                        f"Files: {', '.join(module_info['files'][:5])}. "
                        f"One sentence summary."
                    )
                    resp = await self.client.query(prompt, mode="local")
                    module_info["summary"] = resp.get("response", "")
                except Exception:
                    logger.warning("Failed to generate summary for %s", module_info["name"])
                    module_info["summary"] = ""

        # Get dependency graph (reuse DepsAnalyzer with pre-fetched data)
        deps_analyzer = DepsAnalyzer(client=self.client, depth=self.depth)
        deps_result = await deps_analyzer.analyze()

        return OverviewResult(
            modules=modules_list,
            dependency_graph=deps_result.to_dict(),
        )
