"""Contract tests for GraphStore ABC.

Every GraphStore implementation must satisfy these tests. A simple
dict-backed FakeGraphStore exercises the contract; backend-specific
test files run the same suite via parametrization (Phase 1+).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

from loomgraph.storage.base import GraphStore


class FakeGraphStore(GraphStore):
    """In-memory dict-backed GraphStore — reference implementation for the contract."""

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Any]] = {}
        self._relations: list[dict[str, Any]] = []
        self._workspaces: list[str] = []

    async def create_entity(
        self, entity_name: str, entity_data: dict[str, Any]
    ) -> None:
        self._entities[entity_name] = {"entity_name": entity_name, **entity_data}

    async def entity_exists(self, entity_name: str) -> bool:
        return entity_name in self._entities

    async def get_all_entities(self) -> list[dict[str, Any]]:
        return list(self._entities.values())

    async def create_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_data: dict[str, Any],
    ) -> None:
        keywords = relation_data.get("keywords", "")
        self._relations = [
            r
            for r in self._relations
            if not (
                r.get("src_id") == source_entity
                and r.get("tgt_id") == target_entity
                and r.get("keywords", "") == keywords
            )
        ]
        self._relations.append(
            {"src_id": source_entity, "tgt_id": target_entity, **relation_data}
        )

    async def get_all_relations(self) -> list[dict[str, Any]]:
        return list(self._relations)

    async def insert_custom_kg(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        chunks: list[dict[str, Any]] | None = None,
    ) -> None:
        for e in entities:
            name = e.get("entity_name", "")
            if name:
                await self.create_entity(name, e)
        for r in relationships:
            src = r.get("src_id", "") or r.get("source", "")
            tgt = r.get("tgt_id", "") or r.get("target", "")
            if src and tgt:
                await self.create_relation(src, tgt, r)

    async def delete_all(self) -> None:
        self._entities.clear()
        self._relations.clear()

    async def delete_by_source(self, source_ids: list[str]) -> None:
        sources = set(source_ids)
        self._entities = {
            k: v
            for k, v in self._entities.items()
            if v.get("source_id") not in sources
        }
        self._relations = [
            r for r in self._relations if r.get("source_id") not in sources
        ]

    async def get_source_ids(
        self, source_prefix: str | None = None
    ) -> list[str]:
        sids = {v.get("source_id", "") for v in self._entities.values()}
        sids.discard("")
        if source_prefix:
            sids = {s for s in sids if s.startswith(source_prefix)}
        return sorted(sids)

    async def list_workspaces(self) -> list[str]:
        return list(self._workspaces)

    async def get_orphan_entities(
        self,
        exclude_types: list[str] | None = None,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        in_deg: dict[str, int] = defaultdict(int)
        out_deg: dict[str, int] = defaultdict(int)
        for r in self._relations:
            out_deg[r.get("src_id", "")] += 1
            in_deg[r.get("tgt_id", "")] += 1
        result: list[dict[str, Any]] = []
        for name, e in self._entities.items():
            if in_deg[name] != 0 or out_deg[name] != 0:
                continue
            if exclude_types and e.get("entity_type") in exclude_types:
                continue
            if source_prefix and not (e.get("source_id", "") or "").startswith(
                source_prefix
            ):
                continue
            result.append(e)
        return result

    async def get_degree_distribution(
        self,
        direction: str = "in",
        min_degree: int = 5,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        counts: dict[str, int] = defaultdict(int)
        key_field = "tgt_id" if direction == "in" else "src_id"
        for r in self._relations:
            key = r.get(key_field, "")
            if key:
                counts[key] += 1
        result: list[dict[str, Any]] = []
        for name, degree in counts.items():
            if degree < min_degree:
                continue
            entity = self._entities.get(name)
            if entity is None:
                continue
            if source_prefix and not (
                entity.get("source_id", "") or ""
            ).startswith(source_prefix):
                continue
            result.append({**entity, "degree": degree})
        return result

    async def get_graph_stats(
        self,
        source_prefix: str | None = None,
        module_depth: int = 2,
    ) -> dict[str, Any]:
        if source_prefix:
            entities = [
                e
                for e in self._entities.values()
                if (e.get("source_id", "") or "").startswith(source_prefix)
            ]
            valid = {e.get("entity_name") for e in entities}
            relations = [
                r
                for r in self._relations
                if r.get("src_id") in valid or r.get("tgt_id") in valid
            ]
        else:
            entities = list(self._entities.values())
            relations = list(self._relations)

        def strip(s: str) -> str:
            return (
                s[len(source_prefix) :]
                if source_prefix and s.startswith(source_prefix)
                else s
            )

        def module_of(source_id: str) -> str:
            parts = (source_id or "").split("/")
            return "/".join(parts[:module_depth])

        entity_module: dict[str, str] = {
            e.get("entity_name", ""): module_of(strip(e.get("source_id", "") or ""))
            for e in entities
        }
        cross = 0
        intra = 0
        for r in relations:
            src_m = entity_module.get(r.get("src_id", ""))
            tgt_m = entity_module.get(r.get("tgt_id", ""))
            if src_m and tgt_m:
                if src_m == tgt_m:
                    intra += 1
                else:
                    cross += 1
        total = cross + intra
        return {
            "entity_count": len(entities),
            "relation_count": len(relations),
            "cross_module_relations": cross,
            "intra_module_relations": intra,
            "coupling_density": (cross / total) if total else 0.0,
        }


@pytest.fixture
def store() -> GraphStore:
    return FakeGraphStore()


# ---------- Entity CRUD ----------


class TestEntityCRUD:
    async def test_create_then_read(self, store: GraphStore) -> None:
        await store.create_entity(
            "UserService",
            {"entity_type": "class", "source_id": "src/auth.py:10"},
        )
        entities = await store.get_all_entities()
        assert len(entities) == 1
        assert entities[0]["entity_name"] == "UserService"
        assert entities[0]["entity_type"] == "class"

    async def test_create_is_idempotent_upsert(self, store: GraphStore) -> None:
        await store.create_entity("Foo", {"entity_type": "class"})
        await store.create_entity("Foo", {"entity_type": "function"})
        entities = await store.get_all_entities()
        assert len(entities) == 1
        assert entities[0]["entity_type"] == "function"

    async def test_entity_exists(self, store: GraphStore) -> None:
        assert not await store.entity_exists("Foo")
        await store.create_entity("Foo", {})
        assert await store.entity_exists("Foo")


# ---------- Relation CRUD ----------


class TestRelationCRUD:
    async def test_create_then_read(self, store: GraphStore) -> None:
        await store.create_relation("A", "B", {"keywords": "CALLS"})
        rels = await store.get_all_relations()
        assert len(rels) == 1
        assert rels[0]["src_id"] == "A"
        assert rels[0]["tgt_id"] == "B"
        assert rels[0]["keywords"] == "CALLS"

    async def test_dedup_same_triple(self, store: GraphStore) -> None:
        await store.create_relation("A", "B", {"keywords": "CALLS"})
        await store.create_relation("A", "B", {"keywords": "CALLS"})
        rels = await store.get_all_relations()
        assert len(rels) == 1

    async def test_distinct_keywords_kept(self, store: GraphStore) -> None:
        await store.create_relation("A", "B", {"keywords": "CALLS"})
        await store.create_relation("A", "B", {"keywords": "INHERITS"})
        rels = await store.get_all_relations()
        assert len(rels) == 2


# ---------- Bulk insert ----------


class TestBulkInsert:
    async def test_insert_custom_kg_writes_all(self, store: GraphStore) -> None:
        entities = [
            {"entity_name": "A", "entity_type": "class", "source_id": "f.py"},
            {"entity_name": "B", "entity_type": "function", "source_id": "f.py"},
        ]
        relations = [{"src_id": "A", "tgt_id": "B", "keywords": "CALLS"}]
        await store.insert_custom_kg(entities, relations)
        assert len(await store.get_all_entities()) == 2
        assert len(await store.get_all_relations()) == 1

    async def test_insert_custom_kg_empty_payload(self, store: GraphStore) -> None:
        await store.insert_custom_kg([], [])
        assert await store.get_all_entities() == []
        assert await store.get_all_relations() == []


# ---------- Delete ----------


class TestDelete:
    async def test_delete_all_clears(self, store: GraphStore) -> None:
        await store.create_entity("Foo", {})
        await store.create_relation("Foo", "Bar", {"keywords": "CALLS"})
        await store.delete_all()
        assert await store.get_all_entities() == []
        assert await store.get_all_relations() == []

    async def test_delete_by_source_filters(self, store: GraphStore) -> None:
        await store.create_entity("A", {"source_id": "f1.py"})
        await store.create_entity("B", {"source_id": "f2.py"})
        await store.delete_by_source(["f1.py"])
        names = [e["entity_name"] for e in await store.get_all_entities()]
        assert names == ["B"]


# ---------- Source IDs ----------


class TestSourceIds:
    async def test_dedupes(self, store: GraphStore) -> None:
        await store.create_entity("A", {"source_id": "f.py"})
        await store.create_entity("B", {"source_id": "f.py"})
        assert await store.get_source_ids() == ["f.py"]

    async def test_prefix_filter(self, store: GraphStore) -> None:
        await store.create_entity("A", {"source_id": "src/a.py"})
        await store.create_entity("B", {"source_id": "tests/b.py"})
        assert await store.get_source_ids(source_prefix="src/") == ["src/a.py"]


# ---------- Analytics ----------


class TestAnalyticsContract:
    async def test_orphans_no_edges(self, store: GraphStore) -> None:
        await store.create_entity("A", {"entity_type": "class"})
        await store.create_entity("B", {"entity_type": "class"})
        await store.create_relation("A", "B", {"keywords": "CALLS"})
        assert await store.get_orphan_entities() == []

    async def test_orphans_isolated(self, store: GraphStore) -> None:
        await store.create_entity("Isolated", {"entity_type": "class"})
        await store.create_entity("A", {"entity_type": "class"})
        await store.create_entity("B", {"entity_type": "class"})
        await store.create_relation("A", "B", {"keywords": "CALLS"})
        orphans = await store.get_orphan_entities()
        assert [e["entity_name"] for e in orphans] == ["Isolated"]

    async def test_orphans_exclude_types(self, store: GraphStore) -> None:
        await store.create_entity("Mod", {"entity_type": "module"})
        await store.create_entity("Cls", {"entity_type": "class"})
        orphans = await store.get_orphan_entities(exclude_types=["module"])
        assert [e["entity_name"] for e in orphans] == ["Cls"]

    async def test_degree_distribution_in(self, store: GraphStore) -> None:
        for n in ("A", "B", "Hub"):
            await store.create_entity(n, {})
        for caller in ("A", "B"):
            await store.create_relation(caller, "Hub", {"keywords": "CALLS"})
        result = await store.get_degree_distribution(direction="in", min_degree=2)
        assert len(result) == 1
        assert result[0]["entity_name"] == "Hub"
        assert result[0]["degree"] == 2

    async def test_degree_distribution_out(self, store: GraphStore) -> None:
        for n in ("Caller", "A", "B"):
            await store.create_entity(n, {})
        for tgt in ("A", "B"):
            await store.create_relation("Caller", tgt, {"keywords": "CALLS"})
        result = await store.get_degree_distribution(direction="out", min_degree=2)
        assert len(result) == 1
        assert result[0]["entity_name"] == "Caller"
        assert result[0]["degree"] == 2

    async def test_graph_stats_counts_and_coupling(
        self, store: GraphStore
    ) -> None:
        await store.create_entity("A", {"source_id": "mod1/x.py"})
        await store.create_entity("B", {"source_id": "mod1/y.py"})
        await store.create_entity("C", {"source_id": "mod2/z.py"})
        await store.create_relation("A", "B", {"keywords": "CALLS"})
        await store.create_relation("A", "C", {"keywords": "CALLS"})
        stats = await store.get_graph_stats(module_depth=1)
        assert stats["entity_count"] == 3
        assert stats["relation_count"] == 2
        assert stats["intra_module_relations"] == 1
        assert stats["cross_module_relations"] == 1
        assert stats["coupling_density"] == 0.5


# ---------- Workspaces ----------


class TestWorkspaces:
    async def test_list_workspaces_default(self, store: GraphStore) -> None:
        assert await store.list_workspaces() == []
