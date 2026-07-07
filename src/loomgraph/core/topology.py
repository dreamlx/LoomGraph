"""Graph topology debt analysis.

Analyzes knowledge graph topology to detect structural code smells:
orphan entities, hub fragility, god functions, placeholder modules,
and cross-module coupling density.
"""

from __future__ import annotations

import logging
import re
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

# Data classes and DTOs that are legitimately orphaned (used via serialization)
WHITELIST_ORPHANS = frozenset({
    # Core data models (models.py)
    "EntityData", "RelationData",
    # Result DTOs (to_dict for JSON serialization)
    "CompareResult", "DepsResult", "TopologyResult", "ImpactResult",
    "OverviewResult", "CouplingMetrics", "SimilarResult",
    # Impact analysis models
    "ChangedFile", "ChangedSymbol", "Caller",
    # Embedding models
    "EmbeddingResult",
    # Dataclass utility methods
    "to_dict", "__post_init__",
    # Enums
    "ChangeType", "ErrorCode",
    # Config utilities
    "reset_settings",
    # CLI command groups
    "workspace",
})

# Suffix patterns for entities that are legitimately orphaned
ORPHAN_SUFFIX_PATTERNS = (
    "Analyzer",  # CompareAnalyzer, DepsAnalyzer, etc. - called by CLI dynamically
    "Extractor",  # ChangedSymbolExtractor - helper classes
    "Parser",  # GitDiffParser - utility classes
    "Assessor",  # RiskAssessor - analysis classes
    "Client",  # GraphStore, JinaEmbeddingClient - service clients
)

# Regex patterns for common data classes and DTOs (reduce false positives)
ORPHAN_REGEX_PATTERNS = (
    r".*Config$",  # Configuration classes (e.g., AdaptiveSymbolsConfig)
    r".*Result$",  # Result DTOs (e.g., ScanResult, ParseResult)
    r".*Info$",  # Information classes (e.g., ErrorInfo, RouteInfo)
    r".*Error$",  # Error classes (e.g., ValidationError)
    r".*Data$",  # Data classes (e.g., EntityData, RelationData)
    r".*DTO$",  # Explicit DTOs (e.g., UserDTO)
    r".*Model$",  # Data models (e.g., UserModel)
    r".*Schema$",  # Schema definitions (e.g., RequestSchema)
)

# Public utility functions with expected high fan-in (hubs by design)
WHITELIST_HUBS = frozenset({
    # CLI output helpers (used across all CLI commands)
    "output_success", "output_error", "output_partial_error",
    # Configuration singletons (used across all modules)
    "get_settings", "get_auto_workspace",
    # Internal helpers (high fan-in is intentional)


})


def _is_noise(name: str) -> bool:
    """Check if an entity name is stdlib/noise and should be excluded."""
    if name in STDLIB_ENTITIES:
        return True
    return any(name.endswith(suffix) for suffix in NOISE_SUFFIXES)


def _is_whitelisted_orphan(name: str, source_id: str = "") -> bool:
    """Check if an entity is a legitimate orphan (whitelist).

    Args:
        name: Entity name (may be namespaced like "CompareResult.to_dict")
        source_id: File path where entity is defined

    Returns:
        True if the entity should be excluded from orphan detection
    """
    # Exact match in whitelist
    if name in WHITELIST_ORPHANS:
        return True

    # Test fixtures/helpers (support both "tests/" and "/tests/")
    if "tests/" in source_id or source_id.startswith("test_"):
        return True

    # Models.py file pattern (data classes)
    if "models.py" in source_id or "/models/" in source_id:
        return True

    # Namespaced methods (.to_dict, .__post_init__, etc.)
    if "." in name:
        base_name, method_name = name.rsplit(".", 1)
        if method_name in WHITELIST_ORPHANS:  # e.g., "to_dict", "__post_init__"
            return True
        # Dunder methods (called by runtime)
        if method_name.startswith("__") and method_name.endswith("__"):
            return True

    # Suffix patterns (Analyzer, Extractor, Parser, etc.)
    # Extract the class name (before the last dot if namespaced)
    class_name = name.split(".")[-1] if "." not in name else name.split(".")[0]
    if any(class_name.endswith(pattern) for pattern in ORPHAN_SUFFIX_PATTERNS):
        return True

    # Regex patterns for data classes and DTOs (Config, Result, Info, Error, etc.)
    return any(re.match(pattern, class_name) for pattern in ORPHAN_REGEX_PATTERNS)


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



def _normalize_type_field(items: list[dict[str, Any]]) -> None:
    """Normalize server-side 'entity_type' to client-side 'type' key."""
    for item in items:
        if "entity_type" in item and "type" not in item:
            item["type"] = item.pop("entity_type")


