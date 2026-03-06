"""
Unit tests for DebtAnalyzer
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loomgraph.core.debt_analyzer import CodeindexData, DebtAnalyzer, DebtIssue


@pytest.fixture
def minimal_codeindex_data() -> dict:
    """Load minimal codeindex test fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "codeindex-minimal.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def real_codeindex_data() -> dict:
    """Load real codeindex v0.22.0 output fixture."""
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "codeindex-v0.22.0-output.json"
    )
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def analyzer() -> DebtAnalyzer:
    """Create DebtAnalyzer instance."""
    return DebtAnalyzer()


class TestCodeindexDataImport:
    """Test import_codeindex_data method."""

    def test_import_minimal_data(
        self, analyzer: DebtAnalyzer, minimal_codeindex_data: dict
    ):
        """Test importing minimal codeindex data."""
        result = analyzer.import_codeindex_data(minimal_codeindex_data)

        assert isinstance(result, CodeindexData)
        assert result.target_path == "/path/to/project/src"
        assert result.timestamp == "2026-03-06T21:38:48.660093Z"
        assert result.summary["total_files"] == 10
        assert len(result.giant_files) == 1
        assert len(result.giant_functions) == 2
        assert len(result.test_smells) == 3
        assert len(result.maintainability_scores) == 3
        assert len(result.file_reports) == 1

    def test_import_real_data(self, analyzer: DebtAnalyzer, real_codeindex_data: dict):
        """Test importing real codeindex v0.22.0 data."""
        result = analyzer.import_codeindex_data(real_codeindex_data)

        assert isinstance(result, CodeindexData)
        assert result.target_path == "/Users/dreamlinx/Dropbox/Projects/codeindex/tests"
        assert result.summary["total_files"] == 97
        assert len(result.giant_functions) == 3

    def test_fault_tolerant_missing_fields(self, analyzer: DebtAnalyzer):
        """Test fault-tolerant handling of missing fields."""
        raw_data = {
            "summary": {"total_files": 1},
            # Missing: target_path, timestamp, all arrays
        }

        result = analyzer.import_codeindex_data(raw_data)

        assert result.target_path == "."  # Default
        assert result.timestamp  # Generated timestamp
        assert result.giant_files == []
        assert result.giant_functions == []
        assert result.test_smells == []

    def test_empty_data(self, analyzer: DebtAnalyzer):
        """Test handling of completely empty data."""
        result = analyzer.import_codeindex_data({})

        assert isinstance(result, CodeindexData)
        assert result.target_path == "."
        assert result.summary == {}
        assert result.giant_files == []


class TestEnrichGiantFunctions:
    """Test _enrich_giant_functions method (complexity estimation)."""

    def test_estimate_complexity_from_lines(self, analyzer: DebtAnalyzer):
        """Test complexity estimation from lines."""
        functions = [
            {"path": "test.py", "function_name": "func1", "lines": 150},
            {"path": "test.py", "function_name": "func2", "lines": 95},
        ]

        result = analyzer._enrich_giant_functions(functions)

        assert result[0]["complexity"] == 15  # 150 // 10
        assert result[1]["complexity"] == 9  # 95 // 10

    def test_preserve_existing_complexity(self, analyzer: DebtAnalyzer):
        """Test that existing complexity is not overwritten."""
        functions = [
            {
                "path": "test.py",
                "function_name": "func1",
                "lines": 150,
                "complexity": 25,
            }
        ]

        result = analyzer._enrich_giant_functions(functions)

        assert result[0]["complexity"] == 25  # Original value preserved

    def test_skip_functions_without_lines(self, analyzer: DebtAnalyzer):
        """Test handling of functions without 'lines' field."""
        functions = [{"path": "test.py", "function_name": "func1"}]

        result = analyzer._enrich_giant_functions(functions)

        assert "complexity" not in result[0]

    def test_empty_list(self, analyzer: DebtAnalyzer):
        """Test handling of empty function list."""
        result = analyzer._enrich_giant_functions([])
        assert result == []


class TestNormalizeTestSmells:
    """Test _normalize_test_smells method (field name mapping)."""

    def test_normalize_skipped_test_with_line_number(self, analyzer: DebtAnalyzer):
        """Test normalizing skipped_test with line_number field."""
        smells = [
            {
                "path": "test.py",
                "type": "skipped_test",
                "line_number": 42,
                "details": "Skipped test",
            }
        ]

        result = analyzer._normalize_test_smells(smells)

        assert result[0]["line"] == 42
        assert result[0]["line_number"] == 42  # Original preserved

    def test_normalize_giant_test_with_lines(self, analyzer: DebtAnalyzer):
        """Test normalizing giant_test with lines field."""
        smells = [
            {
                "path": "test.py",
                "type": "giant_test",
                "lines": 1625,
                "details": "Test file too large",
            }
        ]

        result = analyzer._normalize_test_smells(smells)

        assert result[0]["line"] == 1625
        assert result[0]["lines"] == 1625  # Original preserved

    def test_preserve_original_fields(self, analyzer: DebtAnalyzer):
        """Test that original fields are preserved."""
        smells = [
            {
                "path": "test.py",
                "type": "skipped_test",
                "line_number": 120,
                "details": "Some details",
                "metric_value": None,
            }
        ]

        result = analyzer._normalize_test_smells(smells)

        assert result[0]["type"] == "skipped_test"
        assert result[0]["details"] == "Some details"
        assert result[0]["metric_value"] is None

    def test_empty_list(self, analyzer: DebtAnalyzer):
        """Test handling of empty smell list."""
        result = analyzer._normalize_test_smells([])
        assert result == []


