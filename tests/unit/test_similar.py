"""Tests for loomgraph.core.similar module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from loomgraph.core.similar import SimilarAnalyzer, SimilarResult


class TestSimilarResult:
    """Tests for SimilarResult serialization."""

    def test_to_dict(self) -> None:
        """Should serialize to dict correctly."""
        result = SimilarResult(
            query_entity="AuthService",
            matches=[
                {
                    "workspace": "project-a",
                    "entity": "AuthService",
                    "match_type": "exact",
                    "relations_count": 5,
                },
            ],
        )
        d = result.to_dict()
        assert d["query_entity"] == "AuthService"
        assert len(d["matches"]) == 1
        assert d["matches"][0]["match_type"] == "exact"

    def test_to_dict_empty_matches(self) -> None:
        """Empty matches should serialize correctly."""
        result = SimilarResult(query_entity="Missing", matches=[])
        d = result.to_dict()
        assert d["matches"] == []


class TestSimilarAnalyzer:
    """Tests for SimilarAnalyzer class."""

    @pytest.fixture
    def mock_clients(self) -> list[AsyncMock]:
        """Create mock LightRAG clients for 3 workspaces."""
        return [AsyncMock(), AsyncMock(), AsyncMock()]

    @pytest.mark.asyncio
    async def test_exact_match_across_workspaces(self, mock_clients: list[AsyncMock]) -> None:
        """Should find exact name matches across multiple workspaces."""
        mock_clients[0].get_all_entities.return_value = [
            {"entity_name": "AuthService", "entity_type": "class", "source_id": "auth.py"},
        ]
        mock_clients[0].get_all_relations.return_value = [
            {"src_id": "AuthService", "tgt_id": "DB", "keywords": "CALLS"},
            {"src_id": "Login", "tgt_id": "AuthService", "keywords": "CALLS"},
        ]
        mock_clients[1].get_all_entities.return_value = [
            {"entity_name": "AuthService", "entity_type": "class", "source_id": "auth.py"},
        ]
        mock_clients[1].get_all_relations.return_value = [
            {"src_id": "AuthService", "tgt_id": "Cache", "keywords": "CALLS"},
        ]
        mock_clients[2].get_all_entities.return_value = [
            {"entity_name": "UserService", "entity_type": "class", "source_id": "user.py"},
        ]
        mock_clients[2].get_all_relations.return_value = []

        analyzer = SimilarAnalyzer(
            clients=mock_clients,
            workspace_names=["ws-a", "ws-b", "ws-c"],
        )
        result = await analyzer.analyze("AuthService")

        assert result.query_entity == "AuthService"
        exact = [m for m in result.matches if m["match_type"] == "exact"]
        assert len(exact) == 2
        ws_names = {m["workspace"] for m in exact}
        assert ws_names == {"ws-a", "ws-b"}
        # Check relation counts
        ws_a_match = next(m for m in exact if m["workspace"] == "ws-a")
        assert ws_a_match["relations_count"] == 2

    @pytest.mark.asyncio
    async def test_fuzzy_match(self, mock_clients: list[AsyncMock]) -> None:
        """Should find fuzzy name matches (SequenceMatcher ratio > 0.7)."""
        mock_clients[0].get_all_entities.return_value = [
            {"entity_name": "AuthService", "entity_type": "class", "source_id": "a.py"},
        ]
        mock_clients[0].get_all_relations.return_value = []
        mock_clients[1].get_all_entities.return_value = [
            {"entity_name": "AuthServiceV2", "entity_type": "class", "source_id": "a2.py"},
        ]
        mock_clients[1].get_all_relations.return_value = []
        mock_clients[2].get_all_entities.return_value = [
            {"entity_name": "Unrelated", "entity_type": "function", "source_id": "x.py"},
        ]
        mock_clients[2].get_all_relations.return_value = []

        analyzer = SimilarAnalyzer(
            clients=mock_clients,
            workspace_names=["ws-a", "ws-b", "ws-c"],
        )
        result = await analyzer.analyze("AuthService")

        exact = [m for m in result.matches if m["match_type"] == "exact"]
        fuzzy = [m for m in result.matches if m["match_type"] == "fuzzy"]
        assert len(exact) == 1
        assert exact[0]["workspace"] == "ws-a"
        assert len(fuzzy) == 1
        assert fuzzy[0]["entity"] == "AuthServiceV2"

    @pytest.mark.asyncio
    async def test_no_match(self, mock_clients: list[AsyncMock]) -> None:
        """No matches should return empty result."""
        for c in mock_clients:
            c.get_all_entities.return_value = [
                {"entity_name": "Unrelated", "entity_type": "function", "source_id": "x.py"},
            ]
            c.get_all_relations.return_value = []

        analyzer = SimilarAnalyzer(
            clients=mock_clients,
            workspace_names=["ws-a", "ws-b", "ws-c"],
        )
        result = await analyzer.analyze("AuthService")

        assert result.matches == []

    @pytest.mark.asyncio
    async def test_single_workspace(self) -> None:
        """Single workspace should degrade to local search."""
        client = AsyncMock()
        client.get_all_entities.return_value = [
            {"entity_name": "MyFunc", "entity_type": "function", "source_id": "f.py"},
        ]
        client.get_all_relations.return_value = [
            {"src_id": "MyFunc", "tgt_id": "Other", "keywords": "CALLS"},
        ]

        analyzer = SimilarAnalyzer(clients=[client], workspace_names=["solo"])
        result = await analyzer.analyze("MyFunc")

        assert len(result.matches) == 1
        assert result.matches[0]["workspace"] == "solo"
        assert result.matches[0]["match_type"] == "exact"

    @pytest.mark.asyncio
    async def test_fuzzy_threshold(self, mock_clients: list[AsyncMock]) -> None:
        """Names below 0.7 similarity should not match."""
        mock_clients[0].get_all_entities.return_value = [
            {"entity_name": "XYZ", "entity_type": "class", "source_id": "x.py"},
        ]
        mock_clients[0].get_all_relations.return_value = []
        mock_clients[1].get_all_entities.return_value = []
        mock_clients[1].get_all_relations.return_value = []
        mock_clients[2].get_all_entities.return_value = []
        mock_clients[2].get_all_relations.return_value = []

        analyzer = SimilarAnalyzer(
            clients=mock_clients,
            workspace_names=["ws-a", "ws-b", "ws-c"],
        )
        result = await analyzer.analyze("AuthService")

        assert result.matches == []

    @pytest.mark.asyncio
    async def test_case_insensitive_fuzzy(self, mock_clients: list[AsyncMock]) -> None:
        """Fuzzy matching should be case-insensitive."""
        mock_clients[0].get_all_entities.return_value = [
            {"entity_name": "authservice", "entity_type": "class", "source_id": "a.py"},
        ]
        mock_clients[0].get_all_relations.return_value = []
        mock_clients[1].get_all_entities.return_value = []
        mock_clients[1].get_all_relations.return_value = []
        mock_clients[2].get_all_entities.return_value = []
        mock_clients[2].get_all_relations.return_value = []

        analyzer = SimilarAnalyzer(
            clients=mock_clients,
            workspace_names=["ws-a", "ws-b", "ws-c"],
        )
        result = await analyzer.analyze("AuthService")

        # "authservice" vs "AuthService" lowered → exact match on lowercase,
        # but entity_name differs → should be fuzzy with high ratio
        matches = result.matches
        assert len(matches) >= 1

    @pytest.mark.asyncio
    async def test_relations_count_accuracy(self, mock_clients: list[AsyncMock]) -> None:
        """Relations count should only count relations involving the matched entity."""
        mock_clients[0].get_all_entities.return_value = [
            {"entity_name": "Target", "entity_type": "class", "source_id": "t.py"},
            {"entity_name": "Other", "entity_type": "function", "source_id": "o.py"},
        ]
        mock_clients[0].get_all_relations.return_value = [
            {"src_id": "Target", "tgt_id": "Other", "keywords": "CALLS"},
            {"src_id": "Other", "tgt_id": "Target", "keywords": "IMPORTS"},
            {"src_id": "Other", "tgt_id": "Unrelated", "keywords": "CALLS"},
        ]
        mock_clients[1].get_all_entities.return_value = []
        mock_clients[1].get_all_relations.return_value = []
        mock_clients[2].get_all_entities.return_value = []
        mock_clients[2].get_all_relations.return_value = []

        analyzer = SimilarAnalyzer(
            clients=mock_clients,
            workspace_names=["ws-a", "ws-b", "ws-c"],
        )
        result = await analyzer.analyze("Target")

        assert len(result.matches) == 1
        assert result.matches[0]["relations_count"] == 2  # Only relations involving Target

    @pytest.mark.asyncio
    async def test_concurrent_fetch(self, mock_clients: list[AsyncMock]) -> None:
        """All clients should be queried."""
        for c in mock_clients:
            c.get_all_entities.return_value = []
            c.get_all_relations.return_value = []

        analyzer = SimilarAnalyzer(
            clients=mock_clients,
            workspace_names=["ws-a", "ws-b", "ws-c"],
        )
        await analyzer.analyze("Anything")

        for c in mock_clients:
            c.get_all_entities.assert_awaited_once()
            c.get_all_relations.assert_awaited_once()
