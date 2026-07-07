"""Tests for loomgraph.core.topology module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from loomgraph.core.topology import (
    CouplingMetrics,
    TopologyAnalyzer,
    TopologyResult,
    _common_source_prefix,
    _compute_coupled_pairs,
    _compute_score,
    _is_noise,
    _normalize_type_field,
    _strip_line_range,
)


class TestIsNoise:
    """Tests for the _is_noise helper."""

    def test_stdlib_entity(self) -> None:
        assert _is_noise("len") is True
        assert _is_noise("isinstance") is True

    def test_noise_suffix(self) -> None:
        assert _is_noise("foo.get") is True
        assert _is_noise("bar.append") is True

    def test_normal_entity(self) -> None:
        assert _is_noise("TopologyAnalyzer") is False
        assert _is_noise("my_function") is False


class TestTopologyAnalyzerFromData:
    """Tests for TopologyAnalyzer.analyze_from_data (pure function)."""

    def _make_entity(
        self,
        name: str,
        source_id: str,
        entity_type: str = "function",
    ) -> dict:
        return {
            "entity_name": name,
            "source_id": source_id,
            "entity_type": entity_type,
        }

    def _make_relation(self, src: str, tgt: str, keywords: str = "CALLS") -> dict:
        return {"src_id": src, "tgt_id": tgt, "keywords": keywords}

    def test_orphan_detection(self) -> None:
        """Entities with 0 in + 0 out should be detected as orphans."""
        entities = [
            self._make_entity("OrphanFunc", "src/core/orphan.py"),
            self._make_entity("ConnectedA", "src/core/a.py"),
            self._make_entity("ConnectedB", "src/core/b.py"),
        ]
        relations = [
            self._make_relation("ConnectedA", "ConnectedB"),
        ]

        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data(entities, relations)

        orphan_names = [o["entity"] for o in result.orphans]
        assert "OrphanFunc" in orphan_names
        assert "ConnectedA" not in orphan_names
        assert "ConnectedB" not in orphan_names

    def test_orphan_excludes_module_type(self) -> None:
        """Module-type entities should not be flagged as orphans."""
        entities = [
            self._make_entity("core.__init__", "src/core/__init__.py", "module"),
        ]
        relations = []

        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data(entities, relations)

        assert len(result.orphans) == 0

    def test_orphan_excludes_external(self) -> None:
        """External entities should be filtered out entirely."""
        entities = [
            self._make_entity("requests.get", "external", "external"),
        ]
        relations = []

        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data(entities, relations)

        assert len(result.orphans) == 0
        assert result.total_entities == 0

    def test_orphan_class_constructor_aggregation(self) -> None:
        """Class with __init__ calls should NOT be orphan (Issue #28 fix)."""
        entities = [
            self._make_entity("MyClass", "src/models.py", "class"),
            self._make_entity("MyClass.__init__", "src/models.py", "external"),
            self._make_entity("TestCase", "tests/test_models.py"),
        ]
        relations = [
            # Constructor is called, but not the class itself
            self._make_relation("TestCase", "MyClass.__init__"),
        ]

        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data(entities, relations)

        # MyClass should NOT be orphan (has constructor calls)
        orphan_names = [o["entity"] for o in result.orphans]
        assert "MyClass" not in orphan_names

    def test_orphan_whitelist_regex_patterns(self) -> None:
        """Data classes matching regex patterns should be whitelisted (Issue #28 fix)."""
        entities = [
            self._make_entity("UserConfig", "src/config.py", "class"),
            self._make_entity("ScanResult", "src/scanner.py", "class"),
            self._make_entity("ErrorInfo", "src/errors.py", "class"),
            self._make_entity("RequestData", "src/api.py", "class"),
            self._make_entity("UserDTO", "src/dtos.py", "class"),
            self._make_entity("DatabaseModel", "src/db.py", "class"),
            self._make_entity("APISchema", "src/schemas.py", "class"),
            # This one should be detected as orphan (no pattern match)
            self._make_entity("Helper", "src/utils.py", "function"),
        ]
        relations = []  # All have 0 relations

        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data(entities, relations)

        # Only "Helper" should be orphan, all data classes whitelisted
        orphan_names = [o["entity"] for o in result.orphans]
        assert "Helper" in orphan_names
        assert "UserConfig" not in orphan_names  # Matches *Config$
        assert "ScanResult" not in orphan_names  # Matches *Result$
        assert "ErrorInfo" not in orphan_names  # Matches *Info$
        assert "RequestData" not in orphan_names  # Matches *Data$
        assert "UserDTO" not in orphan_names  # Matches *DTO$
        assert "DatabaseModel" not in orphan_names  # Matches *Model$
        assert "APISchema" not in orphan_names  # Matches *Schema$

    def test_hub_detection(self) -> None:
        """Entity with high in-degree should be flagged as hub."""
        entities = [
            self._make_entity("HubFunc", "src/core/hub.py"),
            *[
                self._make_entity(f"Caller{i}", f"src/cli/c{i}.py")
                for i in range(6)
            ],
        ]
        relations = [
            self._make_relation(f"Caller{i}", "HubFunc") for i in range(6)
        ]

        analyzer = TopologyAnalyzer(client=None, hub_threshold=5)
        result = analyzer.analyze_from_data(entities, relations)

        hub_names = [h["entity"] for h in result.hubs]
        assert "HubFunc" in hub_names
        assert result.hubs[0]["in_degree"] == 6

    def test_hub_excludes_stdlib(self) -> None:
        """stdlib entities should not appear as hubs."""
        entities = [
            self._make_entity("len", "src/core/builtins.py"),
            *[
                self._make_entity(f"Caller{i}", f"src/cli/c{i}.py")
                for i in range(6)
            ],
        ]
        relations = [
            self._make_relation(f"Caller{i}", "len") for i in range(6)
        ]

        analyzer = TopologyAnalyzer(client=None, hub_threshold=5)
        result = analyzer.analyze_from_data(entities, relations)

        hub_names = [h["entity"] for h in result.hubs]
        assert "len" not in hub_names

    def test_hub_threshold_configurable(self) -> None:
        """Hub threshold should be configurable."""
        entities = [
            self._make_entity("HubFunc", "src/core/hub.py"),
            *[
                self._make_entity(f"Caller{i}", f"src/cli/c{i}.py")
                for i in range(3)
            ],
        ]
        relations = [
            self._make_relation(f"Caller{i}", "HubFunc") for i in range(3)
        ]

        # Default threshold=5, should not flag
        analyzer = TopologyAnalyzer(client=None, hub_threshold=5)
        result = analyzer.analyze_from_data(entities, relations)
        assert len(result.hubs) == 0

        # Lower threshold=3, should flag
        analyzer = TopologyAnalyzer(client=None, hub_threshold=3)
        result = analyzer.analyze_from_data(entities, relations)
        assert len(result.hubs) == 1

    def test_god_function_detection(self) -> None:
        """Entity with high out-degree should be flagged as god function."""
        entities = [
            self._make_entity("GodFunc", "src/cli/god.py"),
            *[
                self._make_entity(f"Callee{i}", f"src/core/c{i}.py")
                for i in range(6)
            ],
        ]
        relations = [
            self._make_relation("GodFunc", f"Callee{i}") for i in range(6)
        ]

        analyzer = TopologyAnalyzer(client=None, god_threshold=5)
        result = analyzer.analyze_from_data(entities, relations)

        god_names = [g["entity"] for g in result.god_functions]
        assert "GodFunc" in god_names
        assert result.god_functions[0]["out_degree"] == 6

    def test_god_function_excludes_stdlib_callees(self) -> None:
        """Calls to stdlib entities should not count toward out-degree."""
        entities = [
            self._make_entity("MyFunc", "src/core/my.py"),
            self._make_entity("len", "src/core/builtins.py"),
            self._make_entity("Callee1", "src/core/c1.py"),
        ]
        relations = [
            self._make_relation("MyFunc", "len"),
            self._make_relation("MyFunc", "Callee1"),
        ]

        analyzer = TopologyAnalyzer(client=None, god_threshold=2)
        result = analyzer.analyze_from_data(entities, relations)

        # len is noise so out_degree of MyFunc should be 1, not 2
        god_names = [g["entity"] for g in result.god_functions]
        assert "MyFunc" not in god_names

    def test_god_function_excludes_module_type(self) -> None:
        """Module-type entities should not be flagged as god functions."""
        entities = [
            self._make_entity("core.__init__", "src/core/__init__.py", "module"),
            *[
                self._make_entity(f"Callee{i}", f"src/core/c{i}.py")
                for i in range(12)
            ],
        ]
        relations = [
            self._make_relation("core.__init__", f"Callee{i}") for i in range(12)
        ]

        analyzer = TopologyAnalyzer(client=None, god_threshold=5)
        result = analyzer.analyze_from_data(entities, relations)

        god_names = [g["entity"] for g in result.god_functions]
        assert "core.__init__" not in god_names

    def test_coupling_density(self) -> None:
        """Coupling density = cross-module / total counted relations."""
        entities = [
            self._make_entity("A", "src/cli/a.py"),
            self._make_entity("B", "src/core/b.py"),
            self._make_entity("C", "src/core/c.py"),
        ]
        relations = [
            self._make_relation("A", "B"),  # cross-module
            self._make_relation("B", "C"),  # intra-module
        ]

        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data(entities, relations)

        assert result.coupling.cross_module == 1
        assert result.coupling.intra_module == 1
        assert result.coupling.density == pytest.approx(0.5)

    def test_placeholder_module_detection(self) -> None:
        """Modules with only __init__ entities should be flagged."""
        entities = [
            self._make_entity("chunking.__init__", "src/chunking/__init__.py", "module"),
            self._make_entity("RealFunc", "src/core/real.py"),
        ]
        relations = []

        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data(entities, relations)

        # chunking module only has __init__ → placeholder
        placeholder_mods = [p["module"] for p in result.placeholder_modules]
        assert any("chunking" in m for m in placeholder_mods)

    def test_empty_graph(self) -> None:
        """Empty graph should return clean result."""
        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data([], [])

        assert result.total_entities == 0
        assert result.total_relations == 0
        assert len(result.orphans) == 0
        assert len(result.hubs) == 0
        assert len(result.god_functions) == 0
        assert result.topology_score == 100

    def test_module_filter(self) -> None:
        """--module filter should only analyze matching source_ids."""
        entities = [
            self._make_entity("CliFunc", "cli/main.py"),
            self._make_entity("CoreFunc", "core/config.py"),
        ]
        relations = []

        analyzer = TopologyAnalyzer(client=None, module="cli")
        result = analyzer.analyze_from_data(entities, relations)

        # Only cli entities should be counted
        assert result.total_entities == 1
        orphan_names = [o["entity"] for o in result.orphans]
        assert "CliFunc" in orphan_names
        assert "CoreFunc" not in orphan_names

    def test_scope_filter(self) -> None:
        """--scope filters by absolute path prefix, excluding docs/scripts/tests."""
        entities = [
            self._make_entity("Prod", "src/app/main.py"),
            self._make_entity("Harness", "docs/spike/harness.py"),
            self._make_entity("Tool", "scripts/build.py"),
        ]
        relations = []

        analyzer = TopologyAnalyzer(client=None, scope="src/")
        result = analyzer.analyze_from_data(entities, relations)

        # Only src/ entities counted — docs/scripts inflation excluded (#61)
        assert result.total_entities == 1
        orphan_names = [o["entity"] for o in result.orphans]
        assert "Prod" in orphan_names
        assert "Harness" not in orphan_names
        assert "Tool" not in orphan_names

    def test_scope_wins_over_module(self) -> None:
        """When both set, scope (absolute) wins over module (relative)."""
        entities = [
            self._make_entity("A", "src/cli/a.py"),
            self._make_entity("B", "src/core/b.py"),
        ]
        analyzer = TopologyAnalyzer(client=None, module="cli", scope="src/")
        result = analyzer.analyze_from_data(entities, [])
        # scope=src/ keeps both; module=cli would have kept only A
        assert result.total_entities == 2

    def test_to_dict(self) -> None:
        """TopologyResult.to_dict should serialize correctly."""
        result = TopologyResult(
            total_entities=10,
            total_relations=20,
            orphans=[{"entity": "A", "type": "function", "source_id": "a.py"}],
            hubs=[],
            god_functions=[],
            placeholder_modules=[],
            coupling=CouplingMetrics(cross_module=5, intra_module=15, density=0.25),
            topology_score=85,
        )
        d = result.to_dict()

        assert d["summary"]["total_entities"] == 10
        assert d["summary"]["orphan_count"] == 1
        assert d["summary"]["topology_score"] == 85
        assert d["coupling"]["density"] == 0.25
        assert len(d["orphans"]) == 1

    def test_callers_sample_limited_to_5(self) -> None:
        """Hub callers_sample should be limited to 5 entries."""
        entities = [
            self._make_entity("HubFunc", "src/core/hub.py"),
            *[
                self._make_entity(f"Caller{i}", f"src/cli/c{i}.py")
                for i in range(10)
            ],
        ]
        relations = [
            self._make_relation(f"Caller{i}", "HubFunc") for i in range(10)
        ]

        analyzer = TopologyAnalyzer(client=None, hub_threshold=5)
        result = analyzer.analyze_from_data(entities, relations)

        assert len(result.hubs) == 1
        assert len(result.hubs[0]["callers_sample"]) == 5

    def test_noise_suffix_filtered(self) -> None:
        """Entities with noise suffixes should be excluded."""
        entities = [
            self._make_entity("dict.get", "src/core/util.py"),
            self._make_entity("RealFunc", "src/core/real.py"),
        ]
        relations = []

        analyzer = TopologyAnalyzer(client=None)
        result = analyzer.analyze_from_data(entities, relations)

        # dict.get is noise, only RealFunc counted
        assert result.total_entities == 1
        orphan_names = [o["entity"] for o in result.orphans]
        assert "dict.get" not in orphan_names


class TestComputeScore:
    """Tests for _compute_score penalty logic."""

    def test_healthy_graph(self) -> None:
        """Perfect graph should score 100."""
        result = TopologyResult(total_entities=100, total_relations=200)
        assert _compute_score(result) == 100

    def test_orphan_penalty_mild(self) -> None:
        """Orphan ratio 10-20% → -15 penalty."""
        result = TopologyResult(
            total_entities=100,
            orphans=[{"entity": f"o{i}"} for i in range(15)],
        )
        assert _compute_score(result) == 85

    def test_orphan_penalty_severe(self) -> None:
        """Orphan ratio >20% → -25 penalty."""
        result = TopologyResult(
            total_entities=100,
            orphans=[{"entity": f"o{i}"} for i in range(25)],
        )
        assert _compute_score(result) == 75

    def test_hub_penalty(self) -> None:
        """Hub with in_degree >= 15 → -5 per entity."""
        result = TopologyResult(
            total_entities=100,
            hubs=[
                {"entity": "A", "in_degree": 15},
                {"entity": "B", "in_degree": 20},
            ],
        )
        assert _compute_score(result) == 90

    def test_god_function_penalty_severe(self) -> None:
        """God function with out >= 25 → -5 per entity."""
        result = TopologyResult(
            total_entities=100,
            god_functions=[{"entity": "A", "out_degree": 25}],
        )
        assert _compute_score(result) == 95

    def test_god_function_penalty_moderate(self) -> None:
        """God function with out 15-24 → -3 per entity."""
        result = TopologyResult(
            total_entities=100,
            god_functions=[{"entity": "A", "out_degree": 18}],
        )
        assert _compute_score(result) == 97

    def test_god_function_penalty_capped(self) -> None:
        """God function penalty should be capped at -25."""
        result = TopologyResult(
            total_entities=100,
            god_functions=[
                {"entity": f"g{i}", "out_degree": 30} for i in range(10)
            ],
        )
        # 10 × -5 = -50, but capped at -25
        assert _compute_score(result) == 75

    def test_hub_penalty_capped(self) -> None:
        """Hub penalty should be capped at -20."""
        result = TopologyResult(
            total_entities=100,
            hubs=[
                {"entity": f"h{i}", "in_degree": 20} for i in range(10)
            ],
        )
        # 10 × -5 = -50, but capped at -20
        assert _compute_score(result) == 80

    def test_placeholder_penalty(self) -> None:
        """Placeholder modules → -5 per module."""
        result = TopologyResult(
            total_entities=100,
            placeholder_modules=[{"module": "m1"}, {"module": "m2"}],
        )
        assert _compute_score(result) == 90

    def test_coupling_density_penalty(self) -> None:
        """High coupling density → penalty."""
        result = TopologyResult(
            total_entities=100,
            coupling=CouplingMetrics(density=0.6),
        )
        assert _compute_score(result) == 90

    def test_score_floor_at_zero(self) -> None:
        """Score should never go below 0 even with extreme penalties."""
        result = TopologyResult(
            total_entities=10,
            orphans=[{"entity": f"o{i}"} for i in range(5)],
            hubs=[{"entity": f"h{i}", "in_degree": 20} for i in range(10)],
            god_functions=[{"entity": f"g{i}", "out_degree": 30} for i in range(10)],
            placeholder_modules=[{"module": f"m{i}"} for i in range(10)],
            coupling=CouplingMetrics(density=0.8),
        )
        # 100 - 25(orphan) - 20(hub cap) - 25(god cap) - 15(placeholder cap) - 10(coupling) = 5
        # With 10 placeholder modules: capped at -15
        assert _compute_score(result) == 5


class TestTopologyAnalyzerAsync:
    """Tests for TopologyAnalyzer.analyze with async client."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_analyze_fallback_on_server_error(self, mock_client: AsyncMock) -> None:
        """When server-side fails, should fall back to client-side."""
        # Server methods raise
        mock_client.get_orphan_entities.side_effect = Exception("Not found")

        # Client-side data
        mock_client.get_all_entities.return_value = [
            {"entity_name": "Func1", "source_id": "src/a.py", "entity_type": "function"},
            {"entity_name": "Func2", "source_id": "src/b.py", "entity_type": "function"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "Func1", "tgt_id": "Func2", "keywords": "CALLS"},
        ]

        analyzer = TopologyAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        assert isinstance(result, TopologyResult)
        assert result.total_entities == 2
        mock_client.get_all_entities.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_basic(self, mock_client: AsyncMock) -> None:
        """Basic integration test through analyze()."""
        # Make server-side fail to test client path
        mock_client.get_orphan_entities.side_effect = Exception("Not available")

        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "source_id": "src/core/a.py", "entity_type": "function"},
        ]
        mock_client.get_all_relations.return_value = []

        analyzer = TopologyAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        assert result.total_entities == 1
        assert len(result.orphans) == 1


class TestStripLineRange:
    """Tests for _strip_line_range helper."""

    def test_with_range(self) -> None:
        assert _strip_line_range("src/core/a.py:1-50") == "src/core/a.py"

    def test_with_single_line(self) -> None:
        assert _strip_line_range("src/a.py:42") == "src/a.py"

    def test_without_range(self) -> None:
        assert _strip_line_range("src/core/a.py") == "src/core/a.py"

    def test_empty(self) -> None:
        assert _strip_line_range("") == ""


class TestCommonSourcePrefix:
    """Tests for _common_source_prefix helper."""

    def test_common_prefix(self) -> None:
        source_ids = [
            "src/loomgraph/cli/main.py:1-50",
            "src/loomgraph/core/config.py:10-30",
            "src/loomgraph/embedding/client.py",
        ]
        assert _common_source_prefix(source_ids) == "src/loomgraph/"

    def test_partial_prefix(self) -> None:
        source_ids = ["src/cli/a.py", "src/core/b.py"]
        assert _common_source_prefix(source_ids) == "src/"

    def test_no_common_prefix(self) -> None:
        source_ids = ["lib/a.py", "src/b.py"]
        assert _common_source_prefix(source_ids) == ""

    def test_empty_list(self) -> None:
        assert _common_source_prefix([]) == ""

    def test_single_entry(self) -> None:
        assert _common_source_prefix(["src/core/a.py:1-10"]) == "src/core/"

    def test_root_files(self) -> None:
        """Files at root should return empty prefix."""
        assert _common_source_prefix(["a.py", "b.py"]) == ""


class TestServerSideCoupling:
    """Tests for server-side coupling via _analyze_server_side."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_auto_detects_source_prefix(self, mock_client: AsyncMock) -> None:
        """Should auto-detect source_prefix from source_ids."""
        mock_client.get_source_ids.return_value = [
            "src/loomgraph/cli/main.py:1-50",
            "src/loomgraph/core/config.py:10-30",
        ]
        mock_client.get_orphan_entities.return_value = []
        mock_client.get_degree_distribution.return_value = []
        mock_client.get_graph_stats.return_value = {
            "entity_count": 10,
            "relation_count": 20,
            "cross_module_relations": 5,
            "intra_module_relations": 15,
            "coupling_density": 0.25,
        }
        # Needed for _compute_coupled_pairs (cross_module > 0)
        mock_client.get_all_entities.return_value = [
            {"entity_name": "A", "source_id": "src/cli/a.py", "entity_type": "function"},
            {"entity_name": "B", "source_id": "src/core/b.py", "entity_type": "function"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "A", "tgt_id": "B"},
        ]

        analyzer = TopologyAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        # Verify source_prefix was auto-detected and passed to get_graph_stats
        mock_client.get_source_ids.assert_called_once()
        mock_client.get_graph_stats.assert_called_once_with(
            source_prefix="src/loomgraph/",
            module_depth=2,
        )
        assert result.coupling.density == 0.25
        assert result.coupling.cross_module == 5
        assert len(result.coupling.most_coupled_pairs) > 0

    @pytest.mark.asyncio
    async def test_explicit_source_prefix(self, mock_client: AsyncMock) -> None:
        """Should use explicit source_prefix without auto-detection."""
        mock_client.get_orphan_entities.return_value = []
        mock_client.get_degree_distribution.return_value = []
        mock_client.get_graph_stats.return_value = {
            "entity_count": 5,
            "relation_count": 10,
            "cross_module_relations": 2,
            "intra_module_relations": 8,
            "coupling_density": 0.2,
        }
        mock_client.get_all_entities.return_value = []
        mock_client.get_all_relations.return_value = []

        analyzer = TopologyAnalyzer(client=mock_client, source_prefix="app/")
        result = await analyzer.analyze()

        # Should NOT call get_source_ids when prefix is explicit
        mock_client.get_source_ids.assert_not_called()
        mock_client.get_graph_stats.assert_called_once_with(
            source_prefix="app/",
            module_depth=2,
        )
        assert result.coupling.density == 0.2

    @pytest.mark.asyncio
    async def test_module_filter_with_prefix(self, mock_client: AsyncMock) -> None:
        """Module filter should combine with source_prefix for filtering."""
        mock_client.get_orphan_entities.return_value = []
        mock_client.get_degree_distribution.return_value = []
        mock_client.get_graph_stats.return_value = {
            "entity_count": 3,
            "relation_count": 5,
            "cross_module_relations": 0,
            "intra_module_relations": 5,
            "coupling_density": 0.0,
        }

        analyzer = TopologyAnalyzer(
            client=mock_client,
            source_prefix="src/loomgraph/",
            module="cli",
        )
        result = await analyzer.analyze()

        # Orphans/degree should get combined filter prefix
        mock_client.get_orphan_entities.assert_called_once()
        call_args = mock_client.get_orphan_entities.call_args
        assert call_args.kwargs["source_prefix"] == "src/loomgraph/cli/"

        # Stats gets just the source_prefix (for module extraction)
        mock_client.get_graph_stats.assert_called_once_with(
            source_prefix="src/loomgraph/",
            module_depth=2,
        )
        assert isinstance(result, TopologyResult)

    @pytest.mark.asyncio
    async def test_server_side_normalizes_entity_type(self, mock_client: AsyncMock) -> None:
        """Server-side orphans should have entity_type renamed to type."""
        mock_client.get_source_ids.return_value = ["src/core/a.py"]
        mock_client.get_orphan_entities.return_value = [
            {"entity": "Orphan", "entity_type": "class", "source_id": "src/core/a.py"},
        ]
        mock_client.get_degree_distribution.return_value = []
        mock_client.get_graph_stats.return_value = {
            "entity_count": 1,
            "relation_count": 0,
            "cross_module_relations": 0,
            "intra_module_relations": 0,
            "coupling_density": 0.0,
        }

        analyzer = TopologyAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        assert len(result.orphans) == 1
        assert result.orphans[0]["type"] == "class"
        assert "entity_type" not in result.orphans[0]


class TestNormalizeTypeField:
    """Tests for _normalize_type_field helper."""

    def test_renames_entity_type_to_type(self) -> None:
        items = [
            {"entity": "Foo", "entity_type": "class", "source_id": "a.py"},
            {"entity": "Bar", "entity_type": "function", "source_id": "b.py"},
        ]
        _normalize_type_field(items)
        assert items[0]["type"] == "class"
        assert "entity_type" not in items[0]
        assert items[1]["type"] == "function"

    def test_skips_if_type_already_present(self) -> None:
        items = [{"entity": "Foo", "type": "class", "entity_type": "method"}]
        _normalize_type_field(items)
        assert items[0]["type"] == "class"  # unchanged

    def test_no_op_without_entity_type(self) -> None:
        items = [{"entity": "Foo", "source_id": "a.py"}]
        _normalize_type_field(items)
        assert "type" not in items[0]


class TestComputeCoupledPairs:
    """Tests for _compute_coupled_pairs helper."""

    def test_basic_cross_module(self) -> None:
        entities = [
            {"entity_name": "A", "source_id": "src/cli/a.py", "entity_type": "function"},
            {"entity_name": "B", "source_id": "src/core/b.py", "entity_type": "function"},
            {"entity_name": "C", "source_id": "src/core/c.py", "entity_type": "function"},
        ]
        relations = [
            {"src_id": "A", "tgt_id": "B"},
            {"src_id": "A", "tgt_id": "C"},  # same pair: cli → core
            {"src_id": "B", "tgt_id": "C"},  # intra-module, not counted
        ]
        pairs = _compute_coupled_pairs(entities, relations)
        assert len(pairs) == 1
        assert pairs[0]["count"] == 2
        assert pairs[0]["from"] == "src/cli"
        assert pairs[0]["to"] == "src/core"

    def test_excludes_noise_and_external(self) -> None:
        entities = [
            {"entity_name": "A", "source_id": "src/cli/a.py", "entity_type": "function"},
            {"entity_name": "len", "source_id": "src/core/b.py", "entity_type": "function"},
            {"entity_name": "Ext", "source_id": "external", "entity_type": "external"},
        ]
        relations = [
            {"src_id": "A", "tgt_id": "len"},
            {"src_id": "A", "tgt_id": "Ext"},
        ]
        pairs = _compute_coupled_pairs(entities, relations)
        assert len(pairs) == 0

    def test_empty_relations(self) -> None:
        entities = [
            {"entity_name": "A", "source_id": "src/cli/a.py", "entity_type": "function"},
        ]
        pairs = _compute_coupled_pairs(entities, [])
        assert pairs == []

    def test_top_n_limit(self) -> None:
        """Should return only top N pairs."""
        entities = []
        relations = []
        # Create 8 cross-module pairs with different counts
        for i in range(8):
            src_name = f"Src{i}"
            tgt_name = f"Tgt{i}"
            entities.append({"entity_name": src_name, "source_id": f"mod{i}/a.py", "entity_type": "function"})
            entities.append({"entity_name": tgt_name, "source_id": f"mod{i + 10}/b.py", "entity_type": "function"})
            relations.append({"src_id": src_name, "tgt_id": tgt_name})

        pairs = _compute_coupled_pairs(entities, relations, top_n=3)
        assert len(pairs) == 3


class TestCouplingMetrics:
    """Tests for CouplingMetrics serialization."""

    def test_to_dict(self) -> None:
        cm = CouplingMetrics(
            cross_module=10,
            intra_module=90,
            density=0.1,
            most_coupled_pairs=[{"from": "a", "to": "b", "count": 5}],
        )
        d = cm.to_dict()
        assert d["cross_module_relations"] == 10
        assert d["intra_module_relations"] == 90
        assert d["density"] == 0.1
        assert len(d["most_coupled_pairs"]) == 1
