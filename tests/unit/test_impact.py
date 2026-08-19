"""Tests for impact analysis module.

TDD Green Phase: Tests now use actual implementation.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loomgraph.core.impact import (
    Caller,
    ChangedFile,
    ChangedSymbol,
    ChangedSymbolExtractor,
    ChangeType,
    GitDiffParser,
    ImpactAnalyzer,
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

    def test_run_codeindex_uses_venv_python_not_path(self) -> None:
        """#120/#76 regression: ``_run_codeindex`` must invoke codeindex via the
        venv python (``sys.executable -m codeindex.cli parse``), never a bare
        ``codeindex`` PATH lookup — otherwise a stale codeindex elsewhere on
        PATH (e.g. pipx) shadows the pinned ``ai-codeindex`` dep. Same class of
        bug as the graph-export PATH bypass (#76); this is the ``parse`` entry.
        """
        import sys

        from loomgraph.core.impact.extractor import ChangedSymbolExtractor

        captured: dict = {}
        fake_proc = MagicMock()
        fake_proc.returncode = 1  # short-circuit before json.loads
        fake_proc.stdout = ""
        fake_proc.stderr = ""

        def _fake_run(args, **kwargs):
            captured["args"] = args
            return fake_proc

        extractor = ChangedSymbolExtractor()
        with patch("loomgraph.core.impact.extractor.subprocess.run", _fake_run):
            extractor._run_codeindex(Path("src/a.py"))

        cmd = captured["args"]
        assert cmd[0] == sys.executable, (
            "must invoke codeindex via sys.executable (venv python), not a bare PATH lookup"
        )
        assert cmd[1:4] == ["-m", "codeindex.cli", "parse"]

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

    def test_low_resolution_empty_callers_is_unknown(self) -> None:
        """An empty traversal cannot prove isolation on a blind graph."""
        result = ImpactResult(
            commit="abc123",
            changed_symbols=[
                ChangedSymbol(
                    name="setupAlarmListener",
                    file="apps/mobile/service.ts",
                    change_type=ChangeType.MODIFIED,
                )
            ],
        )

        risk = RiskAssessor().assess(result, resolved_ratio=0.0175)

        assert risk.level == "unknown"
        assert "1.8%" in risk.reason
        assert "not establish" in risk.reason

    def test_sufficient_resolution_empty_callers_remains_low(self) -> None:
        """The trust guard does not change normal graph behavior."""
        result = ImpactResult(
            commit="abc123",
            changed_symbols=[
                ChangedSymbol(
                    name="helper",
                    file="src/helper.py",
                    change_type=ChangeType.MODIFIED,
                )
            ],
        )

        risk = RiskAssessor().assess(result, resolved_ratio=0.2)

        assert risk.level == "low"
        assert risk.reason == "Low risk: no callers found, isolated change"

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
    """Tests for impact analysis logic."""

    @pytest.mark.asyncio
    async def test_analyze_with_no_callers(self) -> None:
        """Test analyzing when no callers are found."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(return_value={"response": ""})

        analyzer = ImpactAnalyzer(
            store=mock_client,
            repo_path=Path("."),
        )

        # Mock git parser and extractor
        with patch.object(GitDiffParser, "get_changed_files_for_commit") as mock_git:
            mock_git.return_value = [
                ChangedFile(
                    path="src/test.py",
                    change_type=ChangeType.MODIFIED,
                    added_lines=[(10, 15)],
                )
            ]
            with (
                patch.object(GitDiffParser, "get_current_commit", return_value="abc1234"),
                patch.object(ChangedSymbolExtractor, "extract_from_files") as mock_extract,
            ):
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

    @pytest.mark.asyncio
    async def test_identify_affected_modules(self) -> None:
        """Test that affected modules are correctly identified."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(return_value={"response": ""})

        analyzer = ImpactAnalyzer(store=mock_client)

        modules = analyzer._identify_affected_modules(
            symbols=[
                ChangedSymbol(
                    name="func1",
                    file="src/auth/service.py",
                    change_type=ChangeType.MODIFIED,
                ),
                ChangedSymbol(
                    name="func2",
                    file="src/api/handler.py",
                    change_type=ChangeType.MODIFIED,
                ),
            ],
            direct_callers=[
                Caller(name="caller1", file="src/main.py"),
            ],
            indirect_callers=[],
        )

        assert "src.auth.service" in modules
        assert "src.api.handler" in modules
        assert "src.main" in modules

    @pytest.mark.asyncio
    async def test_identify_affected_tests(self) -> None:
        """Test that affected tests are correctly identified."""
        mock_client = MagicMock()
        mock_client.query = AsyncMock(return_value={"response": ""})

        analyzer = ImpactAnalyzer(store=mock_client)

        tests = analyzer._identify_affected_tests(
            direct_callers=[
                Caller(name="test_func", file="tests/test_service.py"),
                Caller(name="handler", file="src/handler.py"),
            ],
            indirect_callers=[
                Caller(name="test_integration", file="tests/integration/test_api.py"),
            ],
        )

        assert "tests/test_service.py" in tests
        assert "tests/integration/test_api.py" in tests
        assert "src/handler.py" not in tests


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
            resolution={
                "resolved_ratio": 0.0175,
                "caveat": "empty caller lists are inconclusive",
            },
        )

        data = result.to_dict()
        assert data["commit"] == "abc123"
        assert data["resolution"]["resolved_ratio"] == 0.0175
        assert len(data["changed_symbols"]) == 1
        assert data["impact_analysis"]["affected_modules"] == ["src.test", "src.main"]
        assert data["risk_assessment"]["level"] == "low"


class TestQueryCallersNameQualification:
    """#173: direct_callers always empty — name-format mismatch.

    `codeindex parse` returns bare / class-qualified names
    (``func`` or ``Class.method``) WITHOUT the module prefix, but the
    graph stores module-qualified ids (``src.pkg.mod.func`` /
    ``src.pkg.mod.Class.method``). `_query_callers` did an exact-equality
    match on the bare name, so it never matched → direct_callers=[] always.

    Fix (option 1 from #173, preserves #66's collision fix): qualify the
    changed symbol's name with its file's module path before querying —
    `_file_to_module(file) + "." + name` — matching exactly what
    graph-export emits. The indirect path already passes graph-sourced
    (qualified) names, so it's unaffected.
    """

    @pytest.mark.asyncio
    async def test_bare_function_name_resolves_against_qualified_id(
        self,
    ) -> None:
        """A top-level func's bare parse name must resolve to its
        module-qualified graph id.

        parse gives ``create_graph_store``; graph stores
        ``src.loomgraph.storage.factory.create_graph_store``. The qualifier
        built from ``file=src/loomgraph/storage/factory.py`` must bridge them.
        """
        store = MagicMock()
        # One CALLS edge: qualified tgt + qualified src (what the graph holds)
        store.get_all_relations = AsyncMock(
            return_value=[
                {
                    "src_id": "src.loomgraph.cli._common.prepare_workspace_store",
                    "tgt_id": "src.loomgraph.storage.factory.create_graph_store",
                    "keywords": "CALLS",
                    "source_id": "src/loomgraph/cli/_common.py:42",
                }
            ]
        )
        analyzer = ImpactAnalyzer(store=store, repo_path=Path("."))

        # Symbol as codeindex parse returns it: bare name + file
        direct, _ = await analyzer._find_callers(
            [
                ChangedSymbol(
                    name="create_graph_store",
                    file="src/loomgraph/storage/factory.py",
                    change_type=ChangeType.MODIFIED,
                )
            ]
        )

        assert len(direct) == 1
        assert direct[0].name == "src.loomgraph.cli._common.prepare_workspace_store"

    @pytest.mark.asyncio
    async def test_class_qualified_method_name_resolves(self) -> None:
        """A method's parse name (``Class.method``) resolves to
        ``module.Class.method`` — the file_to_module prefix is prepended
        whole, not per-dot-segment."""
        store = MagicMock()
        store.get_all_relations = AsyncMock(
            return_value=[
                {
                    "src_id": "src.app.bootstrap.run",
                    "tgt_id": "src.app.config.Config.load",
                    "keywords": "CALLS",
                    "source_id": "src/app/bootstrap.py:7",
                }
            ]
        )
        analyzer = ImpactAnalyzer(store=store, repo_path=Path("."))

        direct, _ = await analyzer._find_callers(
            [
                ChangedSymbol(
                    name="Config.load",  # parse gives Class.method, no module
                    file="src/app/config.py",
                    change_type=ChangeType.MODIFIED,
                )
            ]
        )

        assert len(direct) == 1
        assert direct[0].name == "src.app.bootstrap.run"

    @pytest.mark.asyncio
    async def test_non_python_file_falls_back_to_bare_name(self) -> None:
        """A non-.py file (file_to_module returns "") must not crash —
        falls back to the bare name (no match expected, but no exception)."""
        store = MagicMock()
        store.get_all_relations = AsyncMock(return_value=[])
        analyzer = ImpactAnalyzer(store=store, repo_path=Path("."))

        # Should not raise; returns empty
        direct, indirect = await analyzer._find_callers(
            [
                ChangedSymbol(
                    name="some_js_func",
                    file="src/app/utils.js",
                    change_type=ChangeType.MODIFIED,
                )
            ]
        )
        assert direct == [] and indirect == []

    @pytest.mark.asyncio
    async def test_indirect_callers_still_resolve_with_qualified_name(
        self,
    ) -> None:
        """The indirect path passes graph-sourced (already-qualified) caller
        names — it must NOT double-qualify. Regression guard: a qualified
        name fed back through _find_callers at depth>1 still resolves."""
        store = MagicMock()
        # Edge into the (already-qualified) direct caller
        store.get_all_relations = AsyncMock(
            return_value=[
                {
                    "src_id": "src.app.entry.main",
                    "tgt_id": "src.app.bootstrap.run",
                    "keywords": "CALLS",
                    "source_id": "src/app/entry.py:3",
                }
            ]
        )
        analyzer = ImpactAnalyzer(store=store, repo_path=Path("."), max_depth=2)

        # Feed an already-qualified name (as the indirect path does via direct.name)
        direct, indirect = await analyzer._find_callers(
            [
                ChangedSymbol(
                    name="src.app.bootstrap.run",  # qualified, no file needed
                    file="src/app/bootstrap.py",
                    change_type=ChangeType.MODIFIED,
                )
            ]
        )
        # qualified name as-is matches the qualified tgt_id
        assert len(direct) == 1
        assert direct[0].name == "src.app.entry.main"
