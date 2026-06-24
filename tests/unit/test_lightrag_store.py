"""LightRAGGraphStore adapter — forwarding tests.

Verifies that every GraphStore ABC method correctly forwards to the
underlying LightRAGClient with the right argument shape. Return-value
adaptation (HTTP dict → None for write methods) is exercised here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from loomgraph.storage.base import GraphStore
from loomgraph.storage.lightrag_store import LightRAGGraphStore


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock()
    # Reasonable defaults so write methods returning dicts don't break adapter
    client.create_entity.return_value = {"status": "success"}
    client.create_relation.return_value = {"status": "success"}
    client.insert_custom_kg.return_value = {"status": "success"}
    client.delete_all.return_value = {"graph": {}}
    client.delete_by_source.return_value = {"deleted": 1}
    return client


@pytest.fixture
def store(mock_client: AsyncMock) -> GraphStore:
    return LightRAGGraphStore(client=mock_client)


# ---------- Entity CRUD ----------


class TestEntityForwarding:
    async def test_create_entity(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        await store.create_entity("Foo", {"entity_type": "class"})
        mock_client.create_entity.assert_awaited_once_with(
            "Foo", {"entity_type": "class"}
        )

    async def test_create_entity_returns_none(
        self, store: GraphStore
    ) -> None:
        # ABC contract: write returns None
        result = await store.create_entity("Foo", {})
        assert result is None

    async def test_entity_exists(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.entity_exists.return_value = True
        assert await store.entity_exists("Foo") is True
        mock_client.entity_exists.assert_awaited_once_with("Foo")

    async def test_get_all_entities(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_all_entities.return_value = [{"entity_name": "X"}]
        assert await store.get_all_entities() == [{"entity_name": "X"}]


# ---------- Relation CRUD ----------


class TestRelationForwarding:
    async def test_create_relation(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        await store.create_relation("A", "B", {"keywords": "CALLS"})
        mock_client.create_relation.assert_awaited_once_with(
            "A", "B", {"keywords": "CALLS"}
        )

    async def test_create_relation_returns_none(
        self, store: GraphStore
    ) -> None:
        result = await store.create_relation("A", "B", {"keywords": "X"})
        assert result is None

    async def test_get_all_relations(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_all_relations.return_value = [{"src_id": "A"}]
        assert await store.get_all_relations() == [{"src_id": "A"}]


# ---------- Bulk insert ----------


class TestBulkInsertForwarding:
    async def test_without_chunks(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        await store.insert_custom_kg(
            [{"entity_name": "A"}], [{"src_id": "A", "tgt_id": "B"}]
        )
        mock_client.insert_custom_kg.assert_awaited_once_with(
            [{"entity_name": "A"}],
            [{"src_id": "A", "tgt_id": "B"}],
            None,
            batch_size=5000,
            progress_callback=None,
        )

    async def test_with_chunks(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        await store.insert_custom_kg(
            [{"entity_name": "A"}],
            [],
            [{"content": "...", "source_id": "f.py"}],
        )
        mock_client.insert_custom_kg.assert_awaited_once_with(
            [{"entity_name": "A"}],
            [],
            [{"content": "...", "source_id": "f.py"}],
            batch_size=5000,
            progress_callback=None,
        )

    async def test_forwards_batch_and_callback(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        callback = lambda b, t, e: None  # noqa: E731
        await store.insert_custom_kg(
            [], [], None, batch_size=100, progress_callback=callback
        )
        mock_client.insert_custom_kg.assert_awaited_once_with(
            [], [], None, batch_size=100, progress_callback=callback
        )

    async def test_returns_none(self, store: GraphStore) -> None:
        result = await store.insert_custom_kg([], [])
        assert result is None


# ---------- Delete ----------


class TestDeleteForwarding:
    async def test_delete_all(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        await store.delete_all()
        mock_client.delete_all.assert_awaited_once_with()

    async def test_delete_all_returns_none(self, store: GraphStore) -> None:
        result = await store.delete_all()
        assert result is None

    async def test_delete_by_source(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        await store.delete_by_source(["f1.py", "f2.py"])
        mock_client.delete_by_source.assert_awaited_once_with(["f1.py", "f2.py"])

    async def test_delete_by_source_returns_none(
        self, store: GraphStore
    ) -> None:
        result = await store.delete_by_source(["f.py"])
        assert result is None


# ---------- Source / workspace queries ----------


class TestQueryForwarding:
    async def test_get_source_ids_no_prefix(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_source_ids.return_value = ["a.py", "b.py"]
        result = await store.get_source_ids()
        assert result == ["a.py", "b.py"]
        mock_client.get_source_ids.assert_awaited_once_with(source_prefix=None)

    async def test_get_source_ids_with_prefix(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_source_ids.return_value = ["src/x.py"]
        await store.get_source_ids(source_prefix="src/")
        mock_client.get_source_ids.assert_awaited_once_with(source_prefix="src/")

    async def test_list_workspaces(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.list_workspaces.return_value = ["proj1", "proj2"]
        result = await store.list_workspaces()
        assert result == ["proj1", "proj2"]


# ---------- Analytics ----------


class TestAnalyticsForwarding:
    async def test_orphan_entities_default(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_orphan_entities.return_value = [{"entity_name": "X"}]
        result = await store.get_orphan_entities()
        assert result == [{"entity_name": "X"}]
        mock_client.get_orphan_entities.assert_awaited_once_with(
            exclude_types=None, source_prefix=None
        )

    async def test_orphan_entities_filters(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_orphan_entities.return_value = []
        await store.get_orphan_entities(
            exclude_types=["module"], source_prefix="src/"
        )
        mock_client.get_orphan_entities.assert_awaited_once_with(
            exclude_types=["module"], source_prefix="src/"
        )

    async def test_degree_distribution_default(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_degree_distribution.return_value = []
        await store.get_degree_distribution()
        mock_client.get_degree_distribution.assert_awaited_once_with(
            direction="in", min_degree=5, source_prefix=None
        )

    async def test_degree_distribution_custom(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_degree_distribution.return_value = []
        await store.get_degree_distribution(
            direction="out", min_degree=10, source_prefix="src/"
        )
        mock_client.get_degree_distribution.assert_awaited_once_with(
            direction="out", min_degree=10, source_prefix="src/"
        )

    async def test_graph_stats_default(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_graph_stats.return_value = {"entity_count": 0}
        result = await store.get_graph_stats()
        assert result == {"entity_count": 0}
        mock_client.get_graph_stats.assert_awaited_once_with(
            source_prefix=None, module_depth=2
        )

    async def test_graph_stats_custom(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        mock_client.get_graph_stats.return_value = {}
        await store.get_graph_stats(source_prefix="src/", module_depth=3)
        mock_client.get_graph_stats.assert_awaited_once_with(
            source_prefix="src/", module_depth=3
        )


# ---------- Adapter wiring ----------


class TestAdapterWiring:
    async def test_client_exposed(
        self, store: GraphStore, mock_client: AsyncMock
    ) -> None:
        # Public attribute so callers needing batch/progress kw of
        # underlying insert_custom_kg can reach it during Phase 1-2.
        assert isinstance(store, LightRAGGraphStore)
        assert store.client is mock_client

    async def test_is_graph_store(self, store: GraphStore) -> None:
        assert isinstance(store, GraphStore)
