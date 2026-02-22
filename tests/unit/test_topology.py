"""Tests for loomgraph.core.topology module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from loomgraph.core.topology import (
    CouplingMetrics,
    TopologyAnalyzer,
    TopologyResult,
    _compute_score,
    _is_noise,
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
        """God function with out >= 20 → -5 per entity."""
        result = TopologyResult(
            total_entities=100,
            god_functions=[{"entity": "A", "out_degree": 20}],
        )
        assert _compute_score(result) == 95

    def test_god_function_penalty_moderate(self) -> None:
        """God function with out 10-19 → -3 per entity."""
        result = TopologyResult(
            total_entities=100,
            god_functions=[{"entity": "A", "out_degree": 12}],
        )
        assert _compute_score(result) == 97

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
        """Score should never go below 0."""
        result = TopologyResult(
            total_entities=10,
            orphans=[{"entity": f"o{i}"} for i in range(5)],
            hubs=[{"entity": f"h{i}", "in_degree": 20} for i in range(10)],
            god_functions=[{"entity": f"g{i}", "out_degree": 25} for i in range(10)],
            placeholder_modules=[{"module": f"m{i}"} for i in range(5)],
            coupling=CouplingMetrics(density=0.8),
        )
        assert _compute_score(result) == 0


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
