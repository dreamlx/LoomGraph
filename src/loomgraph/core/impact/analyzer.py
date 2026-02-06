"""Impact analyzer using LightRAG knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loomgraph.core.impact.models import (
    Caller,
    ChangedSymbol,
    ImpactResult,
)
from loomgraph.core.impact.git_parser import GitDiffParser
from loomgraph.core.impact.extractor import ChangedSymbolExtractor

if TYPE_CHECKING:
    from loomgraph.core.lightrag_client import LightRAGClient


@dataclass
class ImpactAnalyzer:
    """Analyzes impact of code changes using knowledge graph.

    Combines git diff parsing, symbol extraction, and graph queries
    to determine what parts of the codebase are affected by changes.
    """

    lightrag_client: "LightRAGClient"
    repo_path: Path = Path(".")
    max_depth: int = 2

    async def analyze_commit(self, commit: str = "HEAD") -> ImpactResult:
        """Analyze impact of a specific commit.

        Args:
            commit: Commit reference (default: HEAD)

        Returns:
            ImpactResult with all analysis data
        """
        # Parse git diff
        parser = GitDiffParser(repo_path=self.repo_path)
        changed_files = parser.get_changed_files_for_commit(commit)

        # Extract symbols
        extractor = ChangedSymbolExtractor(repo_path=self.repo_path)
        changed_symbols = extractor.extract_from_files(changed_files)

        # Get commit hash
        commit_hash = parser.get_current_commit() if commit == "HEAD" else commit[:7]

        # Query knowledge graph for callers
        direct_callers, indirect_callers = await self._find_callers(changed_symbols)

        # Identify affected modules
        affected_modules = self._identify_affected_modules(
            changed_symbols, direct_callers, indirect_callers
        )

        # Identify affected tests
        affected_tests = self._identify_affected_tests(direct_callers, indirect_callers)

        return ImpactResult(
            commit=commit_hash,
            changed_symbols=changed_symbols,
            direct_callers=direct_callers,
            indirect_callers=indirect_callers,
            affected_modules=affected_modules,
            affected_tests=affected_tests,
        )

    async def analyze_staged(self) -> ImpactResult:
        """Analyze impact of staged changes.

        Returns:
            ImpactResult with all analysis data
        """
        parser = GitDiffParser(repo_path=self.repo_path)
        changed_files = parser.get_staged_changes()

        extractor = ChangedSymbolExtractor(repo_path=self.repo_path)
        changed_symbols = extractor.extract_from_files(changed_files)

        direct_callers, indirect_callers = await self._find_callers(changed_symbols)
        affected_modules = self._identify_affected_modules(
            changed_symbols, direct_callers, indirect_callers
        )
        affected_tests = self._identify_affected_tests(direct_callers, indirect_callers)

        return ImpactResult(
            commit="staged",
            changed_symbols=changed_symbols,
            direct_callers=direct_callers,
            indirect_callers=indirect_callers,
            affected_modules=affected_modules,
            affected_tests=affected_tests,
        )

    async def analyze_branch_diff(
        self, base: str, head: str = "HEAD"
    ) -> ImpactResult:
        """Analyze impact of changes between two branches.

        Args:
            base: Base branch/commit
            head: Head branch/commit

        Returns:
            ImpactResult with all analysis data
        """
        parser = GitDiffParser(repo_path=self.repo_path)
        changed_files = parser.get_branch_diff(base, head)

        extractor = ChangedSymbolExtractor(repo_path=self.repo_path)
        changed_symbols = extractor.extract_from_files(changed_files)

        direct_callers, indirect_callers = await self._find_callers(changed_symbols)
        affected_modules = self._identify_affected_modules(
            changed_symbols, direct_callers, indirect_callers
        )
        affected_tests = self._identify_affected_tests(direct_callers, indirect_callers)

        return ImpactResult(
            commit=f"{base}..{head}",
            changed_symbols=changed_symbols,
            direct_callers=direct_callers,
            indirect_callers=indirect_callers,
            affected_modules=affected_modules,
            affected_tests=affected_tests,
        )

    async def _find_callers(
        self, symbols: list[ChangedSymbol]
    ) -> tuple[list[Caller], list[Caller]]:
        """Find direct and indirect callers using knowledge graph.

        Args:
            symbols: List of changed symbols

        Returns:
            Tuple of (direct_callers, indirect_callers)
        """
        direct_callers: list[Caller] = []
        indirect_callers: list[Caller] = []
        seen_callers: set[str] = set()

        for symbol in symbols:
            # Query LightRAG for callers
            callers_data = await self._query_callers(symbol.name, depth=1)

            for caller_data in callers_data:
                caller_key = f"{caller_data.get('file', '')}:{caller_data.get('name', '')}"
                if caller_key not in seen_callers:
                    seen_callers.add(caller_key)
                    direct_callers.append(
                        Caller(
                            name=caller_data.get("name", ""),
                            file=caller_data.get("file", ""),
                            line=caller_data.get("line", 0),
                            depth=1,
                        )
                    )

            # Find indirect callers if max_depth > 1
            if self.max_depth > 1:
                for direct in direct_callers:
                    indirect_data = await self._query_callers(
                        direct.name, depth=self.max_depth - 1
                    )
                    for caller_data in indirect_data:
                        caller_key = (
                            f"{caller_data.get('file', '')}:{caller_data.get('name', '')}"
                        )
                        if caller_key not in seen_callers:
                            seen_callers.add(caller_key)
                            indirect_callers.append(
                                Caller(
                                    name=caller_data.get("name", ""),
                                    file=caller_data.get("file", ""),
                                    line=caller_data.get("line", 0),
                                    depth=2,
                                )
                            )

        return direct_callers, indirect_callers

    async def _query_callers(self, symbol_name: str, depth: int = 1) -> list[dict]:
        """Query LightRAG for callers of a symbol.

        Args:
            symbol_name: Name of the symbol
            depth: Query depth

        Returns:
            List of caller dicts
        """
        try:
            # Use LightRAG graph query to find callers
            query = f"What functions or methods call {symbol_name}?"
            result = await self.lightrag_client.query(
                query=query,
                mode="local",  # Use local mode for relationship queries
            )

            # Parse the response to extract caller information
            # LightRAG returns natural language, we need to parse it
            return self._parse_caller_response(result)

        except Exception:
            # If query fails, return empty list
            return []

    def _parse_caller_response(self, response: str) -> list[dict]:
        """Parse LightRAG response to extract caller information.

        Args:
            response: Natural language response from LightRAG

        Returns:
            List of caller dicts
        """
        callers = []

        # Look for patterns like "FunctionName in file.py" or "ClassName.method"
        import re

        # Pattern: function/method names followed by location info
        patterns = [
            r"(\w+(?:\.\w+)*)\s+(?:in|from)\s+([^\s,]+\.py)",  # "func in file.py"
            r"([A-Z]\w+(?:\.\w+)+)",  # "ClassName.method"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, response)
            for match in matches:
                if isinstance(match, tuple):
                    name, file = match
                    callers.append({"name": name, "file": file, "line": 0})
                else:
                    callers.append({"name": match, "file": "", "line": 0})

        return callers

    def _identify_affected_modules(
        self,
        symbols: list[ChangedSymbol],
        direct_callers: list[Caller],
        indirect_callers: list[Caller],
    ) -> list[str]:
        """Identify all affected modules.

        Args:
            symbols: Changed symbols
            direct_callers: Direct callers
            indirect_callers: Indirect callers

        Returns:
            List of unique module paths
        """
        modules: set[str] = set()

        # Add modules from changed symbols
        for symbol in symbols:
            module = self._file_to_module(symbol.file)
            if module:
                modules.add(module)

        # Add modules from callers
        for caller in direct_callers + indirect_callers:
            module = self._file_to_module(caller.file)
            if module:
                modules.add(module)

        return sorted(modules)

    def _file_to_module(self, file_path: str) -> str:
        """Convert file path to module name.

        Args:
            file_path: Path to Python file

        Returns:
            Module name (e.g., "src.auth.service")
        """
        if not file_path.endswith(".py"):
            return ""

        # Remove .py extension and convert path separators
        module = file_path[:-3].replace("/", ".").replace("\\", ".")

        # Remove leading dots
        module = module.lstrip(".")

        return module

    def _identify_affected_tests(
        self,
        direct_callers: list[Caller],
        indirect_callers: list[Caller],
    ) -> list[str]:
        """Identify affected test files.

        Args:
            direct_callers: Direct callers
            indirect_callers: Indirect callers

        Returns:
            List of test file paths
        """
        tests: set[str] = set()

        for caller in direct_callers + indirect_callers:
            # Check if the caller is in a test file
            if self._is_test_file(caller.file):
                tests.add(caller.file)

        return sorted(tests)

    def _is_test_file(self, file_path: str) -> bool:
        """Check if a file is a test file.

        Args:
            file_path: Path to file

        Returns:
            True if it's a test file
        """
        if not file_path:
            return False

        # Common test file patterns
        return (
            file_path.startswith("tests/")
            or file_path.startswith("test/")
            or "/tests/" in file_path
            or "/test/" in file_path
            or file_path.endswith("_test.py")
            or "test_" in Path(file_path).name
        )
