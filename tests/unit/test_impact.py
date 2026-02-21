"""Tests for impact analysis module.

TDD Green Phase: Tests now use actual implementation.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from loomgraph.core.impact import (
    ImpactAnalyzer,
    GitDiffParser,
    ChangedSymbolExtractor,
    ChangeType,
    ChangedFile,
    ChangedSymbol,
    Caller,
    ImpactResult,
    RiskAssessment,
    RiskAssessor,
)


class TestGitDiffParser:
    """Tests for Git diff parsing."""

    def test_parse_commit_diff(self) -> None:
        """Test parsing a commit's diff output."""
        diff_output = """diff --git a/src/auth/service.py b/src/auth/service.py
index abc123..def456 100644
--- a/src/auth/service.py
+++ b/src/auth/service.py
@@ -45,1 +45,4 @@ class UserService:
-        return self._verify(username, password)
+        if not username:
+            raise ValueError("Username required")
+        return self._verify(username, password)
"""
        parser = GitDiffParser()
        result = parser._parse_diff(diff_output)

        assert len(result) == 1
        assert result[0].path == "src/auth/service.py"
        assert result[0].change_type == ChangeType.MODIFIED
        assert len(result[0].added_lines) == 1
        assert result[0].added_lines[0] == (45, 48)  # +45,4 means lines 45-48

    def test_parse_new_file(self) -> None:
        """Test parsing a new file diff."""
        diff_output = """diff --git a/src/new_file.py b/src/new_file.py
new file mode 100644
index 0000000..abc123
--- /dev/null
+++ b/src/new_file.py
@@ -0,0 +1,10 @@
+def hello():
+    pass
"""
        parser = GitDiffParser()
        result = parser._parse_diff(diff_output)

        assert len(result) == 1
        assert result[0].path == "src/new_file.py"
        assert result[0].change_type == ChangeType.ADDED
        assert len(result[0].added_lines) == 1
        assert result[0].added_lines[0] == (1, 10)

    def test_parse_deleted_file(self) -> None:
        """Test parsing a deleted file diff."""
        diff_output = """diff --git a/src/old_file.py b/src/old_file.py
deleted file mode 100644
index abc123..0000000
--- a/src/old_file.py
+++ /dev/null
@@ -1,5 +0,0 @@
-def old():
-    pass
"""
        parser = GitDiffParser()
        result = parser._parse_diff(diff_output)

        assert len(result) == 1
        assert result[0].path == "src/old_file.py"
        assert result[0].change_type == ChangeType.DELETED
        assert len(result[0].deleted_lines) == 1
        assert result[0].deleted_lines[0] == (1, 5)

    def test_parse_multiple_files(self) -> None:
        """Test parsing diff with multiple files."""
        diff_output = """diff --git a/file1.py b/file1.py
index abc..def 100644
--- a/file1.py
+++ b/file1.py
@@ -10,1 +10,2 @@
-old
+new1
+new2
diff --git a/file2.py b/file2.py
index abc..def 100644
--- a/file2.py
+++ b/file2.py
@@ -5,1 +5,1 @@
-old
+new
"""
        parser = GitDiffParser()
        result = parser._parse_diff(diff_output)

        assert len(result) == 2
        assert result[0].path == "file1.py"
        assert result[1].path == "file2.py"


class TestChangedSymbolExtractor:
    """Tests for extracting symbols from changed code."""

    def test_extract_from_modified_file(self) -> None:
        """Test extracting symbols from modified file."""
        file = ChangedFile(
            path="src/test.py",
            change_type=ChangeType.MODIFIED,
            added_lines=[(10, 15)],
            deleted_lines=[],
        )

        extractor = ChangedSymbolExtractor()

        # Mock codeindex output and file existence
        with patch.object(extractor, "_run_codeindex") as mock_codeindex:
            mock_codeindex.return_value = [
                {"name": "TestClass.method", "line_start": 8, "line_end": 20},
                {"name": "other_func", "line_start": 25, "line_end": 30},
            ]
            with patch.object(Path, "exists", return_value=True):
                symbols = extractor.extract_from_files([file])

        # Only TestClass.method overlaps with lines 10-15
        assert len(symbols) == 1
        assert symbols[0].name == "TestClass.method"
        assert symbols[0].change_type == ChangeType.MODIFIED

    def test_extract_from_new_file(self) -> None:
        """Test extracting symbols from a new file."""
        file = ChangedFile(
            path="src/new.py",
            change_type=ChangeType.ADDED,
            added_lines=[(1, 20)],
        )

        extractor = ChangedSymbolExtractor()

        with patch.object(extractor, "_run_codeindex") as mock_codeindex:
            mock_codeindex.return_value = [
                {"name": "NewClass", "line_start": 1, "line_end": 10},
                {"name": "new_func", "line_start": 12, "line_end": 18},
            ]
            with patch.object(Path, "exists", return_value=True):
                symbols = extractor.extract_from_files([file])

        # All symbols from new file should be extracted
        assert len(symbols) == 2
        assert all(s.change_type == ChangeType.ADDED for s in symbols)

    def test_extract_from_deleted_file(self) -> None:
        """Test extracting symbols from a deleted file."""
        file = ChangedFile(
            path="src/deleted.py",
            change_type=ChangeType.DELETED,
        )

        extractor = ChangedSymbolExtractor()
        symbols = extractor.extract_from_files([file])

        # Should return a placeholder for deleted files
        assert len(symbols) == 1
        assert symbols[0].change_type == ChangeType.DELETED
        assert "deleted" in symbols[0].name.lower()

    def test_skip_non_python_files(self) -> None:
        """Test that non-Python files are skipped."""
        file = ChangedFile(
            path="README.md",
            change_type=ChangeType.MODIFIED,
        )

        extractor = ChangedSymbolExtractor()
        symbols = extractor.extract_from_files([file])

        assert len(symbols) == 0