def _compute_coupled_pairs(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Compute top N most-coupled module pairs from entities and relations.

    Builds entity→module mapping from source_id, then counts cross-module
    relation pairs. Returns sorted list of {from, to, count}.
    """
    # Build entity name → module mapping
    entity_module: dict[str, str] = {}
    for entity in entities:
        name = _entity_name(entity)
        if not name or _is_external(entity) or _is_noise(name):
            continue
        source_id = entity.get("source_id", "")
        if source_id:
            entity_module[name] = extract_module(source_id, depth=2)

    # Count cross-module pairs
    pair_count: dict[tuple[str, str], int] = {}
    for rel in relations:
        src = rel.get("src_id", "") or rel.get("source", "")
        tgt = rel.get("tgt_id", "") or rel.get("target", "")
        if not src or not tgt:
            continue
        src_mod = entity_module.get(src)
        tgt_mod = entity_module.get(tgt)
        if src_mod and tgt_mod and src_mod != tgt_mod:
            pair = (src_mod, tgt_mod)
            pair_count[pair] = pair_count.get(pair, 0) + 1

    sorted_pairs = sorted(pair_count.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"from": p[0], "to": p[1], "count": c} for (p, c) in sorted_pairs]


def _strip_line_range(source_id: str) -> str:
    """Strip line range suffix from source_id (e.g. 'src/a.py:1-50' → 'src/a.py')."""
    colon_idx = source_id.rfind(":")
    if colon_idx > 0:
        suffix = source_id[colon_idx + 1:]
        if suffix and (suffix[0].isdigit() or suffix[0] == "-"):
            return source_id[:colon_idx]
    return source_id


def _common_source_prefix(source_ids: list[str]) -> str:
    """Compute common directory prefix from source_ids.

    Strips line ranges, extracts directory parts, and finds the longest
    common directory prefix. Returns empty string if no common prefix.

    Examples:
        >>> _common_source_prefix(["src/core/a.py:1-10", "src/core/b.py:1-5"])
        'src/core/'
        >>> _common_source_prefix(["src/cli/a.py", "src/core/b.py"])
        'src/'
    """
    if not source_ids:
        return ""

    # Extract directory paths
    dirs: list[list[str]] = []
    for sid in source_ids:
        clean = _strip_line_range(sid)
        parts = clean.split("/")
        # Drop filename (last element)
        dir_parts = parts[:-1] if len(parts) > 1 else []
        dirs.append(dir_parts)

    if not dirs or not dirs[0]:
        return ""

    # Find common prefix
    prefix_parts: list[str] = []
    for i, part in enumerate(dirs[0]):
        if all(len(d) > i and d[i] == part for d in dirs):
            prefix_parts.append(part)
        else:
            break

    if not prefix_parts:
        return ""

    return "/".join(prefix_parts) + "/"


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
        client: GraphStore instance
        hub_threshold: Minimum in-degree to flag as hub
        god_threshold: Minimum out-degree to flag as god function
        module: Optional module prefix filter (e.g. "cli" filters source_id)
        source_prefix: Common prefix to strip from source_ids for module
            extraction. Auto-detected from source_ids if None.
    """

    client: Any  # GraphStore
    hub_threshold: int = 8
    god_threshold: int = 10
    module: str | None = None
    source_prefix: str | None = None
    scope: str | None = None  # absolute path-prefix filter ("src/"); wins over module (#61)

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

        # Auto-detect source_prefix for correct module extraction in coupling
        effective_prefix = self.source_prefix
        if effective_prefix is None:
            source_ids = await self.client.get_source_ids()
            effective_prefix = _common_source_prefix(source_ids)
            logger.debug("Auto-detected source_prefix: %r", effective_prefix)

        # For filtering endpoints (orphans/degree): scope wins (absolute path
        # prefix, e.g. "src/"); else combine auto prefix + module (#61).
        if self.scope:
            filter_prefix = self.scope
        else:
            filter_prefix = effective_prefix or ""
            if self.module:
                filter_prefix = filter_prefix + self.module + "/"
            filter_prefix = filter_prefix or None

        orphans, hubs, gods, stats = await asyncio.gather(
            self.client.get_orphan_entities(
                exclude_types=["module"], source_prefix=filter_prefix
            ),
            self.client.get_degree_distribution(
                direction="in",
                min_degree=self.hub_threshold,
                source_prefix=filter_prefix,
            ),
            self.client.get_degree_distribution(
                direction="out",
                min_degree=self.god_threshold,
                source_prefix=filter_prefix,
            ),
            self.client.get_graph_stats(
                # ponytail: coupling still uses the global source prefix —
                # scope-filtering coupling needs a store API change. orphans/
                # hubs/gods (the #61 pain points) are already scoped above.
                source_prefix=effective_prefix or None,
                module_depth=2,
            ),
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

        def _keep_orphan(item: dict[str, Any]) -> bool:
            """Filter orphans, excluding whitelisted data classes."""
            if not _keep(item):
                return False
            name = _server_name(item)
            source_id = item.get("source_id", "")
            # Use unified whitelist logic
            return not _is_whitelisted_orphan(name, source_id)

        def _keep_hub(item: dict[str, Any]) -> bool:
            """Filter hubs, excluding whitelisted utilities."""
            if not _keep(item):
                return False
            name = _server_name(item)
            # Exclude whitelisted hubs (public utilities)
            return name not in WHITELIST_HUBS

        orphans = [o for o in orphans if _keep_orphan(o)]
        hubs = [h for h in hubs if _keep_hub(h)]
        gods = [
            g for g in gods
            if _keep(g) and g.get("entity_type") != "module"
        ]

        # Normalize field names to match client-side format
        _normalize_type_field(orphans)
        _normalize_type_field(hubs)
        _normalize_type_field(gods)
        for h in hubs:
            if "degree" in h and "in_degree" not in h:
                h["in_degree"] = h.pop("degree")
        for g in gods:
            if "degree" in g and "out_degree" not in g:
                g["out_degree"] = g.pop("degree")

        # Stats: handle both field naming conventions
        total_entities = stats.get("total_entities") or stats.get("entity_count", 0)
        total_relations = stats.get("total_relations") or stats.get("relation_count", 0)

        # Compute coupled pairs client-side (server doesn't return pair detail)
        coupled_pairs: list[dict[str, Any]] = []
        if stats.get("cross_module_relations", 0) > 0:
            all_entities = await self.client.get_all_entities()
            all_relations = await self.client.get_all_relations()
            coupled_pairs = _compute_coupled_pairs(all_entities, all_relations)

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
                most_coupled_pairs=coupled_pairs,
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
        # Apply path filter at entry: scope (absolute prefix) wins over module (#61)
        if self.scope:
            entities = [
                e for e in entities
                if e.get("source_id", "").startswith(self.scope)
            ]
        elif self.module:
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

        # Aggregate class and constructor relations (fix false positive orphans)
        # For classes, include relations of their __init__ methods
        aggregated_in_degree = dict(in_degree)
        aggregated_out_degree = dict(out_degree)

        for name, entity in entity_map.items():
            if entity.get("entity_type", "") == "class":
                # Check if constructor has relations
                init_name = f"{name}.__init__"
                if init_name in in_degree:
                    # Merge constructor's callers into class
                    if name not in aggregated_in_degree:
                        aggregated_in_degree[name] = []
                    aggregated_in_degree[name].extend(in_degree[init_name])
                if init_name in out_degree:
                    # Merge constructor's callees into class
                    if name not in aggregated_out_degree:
                        aggregated_out_degree[name] = []
                    aggregated_out_degree[name].extend(out_degree[init_name])

        # Detect orphans (0 in + 0 out, exclude module type and whitelisted)
        orphans = []
        for name, entity in entity_map.items():
            if entity.get("entity_type", "") == "module":
                continue
            # Use aggregated degrees (includes constructor relations for classes)
            if name not in aggregated_in_degree and name not in aggregated_out_degree:
                source_id = entity.get("source_id", "")
                # Exclude whitelisted orphans (data classes, DTOs, test fixtures, etc.)
                if _is_whitelisted_orphan(name, source_id):
                    continue
                orphans.append({
                    "entity": name,
                    "type": entity.get("entity_type", "unknown"),
                    "source_id": source_id,
                })

        # Detect hubs (high in-degree)
        hubs = []
        for name, callers in sorted(
            in_degree.items(), key=lambda x: len(x[1]), reverse=True
        ):
            if len(callers) >= self.hub_threshold and name in entity_map:
                # Skip whitelisted hubs (public utilities)
                if name in WHITELIST_HUBS:
                    continue
                entity = entity_map[name]
                source_id = entity.get("source_id", "")
                # Exclude by file pattern (common utilities)
                if "_common.py" in source_id or "/config.py" in source_id:
                    continue
                hubs.append({
                    "entity": name,
                    "type": entity.get("entity_type", "unknown"),
                    "source_id": source_id,
                    "in_degree": len(callers),
                    "callers_sample": callers[:5],
                })

        # Detect god functions (high out-degree, exclude modules)
        god_functions = []
        for name, callees in sorted(
            out_degree.items(), key=lambda x: len(x[1]), reverse=True
        ):
            if len(callees) >= self.god_threshold and name in entity_map:
                entity = entity_map[name]
                if entity.get("entity_type", "") == "module":
                    continue
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

    Penalty rules (per-category capped to prevent runaway deductions):
      - orphan_ratio > 20% → -25
      - orphan_ratio > 10% → -15
      - hub (in_degree >= 15) → -5 per entity (cap -20)
      - god_function (out >= 25) → -5 per entity (cap -25)
      - god_function (out >= 15) → -3 per entity (cap -25)
      - placeholder_modules > 0 → -5 per module (cap -15)
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

    # Hub penalty (severe hubs with in_degree >= 15, cap -20)
    hub_penalty = 0
    for hub in result.hubs:
        if hub.get("in_degree", 0) >= 15:
            hub_penalty += 5
    score -= min(hub_penalty, 20)

    # God function penalty (cap -25)
    god_penalty = 0
    for gf in result.god_functions:
        out = gf.get("out_degree", 0)
        if out >= 25:
            god_penalty += 5
        elif out >= 15:
            god_penalty += 3
    score -= min(god_penalty, 25)

    # Placeholder module penalty (cap -15)
    score -= min(5 * len(result.placeholder_modules), 15)

    # Coupling density penalty
    if result.coupling.density > 0.5:
        score -= 10
    elif result.coupling.density > 0.3:
        score -= 5

    return max(0, score)
