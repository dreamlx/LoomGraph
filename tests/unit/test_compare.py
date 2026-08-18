"""Tests for loomgraph.core.compare module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from loomgraph.core.compare import CompareAnalyzer, CompareResult


class TestCompareResult:
    """Tests for CompareResult serialization."""

    def test_to_dict(self) -> None:
        """Should serialize to dict correctly."""
        result = CompareResult(
            ws1="alpha",
            ws2="beta",
            summary={"only_in_ws1": 1, "only_in_ws2": 2, "in_both": 3, "relations_diff": 0},
            only_in_ws1=[{"name": "FuncA", "type": "function", "source_id": "a.py"}],
            only_in_ws2=[
                {"name": "FuncB", "type": "function", "source_id": "b.py"},
                {"name": "FuncC", "type": "class", "source_id": "c.py"},
            ],
            relation_changes=[],
        )
        d = result.to_dict()
        assert d["ws1"] == "alpha"
        assert d["ws2"] == "beta"
        assert d["summary"]["only_in_ws1"] == 1
        assert d["summary"]["only_in_ws2"] == 2
        assert len(d["only_in_ws1"]) == 1
        assert len(d["only_in_ws2"]) == 2
        assert d["relation_changes"] == []

    def test_to_dict_with_relation_changes(self) -> None:
        """Should include relation_changes in serialization."""
        result = CompareResult(
            ws1="a",
            ws2="b",
            summary={"only_in_ws1": 0, "only_in_ws2": 0, "in_both": 1, "relations_diff": 1},
            only_in_ws1=[],
            only_in_ws2=[],
            relation_changes=[
                {
                    "entity": "AuthService",
                    "ws1_count": 3,
                    "ws2_count": 5,
                    "added": [{"src": "NewCaller", "tgt": "AuthService", "keywords": "CALLS"}],
                    "removed": [],
                },
            ],
        )
        d = result.to_dict()
        assert len(d["relation_changes"]) == 1
        assert d["relation_changes"][0]["entity"] == "AuthService"

    def test_to_dict_makes_no_content_comparison_claim(self) -> None:
        """`compare` remains L0/L1-only until it adopts the L2 contract."""
        result = CompareResult(ws1="before", ws2="after")

        assert "content_comparison" not in result.to_dict()


class TestCompareAnalyzer:
    """Tests for CompareAnalyzer class."""

    @pytest.fixture
    def mock_client1(self) -> AsyncMock:
        """Create a mock LightRAG client for ws1."""
        return AsyncMock()

    @pytest.fixture
    def mock_client2(self) -> AsyncMock:
        """Create a mock LightRAG client for ws2."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_identical_workspaces(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """Two identical workspaces should produce zero diffs."""
        entities = [
            {"entity_name": "FuncA", "entity_type": "function", "source_id": "a.py"},
            {"entity_name": "FuncB", "entity_type": "class", "source_id": "b.py"},
        ]
        relations = [
            {"src_id": "FuncA", "tgt_id": "FuncB", "keywords": "CALLS", "source_id": "a.py"},
        ]
        mock_client1.get_all_entities.return_value = entities
        mock_client1.get_all_relations.return_value = relations
        mock_client2.get_all_entities.return_value = entities
        mock_client2.get_all_relations.return_value = relations

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        result = await analyzer.analyze()

        assert isinstance(result, CompareResult)
        assert result.summary["only_in_ws1"] == 0
        assert result.summary["only_in_ws2"] == 0
        assert result.summary["in_both"] == 2
        assert result.only_in_ws1 == []
        assert result.only_in_ws2 == []
        assert result.summary["relations_diff"] == 0

    @pytest.mark.asyncio
    async def test_ws2_has_added_entities(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """Entities in ws2 but not in ws1 should appear in only_in_ws2."""
        mock_client1.get_all_entities.return_value = [
            {"entity_name": "FuncA", "entity_type": "function", "source_id": "a.py"},
        ]
        mock_client1.get_all_relations.return_value = []
        mock_client2.get_all_entities.return_value = [
            {"entity_name": "FuncA", "entity_type": "function", "source_id": "a.py"},
            {"entity_name": "FuncB", "entity_type": "class", "source_id": "b.py"},
        ]
        mock_client2.get_all_relations.return_value = []

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        result = await analyzer.analyze()

        assert result.summary["only_in_ws1"] == 0
        assert result.summary["only_in_ws2"] == 1
        assert result.only_in_ws2[0]["name"] == "FuncB"

    @pytest.mark.asyncio
    async def test_ws1_has_removed_entities(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """Entities in ws1 but not ws2 should appear in only_in_ws1."""
        mock_client1.get_all_entities.return_value = [
            {"entity_name": "OldFunc", "entity_type": "function", "source_id": "old.py"},
            {"entity_name": "Shared", "entity_type": "class", "source_id": "s.py"},
        ]
        mock_client1.get_all_relations.return_value = []
        mock_client2.get_all_entities.return_value = [
            {"entity_name": "Shared", "entity_type": "class", "source_id": "s.py"},
        ]
        mock_client2.get_all_relations.return_value = []

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        result = await analyzer.analyze()

        assert result.summary["only_in_ws1"] == 1
        assert result.only_in_ws1[0]["name"] == "OldFunc"
        assert result.summary["in_both"] == 1

    @pytest.mark.asyncio
    async def test_relation_changes_detected(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """Should detect relation changes for shared entities."""
        shared_entities = [
            {"entity_name": "AuthService", "entity_type": "class", "source_id": "auth.py"},
            {"entity_name": "LoginHandler", "entity_type": "function", "source_id": "login.py"},
        ]
        mock_client1.get_all_entities.return_value = shared_entities
        mock_client2.get_all_entities.return_value = shared_entities

        mock_client1.get_all_relations.return_value = [
            {"src_id": "LoginHandler", "tgt_id": "AuthService", "keywords": "CALLS", "source_id": "login.py"},
        ]
        mock_client2.get_all_relations.return_value = [
            {"src_id": "LoginHandler", "tgt_id": "AuthService", "keywords": "CALLS", "source_id": "login.py"},
            {"src_id": "AuthService", "tgt_id": "LoginHandler", "keywords": "CALLS", "source_id": "auth.py"},
        ]

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        result = await analyzer.analyze()

        assert result.summary["relations_diff"] > 0
        # AuthService has a new outgoing relation in ws2
        changed = {c["entity"] for c in result.relation_changes}
        assert "AuthService" in changed

    @pytest.mark.asyncio
    async def test_empty_workspaces(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """Two empty workspaces should produce zero diffs."""
        mock_client1.get_all_entities.return_value = []
        mock_client1.get_all_relations.return_value = []
        mock_client2.get_all_entities.return_value = []
        mock_client2.get_all_relations.return_value = []

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        result = await analyzer.analyze()

        assert result.summary["only_in_ws1"] == 0
        assert result.summary["only_in_ws2"] == 0
        assert result.summary["in_both"] == 0
        assert result.summary["relations_diff"] == 0

    @pytest.mark.asyncio
    async def test_one_empty_workspace(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """One empty, one populated workspace."""
        mock_client1.get_all_entities.return_value = [
            {"entity_name": "A", "entity_type": "class", "source_id": "a.py"},
            {"entity_name": "B", "entity_type": "function", "source_id": "b.py"},
        ]
        mock_client1.get_all_relations.return_value = [
            {"src_id": "A", "tgt_id": "B", "keywords": "CALLS", "source_id": "a.py"},
        ]
        mock_client2.get_all_entities.return_value = []
        mock_client2.get_all_relations.return_value = []

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        result = await analyzer.analyze()

        assert result.summary["only_in_ws1"] == 2
        assert result.summary["only_in_ws2"] == 0
        assert result.summary["in_both"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_fetch(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """Verify both clients' methods are called (concurrency correctness)."""
        mock_client1.get_all_entities.return_value = []
        mock_client1.get_all_relations.return_value = []
        mock_client2.get_all_entities.return_value = []
        mock_client2.get_all_relations.return_value = []

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        await analyzer.analyze()

        mock_client1.get_all_entities.assert_awaited_once()
        mock_client1.get_all_relations.assert_awaited_once()
        mock_client2.get_all_entities.assert_awaited_once()
        mock_client2.get_all_relations.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_relation_removed_in_ws2(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """Should detect relations removed in ws2."""
        entities = [
            {"entity_name": "A", "entity_type": "class", "source_id": "a.py"},
            {"entity_name": "B", "entity_type": "function", "source_id": "b.py"},
        ]
        mock_client1.get_all_entities.return_value = entities
        mock_client2.get_all_entities.return_value = entities

        mock_client1.get_all_relations.return_value = [
            {"src_id": "A", "tgt_id": "B", "keywords": "CALLS", "source_id": "a.py"},
            {"src_id": "B", "tgt_id": "A", "keywords": "IMPORTS", "source_id": "b.py"},
        ]
        mock_client2.get_all_relations.return_value = [
            {"src_id": "A", "tgt_id": "B", "keywords": "CALLS", "source_id": "a.py"},
        ]

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        result = await analyzer.analyze()

        assert result.summary["relations_diff"] > 0
        # B lost an outgoing relation
        b_changes = [c for c in result.relation_changes if c["entity"] == "B"]
        assert len(b_changes) == 1
        assert len(b_changes[0]["removed"]) == 1

    @pytest.mark.asyncio
    async def test_mixed_added_removed_entities(
        self, mock_client1: AsyncMock, mock_client2: AsyncMock
    ) -> None:
        """Both workspaces have unique and shared entities."""
        mock_client1.get_all_entities.return_value = [
            {"entity_name": "Shared", "entity_type": "class", "source_id": "s.py"},
            {"entity_name": "OnlyWs1", "entity_type": "function", "source_id": "o1.py"},
        ]
        mock_client1.get_all_relations.return_value = []
        mock_client2.get_all_entities.return_value = [
            {"entity_name": "Shared", "entity_type": "class", "source_id": "s.py"},
            {"entity_name": "OnlyWs2", "entity_type": "function", "source_id": "o2.py"},
        ]
        mock_client2.get_all_relations.return_value = []

        analyzer = CompareAnalyzer(client1=mock_client1, client2=mock_client2, ws1="ws1", ws2="ws2")
        result = await analyzer.analyze()

        assert result.summary["only_in_ws1"] == 1
        assert result.summary["only_in_ws2"] == 1
        assert result.summary["in_both"] == 1
        assert result.only_in_ws1[0]["name"] == "OnlyWs1"
        assert result.only_in_ws2[0]["name"] == "OnlyWs2"
