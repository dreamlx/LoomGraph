"""Graph topology debt analysis.

Analyzes knowledge graph topology to detect structural code smells:
orphan entities, hub fragility, god functions, placeholder modules,
and cross-module coupling density.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from loomgraph.core.deps import extract_module

logger = logging.getLogger(__name__)

# Python builtins and stdlib entities to exclude from hub/god/orphan analysis
STDLIB_ENTITIES = frozenset({
    # Builtins
    "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "isinstance", "issubclass", "hasattr", "getattr", "setattr",
    "print", "range", "enumerate", "zip", "map", "filter",
    "super", "type", "object", "None", "True", "False",
    # Common stdlib modules
    "logging", "asyncio", "json", "os", "sys", "pathlib",
    "asyncio.run", "json.dumps", "json.loads",
})

# Method-call suffixes that indicate generic operations (not meaningful edges)
NOISE_SUFFIXES = frozenset({
    ".get", ".append", ".extend", ".items", ".keys", ".values",
    ".strip", ".split", ".replace", ".format", ".encode", ".decode",
    ".join", ".pop", ".update", ".add", ".remove", ".clear",
    ".startswith", ".endswith", ".lower", ".upper",
})


def _is_noise(name: str) -> bool:
    """Check if an entity name is stdlib/noise and should be excluded."""
    if name in STDLIB_ENTITIES:
        return True
    return any(name.endswith(suffix) for suffix in NOISE_SUFFIXES)


def _entity_name(entity: dict[str, Any]) -> str:
    """Extract entity name from various API response formats."""
    return (
        entity.get("entity_name", "")
        or entity.get("entity_id", "")
        or entity.get("id", "")
    )


def _is_external(entity: dict[str, Any]) -> bool:
    """Check if entity is an external stub."""
    return (
        entity.get("entity_type", "") == "external"
        or entity.get("source_id", "") == "external"
    )


@dataclass
class CouplingMetrics:
    """Cross-module coupling metrics."""

    cross_module: int = 0
    intra_module: int = 0
    density: float = 0.0
    most_coupled_pairs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cross_module_relations": self.cross_module,
            "intra_module_relations": self.intra_module,
            "density": round(self.density, 3),
            "most_coupled_pairs": self.most_coupled_pairs,
        }


@dataclass
class TopologyResult:
    """Result of graph topology analysis."""

    total_entities: int = 0
    total_relations: int = 0
    orphans: list[dict[str, Any]] = field(default_factory=list)
    hubs: list[dict[str, Any]] = field(default_factory=list)
    god_functions: list[dict[str, Any]] = field(default_factory=list)
    placeholder_modules: list[dict[str, Any]] = field(default_factory=list)
    coupling: CouplingMetrics = field(default_factory=CouplingMetrics)
    topology_score: int = 100

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "summary": {
                "total_entities": self.total_entities,
                "total_relations": self.total_relations,
                "orphan_count": len(self.orphans),
                "hub_count": len(self.hubs),
                "god_function_count": len(self.god_functions),
                "placeholder_module_count": len(self.placeholder_modules),
                "coupling_density": round(self.coupling.density, 3),
                "topology_score": self.topology_score,
            },
            "orphans": self.orphans,
            "hubs": self.hubs,
            "god_functions": self.god_functions,
            "placeholder_modules": self.placeholder_modules,
            "coupling": self.coupling.to_dict(),
        }


@dataclass
class TopologyAnalyzer:
    """Analyzes knowledge graph topology for structural code smells.

    Args:
        client: LightRAG client instance
        hub_threshold: Minimum in-degree to flag as hub
        god_threshold: Minimum out-degree to flag as god function
        module: Optional module prefix filter (e.g. "cli" filters source_id)
    """

    client: Any  # LightRAGClient
    hub_threshold: int = 5
    god_threshold: int = 5
    module: str | None = None

    async def analyze(self) -> TopologyResult:
        """Run topology analysis with server-side fallback.

        Tries server-side computation first (efficient for large graphs),
        falls back to client-side computation from raw data.
        """
        try:
            return await self._analyze_server_side()
        except Exception:
            logger.info("Server-side topology not available, falling back to client-side")
            entities = await self.client.get_all_entities()
            relations = await self.client.get_all_relations()
            return self.analyze_from_data(entities, relations)

    async def _analyze_server_side(self) -> TopologyResult:
        """Server-side topology analysis using dedicated endpoints."""
        import asyncio

        source_prefix = (self.module + "/") if self.module else None

        orphans, hubs, gods, stats = await asyncio.gather(
            self.client.get_orphan_entities(
                exclude_types=["module"], source_prefix=source_prefix
            ),
            self.client.get_degree_distribution(
                direction="in",
                min_degree=self.hub_threshold,
                source_prefix=source_prefix,
            ),
            self.client.get_degree_distribution(
                direction="out",
                min_degree=self.god_threshold,
                source_prefix=source_prefix,
            ),
            self.client.get_graph_stats(source_prefix=source_prefix),
        )

        # Filter noise and external entities from server results
        def _server_name(item: dict[str, Any]) -> str:
            return item.get("entity", "") or _entity_name(item)

        def _keep(item: dict[str, Any]) -> bool:
            name = _server_name(item)
            if _is_noise(name):
                return False
            return not (
                item.get("entity_type") == "external"
                or item.get("source_id") == "external"
            )

        orphans = [o for o in orphans if _keep(o)]
        hubs = [h for h in hubs if _keep(h)]
        gods = [g for g in gods if _keep(g)]

        # Normalize hub/god entries to match client-side format
        for h in hubs:
            if "degree" in h and "in_degree" not in h:
                h["in_degree"] = h.pop("degree")
        for g in gods:
            if "degree" in g and "out_degree" not in g:
                g["out_degree"] = g.pop("degree")

        # Stats: handle both field naming conventions
        total_entities = stats.get("total_entities") or stats.get("entity_count", 0)
        total_relations = stats.get("total_relations") or stats.get("relation_count", 0)

        result = TopologyResult(
            total_entities=total_entities,
            total_relations=total_relations,
            orphans=orphans,
            hubs=hubs,
            god_functions=gods,
            coupling=CouplingMetrics(
                cross_module=stats.get("cross_module_relations", 0),
                intra_module=stats.get("intra_module_relations", 0),
                density=stats.get("coupling_density", 0.0),
            ),
        )
        result.topology_score = _compute_score(result)
        return result

    def analyze_from_data(
        self,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> TopologyResult:
        """Client-side topology computation from raw entity/relation data.

        Pure function — no I/O, easy to unit test.
        """
        # Apply module filter at entry
        if self.module:
            prefix = self.module + "/"
            entities = [
                e for e in entities
                if e.get("source_id", "").startswith(prefix)
            ]

        # Build lookup structures
        entity_map: dict[str, dict[str, Any]] = {}
        module_entities: dict[str, list[str]] = {}  # module -> entity names

        for entity in entities:
            name = _entity_name(entity)
            if not name:
                continue
            if _is_external(entity):
                continue
            if _is_noise(name):
                continue
            entity_map[name] = entity
            source_id = entity.get("source_id", "")
            if source_id:
                mod = extract_module(source_id, depth=2)
                module_entities.setdefault(mod, []).append(name)

        # Build degree maps
        in_degree: dict[str, list[str]] = {}   # entity -> list of callers
        out_degree: dict[str, list[str]] = {}  # entity -> list of callees

        cross_module = 0
        intra_module = 0
        module_pair_count: dict[tuple[str, str], int] = {}

        for rel in relations:
            src = rel.get("src_id", "") or rel.get("source", "")
            tgt = rel.get("tgt_id", "") or rel.get("target", "")

            if not src or not tgt:
                continue

            # Only count relations where at least one endpoint is in our entity set
            src_in = src in entity_map
            tgt_in = tgt in entity_map

            if src_in and not _is_noise(tgt):
                out_degree.setdefault(src, []).append(tgt)
            if tgt_in and not _is_noise(src):
                in_degree.setdefault(tgt, []).append(src)

            # Coupling: count cross-module vs intra-module
            if src_in and tgt_in:
                src_sid = entity_map[src].get("source_id", "")
                tgt_sid = entity_map[tgt].get("source_id", "")
                src_mod = extract_module(src_sid, depth=2)
                tgt_mod = extract_module(tgt_sid, depth=2)
                if src_mod != tgt_mod:
                    cross_module += 1
                    pair = (src_mod, tgt_mod)
                    module_pair_count[pair] = module_pair_count.get(pair, 0) + 1
                else:
                    intra_module += 1

        total_relations_counted = cross_module + intra_module
        density = (
            cross_module / total_relations_counted
            if total_relations_counted > 0
            else 0.0
        )

        # Top coupled pairs
        sorted_pairs = sorted(
            module_pair_count.items(), key=lambda x: x[1], reverse=True
        )[:5]
        most_coupled = [
            {"from": p[0], "to": p[1], "count": c} for (p, c) in sorted_pairs
        ]

        # Detect orphans (0 in + 0 out, exclude module type)
        orphans = []
        for name, entity in entity_map.items():
            if entity.get("entity_type", "") == "module":
                continue
            if name not in in_degree and name not in out_degree:
                orphans.append({
                    "entity": name,
                    "type": entity.get("entity_type", "unknown"),
                    "source_id": entity.get("source_id", ""),
                })

        # Detect hubs (high in-degree)
        hubs = []
        for name, callers in sorted(
            in_degree.items(), key=lambda x: len(x[1]), reverse=True
        ):
            if len(callers) >= self.hub_threshold and name in entity_map:
                entity = entity_map[name]
                hubs.append({
                    "entity": name,
                    "type": entity.get("entity_type", "unknown"),
                    "source_id": entity.get("source_id", ""),
                    "in_degree": len(callers),
                    "callers_sample": callers[:5],
                })

        # Detect god functions (high out-degree)
        god_functions = []
        for name, callees in sorted(
            out_degree.items(), key=lambda x: len(x[1]), reverse=True
        ):
            if len(callees) >= self.god_threshold and name in entity_map:
                entity = entity_map[name]
                god_functions.append({
                    "entity": name,
                    "type": entity.get("entity_type", "unknown"),
                    "source_id": entity.get("source_id", ""),
                    "out_degree": len(callees),
                    "callees_sample": callees[:5],
                })

        # Detect placeholder modules (only __init__ entities)
        placeholder_modules = []
        for mod, names in module_entities.items():
            if all(n.endswith(".__init__") or n.endswith("__init__") for n in names):
                placeholder_modules.append({
                    "module": mod,
                    "entities": names,
                    "status": "empty",
                })

        coupling = CouplingMetrics(
            cross_module=cross_module,
            intra_module=intra_module,
            density=density,
            most_coupled_pairs=most_coupled,
        )

        result = TopologyResult(
            total_entities=len(entity_map),
            total_relations=len(relations),
            orphans=orphans,
            hubs=hubs,
            god_functions=god_functions,
            placeholder_modules=placeholder_modules,
            coupling=coupling,
        )
        result.topology_score = _compute_score(result)
        return result


def _compute_score(result: TopologyResult) -> int:
    """Compute topology health score (0-100, higher is healthier).

    Penalty rules from EPIC-009:
      - orphan_ratio > 20% → -25
      - orphan_ratio > 10% → -15
      - hub (in_degree >= 15) → -5 per entity
      - god_function (out >= 20) → -5 per entity
      - god_function (out >= 10) → -3 per entity
      - placeholder_modules > 0 → -5 per module
      - coupling_density > 0.5 → -10
      - coupling_density > 0.3 → -5
    """
    score = 100

    # Orphan ratio penalty
    if result.total_entities > 0:
        orphan_ratio = len(result.orphans) / result.total_entities
        if orphan_ratio > 0.20:
            score -= 25
        elif orphan_ratio > 0.10:
            score -= 15

    # Hub penalty (severe hubs with in_degree >= 15)
    for hub in result.hubs:
        if hub.get("in_degree", 0) >= 15:
            score -= 5

    # God function penalty
    for gf in result.god_functions:
        out = gf.get("out_degree", 0)
        if out >= 20:
            score -= 5
        elif out >= 10:
            score -= 3

    # Placeholder module penalty
    score -= 5 * len(result.placeholder_modules)

    # Coupling density penalty
    if result.coupling.density > 0.5:
        score -= 10
    elif result.coupling.density > 0.3:
        score -= 5

    return max(0, score)