class TestAggregateBreakdown:
    """Test aggregate_breakdown method."""

    def test_aggregate_from_file_reports(
        self, analyzer: DebtAnalyzer, minimal_codeindex_data: dict
    ):
        """Test aggregating breakdown from file_reports."""
        file_reports = minimal_codeindex_data["file_reports"]
        path = "src/services/UserService.ts"

        result = analyzer.aggregate_breakdown(file_reports, path)

        assert result["file_size_penalty"] == 1  # super_large_file
        assert result["comment_ratio_penalty"] == 0
        assert result["naming_violations"] == 0

    def test_aggregate_multiple_categories(self, analyzer: DebtAnalyzer):
        """Test aggregating multiple issue categories."""
        file_reports = [
            {
                "file_path": "test.py",
                "issues": [
                    {"category": "super_large_file", "severity": "critical"},
                    {"category": "low_comment_ratio", "severity": "medium"},
                    {"category": "naming_violation", "severity": "low"},
                    {"category": "naming_violation", "severity": "low"},
                ],
            }
        ]

        result = analyzer.aggregate_breakdown(file_reports, "test.py")

        assert result["file_size_penalty"] == 1
        assert result["comment_ratio_penalty"] == 1
        assert result["naming_violations"] == 2

    def test_file_not_found(self, analyzer: DebtAnalyzer):
        """Test handling of file not found in reports."""
        file_reports = [{"file_path": "other.py", "issues": []}]

        result = analyzer.aggregate_breakdown(file_reports, "notfound.py")

        assert result == {
            "file_size_penalty": 0,
            "comment_ratio_penalty": 0,
            "naming_violations": 0,
        }

    def test_empty_file_reports(self, analyzer: DebtAnalyzer):
        """Test handling of empty file_reports."""
        result = analyzer.aggregate_breakdown([], "test.py")

        assert result == {
            "file_size_penalty": 0,
            "comment_ratio_penalty": 0,
            "naming_violations": 0,
        }


class TestAnalyze:
    """Test analyze method (main entry point)."""

    @pytest.mark.asyncio
    async def test_analyze_with_minimal_data(
        self, analyzer: DebtAnalyzer, minimal_codeindex_data: dict
    ):
        """Test full analysis with minimal data."""
        result = await analyzer.analyze(codeindex_data=minimal_codeindex_data)

        assert result["schema_version"] == "1.0"
        assert result["timestamp"]
        assert result["project"] == "unknown"
        assert result["generator"]["tool"] == "loomgraph"

        # Check overall_health
        health = result["overall_health"]
        assert "total_score" in health
        assert "grade" in health
        assert health["summary"]["p0_issues"] >= 0

        # Check issues
        issues = result["issues"]
        assert len(issues) > 0
        assert all(issue["id"].startswith("debt-") for issue in issues)

    @pytest.mark.asyncio
    async def test_analyze_without_data(self, analyzer: DebtAnalyzer):
        """Test analysis without codeindex data."""
        result = await analyzer.analyze(codeindex_data=None)

        assert result["schema_version"] == "1.0"
        assert len(result["issues"]) == 0
        assert result["overall_health"]["total_score"] == 100  # Perfect score

    @pytest.mark.asyncio
    async def test_issue_generation_from_giant_files(
        self, analyzer: DebtAnalyzer, minimal_codeindex_data: dict
    ):
        """Test issue generation from giant_files."""
        await analyzer.analyze(codeindex_data=minimal_codeindex_data)

        giant_file_issues = [i for i in analyzer.issues if i.category == "god_class"]
        assert len(giant_file_issues) == 1
        assert giant_file_issues[0].severity == "P0"
        assert giant_file_issues[0].entity == "UserService.ts"
        assert giant_file_issues[0].metrics["lines"] == 2500

    @pytest.mark.asyncio
    async def test_issue_generation_from_giant_functions(
        self, analyzer: DebtAnalyzer, minimal_codeindex_data: dict
    ):
        """Test issue generation from giant_functions."""
        await analyzer.analyze(codeindex_data=minimal_codeindex_data)

        func_issues = [i for i in analyzer.issues if i.category == "god_function"]
        assert len(func_issues) == 2
        assert all(issue.severity == "P1" for issue in func_issues)
        assert func_issues[0].entity == "processComplexOrder"
        assert func_issues[0].metrics["complexity"] == 15  # Estimated: 150 // 10

    @pytest.mark.asyncio
    async def test_issue_generation_from_test_smells(
        self, analyzer: DebtAnalyzer, minimal_codeindex_data: dict
    ):
        """Test issue generation from test_smells."""
        await analyzer.analyze(codeindex_data=minimal_codeindex_data)

        smell_issues = [i for i in analyzer.issues if i.category == "test_smell"]
        assert len(smell_issues) == 3
        assert all(issue.severity == "P2" for issue in smell_issues)
        # Check normalized line field
        assert smell_issues[0].location["start_line"] == 1625  # giant_test
        assert smell_issues[1].location["start_line"] == 42  # skipped_test


