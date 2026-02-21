"""Impact analyzer using LightRAG knowledge graph.

Replaces the previous NL-query approach (asking LightRAG "What calls X?")
with deterministic graph traversal via get_all_relations() + get_all_entities().

Key improvement: zero LLM calls, instant and reliable results.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from loomgraph.core.impact.models import (
    Caller,
    ChangedSymbol,
    ImpactResult,
)
from loomgraph.core.impact.git_parser import GitDiffParser
from loomgraph.core.impact.extractor import ChangedSymbolExtractor
from loomgraph.core.impact.risk import RiskAssessor

if TYPE_CHECKING:
    from loomgraph.core.lightrag_client import LightRAGClient

logger = logging.getLogger(__name__)

@dataclass
class _EntityInfo:
    """Lightweight entity info extracted from LightRAG."""

    name: str
    file_path: str = ""
    line_start: int = 0


@dataclass
class ImpactAnalyzer:
    """Analyzes impact of code changes using knowledge graph.

    Uses graph traversal via LightRAG's get_all_relations() and
    get_all_entities() to find callers deterministically.
    No LLM queries, no NL parsing — just graph edges.
    """

    lightrag_client: "LightRAGClient"
    repo_path: Path = Path(".")
    max_depth: int = 2

    # Cached graph data (populated on first analysis)
    _caller_map: dict[str, list[str]] = field(default_factory=dict, repr=False)
    _entity_map: dict[str, _EntityInfo] = field(default_factory=dict, repr=False)
    _graph_loaded: bool = field(default=False, repr=False)

    async def _ensure_graph_loaded(self) -> None:
        """Load relations and entities from LightRAG into local maps."""
        if self._graph_loaded:
            return

        try:
            relations = await self.lightrag_client.get_all_relations()
            entities = await self.lightrag_client.get_all_entities()
        except Exception as e:
            logger.warning("Failed to load graph data: %s", e)
            self._graph_loaded = True
            return

        # Build caller map: target -> [callers]
        caller_map: dict[str, list[str]] = defaultdict(list)
        for rel in relations:
            keywords = rel.get("keywords", "") or rel.get("relation_type", "")
            if "CALLS" in str(keywords).upper():
                src = rel.get("src_id", "") or rel.get("source_entity", "")
                tgt = rel.get("tgt_id", "") or rel.get("target_entity", "")
                if src and tgt:
                    caller_map[tgt].append(src)
        self._caller_map = dict(caller_map)

        # Build entity map: name -> info
        for ent in entities:
            name = ent.get("entity_name", "") or ent.get("name", "")
            if not name:
                continue
            data = ent.get("entity_data", ent)
            self._entity_map[name] = _EntityInfo(
                name=name,
                file_path=data.get("file_path", "") or data.get("source_id", "").split(":")[0],
                line_start=int(data.get("line_start", 0) or 0),
            )

        self._graph_loaded = True
        logger.info(
            "Graph loaded: %d entities, %d caller edges",
            len(self._entity_map), sum(len(v) for v in self._caller_map.values()),
        )

    async def analyze_commit(self, commit: str = "HEAD") -> ImpactResult:
        """Analyze impact of a specific commit."""
        parser = GitDiffParser(repo_path=self.repo_path)
        changed_files = parser.get_changed_files_for_commit(commit)

        extractor = ChangedSymbolExtractor(repo_path=self.repo_path)
        changed_symbols = extractor.extract_from_files(changed_files)

        commit_hash = parser.get_current_commit() if commit == "HEAD" else commit[:7]
        return await self._build_result(commit_hash, changed_symbols)

    async def analyze_staged(self) -> ImpactResult:
        """Analyze impact of staged changes."""
        parser = GitDiffParser(repo_path=self.repo_path)
        changed_files = parser.get_staged_changes()

        extractor = ChangedSymbolExtractor(repo_path=self.repo_path)
        changed_symbols = extractor.extract_from_files(changed_files)

        return await self._build_result("staged", changed_symbols)

    async def analyze_branch_diff(
        self, base: str, head: str = "HEAD"
    ) -> ImpactResult:
        """Analyze impact of changes between two branches."""
        parser = GitDiffParser(repo_path=self.repo_path)
        changed_files = parser.get_branch_diff(base, head)

        extractor = ChangedSymbolExtractor(repo_path=self.repo_path)
        changed_symbols = extractor.extract_from_files(changed_files)

        return await self._build_result(f"{base}..{head}", changed_symbols)

    async def _build_result(
        self, commit: str, changed_symbols: list[ChangedSymbol]
    ) -> ImpactResult:
        """Build complete impact result with graph-based caller lookup."""
        await self._ensure_graph_loaded()

        direct_callers, indirect_callers = self._find_callers(changed_symbols)
        affected_modules = self._identify_affected_modules(
            changed_symbols, direct_callers, indirect_callers
        )
        affected_tests = self._identify_affected_tests(
            direct_callers, indirect_callers
        )

        result = ImpactResult(
            commit=commit,
            changed_symbols=changed_symbols,
            direct_callers=direct_callers,
            indirect_callers=indirect_callers,
            affected_modules=affected_modules,
            affected_tests=affected_tests,
        )

        # Auto-run risk assessment
        assessor = RiskAssessor()
        result.risk_assessment = assessor.assess(result)

        return result

    def _find_callers(
        self, symbols: list[ChangedSymbol]
    ) -> tuple[list[Caller], list[Caller]]:
        """Find direct and indirect callers via graph traversal.

        Uses the pre-loaded caller_map (built from CALLS relations)
        instead of sending NL queries to LightRAG.
        """
        direct_callers: list[Caller] = []
        indirect_callers: list[Caller] = []
        seen: set[str] = set()

        for symbol in symbols:
            # Look up callers of this symbol in the graph
            caller_names = self._caller_map.get(symbol.name, [])

            for caller_name in caller_names:
                info = self._entity_map.get(caller_name, _EntityInfo(name=caller_name))
                key = f"{info.file_path}:{caller_name}"
                if key in seen:
                    continue
                seen.add(key)
                direct_callers.append(Caller(
                    name=caller_name,
                    file=info.file_path,
                    line=info.line_start,
                    depth=1,
                ))

            # Indirect callers (depth 2+)
            if self.max_depth > 1:
                for direct in list(direct_callers):
                    indirect_names = self._caller_map.get(direct.name, [])
                    for ind_name in indirect_names:
                        info = self._entity_map.get(ind_name, _EntityInfo(name=ind_name))
                        key = f"{info.file_path}:{ind_name}"
                        if key in seen:
                            continue
                        seen.add(key)
                        indirect_callers.append(Caller(
                            name=ind_name,
                            file=info.file_path,
                            line=info.line_start,
                            depth=2,
                        ))

        return direct_callers, indirect_callers

    def _identify_affected_modules(
        self,
        symbols: list[ChangedSymbol],
        direct_callers: list[Caller],
        indirect_callers: list[Caller],
    ) -> list[str]:
        """Identify all affected modules."""
        modules: set[str] = set()
        for symbol in symbols:
            module = self._file_to_module(symbol.file)
            if module:
                modules.add(module)
        for caller in direct_callers + indirect_callers:
            module = self._file_to_module(caller.file)
            if module:
                modules.add(module)
        return sorted(modules)

    def _file_to_module(self, file_path: str) -> str:
        """Convert file path to module name."""
        if not file_path.endswith(".py"):
            return ""
        module = file_path[:-3].replace("/", ".").replace("\\", ".")
        return module.lstrip(".")

    def _identify_affected_tests(
        self,
        direct_callers: list[Caller],
        indirect_callers: list[Caller],
    ) -> list[str]:
        """Identify affected test files."""
        tests: set[str] = set()
        for caller in direct_callers + indirect_callers:
            if self._is_test_file(caller.file):
                tests.add(caller.file)
        return sorted(tests)

    def _is_test_file(self, file_path: str) -> bool:
        """Check if a file is a test file."""
        if not file_path:
            return False
        fp = file_path.replace("\\", "/")
        return (
            fp.startswith("tests/")
            or fp.startswith("test/")
            or "/tests/" in fp
            or "/test/" in fp
            or fp.endswith("_test.py")
            or "test_" in Path(fp).name
        )
