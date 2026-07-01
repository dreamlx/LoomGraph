"""
Unit tests for DebtAnalyzer topology integration (Phase 3)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from loomgraph.core.debt_analyzer import DebtAnalyzer
from loomgraph.core.topology import CouplingMetrics, TopologyResult


@pytest.fixture
def mock_client():
    """Create mock LightRAG client."""
    return MagicMock()


@pytest.fixture
def mock_topology_result():
    """Create mock topology result with various smells."""
    return TopologyResult(
        total_entities=100,
        total_relations=150,
        orphans=[
            {
                "entity": "OrphanClass",
                "entity_name": "OrphanClass",
                "type": "class",
                "source_id": "src/orphan.py",
                "in_degree": 0,
                "out_degree": 0,
            }
        ],
        hubs=[
            {
                "entity": "HubClass",
                "entity_name": "HubClass",
                "type": "class",
                "source_id": "src/hub.py",
                "in_degree": 15,
            }
        ],
        god_functions=[
            {
                "entity": "GodFunction",
                "entity_name": "GodFunction",
                "type": "function",
                "source_id": "src/god.py",
                "out_degree": 25,
            }
        ],
        placeholder_modules=[
            {
                "entity": "EmptyModule",
                "entity_name": "EmptyModule",
                "type": "module",
                "source_id": "src/empty/",
                "entity_count": 2,
            }
        ],
        coupling=CouplingMetrics(
            cross_module=50,
            intra_module=100,
            density=0.6,
            most_coupled_pairs=[
                {"from": "src/cli", "to": "src/core", "count": 15},
                {"from": "src/core", "to": "src/utils", "count": 10},
            ],
        ),
        topology_score=75,
    )


class TestTopologyIntegration:
    """Test topology analysis integration."""

    @pytest.mark.asyncio
    async def test_analyze_without_client(self):
        """Test analyze skips topology if client is None."""
        analyzer = DebtAnalyzer(client=None)
        result = await analyzer.analyze()

        assert result["overall_health"]["breakdown"]["topology"] == 100
        assert len([i for i in result["issues"] if i["category"] == "orphan_entity"]) == 0

    @pytest.mark.asyncio
    async def test_analyze_with_topology(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test analyze integrates topology results."""
        # Mock TopologyAnalyzer
        async def mock_analyze(self):
            return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        # Check topology score is used
        assert result["overall_health"]["breakdown"]["topology"] == 75

        # Check topology issues are converted
        issues = result["issues"]
        orphan_issues = [i for i in issues if i["category"] == "orphan_entity"]
        hub_issues = [i for i in issues if i["category"] == "hub_fragility"]
        god_issues = [i for i in issues if i["category"] == "god_function"]
        placeholder_issues = [i for i in issues if i["category"] == "placeholder_module"]
        coupling_issues = [i for i in issues if i["category"] == "coupling_density"]

        assert len(orphan_issues) == 1
        assert len(hub_issues) == 1
        assert len(god_issues) == 1
        assert len(placeholder_issues) == 1
        assert len(coupling_issues) == 1

    @pytest.mark.asyncio
    async def test_orphan_entity_conversion(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test orphan entity is converted to DebtIssue correctly."""
        async def mock_analyze(self):
            return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        orphan_issue = next(
            i for i in result["issues"] if i["category"] == "orphan_entity"
        )

        assert orphan_issue["severity"] == "P1"
        assert orphan_issue["entity"] == "OrphanClass"
        assert orphan_issue["entity_type"] == "class"
        assert orphan_issue["location"]["file"] == "src/orphan.py"
        assert orphan_issue["metrics"]["in_degree"] == 0
        assert orphan_issue["metrics"]["out_degree"] == 0
        assert "Connect to other entities" in orphan_issue["suggestion"]

    @pytest.mark.asyncio
    async def test_hub_fragility_conversion(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test hub is converted to hub_fragility issue."""
        async def mock_analyze(self):
            return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        hub_issue = next(
            i for i in result["issues"] if i["category"] == "hub_fragility"
        )

        assert hub_issue["severity"] == "P1"
        assert hub_issue["entity"] == "HubClass"
        assert hub_issue["metrics"]["in_degree"] == 15
        assert "fan-in" in hub_issue["suggestion"]

    @pytest.mark.asyncio
    async def test_god_function_conversion(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test god function is converted to P0 issue (business logic)."""
        async def mock_analyze(self):
            return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        god_issue = next(
            i for i in result["issues"] if i["category"] == "god_function"
        )

        assert god_issue["severity"] == "P0"
        assert god_issue["entity"] == "GodFunction"
        assert god_issue["metrics"]["out_degree"] == 25
        assert "fan-out" in god_issue["suggestion"]

    @pytest.mark.asyncio
    async def test_god_function_whitelist_downgrade(
        self, mock_client, monkeypatch
    ):
        """Test god function matching whitelist is downgraded to P1 (v0.9.2)."""
        from loomgraph.core import topology
        from loomgraph.core.topology import CouplingMetrics, TopologyResult

        # Mock topology result with Parser domain god function
        mock_result = TopologyResult(
            orphans=[],
            hubs=[],
            god_functions=[
                {
                    "entity": "PythonParser.visit_module",
                    "entity_name": "PythonParser.visit_module",
                    "type": "function",
                    "source_id": "src/parser.py",
                    "out_degree": 25,
                }
            ],
            placeholder_modules=[],
            coupling=CouplingMetrics(
                intra_module=10, cross_module=5, density=0.33, most_coupled_pairs=[]
            ),
            topology_score=100,
        )

        async def mock_analyze(self):
            return mock_result

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        god_issue = next(
            i for i in result["issues"] if i["category"] == "god_function"
        )

        # Should be downgraded to P1 (domain complexity, not debt)
        assert god_issue["severity"] == "P1"
        assert god_issue["entity"] == "PythonParser.visit_module"
        assert god_issue["details"]["is_domain_complexity"] is True
        assert "Domain complexity" in god_issue["suggestion"]

    @pytest.mark.asyncio
    async def test_placeholder_module_conversion(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test placeholder module is converted to P2 issue."""
        async def mock_analyze(self):
            return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        placeholder_issue = next(
            i for i in result["issues"] if i["category"] == "placeholder_module"
        )

        assert placeholder_issue["severity"] == "P2"
        assert placeholder_issue["entity"] == "EmptyModule"
        assert placeholder_issue["entity_type"] == "module"
        assert placeholder_issue["metrics"]["entity_count"] == 2

    @pytest.mark.asyncio
    async def test_coupling_density_conversion(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test high coupling density is converted to P1 issue."""
        async def mock_analyze(self):
            return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        coupling_issue = next(
            i for i in result["issues"] if i["category"] == "coupling_density"
        )

        assert coupling_issue["severity"] == "P1"
        assert coupling_issue["entity"] == "cross-module"
        assert coupling_issue["entity_type"] == "system"
        assert coupling_issue["metrics"]["density"] == 0.6
        assert len(coupling_issue["details"]["most_coupled_pairs"]) == 2

    @pytest.mark.asyncio
    async def test_low_coupling_no_issue(self, mock_client, monkeypatch):
        """Test low coupling density does not generate issue."""
        low_coupling_result = TopologyResult(
            total_entities=100,
            total_relations=150,
            coupling=CouplingMetrics(
                cross_module=20,
                intra_module=100,
                density=0.3,  # < 0.5 threshold
            ),
            topology_score=90,
        )

        async def mock_analyze(self):
            return low_coupling_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        coupling_issues = [
            i for i in result["issues"] if i["category"] == "coupling_density"
        ]
        assert len(coupling_issues) == 0

    @pytest.mark.asyncio
    async def test_combined_codeindex_and_topology(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test combining codeindex and topology issues."""
        async def mock_analyze(self):
            return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        codeindex_data = {
            "target_path": "test",
            "timestamp": "2026-01-01T00:00:00Z",
            "summary": {},
            "giant_functions": [
                {"path": "test.py", "function_name": "giant_func", "lines": 100}
            ],
        }

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze(codeindex_data=codeindex_data)

        # Should have issues from both sources
        god_function_issues = [
            i for i in result["issues"] if i["category"] == "god_function"
        ]
        # 1 from codeindex + 1 from topology
        assert len(god_function_issues) == 2

    @pytest.mark.asyncio
    async def test_overall_health_with_topology(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test overall health calculation includes topology score."""
        async def mock_analyze(self):
            return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology.TopologyAnalyzer, "analyze", mock_analyze)

        analyzer = DebtAnalyzer(client=mock_client)
        result = await analyzer.analyze()

        health = result["overall_health"]
        # Post-#59 fix: topology-source issues do NOT penalize quality_score;
        # they are already captured (graduated) by topology_score. The 5
        # topology issues leave quality untouched.
        # Quality = 100 (no static issues; no codeindex data)
        # Maintainability = 100 (default)
        # Topology = 75 (from mock — where the topology issues DO count)
        # Total = int(100 * 0.4 + 100 * 0.3 + 75 * 0.3) = int(92.5) = 92
        assert health["breakdown"]["quality"] == 100
        assert health["breakdown"]["maintainability"] == 100
        assert health["breakdown"]["topology"] == 75
        assert health["total_score"] == 92
        assert health["grade"] == "A"
        # Summary still lists ALL issues (topology ones aren't hidden, just
        # not double-counted into quality):
        assert health["summary"]["p0_issues"] >= 1

    @pytest.mark.asyncio
    async def test_module_filter_passed_to_topology(
        self, mock_client, mock_topology_result, monkeypatch
    ):
        """Test module filter is passed to TopologyAnalyzer."""
        captured_module = None

        class MockTopologyAnalyzer:
            def __init__(self, client, hub_threshold, god_threshold, module):
                nonlocal captured_module
                captured_module = module

            async def analyze(self):
                return mock_topology_result

        from loomgraph.core import topology

        monkeypatch.setattr(topology, "TopologyAnalyzer", MockTopologyAnalyzer)

        analyzer = DebtAnalyzer(client=mock_client)
        await analyzer.analyze(module="cli")

        assert captured_module == "cli"
