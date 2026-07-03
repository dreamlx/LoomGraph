"""SqliteGraphStore vec0 tests — embedding writes, KNN search, cascade deletes.

EPIC-011 Phase 2. Verifies that caller-provided embeddings round-trip
through the vec0 virtual table and KNN returns the right neighbors with
the right metadata.
"""

from __future__ import annotations

from typing import Any

import pytest

from loomgraph.storage.base import GraphStore
from loomgraph.storage.sqlite_store import (
    DEFAULT_VECTOR_DIM as VECTOR_DIM,
)
from loomgraph.storage.sqlite_store import (
    SqliteDimensionMismatchError,
    SqliteGraphStore,
)

# ---------- Helpers ----------


def _vec(seed: float) -> list[float]:
    """Build a deterministic VECTOR_DIM-length vector for tests."""
    return [seed] + [0.0] * (VECTOR_DIM - 1)


def _vec_normalized(idx: int) -> list[float]:
    """Build a unit-length vector pointing along the `idx`-th axis."""
    v = [0.0] * VECTOR_DIM
    v[idx] = 1.0
    return v


@pytest.fixture
async def store() -> Any:
    s = SqliteGraphStore(db_path=":memory:")
    await s.initialize()
    try:
        yield s
    finally:
        await s.close()


# ---------- Embedding write path ----------


class TestEmbeddingWrite:
    async def test_create_entity_with_embedding(self, store: SqliteGraphStore) -> None:
        await store.create_entity(
            "Foo",
            {
                "entity_type": "class",
                "source_id": "src/foo.py",
                "embedding": _vec(0.5),
            },
        )
        # Entity row preserved without embedding leaking into properties_json
        entities = await store.get_all_entities()
        assert len(entities) == 1
        assert "embedding" not in entities[0]

        # vec0 has the embedding
        result = await store.search_similar(_vec(0.5), k=1)
        assert len(result) == 1
        assert result[0]["entity_name"] == "Foo"
        assert result[0]["source_id"] == "src/foo.py"
        assert result[0]["distance"] == pytest.approx(0.0, abs=1e-5)

    async def test_create_entity_without_embedding(
        self, store: SqliteGraphStore
    ) -> None:
        await store.create_entity("Foo", {"entity_type": "class"})
        # KNN should find no neighbors
        result = await store.search_similar(_vec(0.5), k=10)
        assert result == []


# ---------- vector_count (EPIC-015: clean empty-state detection) ----------


class TestVectorCount:
    async def test_fresh_store_has_zero_vectors(self, store: SqliteGraphStore) -> None:
        assert await store.vector_count() == 0

    async def test_counts_embedded_entities(self, store: SqliteGraphStore) -> None:
        await store.create_entity("A", {"entity_type": "function", "embedding": _vec(0.1)})
        await store.create_entity("B", {"entity_type": "function", "embedding": _vec(0.2)})
        assert await store.vector_count() == 2

    async def test_entities_without_embeddings_not_counted(
        self, store: SqliteGraphStore
    ) -> None:
        # Entities exist but none carry an embedding → vector_count stays 0.
        await store.create_entity("NoEmb", {"entity_type": "function"})
        await store.create_entity("BadDim", {"embedding": [0.1, 0.2, 0.3]})
        assert await store.vector_count() == 0

    async def test_invalid_embedding_dim_ignored(
        self, store: SqliteGraphStore
    ) -> None:
        await store.create_entity(
            "Foo", {"embedding": [0.1, 0.2, 0.3]}
        )  # too short
        result = await store.search_similar(_vec(0.5), k=10)
        assert result == []

    async def test_embedding_upsert(self, store: SqliteGraphStore) -> None:
        # Insert with embedding A, then upsert with embedding B —
        # vec0 should only contain B.
        await store.create_entity("Foo", {"embedding": _vec_normalized(0)})
        await store.create_entity("Foo", {"embedding": _vec_normalized(1)})
        # Querying along axis 1 should hit Foo at distance 0
        result = await store.search_similar(_vec_normalized(1), k=1)
        assert len(result) == 1
        assert result[0]["distance"] == pytest.approx(0.0, abs=1e-5)


# ---------- Bulk insert ----------


