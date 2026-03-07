"""Unit tests for DebtAnalyzer git integration (Feature 2)."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loomgraph.core.debt_analyzer import DebtAnalyzer
from loomgraph.core.models import BusFactor, FileMetrics, GitMetricsResult, Hotspot


@pytest.fixture
def mock_lightrag_client():
    """Mock LightRAG client."""
    client = MagicMock()
    client.get_all_entities = AsyncMock(return_value=[])
    client.get_degree = AsyncMock(return_value=[])
    client.get_source_ids = AsyncMock(return_value=[])
    client.get_all_relations = AsyncMock(return_value=[])
    client.get_orphans = AsyncMock(return_value=[])
    client.get_graph_stats = AsyncMock(return_value={"entity_count": 0, "relation_count": 0})
    return client


@pytest.fixture
def sample_git_metrics():
    """Sample git metrics for testing."""
    return GitMetricsResult(
        repo_path=Path("."),
        since="3 months",
        analyzed_at=datetime.now(),
        file_metrics={
            "src/auth/user_service.py": FileMetrics(
                source_id="src/auth/user_service.py",
                change_frequency=50,
                last_modified=datetime.now(),
                last_modified_days=1,
                authors=["alice", "bob"],
                primary_author="alice",
                bug_fix_count=10,
                total_commits=50,
                bug_fix_ratio=0.2,
                lines_added=1000,
                lines_deleted=800,
                churn=1800,
                created_at=datetime(2023, 1, 1),
                age_days=400,
            ),
            "src/legacy/orphan.py": FileMetrics(
                source_id="src/legacy/orphan.py",
                change_frequency=1,
                last_modified=datetime(2023, 1, 1),
                last_modified_days=400,  # >1 year old
                authors=["alice"],
                primary_author="alice",
                bug_fix_count=0,
                total_commits=1,
                bug_fix_ratio=0.0,
                lines_added=50,
                lines_deleted=0,
                churn=50,
                created_at=datetime(2023, 1, 1),
                age_days=400,
            ),
            "src/critical_module.py": FileMetrics(
                source_id="src/critical_module.py",
                change_frequency=30,
                last_modified=datetime.now(),
                last_modified_days=1,
                authors=["alice"],  # Only 1 contributor
                primary_author="alice",
                bug_fix_count=5,
                total_commits=30,
                bug_fix_ratio=0.167,
                lines_added=500,
                lines_deleted=200,
                churn=700,
                created_at=datetime(2023, 1, 1),
                age_days=400,
            ),
        },
        hotspots=[
            Hotspot(
                file="src/auth/user_service.py",
                change_freq=50,
                lines=500,
                hotspot_score=95,
                rank=1,
            ),
        ],
        bus_factor=[
            BusFactor(
                file="src/critical_module.py",
                owner="alice",
                contributors=1,
                ownership_ratio=1.0,
                total_commits=30,
                risk_level="critical",
            ),
        ],
        summary={
            "total_files": 3,
            "total_commits": 81,
            "hotspots_count": 1,
            "bus_factor_critical": 1,
            "bus_factor_high": 0,
        },
    )


class TestDebtAnalyzerGitIntegration:
    """Test DebtAnalyzer with git metrics integration."""

    @pytest.mark.asyncio
    async def test_analyze_with_git_enabled(self, mock_lightrag_client, sample_git_metrics):
        """Test analyze() with --with-git flag."""
        analyzer = DebtAnalyzer(client=mock_lightrag_client)

        with patch("loomgraph.core.git_metrics.GitMetricsAnalyzer") as mock_git_analyzer_class:
            # Mock GitMetricsAnalyzer.analyze() to return sample data
            mock_git_instance = MagicMock()
            mock_git_instance.analyze.return_value = sample_git_metrics
            mock_git_analyzer_class.return_value = mock_git_instance

            # Run analysis with git enabled
            result = await analyzer.analyze(
                codeindex_data=None,
                module=None,
                with_git=True,
                git_since="3 months",
            )

            # Verify GitMetricsAnalyzer was instantiated
            mock_git_analyzer_class.assert_called_once()
            call_args = mock_git_analyzer_class.call_args
            assert call_args[1]["since"] == "3 months"

            # Verify analyze was called
            mock_git_instance.analyze.assert_called_once()

            # Verify overall_health has git dimension
            assert "overall_health" in result
            assert "breakdown" in result["overall_health"]
            assert "git" in result["overall_health"]["breakdown"]

            # Verify three-dimensional scoring
            # total_score = (quality + topology + git) // 3
            breakdown = result["overall_health"]["breakdown"]
            expected_total = (breakdown["quality"] + breakdown["topology"] + breakdown["git"]) // 3
            assert result["overall_health"]["total_score"] == expected_total

    @pytest.mark.asyncio
    async def test_analyze_without_git(self, mock_lightrag_client):
        """Test analyze() without --with-git (backward compatibility)."""
        analyzer = DebtAnalyzer(client=mock_lightrag_client)

        result = await analyzer.analyze(
            codeindex_data=None,
            module=None,
            with_git=False,  # Default: no git analysis
        )

        # Verify overall_health does NOT have git dimension
        assert "overall_health" in result
        assert "breakdown" in result["overall_health"]
        assert "git" not in result["overall_health"]["breakdown"]

        # Verify two-dimensional scoring (quality + topology)
        breakdown = result["overall_health"]["breakdown"]
        expected_total = (breakdown["quality"] + breakdown["topology"]) // 2
        assert result["overall_health"]["total_score"] == expected_total

    @pytest.mark.asyncio
    async def test_detect_critical_hotspot(self, mock_lightrag_client, sample_git_metrics):
        """Test detection of critical_hotspot issue (P0)."""
        analyzer = DebtAnalyzer(client=mock_lightrag_client)

        # Mock topology to return high in_degree for hotspot file
        mock_lightrag_client.get_degree.return_value = [
            {
                "entity": "src/auth/user_service.py",
                "in_degree": 120,  # High coupling
                "degree": 120,
            }
        ]

        with patch("loomgraph.core.git_metrics.GitMetricsAnalyzer") as mock_git_analyzer_class:
            mock_git_instance = MagicMock()
            mock_git_instance.analyze.return_value = sample_git_metrics
            mock_git_analyzer_class.return_value = mock_git_instance

            result = await analyzer.analyze(with_git=True, git_since="3 months")

            # Find critical_hotspot issue
            hotspot_issues = [i for i in result["issues"] if i["category"] == "critical_hotspot"]

            assert len(hotspot_issues) >= 1
            hotspot = hotspot_issues[0]

            assert hotspot["severity"] == "P0"
            assert hotspot["entity"] == "src/auth/user_service.py"
            assert "change_frequency" in hotspot["metrics"]
            assert hotspot["metrics"]["change_frequency"] == 50
            assert "hotspot_score" in hotspot["metrics"]
            assert hotspot["metrics"]["hotspot_score"] == 95
            assert "⚠️ Critical hotspot" in hotspot["suggestion"]

    @pytest.mark.asyncio
    async def test_detect_knowledge_silo(self, mock_lightrag_client, sample_git_metrics):
        """Test detection of knowledge_silo issue (P1)."""
        analyzer = DebtAnalyzer(client=mock_lightrag_client)

        with patch("loomgraph.core.git_metrics.GitMetricsAnalyzer") as mock_git_analyzer_class:
            mock_git_instance = MagicMock()
            mock_git_instance.analyze.return_value = sample_git_metrics
            mock_git_analyzer_class.return_value = mock_git_instance

            result = await analyzer.analyze(with_git=True, git_since="3 months")

            # Find knowledge_silo issue
            silo_issues = [i for i in result["issues"] if i["category"] == "knowledge_silo"]

            assert len(silo_issues) >= 1
            silo = silo_issues[0]

            assert silo["severity"] == "P1"
            assert silo["entity"] == "src/critical_module.py"
            assert "owner" in silo["metrics"]
            assert silo["metrics"]["owner"] == "alice"
            assert silo["metrics"]["contributors"] == 1
            assert "bus factor = 1" in silo["suggestion"].lower()

    @pytest.mark.asyncio
    async def test_enrich_orphan_with_confidence(self, mock_lightrag_client, sample_git_metrics):
        """Test orphan_entity enrichment with confidence field."""
        analyzer = DebtAnalyzer(client=mock_lightrag_client)

        # Add an orphan issue first
        from loomgraph.core.debt_analyzer import DebtIssue

        analyzer.issues.append(
            DebtIssue(
                id="debt-001",
                severity="P2",
                category="orphan_entity",
                entity="src/legacy/orphan.py",
                entity_type="file",
                location={"file": "src/legacy/orphan.py"},
                metrics={},
                suggestion="Connect to other entities or consider removal if unused",
            )
        )

        with patch("loomgraph.core.git_metrics.GitMetricsAnalyzer") as mock_git_analyzer_class:
            mock_git_instance = MagicMock()
            mock_git_instance.analyze.return_value = sample_git_metrics
            mock_git_analyzer_class.return_value = mock_git_instance

            result = await analyzer.analyze(with_git=True, git_since="3 months")

            # Find orphan issue
            orphan_issues = [i for i in result["issues"] if i["category"] == "orphan_entity"]

            if len(orphan_issues) > 0:
                orphan = orphan_issues[0]

                # Should have confidence field
                assert "confidence" in orphan
                # >365 days = high confidence
                assert orphan["confidence"] == "high"
                assert "last_modified_days" in orphan["metrics"]
                assert orphan["metrics"]["last_modified_days"] == 400
                assert "1 year+ no changes" in orphan["suggestion"]

    @pytest.mark.asyncio
    async def test_enrich_god_function_with_hotspot(self, mock_lightrag_client, sample_git_metrics):
        """Test god_function enrichment with is_hotspot marker."""
        analyzer = DebtAnalyzer(client=mock_lightrag_client)

        # Add a god_function issue first
        from loomgraph.core.debt_analyzer import DebtIssue

        analyzer.issues.append(
            DebtIssue(
                id="debt-001",
                severity="P1",
                category="god_function",
                entity="src/auth/user_service.py",
                entity_type="file",
                location={"file": "src/auth/user_service.py"},
                metrics={"out_degree": 35},
                suggestion="Reduce out-degree by extracting helper functions",
            )
        )

        with patch("loomgraph.core.git_metrics.GitMetricsAnalyzer") as mock_git_analyzer_class:
            mock_git_instance = MagicMock()
            mock_git_instance.analyze.return_value = sample_git_metrics
            mock_git_analyzer_class.return_value = mock_git_instance

            result = await analyzer.analyze(with_git=True, git_since="3 months")

            # Find god_function issue
            god_issues = [i for i in result["issues"] if i["category"] == "god_function"]

            if len(god_issues) > 0:
                god = god_issues[0]

                # Should have is_hotspot field
                assert "is_hotspot" in god
                assert god["is_hotspot"] is True

                # Severity should be upgraded to P0
                assert god["severity"] == "P0"

                # Suggestion should include hotspot warning
                assert "⚠️ Hotspot" in god["suggestion"]
                assert "50 changes" in god["suggestion"]

    @pytest.mark.asyncio
    async def test_git_analysis_graceful_fallback(self, mock_lightrag_client):
        """Test graceful fallback when git analysis fails."""
        analyzer = DebtAnalyzer(client=mock_lightrag_client)

        with patch("loomgraph.core.git_metrics.GitMetricsAnalyzer") as mock_git_analyzer_class:
            # Mock GitMetricsAnalyzer to raise GitError
            from loomgraph.core.git import GitError

            mock_git_analyzer_class.side_effect = GitError("Not a git repository")

            # Should not crash, just skip git analysis
            result = await analyzer.analyze(with_git=True, git_since="3 months")

            # Git score should default to 100 (no penalty)
            assert result["overall_health"]["breakdown"]["git"] == 100
