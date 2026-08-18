"""Directional branch diff between two workspace snapshots (EPIC-016 #185).

`CompareAnalyzer` 是对称的 name-set diff(只报双边实体的边);branch-diff 的
消费者要的是**方向性框架**:base→head 的 added/removed、断链(base 有 head
无的边且 src 实体存活——「调用方还在、被调方没了」)、新链(head 新边且
src 在 base 已存在)、content_hash 语义层(图形状没变但 body 变了)、模块
耦合 delta。零 config knob(EPIC-016 renunciation):cap 是模块常量。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loomgraph.core.deps import extract_module
from loomgraph.core.topology import _strip_line_range

_LIST_CAP = 50          # 每 section 列表上限(配合 summary.*_total 计数)
_MODULE_CAP = 20        # module_delta 条目上限
_MODULE_DEPTH = 2       # extract_module depth,与 deps 默认口径一致

EdgeKey = tuple[str, str, str]


@dataclass
class BranchDiffResult:
    """Result of a directional base→head branch diff."""

    summary: dict[str, int] = field(default_factory=dict)
    graph_sizes: dict[str, int] = field(default_factory=dict)
    entities_added: list[dict[str, Any]] = field(default_factory=list)
    entities_removed: list[dict[str, Any]] = field(default_factory=list)
    edges_added: list[dict[str, Any]] = field(default_factory=list)
    edges_removed: list[dict[str, Any]] = field(default_factory=list)
    broken_chains: list[dict[str, Any]] = field(default_factory=list)
    new_chains: list[dict[str, Any]] = field(default_factory=list)
    content_comparison: dict[str, Any] = field(default_factory=dict)
    module_delta: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "summary": self.summary,
            "graph_sizes": self.graph_sizes,
            "entities_added": self.entities_added,
            "entities_removed": self.entities_removed,
            "edges_added": self.edges_added,
            "edges_removed": self.edges_removed,
            "broken_chains": self.broken_chains,
            "new_chains": self.new_chains,
            "content_comparison": self.content_comparison,
            "module_delta": self.module_delta,
        }


def _entity_to_info(entity: dict[str, Any]) -> dict[str, str]:
    """Entity summary info(shape parity with compare._entity_to_info)."""
    return {
        "name": entity.get("entity_name", ""),
        "type": entity.get("entity_type", ""),
        "source_id": entity.get("source_id", ""),
    }


def _edge_key(rel: dict[str, Any]) -> EdgeKey:
    return (rel.get("src_id", ""), rel.get("tgt_id", ""), rel.get("keywords", ""))


def _edge_info(key: EdgeKey) -> dict[str, str]:
    return {"src": key[0], "tgt": key[1], "keywords": key[2]}


def _resolvable_edges(
    relations: list[dict[str, Any]], entity_names: set[str]
) -> tuple[set[EdgeKey], int]:
    """Edges whose both endpoints resolve to entities (#149/#154 口径).

    Returns the resolvable edge-key set + the count of dropped (unresolved)
    edges — unresolved edges churn noise and never enter the diff itself.
    """
    resolved: set[EdgeKey] = set()
    unresolved = 0
    for rel in relations:
        key = _edge_key(rel)
        if key[0] in entity_names and key[1] in entity_names:
            resolved.add(key)
        else:
            unresolved += 1
    return resolved, unresolved


def _module_of(entity: dict[str, Any]) -> str:
    return extract_module(_strip_line_range(entity.get("source_id", "")), _MODULE_DEPTH)


@dataclass
class BranchDiffAnalyzer:
    """Directional base→head diff over two already-open stores.

    Args:
        base_store: GraphStore for the base (old) ref snapshot
        head_store: GraphStore for the head (new) ref snapshot
        base: Base snapshot label (for logging/output framing)
        head: Head snapshot label
    """

    base_store: Any  # GraphStore
    head_store: Any  # GraphStore
    base: str = "base"
    head: str = "head"
    base_backend: str = "codeindex"
    head_backend: str = "codeindex"

    async def analyze(self) -> BranchDiffResult:
        """Run the directional diff.

        Algorithm:
            1. Concurrently fetch entities + relations from both snapshots
            2. Entity name-set diff → added / removed / shared
            3. Resolvable edge sets per side; set diff → edges_added/removed
            4. broken_chains = removed edges whose src survives in head;
               new_chains = added edges whose src existed in base
            5. content comparison: same-backend codeindex hashes only;
               unavailable comparisons return an explicit null change list
            6. module_delta: added/removed edges attributed to src's module

        Returns:
            BranchDiffResult with capped lists + uncapped summary totals
        """
        base_entities, base_relations, head_entities, head_relations = (
            await asyncio.gather(
                self.base_store.get_all_entities(),
                self.base_store.get_all_relations(),
                self.head_store.get_all_entities(),
                self.head_store.get_all_relations(),
            )
        )

        base_map = {e.get("entity_name", ""): e for e in base_entities}
        head_map = {e.get("entity_name", ""): e for e in head_entities}
        base_names = set(base_map)
        head_names = set(head_map)

        entities_removed = sorted(
            (_entity_to_info(base_map[n]) for n in base_names - head_names),
            key=lambda x: x["name"],
        )
        entities_added = sorted(
            (_entity_to_info(head_map[n]) for n in head_names - base_names),
            key=lambda x: x["name"],
        )
        shared = base_names & head_names

        base_edges, base_unresolved = _resolvable_edges(base_relations, base_names)
        head_edges, head_unresolved = _resolvable_edges(head_relations, head_names)

        removed_keys = base_edges - head_edges
        added_keys = head_edges - base_edges
        edges_removed = [_edge_info(k) for k in sorted(removed_keys)]
        edges_added = [_edge_info(k) for k in sorted(added_keys)]

        broken = sorted(k for k in removed_keys if k[0] in head_names)
        new = sorted(k for k in added_keys if k[0] in base_names)

        # L2: content comparison is deliberately narrower than graph
        # comparison. A hash from a different extractor is not evidence that
        # two symbols' source bodies are comparable.
        content_changed: list[dict[str, Any]] = []
        hash_missing = 0
        comparison_reason: str | None = None
        comparable_shared = 0
        if self.base_backend != self.head_backend:
            comparison_reason = "cross_backend_comparison_not_supported"
            hash_missing = len(shared)
        elif self.base_backend != "codeindex":
            comparison_reason = "backend_has_no_per_entity_content_hash"
            hash_missing = len(shared)
        else:
            for name in shared:
                base_hash = base_map[name].get("content_hash")
                head_hash = head_map[name].get("content_hash")
                if base_hash is None or head_hash is None:
                    hash_missing += 1
                else:
                    comparable_shared += 1
                    if base_hash != head_hash:
                        content_changed.append(_entity_to_info(head_map[name]))
            content_changed.sort(key=lambda x: x["name"])

        if comparison_reason is not None or (
            comparable_shared == 0 and hash_missing
        ):
            content_status = "unavailable"
            comparison_reason = comparison_reason or "missing_per_entity_content_hash"
            changed: list[dict[str, Any]] | None = None
            changes_total: int | None = None
        else:
            content_status = "partial" if hash_missing else "available"
            changed = content_changed[:_LIST_CAP]
            changes_total = len(content_changed)

        content_comparison: dict[str, Any] = {
            "version": 1,
            "status": content_status,
            "scope": "same_backend_only",
            "base_backend": self.base_backend,
            "head_backend": self.head_backend,
            "comparable_shared": comparable_shared,
            "uncomparable_shared": hash_missing,
            "changes_total": changes_total,
            "changed": changed,
        }
        if comparison_reason is not None:
            content_comparison["reason"] = comparison_reason

        # module_delta: 边按 src 端模块聚合(removed 归 base 侧模块,added 归 head 侧)
        module_added: dict[str, int] = {}
        module_removed: dict[str, int] = {}
        for k in added_keys:
            src = head_map.get(k[0]) or base_map.get(k[0])
            mod = _module_of(src) if src else "."
            module_added[mod] = module_added.get(mod, 0) + 1
        for k in removed_keys:
            src = base_map.get(k[0]) or head_map.get(k[0])
            mod = _module_of(src) if src else "."
            module_removed[mod] = module_removed.get(mod, 0) + 1
        module_rows: list[dict[str, Any]] = [
            {
                "module": mod,
                "edges_added": module_added.get(mod, 0),
                "edges_removed": module_removed.get(mod, 0),
            }
            for mod in set(module_added) | set(module_removed)
        ]
        module_delta = sorted(
            module_rows,
            key=lambda d: (-(d["edges_added"] + d["edges_removed"]), d["module"]),
        )

        def cap(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
            return items[:limit]

        return BranchDiffResult(
            summary={
                "entities_added_total": len(entities_added),
                "entities_removed_total": len(entities_removed),
                "entities_shared": len(shared),
                "edges_added_total": len(edges_added),
                "edges_removed_total": len(edges_removed),
                "broken_chains_total": len(broken),
                "new_chains_total": len(new),
                "module_changed": len(module_delta),
                "base_unresolved_edges": base_unresolved,
                "head_unresolved_edges": head_unresolved,
            },
            graph_sizes={
                "base_entities": len(base_entities),
                "base_relations": len(base_relations),
                "head_entities": len(head_entities),
                "head_relations": len(head_relations),
            },
            entities_added=cap(entities_added, _LIST_CAP),
            entities_removed=cap(entities_removed, _LIST_CAP),
            edges_added=cap(edges_added, _LIST_CAP),
            edges_removed=cap(edges_removed, _LIST_CAP),
            broken_chains=cap([_edge_info(k) for k in broken], _LIST_CAP),
            new_chains=cap([_edge_info(k) for k in new], _LIST_CAP),
            content_comparison=content_comparison,
            module_delta=cap(module_delta, _MODULE_CAP),
        )