class TestBulkEmbeddingWrite:
    async def test_insert_custom_kg_with_mixed_embeddings(
        self, store: SqliteGraphStore
    ) -> None:
        entities = [
            {
                "entity_name": "A",
                "source_id": "f1.py",
                "embedding": _vec_normalized(0),
            },
            {
                "entity_name": "B",
                "source_id": "f2.py",
                "embedding": _vec_normalized(1),
            },
            {"entity_name": "NoVec", "source_id": "f3.py"},
        ]
        await store.insert_custom_kg(entities, [])
        assert len(await store.get_all_entities()) == 3

        # KNN finds A and B, not NoVec
        result = await store.search_similar(_vec_normalized(0), k=10)
        names = [r["entity_name"] for r in result]
        assert "A" in names
        assert "B" in names
        assert "NoVec" not in names


# ---------- KNN search ----------


class TestKNNSearch:
    async def _seed(self, store: SqliteGraphStore) -> None:
        await store.insert_custom_kg(
            [
                {"entity_name": f"E{i}", "source_id": f"src/m{i % 2}/f.py",
                 "embedding": _vec_normalized(i)}
                for i in range(5)
            ],
            [],
        )

    async def test_k_limits_results(self, store: SqliteGraphStore) -> None:
        await self._seed(store)
        result = await store.search_similar(_vec_normalized(0), k=2)
        assert len(result) == 2

    async def test_results_sorted_by_distance(
        self, store: SqliteGraphStore
    ) -> None:
        await self._seed(store)
        result = await store.search_similar(_vec_normalized(0), k=5)
        # First result is the exact match
        assert result[0]["entity_name"] == "E0"
        # Distances non-decreasing
        for i in range(len(result) - 1):
            assert result[i]["distance"] <= result[i + 1]["distance"]

    async def test_source_prefix_filter(self, store: SqliteGraphStore) -> None:
        await self._seed(store)
        # m0 modules: E0, E2, E4
        result = await store.search_similar(
            _vec_normalized(0), k=10, source_prefix="src/m0/"
        )
        names = sorted(r["entity_name"] for r in result)
        assert names == ["E0", "E2", "E4"]

    async def test_invalid_query_dim_raises(
        self, store: SqliteGraphStore
    ) -> None:
        with pytest.raises(ValueError, match=str(VECTOR_DIM)):
            await store.search_similar([0.1, 0.2, 0.3], k=5)


# ---------- Cascade deletes ----------


class TestCascadeDelete:
    async def test_delete_by_source_cascades_to_vec0(
        self, store: SqliteGraphStore
    ) -> None:
        await store.create_entity(
            "A", {"source_id": "f1.py", "embedding": _vec_normalized(0)}
        )
        await store.create_entity(
            "B", {"source_id": "f2.py", "embedding": _vec_normalized(1)}
        )
        await store.delete_by_source(["f1.py"])
        result = await store.search_similar(_vec_normalized(0), k=10)
        names = [r["entity_name"] for r in result]
        assert "A" not in names
        assert "B" in names

    async def test_delete_all_cascades_to_vec0(
        self, store: SqliteGraphStore
    ) -> None:
        await store.create_entity("A", {"embedding": _vec_normalized(0)})
        await store.delete_all()
        result = await store.search_similar(_vec_normalized(0), k=10)
        assert result == []


# ---------- Backend without vector support ----------


class TestDimensionParametrization:
    async def test_custom_dimension_stored_in_schema(
        self, tmp_path: Any
    ) -> None:
        path = tmp_path / "custom.db"
        s = SqliteGraphStore(db_path=path, dimension=1024)
        await s.initialize()
        try:
            assert s.dimension == 1024
            # Write a 1024-dim embedding and read it back via KNN
            await s.create_entity(
                "X",
                {
                    "source_id": "f.py",
                    "embedding": [1.0] + [0.0] * 1023,
                },
            )
            result = await s.search_similar([1.0] + [0.0] * 1023, k=1)
            assert result and result[0]["entity_name"] == "X"
        finally:
            await s.close()

    async def test_dimension_mismatch_raises(self, tmp_path: Any) -> None:
        path = tmp_path / "mixed.db"
        # First open with 768
        a = SqliteGraphStore(db_path=path, dimension=768)
        await a.initialize()
        await a.close()
        # Reopen with 1024 — should bail before any write
        b = SqliteGraphStore(db_path=path, dimension=1024)
        with pytest.raises(SqliteDimensionMismatchError) as exc:
            await b.initialize()
        assert exc.value.expected == 1024
        assert exc.value.found == 768