class TestLookupMaintainability:
    """Test _lookup_maintainability helper method."""

    def test_lookup_existing_score(
        self, analyzer: DebtAnalyzer, minimal_codeindex_data: dict
    ):
        """Test looking up existing maintainability score."""
        data = analyzer.import_codeindex_data(minimal_codeindex_data)
        score = analyzer._lookup_maintainability(data, "src/services/UserService.ts")

        assert score == 3.0

    def test_lookup_missing_score(
        self, analyzer: DebtAnalyzer, minimal_codeindex_data: dict
    ):
        """Test looking up non-existent maintainability score."""
        data = analyzer.import_codeindex_data(minimal_codeindex_data)
        score = analyzer._lookup_maintainability(data, "nonexistent.py")

        assert score == 5.0  # Default mid-range


class TestCalculateOverallHealth:
    """Test _calculate_overall_health method."""

    def test_calculate_health_with_mixed_issues(self, analyzer: DebtAnalyzer):
        """Test health calculation with mixed severity issues."""
        analyzer.issues = [
            DebtIssue(
                id="debt-001",
                severity="P0",
                category="god_class",
                entity="Test",
                entity_type="class",
                location={},
                metrics={},
            ),
            DebtIssue(
                id="debt-002",
                severity="P1",
                category="god_function",
                entity="Test",
                entity_type="function",
                location={},
                metrics={},
            ),
            DebtIssue(
                id="debt-003",
                severity="P2",
                category="test_smell",
                entity="Test",
                entity_type="file",
                location={},
                metrics={},
            ),
        ]

        result = analyzer._calculate_overall_health(topology_score=100)

        # Quality = 100 - (1*10 + 1*5 + 1*1) = 84
        # Topology = 100 (passed in)
        # Total = (84 + 100) // 2 = 92
        assert result["total_score"] == 92
        assert result["grade"] == "A"
        assert result["breakdown"]["quality"] == 84
        assert result["breakdown"]["topology"] == 100
        assert result["summary"]["p0_issues"] == 1
        assert result["summary"]["p1_issues"] == 1
        assert result["summary"]["p2_issues"] == 1

    def test_calculate_health_with_no_issues(self, analyzer: DebtAnalyzer):
        """Test health calculation with no issues."""
        analyzer.issues = []

        result = analyzer._calculate_overall_health()

        assert result["total_score"] == 100
        assert result["grade"] == "A"
        assert result["summary"]["p0_issues"] == 0

    def test_grade_thresholds(self, analyzer: DebtAnalyzer):
        """Test all grade thresholds with multi-dimensional scoring."""
        test_cases = [
            (100, "A"),
            (90, "A"),
            (89, "B"),
            (80, "B"),
            (79, "C"),
            (70, "C"),
            (69, "D"),
            (60, "D"),
            (59, "F"),
            (0, "F"),
        ]

        for target_score, expected_grade in test_cases:
            # With topology_score=100 (perfect), total = (quality + 100) // 2
            # To get target_score, quality = 2*target_score - 100
            # quality = 100 - penalty → penalty = 100 - quality = 200 - 2*target_score
            quality_needed = 2 * target_score - 100
            penalty = 100 - quality_needed

            # Use P2 issues (penalty = 1 each)
            analyzer.issues = [
                DebtIssue(
                    id=f"debt-{i:03d}",
                    severity="P2",
                    category="test",
                    entity="Test",
                    entity_type="file",
                    location={},
                    metrics={},
                )
                for i in range(max(0, penalty))
            ]

            result = analyzer._calculate_overall_health(topology_score=100)
            assert (
                result["grade"] == expected_grade
            ), f"Target {target_score} (quality={quality_needed}) should be grade {expected_grade}, got {result['grade']} (total={result['total_score']})"


class TestIssueToDict:
    """Test _issue_to_dict helper method."""

    def test_convert_issue_to_dict(self, analyzer: DebtAnalyzer):
        """Test converting DebtIssue to dict."""
        issue = DebtIssue(
            id="debt-001",
            severity="P0",
            category="god_class",
            entity="UserService",
            entity_type="class",
            location={"file": "user.py", "start_line": 10},
            metrics={"lines": 2500, "complexity": 250},
            details={"reason": "Too large"},
            suggestion="Split into smaller classes",
            estimated_effort={"size": "large", "hours": "40-80"},
            references=["ADR-012"],
        )

        result = analyzer._issue_to_dict(issue)

        assert result["id"] == "debt-001"
        assert result["severity"] == "P0"
        assert result["category"] == "god_class"
        assert result["entity"] == "UserService"
        assert result["location"]["file"] == "user.py"
        assert result["metrics"]["lines"] == 2500
        assert result["suggestion"] == "Split into smaller classes"
