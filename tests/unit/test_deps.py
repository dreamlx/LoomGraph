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
    async def test_resolved_module_import_without_unique_source_mapping_is_skipped(
        self, mock_client: AsyncMock
    ) -> None:
        """#239: module endpoints must map uniquely from source-bearing entities."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "src.cli.handler.run", "source_id": "src/cli/handler.py"},
            {"entity_name": "src.core.service.authenticate", "source_id": "src/core/service.py"},
            {"entity_name": "src.core.service.legacy", "source_id": "vendor/core/service.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {
                "src_id": "src.cli.handler",
                "tgt_id": "src.core.service",
                "keywords": "IMPORTS",
                "resolution_qualifier": "resolved",
            },
            {
                "src_id": "src.cli.handler",
                "tgt_id": "src.no_source",
                "keywords": "IMPORTS",
                "resolution_qualifier": "resolved",
            },
            {
                "src_id": "src.cli.handler",
                "tgt_id": "third_party",
                "keywords": "IMPORTS",
                "resolution_qualifier": "unresolved",
            },
        ]

        result = await DepsAnalyzer(client=mock_client, depth=2).analyze()

        assert result.dependencies == []

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


class TestAutoDepthDrillDown:
    """#106: single-package repos (src/<pkg>/*) collapse to one module at the
    starting depth, hiding cli→core etc. auto_depth re-runs at increasing depth
    until more than one real module appears. On by default; opt out with
    auto_depth=False."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_drills_single_package_repo(self, mock_client: AsyncMock) -> None:
        """src/loomgraph/{cli,core} at depth=2 is one module → drill to depth=3."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "cli.run", "source_id": "src/lg/cli/run.py"},
            {"entity_name": "core.Worker", "source_id": "src/lg/core/worker.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "cli.run", "tgt_id": "core.Worker", "keywords": "CALLS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=2)  # auto_depth default True
        result = await analyzer.analyze()

        # depth=2 would give a single "src/lg" module + 0 deps; auto_depth
        # drills to depth=3 so cli→core surfaces.
        assert "src/lg/cli" in result.modules
        assert "src/lg/core" in result.modules
        assert len(result.dependencies) == 1
        assert result.dependencies[0]["from"] == "src/lg/cli"
        assert result.dependencies[0]["to"] == "src/lg/core"

    @pytest.mark.asyncio
    async def test_no_drill_when_already_multi_module(self, mock_client: AsyncMock) -> None:
        """Multi-module repo at depth=2 already has >1 module → no drill."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "source_id": "src/auth/a.py"},
            {"entity_name": "B", "source_id": "src/api/b.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "A", "tgt_id": "B", "keywords": "CALLS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze()

        # stays at depth=2: src/auth, src/api (not drilled to src/auth/*, src/api/*)
        assert result.modules == ["src/api", "src/auth"]
        assert len(result.dependencies) == 1

    @pytest.mark.asyncio
    async def test_auto_depth_disabled_keeps_fixed_depth(self, mock_client: AsyncMock) -> None:
        """auto_depth=False preserves exact depth even if it yields one module."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "cli.run", "source_id": "src/lg/cli/run.py"},
            {"entity_name": "core.Worker", "source_id": "src/lg/core/worker.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "cli.run", "tgt_id": "core.Worker", "keywords": "CALLS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=2, auto_depth=False)
        result = await analyzer.analyze()

        # fixed depth=2 → one module "src/lg", 0 deps (the pre-#106 behaviour)
        assert result.modules == ["src/lg"]
        assert len(result.dependencies) == 0

    @pytest.mark.asyncio
    async def test_drill_stops_at_first_multi_module_depth(self, mock_client: AsyncMock) -> None:
        """Don't over-drill: stop as soon as >1 module appears (no finer split)."""
        mock_client.get_all_entities.return_value = [
            {"entity_name": "a", "source_id": "src/lg/cli/x/a.py"},
            {"entity_name": "b", "source_id": "src/lg/core/y/b.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "a", "tgt_id": "b", "keywords": "CALLS"},
        ]

        analyzer = DepsAnalyzer(client=mock_client, depth=2)
        result = await analyzer.analyze()

        # depth=3 already yields src/lg/cli + src/lg/core → stop there, NOT depth=4
        assert result.modules == ["src/lg/cli", "src/lg/core"]


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
