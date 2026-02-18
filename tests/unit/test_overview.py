"""Tests for loomgraph.core.overview module."""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest

from loomgraph.core.overview import OverviewAnalyzer, OverviewResult


class TestOverviewAnalyzer:
    """Tests for OverviewAnalyzer class."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock LightRAG client."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_module_grouping(self, mock_client: AsyncMock) -> None:
        """Should group entities by module correctly."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "ClientA", "entity_type": "class", "source_id": "src/core/client.py"},
            {"entity_name": "func_b", "entity_type": "function", "source_id": "src/core/utils.py"},
            {"entity_name": "Handler", "entity_type": "class", "source_id": "src/cli/handler.py"},
        ]
        mock_client.get_all_relations.return_value = []

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze(no_summary=True)

        assert isinstance(result, OverviewResult)
        module_names = [m["name"] for m in result.modules]
        assert "src/core" in module_names
        assert "src/cli" in module_names

        core_module = next(m for m in result.modules if m["name"] == "src/core")
        assert core_module["entity_count"] == 2

    @pytest.mark.asyncio
    async def test_entity_type_statistics(self, mock_client: AsyncMock) -> None:
        """Should count entities by type."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "entity_type": "class", "source_id": "src/core/a.py"},
            {"entity_name": "B", "entity_type": "class", "source_id": "src/core/b.py"},
            {"entity_name": "c", "entity_type": "function", "source_id": "src/core/c.py"},
        ]
        mock_client.get_all_relations.return_value = []

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze(no_summary=True)

        core_module = next(m for m in result.modules if m["name"] == "src/core")
        assert core_module["entities_by_type"]["class"] == 2
        assert core_module["entities_by_type"]["function"] == 1

    @pytest.mark.asyncio
    async def test_top_entities_sorted_by_relation_count(self, mock_client: AsyncMock) -> None:
        """Top entities should be sorted by relation count (descending)."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "Popular", "entity_type": "class", "source_id": "src/core/pop.py"},
            {"entity_name": "Lonely", "entity_type": "class", "source_id": "src/core/lonely.py"},
            {"entity_name": "Medium", "entity_type": "function", "source_id": "src/core/med.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "Popular", "tgt_id": "Lonely", "keywords": "CALLS"},
            {"src_id": "Medium", "tgt_id": "Popular", "keywords": "CALLS"},
            {"src_id": "Popular", "tgt_id": "Medium", "keywords": "IMPORTS"},
        ]

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze(no_summary=True)

        core_module = next(m for m in result.modules if m["name"] == "src/core")
        # Popular has 3 relations, Medium has 2, Lonely has 1
        assert core_module["top_entities"][0] == "Popular"

    @pytest.mark.asyncio
    async def test_files_extracted(self, mock_client: AsyncMock) -> None:
        """Should extract unique filenames per module."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "entity_type": "class", "source_id": "src/core/client.py"},
            {"entity_name": "B", "entity_type": "function", "source_id": "src/core/client.py"},
            {"entity_name": "C", "entity_type": "class", "source_id": "src/core/utils.py"},
        ]
        mock_client.get_all_relations.return_value = []

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze(no_summary=True)

        core_module = next(m for m in result.modules if m["name"] == "src/core")
        assert sorted(core_module["files"]) == ["client.py", "utils.py"]

    @pytest.mark.asyncio
    async def test_no_summary_skips_query(self, mock_client: AsyncMock) -> None:
        """When no_summary=True, should not call client.query()."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "entity_type": "class", "source_id": "src/core/a.py"},
        ]
        mock_client.get_all_relations.return_value = []

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        await analyzer.analyze(no_summary=True)

        mock_client.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_summary_calls_query(self, mock_client: AsyncMock) -> None:
        """When no_summary=False, should call client.query() for each module."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "entity_type": "class", "source_id": "src/core/a.py"},
            {"entity_name": "B", "entity_type": "class", "source_id": "src/cli/b.py"},
        ]
        mock_client.get_all_relations.return_value = []
        mock_client.query.return_value = {"response": "This module does X"}

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze(no_summary=False)

        assert mock_client.query.call_count == 2
        for module in result.modules:
            assert module["summary"] == "This module does X"

    @pytest.mark.asyncio
    async def test_summary_graceful_degradation(self, mock_client: AsyncMock) -> None:
        """LLM failure should not crash; summary should be empty string."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "entity_type": "class", "source_id": "src/core/a.py"},
        ]
        mock_client.get_all_relations.return_value = []
        mock_client.query.side_effect = Exception("LLM timeout")

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze(no_summary=False)

        core_module = next(m for m in result.modules if m["name"] == "src/core")
        assert core_module["summary"] == ""

    @pytest.mark.asyncio
    async def test_includes_dependency_graph(self, mock_client: AsyncMock) -> None:
        """Should include dependency graph from DepsAnalyzer."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "entity_type": "class", "source_id": "src/cli/a.py"},
            {"entity_name": "B", "entity_type": "class", "source_id": "src/core/b.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "A", "tgt_id": "B", "keywords": "CALLS"},
        ]

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze(no_summary=True)

        assert "dependency_graph" in result.to_dict()
        dep_graph = result.dependency_graph
        assert len(dep_graph["dependencies"]) == 1

    @pytest.mark.asyncio
    async def test_empty_graph(self, mock_client: AsyncMock) -> None:
        """Empty graph should return empty overview."""
        mock_client.get_all_entities.return_value = []
        mock_client.get_all_relations.return_value = []

        analyzer = OverviewAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze(no_summary=True)

        assert result.modules == []


class TestOverviewResult:
    """Tests for OverviewResult serialization."""

    def test_to_dict(self) -> None:
        """Should serialize to dict correctly."""
        result = OverviewResult(
            modules=[
                {
                    "name": "src/core",
                    "entity_count": 5,
                    "entities_by_type": {"class": 3},
                    "top_entities": ["A"],
                    "files": ["a.py"],
                    "summary": "Core module",
                },
            ],
            dependency_graph={
                "modules": ["src/core"],
                "dependencies": [],
                "stats": {"total_modules": 1, "total_dependencies": 0, "total_entities": 5, "total_relations": 10},
            },
        )
        d = result.to_dict()
        assert len(d["modules"]) == 1
        assert d["modules"][0]["name"] == "src/core"
        assert "dependency_graph" in d