class TestRiskAssessor:
    """Tests for risk assessment logic."""

    def test_low_risk_single_caller(self) -> None:
        """Test low risk when symbol has few callers."""
        callers = [Caller(name="main", file="app.py")]

        assessor = RiskAssessor()
        risk = assessor.assess_from_callers(callers)

        assert risk.level == "low"
        assert "1" in risk.reason

    def test_medium_risk_multiple_callers(self) -> None:
        """Test medium risk when symbol has 3-9 callers."""
        callers = [
            Caller(name=f"func{i}", file=f"file{i}.py")
            for i in range(5)
        ]

        assessor = RiskAssessor()
        risk = assessor.assess_from_callers(callers)

        assert risk.level == "medium"
        assert "5" in risk.reason

    def test_high_risk_many_callers(self) -> None:
        """Test high risk when symbol has 10+ callers."""
        callers = [
            Caller(name=f"func{i}", file=f"file{i}.py")
            for i in range(12)
        ]

        assessor = RiskAssessor()
        risk = assessor.assess_from_callers(callers)

        assert risk.level == "high"
        assert "12" in risk.reason

    def test_high_risk_core_module(self) -> None:
        """Test high risk when changing core module (auth, payment)."""
        symbols = [
            ChangedSymbol(
                name="UserAuth.login",
                file="src/auth/service.py",
                change_type=ChangeType.MODIFIED,
            )
        ]

        result = ImpactResult(
            commit="abc123",
            changed_symbols=symbols,
            direct_callers=[],
            indirect_callers=[],
        )

        assessor = RiskAssessor()
        risk = assessor.assess(result)

        assert risk.level == "high"
        assert "auth" in risk.reason.lower()

    def test_suggestions_include_tests(self) -> None:
        """Test that suggestions include running tests."""
        result = ImpactResult(
            commit="abc123",
            changed_symbols=[
                ChangedSymbol(
                    name="func",
                    file="src/utils.py",
                    change_type=ChangeType.MODIFIED,
                )
            ],
            direct_callers=[],
            indirect_callers=[],
            affected_tests=["tests/test_utils.py"],
        )

        assessor = RiskAssessor()
        risk = assessor.assess(result)

        # Should suggest running affected tests
        assert any("test" in s.lower() for s in risk.suggestions)