class TestUnsupportedBackends:
    async def test_abc_default_raises_not_implemented(self) -> None:
        """Backends that don't implement vec0 should fall back to ABC default."""

        class NoVecStore(GraphStore):
            async def create_entity(self, name, data):
                return None

            async def entity_exists(self, name):
                return False

            async def get_all_entities(self):
                return []

            async def create_relation(self, src, tgt, data):
                return None

            async def get_all_relations(self):
                return []

            async def insert_custom_kg(
                self, entities, relationships, chunks=None,
                *, batch_size=5000, progress_callback=None,
            ):
                return None

            async def delete_all(self):
                return None

            async def delete_by_source(self, source_ids):
                return None

            async def get_source_ids(self, source_prefix=None):
                return []

            async def list_workspaces(self):
                return []

            async def get_orphan_entities(self, exclude_types=None, source_prefix=None):
                return []

            async def get_degree_distribution(self, direction="in", min_degree=5, source_prefix=None):
                return []

            async def get_graph_stats(self, source_prefix=None, module_depth=2):
                return {}

        store = NoVecStore()
        with pytest.raises(NotImplementedError):
            await store.search_similar(_vec_normalized(0), k=1)


# ---------- write_embeddings (EPIC-015 Phase 3 backfill) ----------


class TestWriteEmbeddings:
    """Bulk embedding write for backfill: entities already exist, vec0 is empty."""

    async def test_write_embeddings_populates_vec0(
        self, store: SqliteGraphStore
    ) -> None:
        # Pre-create entities without embeddings (simulates import-export path)
        await store.create_entity("Alpha", {"entity_type": "class", "source_id": "a.py", "description": "first"})
        await store.create_entity("Beta", {"entity_type": "function", "source_id": "b.py", "description": "second"})

        assert await store.vector_count() == 0

        # Write embeddings in bulk
        count = await store.write_embeddings([
            ("Alpha", "a.py", _vec(1.0)),
            ("Beta", "b.py", _vec(2.0)),
        ])
        assert count == 2
        assert await store.vector_count() == 2

        # KNN: Alpha should be closest to _vec(1.0)
        hits = await store.search_similar(_vec(1.0), k=2)
        assert hits[0]["entity_name"] == "Alpha"
        assert hits[1]["entity_name"] == "Beta"

    async def test_write_embeddings_idempotent_by_name(
        self, store: SqliteGraphStore
    ) -> None:
        await store.create_entity("Alpha", {"entity_type": "class", "source_id": "a.py"})
        await store.write_embeddings([("Alpha", "a.py", _vec(1.0))])
        assert await store.vector_count() == 1

        # Re-write with a different vector -> still 1 row, vec updated
        await store.write_embeddings([("Alpha", "a.py", _vec(9.0))])
        assert await store.vector_count() == 1

        hits = await store.search_similar(_vec(9.0), k=1)
        assert hits[0]["entity_name"] == "Alpha"
        assert hits[0]["distance"] == pytest.approx(0.0, abs=1e-5)

    async def test_write_embeddings_skips_invalid(
        self, store: SqliteGraphStore
    ) -> None:
        await store.create_entity("Alpha", {"entity_type": "class", "source_id": "a.py"})
        # Wrong-dimension vector is silently skipped
        count = await store.write_embeddings([
            ("Alpha", "a.py", [0.5]),  # too short
        ])
        assert count == 0
        assert await store.vector_count() == 0

    async def test_write_embeddings_empty_list_returns_zero(
        self, store: SqliteGraphStore
    ) -> None:
        count = await store.write_embeddings([])
        assert count == 0

    async def test_write_embeddings_entity_not_in_entities_table_ok(
        self, store: SqliteGraphStore
    ) -> None:
        """write_embeddings writes to vec0 directly; entity existence not enforced."""
        count = await store.write_embeddings([
            ("Ghost", "ghost.py", _vec(3.0)),
        ])
        assert count == 1
        assert await store.vector_count() == 1

        hits = await store.search_similar(_vec(3.0), k=1)
        assert hits[0]["entity_name"] == "Ghost"
