"""Tests for loomgraph.core.deps module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from loomgraph.core.deps import DepsAnalyzer, DepsResult, extract_module


class TestExtractModule:
    """Tests for extract_module function."""

    def test_depth_2(self) -> None:
        """Should extract 2-level module path."""
        assert extract_module("src/auth/service.py", depth=2) == "src/auth"

    def test_depth_1(self) -> None:
        """Should extract 1-level module path."""
        assert extract_module("src/auth/service.py", depth=1) == "src"

    def test_depth_3(self) -> None:
        """Should extract 3-level module path."""
        assert extract_module("src/loomgraph/core/lightrag_client.py", depth=3) == "src/loomgraph/core"

    def test_root_file(self) -> None:
        """Root-level file should return '.'."""
        assert extract_module("main.py", depth=2) == "."

    def test_shallow_file_depth_exceeds(self) -> None:
        """When depth exceeds path parts, return full directory."""
        assert extract_module("src/main.py", depth=3) == "src"

    def test_empty_path(self) -> None:
        """Empty path should return '.'."""
        assert extract_module("", depth=2) == "."

    def test_deep_path_depth_1(self) -> None:
        """Deep path with depth=1 returns first dir only."""
        assert extract_module("a/b/c/d/e.py", depth=1) == "a"


class TestDepsAnalyzer:
    """Tests for DepsAnalyzer class."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock LightRAG client."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_basic_cross_module_dependency(self, mock_client: AsyncMock) -> None:
        """Should detect cross-module dependency."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "LoginHandler", "source_id": "src/cli/login.py"},
            {"entity_name": "AuthService", "source_id": "src/core/auth.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "LoginHandler", "tgt_id": "AuthService", "keywords": "CALLS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze()

        assert isinstance(result, DepsResult)
        assert "src/cli" in result.modules
        assert "src/core" in result.modules
        assert len(result.dependencies) == 1
        dep = result.dependencies[0]
        assert dep["from"] == "src/cli"
        assert dep["to"] == "src/core"
        assert dep["count"] == 1
        assert "CALLS" in dep["types"]

    @pytest.mark.asyncio
    async def test_same_module_excluded(self, mock_client: AsyncMock) -> None:
        """Relations within the same module should be excluded."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "FuncA", "source_id": "src/core/a.py"},
            {"entity_name": "FuncB", "source_id": "src/core/b.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "FuncA", "tgt_id": "FuncB", "keywords": "CALLS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze()

        assert len(result.dependencies) == 0

    @pytest.mark.asyncio
    async def test_external_entity_skipped(self, mock_client: AsyncMock) -> None:
        """Entities without source_id should be skipped."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "MyClass", "source_id": "src/core/foo.py"},
            {"entity_name": "ExternalLib"},  # No source_id
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "MyClass", "tgt_id": "ExternalLib", "keywords": "IMPORTS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze()

        # ExternalLib has no source_id so the relation is skipped
        assert len(result.dependencies) == 0
        assert "src/core" in result.modules

    @pytest.mark.asyncio
    async def test_multiple_relation_types_aggregated(self, mock_client: AsyncMock) -> None:
        """Multiple relations between same modules should aggregate."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "Handler", "source_id": "src/cli/handler.py"},
            {"entity_name": "Service", "source_id": "src/core/service.py"},
            {"entity_name": "Config", "source_id": "src/core/config.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "Handler", "tgt_id": "Service", "keywords": "CALLS"},
            {"src_id": "Handler", "tgt_id": "Config", "keywords": "IMPORTS"},
            {"src_id": "Handler", "tgt_id": "Service", "keywords": "IMPORTS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze()

        assert len(result.dependencies) == 1
        dep = result.dependencies[0]
        assert dep["from"] == "src/cli"
        assert dep["to"] == "src/core"
        assert dep["count"] == 3
        assert dep["types"]["CALLS"] == 1
        assert dep["types"]["IMPORTS"] == 2

    @pytest.mark.asyncio
    async def test_empty_graph(self, mock_client: AsyncMock) -> None:
        """Empty graph should return empty result."""
        mock_client.get_all_entities.return_value = []
        mock_client.get_all_relations.return_value = []

        analyzer = DepsAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze()

        assert result.modules == []
        assert result.dependencies == []
        assert result.stats["total_modules"] == 0

    @pytest.mark.asyncio
    async def test_depth_1(self, mock_client: AsyncMock) -> None:
        """Depth=1 should use top-level directory grouping."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "source_id": "src/cli/login.py"},
            {"entity_name": "B", "source_id": "tests/test_login.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "B", "tgt_id": "A", "keywords": "IMPORTS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=1)
        result = await analyzer.analyze()

        assert len(result.dependencies) == 1
        dep = result.dependencies[0]
        assert dep["from"] == "tests"
        assert dep["to"] == "src"


class TestDepsResult:
    """Tests for DepsResult serialization."""

    def test_to_dict(self) -> None:
        """Should serialize to dict correctly."""
        result = DepsResult(
            modules=["src/cli", "src/core"],
            dependencies=[
                {"from": "src/cli", "to": "src/core", "count": 5, "types": {"CALLS": 5}},
            ],
            stats={
                "total_modules": 2,
                "total_dependencies": 1,
                "total_entities": 10,
                "total_relations": 20,
            },
        )
        d = result.to_dict()
        assert d["modules"] == ["src/cli", "src/core"]
        assert len(d["dependencies"]) == 1
        assert d["stats"]["total_modules"] == 2