class TestImpactAnalyzer:
    """Tests for graph-based impact analysis."""

    @pytest.mark.asyncio
    async def test_analyze_with_no_callers(self) -> None:
        """Test analyzing when no callers are found in the graph."""
        mock_client = MagicMock()
        mock_client.get_all_relations = AsyncMock(return_value=[])
        mock_client.get_all_entities = AsyncMock(return_value=[])

        analyzer = ImpactAnalyzer(
            lightrag_client=mock_client,
            repo_path=Path("."),
        )

        with patch.object(GitDiffParser, "get_changed_files_for_commit") as mock_git:
            mock_git.return_value = [
                ChangedFile(
                    path="src/test.py",
                    change_type=ChangeType.MODIFIED,
                    added_lines=[(10, 15)],
                )
            ]
            with patch.object(GitDiffParser, "get_current_commit", return_value="abc1234"):
                with patch.object(ChangedSymbolExtractor, "extract_from_files") as mock_extract:
                    mock_extract.return_value = [
                        ChangedSymbol(
                            name="test_func",
                            file="src/test.py",
                            change_type=ChangeType.MODIFIED,
                            lines_changed=5,
                        )
                    ]

                    result = await analyzer.analyze_commit("HEAD")

        assert result.commit == "abc1234"
        assert len(result.changed_symbols) == 1
        assert result.changed_symbols[0].name == "test_func"
        assert len(result.direct_callers) == 0
        # Risk assessment should be auto-populated
        assert result.risk_assessment is not None
        assert result.risk_assessment.level == "low"

    @pytest.mark.asyncio
    async def test_graph_based_caller_lookup(self) -> None:
        """Test that callers are found via graph relations, not NL queries."""
        mock_client = MagicMock()
        mock_client.get_all_relations = AsyncMock(return_value=[
            {"src_id": "handler.process", "tgt_id": "service.validate", "keywords": "CALLS"},
            {"src_id": "main.run", "tgt_id": "handler.process", "keywords": "CALLS"},
            {"src_id": "service.validate", "tgt_id": "utils.check", "keywords": "CALLS"},
        ])
        mock_client.get_all_entities = AsyncMock(return_value=[
            {"entity_name": "handler.process", "entity_data": {"file_path": "src/handler.py", "line_start": 10}},
            {"entity_name": "main.run", "entity_data": {"file_path": "src/main.py", "line_start": 5}},
            {"entity_name": "service.validate", "entity_data": {"file_path": "src/service.py", "line_start": 20}},
        ])

        analyzer = ImpactAnalyzer(
            lightrag_client=mock_client,
            repo_path=Path("."),
            max_depth=2,
        )

        with patch.object(GitDiffParser, "get_changed_files_for_commit") as mock_git:
            mock_git.return_value = [
                ChangedFile(path="src/service.py", change_type=ChangeType.MODIFIED, added_lines=[(20, 25)])
            ]
            with patch.object(GitDiffParser, "get_current_commit", return_value="def5678"):
                with patch.object(ChangedSymbolExtractor, "extract_from_files") as mock_extract:
                    mock_extract.return_value = [
                        ChangedSymbol(name="service.validate", file="src/service.py",
                                      change_type=ChangeType.MODIFIED, lines_changed=5)
                    ]
                    result = await analyzer.analyze_commit("HEAD")

        # handler.process calls service.validate -> direct caller
        assert len(result.direct_callers) == 1
        assert result.direct_callers[0].name == "handler.process"
        assert result.direct_callers[0].file == "src/handler.py"
        assert result.direct_callers[0].depth == 1

        # main.run calls handler.process -> indirect caller
        assert len(result.indirect_callers) == 1
        assert result.indirect_callers[0].name == "main.run"
        assert result.indirect_callers[0].depth == 2

        # No NL query should have been made
        mock_client.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_graph_data_cached(self) -> None:
        """Test that graph data is loaded only once (cached)."""
        mock_client = MagicMock()
        mock_client.get_all_relations = AsyncMock(return_value=[])
        mock_client.get_all_entities = AsyncMock(return_value=[])

        analyzer = ImpactAnalyzer(lightrag_client=mock_client, repo_path=Path("."))

        with patch.object(GitDiffParser, "get_changed_files_for_commit", return_value=[]):
            with patch.object(GitDiffParser, "get_current_commit", return_value="abc"):
                with patch.object(ChangedSymbolExtractor, "extract_from_files", return_value=[]):
                    await analyzer.analyze_commit("HEAD")
                    await analyzer.analyze_commit("HEAD")

        # get_all_relations should be called only once (cached)
        assert mock_client.get_all_relations.call_count == 1


class TestImpactModels:
    """Tests for impact data models."""

    def test_changed_file_to_dict(self) -> None:
        """Test ChangedFile serialization."""
        file = ChangedFile(
            path="src/test.py",
            change_type=ChangeType.MODIFIED,
            added_lines=[(1, 5)],
            deleted_lines=[(10, 12)],
        )

        data = file.to_dict()
        assert data["path"] == "src/test.py"
        assert data["change_type"] == "modified"
        assert data["added_lines"] == [(1, 5)]

    def test_changed_symbol_to_dict(self) -> None:
        """Test ChangedSymbol serialization."""
        symbol = ChangedSymbol(
            name="TestClass.method",
            file="src/test.py",
            change_type=ChangeType.ADDED,
            lines_changed=10,
        )

        data = symbol.to_dict()
        assert data["name"] == "TestClass.method"
        assert data["change_type"] == "added"
        assert data["lines_changed"] == 10

    def test_impact_result_to_dict(self) -> None:
        """Test ImpactResult serialization."""
        result = ImpactResult(
            commit="abc123",
            changed_symbols=[
                ChangedSymbol(
                    name="func",
                    file="src/test.py",
                    change_type=ChangeType.MODIFIED,
                )
            ],
            direct_callers=[
                Caller(name="caller", file="src/main.py"),
            ],
            affected_modules=["src.test", "src.main"],
            affected_tests=["tests/test_main.py"],
            risk_assessment=RiskAssessment(
                level="low",
                reason="Limited impact",
                suggestions=["Run unit tests"],
            ),
        )

        data = result.to_dict()
        assert data["commit"] == "abc123"
        assert len(data["changed_symbols"]) == 1
        assert data["impact_analysis"]["affected_modules"] == ["src.test", "src.main"]
        assert data["risk_assessment"]["level"] == "low"
