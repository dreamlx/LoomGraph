"""
Technical Debt Analyzer

Integrates codeindex static analysis data with LoomGraph graph topology
to provide multi-dimensional technical debt scoring.

Responsibility:
- Import and normalize codeindex JSON output (fault-tolerant)
- Estimate complexity from lines (inference layer)
- Aggregate detailed breakdown from file_reports (aggregation layer)
- Calculate multi-dimensional scores (maintainability, testability, impact, coupling)
- Generate debt reports in JSON/Markdown/Console formats
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loomgraph import __version__
from loomgraph.storage.base import GraphStore

logger = logging.getLogger(__name__)

# God Function Domain Complexity Whitelist (v0.9.2)
# These patterns identify functions with inherent domain complexity,
# not code quality issues. Matches are downgraded from P0 → P1 warning.
GOD_FUNCTION_WHITELIST_PATTERNS = (
    # Parser domain (tree-sitter traversal requires extensive branching)
    r".*Parser\.visit_.*",
    r".*Parser\._parse_.*",
    r".*Parser\._extract_.*",
    # Code generators (string template accumulation)
    r".*\.generate_.*",
    r".*\.render_.*",
    r".*\.format_.*_output",
    r".*\.format_.*_report",
    # CLI commands (exception handling chains + user interaction)
    r".*Command\.execute",
    r".*CLI\._handle_.*",
    r".*\.main$",  # Main entry points are typically orchestration
    # Build/packaging scripts (sequential steps)
    r".*\.package_.*",
    r".*\.build_.*",
)


@dataclass
class CodeindexData:
    """Normalized codeindex output data.

    This class represents the imported and normalized data from codeindex,
    with fault-tolerant defaults for missing fields.
    """

    target_path: str
    timestamp: str
    summary: dict[str, Any]
    giant_files: list[dict[str, Any]] = field(default_factory=list)
    giant_functions: list[dict[str, Any]] = field(default_factory=list)
    test_smells: list[dict[str, Any]] = field(default_factory=list)
    maintainability_scores: list[dict[str, Any]] = field(default_factory=list)
    file_reports: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DebtIssue:
    """Represents a single technical debt issue.

    Maps to the 'issues' array in the debt report format.
    """

    id: str  # debt-001, debt-002, ...
    severity: str  # P0, P1, P2
    category: str  # god_class, god_function, etc.
    entity: str
    entity_type: str  # class, function, module, file
    location: dict[str, Any]
    metrics: dict[str, Any]
    details: dict[str, Any] = field(default_factory=dict)
    suggestion: str = ""
    estimated_effort: dict[str, str] = field(default_factory=dict)
    references: list[str] = field(default_factory=list)
    # Which analysis dimension produced this issue. Only "static" issues
    # feed quality_score — "topology"/"git" issues have their own graduated
    # dimensions (topology_score / git_score), so counting them in
    # quality_score too would double-penalize (see #59).
    source: str = "static"  # static | topology | git
    # EPIC-010 Feature 2: Git enrichment fields
    confidence: str | None = None  # high/medium/low for orphan entities
    is_hotspot: bool | None = None  # True if god_function + high change_freq


class DebtAnalyzer:
    """
    Technical Debt Analyzer

    Combines codeindex static analysis with LoomGraph graph topology
    to provide comprehensive technical debt analysis.

    Usage:
        from loomgraph.storage import create_graph_store

        store = await create_graph_store(workspace="myproj")
        analyzer = DebtAnalyzer(client=store)
        result = await analyzer.analyze(codeindex_data=codeindex_json)
    """

    def __init__(self, client: GraphStore | None = None) -> None:
        """Initialize DebtAnalyzer.

        Args:
            client: Optional GraphStore for topology analysis.
                   If None, topology analysis will be skipped.
        """
        self.client = client
        self.issues: list[DebtIssue] = []
        # Entity count from the topology run; feeds summary.total_entities (#60)
        self._topology_total_entities: int = 0

    @staticmethod
    def _is_whitelisted_god_function(entity_name: str) -> bool:
        """Check if a god function matches domain complexity patterns.

        Args:
            entity_name: Full entity name (e.g., "PythonParser.visit_module")

        Returns:
            True if the function is whitelisted (domain complexity, not debt)
        """
        return any(
            re.match(pattern, entity_name)
            for pattern in GOD_FUNCTION_WHITELIST_PATTERNS
        )

    def import_codeindex_data(self, raw_data: dict[str, Any]) -> CodeindexData:
        """
        Import and normalize codeindex JSON output.

        Responsibility:
        - Fault-tolerant: provides defaults for missing fields
        - Enrichment: estimates complexity from lines
        - Normalization: unifies test_smells field names

        Args:
            raw_data: Raw JSON output from codeindex tech-debt command

        Returns:
            Normalized CodeindexData object
        """
        # Fault-tolerant extraction with defaults
        target_path = raw_data.get("target_path", ".")
        timestamp = raw_data.get("timestamp", datetime.now(UTC).isoformat())
        summary = raw_data.get("summary", {})

        # Extract arrays (empty list as default)
        giant_files = raw_data.get("giant_files", [])
        giant_functions = raw_data.get("giant_functions", [])
        test_smells = raw_data.get("test_smells", [])
        maintainability_scores = raw_data.get("maintainability_scores", [])
        file_reports = raw_data.get("file_reports", [])

        # Enrich giant_functions: estimate complexity from lines
        giant_functions = self._enrich_giant_functions(giant_functions)

        # Normalize test_smells: unify field names
        test_smells = self._normalize_test_smells(test_smells)

        return CodeindexData(
            target_path=target_path,
            timestamp=timestamp,
            summary=summary,
            giant_files=giant_files,
            giant_functions=giant_functions,
            test_smells=test_smells,
            maintainability_scores=maintainability_scores,
            file_reports=file_reports,
        )

    def _apply_scope(self, data: CodeindexData, scope: str) -> CodeindexData:
        """Filter codeindex lists to a path prefix (--scope, #61).

        Excludes docs/scripts/tests/etc. from the static debt layer so they
        don't inflate giant_files / test_smells / file_reports.
        """
        prefix = scope.strip().rstrip("/")
        if not prefix:
            return data

        def in_scope(p: str) -> bool:
            return p == prefix or p.startswith(prefix + "/")

        data.giant_files = [d for d in data.giant_files if in_scope(d.get("path", ""))]
        data.giant_functions = [
            d for d in data.giant_functions if in_scope(d.get("path", ""))
        ]
        data.test_smells = [d for d in data.test_smells if in_scope(d.get("path", ""))]
        data.file_reports = [
            d for d in data.file_reports if in_scope(d.get("file_path", ""))
        ]
        return data

    def _enrich_giant_functions(
        self, functions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Estimate complexity from lines.

        Responsibility: LoomGraph inference layer
        - codeindex provides: lines (raw data)
        - LoomGraph estimates: complexity (inference)

        Formula: complexity ≈ lines // 10
        (Heuristic: 10 lines per decision point on average)
        """
        enriched = []
        for func in functions:
            func_copy = func.copy()
            if "complexity" not in func_copy and "lines" in func_copy:
                # Estimation formula
                func_copy["complexity"] = func_copy["lines"] // 10
            enriched.append(func_copy)
        return enriched

    def _normalize_test_smells(
        self, smells: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Normalize test_smells field names.

        Responsibility: Field name mapping
        - codeindex uses: line_number (行号) for skipped_test
        - codeindex uses: lines (行数) for giant_test
        - LoomGraph normalizes: both to 'line' field for consistency
        """
        normalized = []
        for smell in smells:
            smell_copy = smell.copy()
            # Preserve original fields, add normalized 'line' field
            if "line_number" in smell_copy:
                smell_copy["line"] = smell_copy["line_number"]
            elif "lines" in smell_copy:
                smell_copy["line"] = smell_copy["lines"]
            normalized.append(smell_copy)
        return normalized

    def aggregate_breakdown(
        self, file_reports: list[dict[str, Any]], path: str
    ) -> dict[str, int]:
        """
        Aggregate detailed breakdown from file_reports.

        Responsibility: LoomGraph aggregation layer
        - codeindex provides: file_reports (raw issue list)
        - LoomGraph aggregates: breakdown (penalty breakdown)

        Args:
            file_reports: Complete issue list from codeindex
            path: File path to aggregate breakdown for

        Returns:
            Detailed breakdown dict with penalty counts
        """
        # Find file report for this path
        file_report = next(
            (r for r in file_reports if r.get("file_path") == path), None
        )

        if not file_report:
            return {
                "file_size_penalty": 0,
                "comment_ratio_penalty": 0,
                "naming_violations": 0,
            }

        issues = file_report.get("issues", [])

        # Count issues by category
        breakdown = {
            "file_size_penalty": sum(
                1
                for issue in issues
                if issue.get("category")
                in ("super_large_file", "large_file", "medium_large_file")
            ),
            "comment_ratio_penalty": sum(
                1 for issue in issues if issue.get("category") == "low_comment_ratio"
            ),
            "naming_violations": sum(
                1 for issue in issues if issue.get("category") == "naming_violation"
            ),
        }

        return breakdown

    async def analyze(
        self,
        codeindex_data: dict[str, Any] | None = None,
        module: str | None = None,
        with_git: bool = False,
        git_since: str = "3 months",
        scope: str | None = None,
    ) -> dict[str, Any]:
        """
        Main analysis entry point.

        Combines codeindex static analysis with LoomGraph graph topology
        and optionally git history metrics (EPIC-010 Feature 2).

        Args:
            codeindex_data: Optional codeindex JSON output
            module: Optional module filter for topology analysis (e.g. "cli")
            with_git: Enable git metrics analysis (default: False)
            git_since: Time window for git analysis (default: "3 months")
            scope: Optional absolute path-prefix filter (e.g. "src/") — limits
                both the codeindex static layer and topology to production source,
                excluding docs/scripts/tests. Wins over module (#61).

        Returns:
            Debt report in standardized format (ADR-012)
        """
        # Step 1: Import codeindex data (if provided)
        imported_data = None
        if codeindex_data:
            imported_data = self.import_codeindex_data(codeindex_data)

        # Step 1.5: Apply --scope path-prefix filter to the static layer (#61)
        if scope and imported_data:
            imported_data = self._apply_scope(imported_data, scope)

        # Step 2: Analyze issues from codeindex data
        if imported_data:
            await self._analyze_codeindex_issues(imported_data)

        # Step 3: Analyze graph topology (if client available)
        topology_score = 100  # Default perfect score
        if self.client:
            topology_score = await self._analyze_topology_issues(
                module=module, scope=scope
            )

        # Step 3.5: Analyze git history (EPIC-010 Feature 2)
        git_score = 100  # Default perfect score (no git penalties)
        if with_git:
            try:
                from loomgraph.core.git_metrics import GitMetricsAnalyzer

                analyzer = GitMetricsAnalyzer(Path.cwd(), since=git_since)
                git_metrics = analyzer.analyze()
                git_score = self._analyze_git_issues(git_metrics)
                self._enrich_with_git_metrics(git_metrics)
            except Exception as e:
                # Graceful fallback: non-git projects or git errors
                logger.warning(f"Git analysis failed, skipping: {e}")
                git_score = 100  # No penalty

        # Step 4: Calculate maintainability score from codeindex
        maintainability_score = self._calculate_maintainability_score(imported_data)

        # Step 5: Calculate overall health (multi-dimensional)
        overall_health = self._calculate_overall_health(
            topology_score=topology_score,
            git_score=git_score if with_git else None,
            maintainability_score=maintainability_score,
        )

        # Step 5.5: Auto-save metrics snapshot for trend analysis (EPIC-010 Feature 3)
        self._save_metrics_snapshot(
            entity="project",  # Project-level snapshot
            overall_health=overall_health,
        )

        # Step 6: Generate report
        return {
            "schema_version": "1.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "project": "unknown",  # TODO: detect from workspace
            "generator": {
                "tool": "loomgraph",
                "version": __version__,
            },
            "overall_health": overall_health,
            "issues": [self._issue_to_dict(issue) for issue in self.issues],
            "recommendations": [],  # TODO: generate recommendations
        }

    async def _analyze_codeindex_issues(self, data: CodeindexData) -> None:
        """
        Analyze issues from codeindex data.

        Converts codeindex findings into DebtIssue objects.
        """
        issue_id_counter = 1

        # Analyze giant_files
        for file_data in data.giant_files:
            self.issues.append(
                DebtIssue(
                    id=f"debt-{issue_id_counter:03d}",
                    severity="P0" if file_data.get("severity") == "critical" else "P1",
                    category="god_class",  # Simplification: large file ~ god class
                    entity=file_data["path"].split("/")[-1],
                    entity_type="file",
                    location={"file": file_data["path"], "start_line": 1},
                    metrics={
                        "lines": file_data["lines"],
                        "maintainability_score": self._lookup_maintainability(
                            data, file_data["path"]
                        ),
                        "total_score": 0,  # TODO: calculate
                    },
                    suggestion="Consider splitting into multiple files",
                )
            )
            issue_id_counter += 1

        # Analyze giant_functions
        for func_data in data.giant_functions:
            self.issues.append(
                DebtIssue(
                    id=f"debt-{issue_id_counter:03d}",
                    severity="P1",
                    category="god_function",
                    entity=func_data["function_name"],
                    entity_type="function",
                    location={"file": func_data["path"]},
                    metrics={
                        "lines": func_data["lines"],
                        "complexity": func_data.get("complexity", 0),
                        "total_score": 0,
                    },
                    suggestion="Refactor into smaller functions",
                )
            )
            issue_id_counter += 1

        # Analyze test_smells
        for smell_data in data.test_smells:
            self.issues.append(
                DebtIssue(
                    id=f"debt-{issue_id_counter:03d}",
                    severity="P2",
                    category="test_smell",
                    entity=smell_data["path"].split("/")[-1],
                    entity_type="file",
                    location={
                        "file": smell_data["path"],
                        "start_line": smell_data.get("line", 0),
                    },
                    metrics={},
                    details={"smell_type": smell_data["type"]},
                    suggestion=f"Fix {smell_data['type']}",
                )
            )
            issue_id_counter += 1

    async def _analyze_topology_issues(
        self, module: str | None = None, scope: str | None = None
    ) -> int:
        """
        Analyze graph topology for structural code smells.

        Converts topology analysis results into DebtIssue objects.

        Args:
            module: Optional module filter (e.g. "cli" for src/cli/)

        Returns:
            Topology score (0-100)
        """
        from loomgraph.core.topology import TopologyAnalyzer

        analyzer = TopologyAnalyzer(
            client=self.client,
            hub_threshold=8,
            god_threshold=10,
            module=module,
            scope=scope,
        )
        result = await analyzer.analyze()

        issue_id_counter = len(self.issues) + 1

        # Convert orphan entities to issues. #154: only truly-isolated
        # orphans are P1; "neighbors_unresolved" means edges exist but
        # resolution failed (Java DI / TS alias blind spots) — that is a
        # resolution-quality signal, not dead-code evidence, so P2.
        for orphan in result.orphans:
            unresolved = orphan.get("reason") == "neighbors_unresolved"
            self.issues.append(
                DebtIssue(
                    id=f"debt-{issue_id_counter:03d}",
                    severity="P2" if unresolved else "P1",
                    category="orphan_entity",
                    source="topology",
                    entity=orphan.get("entity", orphan.get("entity_name", "unknown")),
                    entity_type=orphan.get("type", orphan.get("entity_type", "unknown")),
                    location={
                        "file": orphan.get("source_id", "unknown"),
                    },
                    metrics={
                        "in_degree": orphan.get("in_degree", 0),
                        "out_degree": orphan.get("out_degree", 0),
                    },
                    confidence="low" if unresolved else "medium",
                    suggestion=(
                        "Edges exist but none resolved — likely an edge-resolution "
                        "blind spot (dynamic dispatch / DI receiver), not dead code; "
                        "check resolved_ratio before acting"
                        if unresolved
                        else "Connect to other entities or consider removal if unused"
                    ),
                )
            )
            issue_id_counter += 1

        # Convert hubs to issues (P1 - fragility risk)
        for hub in result.hubs:
            self.issues.append(
                DebtIssue(
                    id=f"debt-{issue_id_counter:03d}",
                    severity="P1",
                    category="hub_fragility",
                    source="topology",
                    entity=hub.get("entity", hub.get("entity_name", "unknown")),
                    entity_type=hub.get("type", hub.get("entity_type", "unknown")),
                    location={
                        "file": hub.get("source_id", "unknown"),
                    },
                    metrics={
                        "in_degree": hub.get("in_degree", 0),
                    },
                    suggestion="High fan-in creates fragility; consider splitting responsibilities",
                )
            )
            issue_id_counter += 1

        # Convert god functions to issues (P0 or P1 based on domain)
        for god in result.god_functions:
            entity_name = god.get("entity", god.get("entity_name", "unknown"))

            # Check if this is domain complexity (not technical debt)
            is_domain_complexity = self._is_whitelisted_god_function(entity_name)

            # Downgrade domain complexity to P1 warning
            severity = "P1" if is_domain_complexity else "P0"
            suggestion = "High fan-out indicates excessive responsibility; refactor into smaller functions"

            if is_domain_complexity:
                suggestion = (
                    "Domain complexity (Parser/Generator/CLI). "
                    "Refactoring can improve readability but is not critical."
                )

            self.issues.append(
                DebtIssue(
                    id=f"debt-{issue_id_counter:03d}",
                    severity=severity,
                    category="god_function",
                    source="topology",
                    entity=entity_name,
                    entity_type=god.get("type", god.get("entity_type", "function")),
                    location={
                        "file": god.get("source_id", "unknown"),
                    },
                    metrics={
                        "out_degree": god.get("out_degree", 0),
                    },
                    suggestion=suggestion,
                    details={"is_domain_complexity": is_domain_complexity},
                )
            )
            issue_id_counter += 1

        # Convert placeholder modules to issues (P2 - maintenance burden)
        for placeholder in result.placeholder_modules:
            self.issues.append(
                DebtIssue(
                    id=f"debt-{issue_id_counter:03d}",
                    severity="P2",
                    category="placeholder_module",
                    source="topology",
                    entity=placeholder.get("entity", placeholder.get("entity_name", "unknown")),
                    entity_type="module",
                    location={
                        "file": placeholder.get("source_id", "unknown"),
                    },
                    metrics={
                        "entity_count": placeholder.get("entity_count", 0),
                    },
                    suggestion="Low entity count suggests incomplete or placeholder module",
                )
            )
            issue_id_counter += 1

        # Convert coupling density to issue if high (P1)
        if result.coupling.density > 0.5:
            most_coupled = result.coupling.most_coupled_pairs[:3]  # Top 3
            self.issues.append(
                DebtIssue(
                    id=f"debt-{issue_id_counter:03d}",
                    severity="P1",
                    category="coupling_density",
                    source="topology",
                    entity="cross-module",
                    entity_type="system",
                    location={},
                    metrics={
                        "density": result.coupling.density,
                        "cross_module_relations": result.coupling.cross_module,
                        "intra_module_relations": result.coupling.intra_module,
                    },
                    details={
                        "most_coupled_pairs": most_coupled,
                    },
                    suggestion=f"High coupling density ({result.coupling.density:.2f}); consider architectural refactoring",
                )
            )

        self._topology_total_entities = result.total_entities
        return result.topology_score

    def _lookup_maintainability(self, data: CodeindexData, path: str) -> float:
        """Lookup maintainability score from codeindex data."""
        for score_data in data.maintainability_scores:
            if score_data["path"] == path:
                return score_data["score"]
        return 5.0  # Default mid-range score

    def _calculate_maintainability_score(
        self, data: CodeindexData | None
    ) -> float | None:
        """Calculate aggregated maintainability score from codeindex data.

        Args:
            data: Imported codeindex data (None if not provided)

        Returns:
            Maintainability score (0-100), or None when no data flowed in —
            vacuous perfection is misleading (#153 提案 2): a missing
            dimension is reported as null and excluded from the weighted
            total, never as a perfect 100.
        """
        if not data or not data.maintainability_scores:
            return None

        # Aggregate: average of all file maintainability scores
        scores = [item["score"] for item in data.maintainability_scores]
        avg_score = sum(scores) / len(scores)

        # Normalize: codeindex uses 0-10 scale, convert to 0-100
        return avg_score * 10.0

    def _calculate_overall_health(
        self,
        topology_score: int = 100,
        git_score: int | None = None,
        maintainability_score: float | None = None,
    ) -> dict[str, Any]:
        """Calculate overall health score from issues.

        Args:
            topology_score: Topology health score from TopologyAnalyzer (0-100)
            git_score: Git metrics health score (0-100), None if --with-git not enabled
            maintainability_score: Aggregated maintainability from codeindex
                (0-100), None when no codeindex data flowed in

        Returns:
            Overall health dict with breakdown by dimension. Missing
            dimensions are reported as null and their weight is
            redistributed (#153 提案 2 — no vacuous perfection).
        """
        p0_issues = sum(1 for i in self.issues if i.severity == "P0")
        p1_issues = sum(1 for i in self.issues if i.severity == "P1")
        p2_issues = sum(1 for i in self.issues if i.severity == "P2")

        # Quality scoring penalizes ONLY static-source issues (#59).
        # topology-/git-source issues have their own graduated dimensions
        # (topology_score / git_score); counting them here as well would
        # double-penalize and drag healthy codebases to grade F.
        static_p0 = sum(1 for i in self.issues if i.severity == "P0" and i.source == "static")
        static_p1 = sum(1 for i in self.issues if i.severity == "P1" and i.source == "static")
        static_p2 = sum(1 for i in self.issues if i.severity == "P2" and i.source == "static")
        quality_score = max(0, 100 - (static_p0 * 10 + static_p1 * 5 + static_p2 * 1))

        # Overall score: Multi-dimensional weighted formula (v0.9.2 fix)
        # - quality_score (40%): Issue penalties
        # - maintainability_score (30%): Codeindex static analysis (None =
        #   no data; weight redistributes over present dimensions)
        # - topology_score (30%): Graph topology OR
        # - git_score replaces topology if enabled
        structural_score = git_score if git_score is not None else topology_score
        dimensions: list[tuple[str, float, float | None]] = [
            ("quality", 0.4, quality_score),
            ("maintainability", 0.3, maintainability_score),
            ("topology" if git_score is None else "git", 0.3, float(structural_score)),
        ]
        present = [(name, w, s) for name, w, s in dimensions if s is not None]
        weight_sum = sum(w for _, w, _ in present) or 1.0
        total_score = int(sum(s * w for _, w, s in present) / weight_sum)

        # Grade calculation
        if total_score >= 90:
            grade = "A"
        elif total_score >= 80:
            grade = "B"
        elif total_score >= 70:
            grade = "C"
        elif total_score >= 60:
            grade = "D"
        else:
            grade = "F"

        # NOTE: test_coverage is intentionally NOT emitted — it was a
        # hardcoded 0 that reads as "0% coverage" and isn't part of the
        # score formula (#60). Add it back only when coverage is wired.
        breakdown: dict[str, Any] = {
            "topology": topology_score,
            "quality": quality_score,
            # None = no codeindex data flowed in (#153 提案 2)
            "maintainability": (
                int(maintainability_score) if maintainability_score is not None else None
            ),
        }

        # Add git dimension if enabled
        if git_score is not None:
            breakdown["git"] = git_score

        return {
            "total_score": total_score,
            "grade": grade,
            "breakdown": breakdown,
            "summary": {
                "total_entities": self._topology_total_entities,
                "p0_issues": p0_issues,
                "p1_issues": p1_issues,
                "p2_issues": p2_issues,
            },
        }

    def _issue_to_dict(self, issue: DebtIssue) -> dict[str, Any]:
        """Convert DebtIssue to dict for JSON serialization."""
        result = {
            "id": issue.id,
            "severity": issue.severity,
            "category": issue.category,
            "entity": issue.entity,
            "entity_type": issue.entity_type,
            "location": issue.location,
            "metrics": issue.metrics,
            "details": issue.details,
            "suggestion": issue.suggestion,
            "estimated_effort": issue.estimated_effort,
            "references": issue.references,
        }

        # Add git enrichment fields if present (EPIC-010)
        if issue.confidence is not None:
            result["confidence"] = issue.confidence
        if issue.is_hotspot is not None:
            result["is_hotspot"] = issue.is_hotspot

        return result

    def _analyze_git_issues(self, git_metrics: Any) -> int:
        """Generate debt issues from git metrics (EPIC-010 Feature 2).

        Detects:
        1. critical_hotspot (P0): High change_freq + high in_degree = system fragile points
        2. knowledge_silo (P1): Bus factor = 1 (single contributor)

        Args:
            git_metrics: GitMetricsResult from GitMetricsAnalyzer

        Returns:
            Git health score (0-100), penalty-based
        """
        penalty = 0

        # 1. Critical Hotspot Detection (P0)
        for hotspot in git_metrics.hotspots:
            if hotspot.hotspot_score >= 80:  # Critical threshold
                issue_id = f"debt-git-{len(self.issues) + 1:03d}"
                self.issues.append(
                    DebtIssue(
                        id=issue_id,
                        severity="P0",
                        category="critical_hotspot",
                        source="git",
                        entity=hotspot.file,
                        entity_type="file",
                        location={"file": hotspot.file},
                        metrics={
                            "change_frequency": hotspot.change_freq,
                            "hotspot_score": hotspot.hotspot_score,
                            "rank": hotspot.rank,
                        },
                        suggestion=f"⚠️ Critical hotspot: {hotspot.change_freq} changes in {git_metrics.since}. Refactor ASAP to reduce fragility.",
                    )
                )
                penalty += 15  # P0 hotspot = 15 points

        # 2. Knowledge Silo Detection (P1)
        for silo in git_metrics.bus_factor:
            if silo.risk_level == "critical":  # contributors = 1
                issue_id = f"debt-git-{len(self.issues) + 1:03d}"
                self.issues.append(
                    DebtIssue(
                        id=issue_id,
                        severity="P1",
                        category="knowledge_silo",
                        source="git",
                        entity=silo.file,
                        entity_type="file",
                        location={"file": silo.file},
                        metrics={
                            "owner": silo.owner,
                            "contributors": silo.contributors,
                            "total_commits": silo.total_commits,
                        },
                        suggestion=f"Only {silo.owner} knows this code (bus factor = 1). Add documentation or pair programming.",
                    )
                )
                penalty += 8  # P1 silo = 8 points

        return max(0, 100 - penalty)

    def _enrich_with_git_metrics(self, git_metrics: Any) -> None:
        """Enrich existing issues with git metrics (EPIC-010 Feature 2).

        1. orphan_entity: Add confidence field (high/medium/low based on last_modified_days)
        2. god_function: Add is_hotspot marker (if change_frequency > 10)

        Args:
            git_metrics: GitMetricsResult from GitMetricsAnalyzer
        """
        # Build file_path → FileMetrics lookup
        file_metrics_map = git_metrics.file_metrics

        for issue in self.issues:
            file_path = issue.location.get("file", "")

            # Skip if no git data for this file
            if file_path not in file_metrics_map:
                continue

            fm = file_metrics_map[file_path]

            # 1. Enrich orphan_entity with confidence
            if issue.category == "orphan_entity":
                days = fm.last_modified_days

                if days > 365:
                    issue.confidence = "high"
                    issue.suggestion += " (1 year+ no changes, high confidence dead code)"
                elif days > 90:
                    issue.confidence = "medium"
                else:
                    issue.confidence = "low"
                    issue.suggestion += " (recently modified, may be new or dynamic call)"

                issue.metrics["last_modified_days"] = days

            # 2. Enrich god_function with is_hotspot marker
            if issue.category == "god_function":
                freq = fm.change_frequency

                if freq > 10:  # Hotspot threshold
                    issue.is_hotspot = True
                    issue.severity = "P0"  # Upgrade from P1 to P0
                    issue.suggestion += f" ⚠️ Hotspot: {freq} changes in {git_metrics.since}."
                    issue.metrics["change_frequency"] = freq

    def _save_metrics_snapshot(
        self,
        entity: str,
        overall_health: dict[str, Any],
    ) -> None:
        """Auto-save metrics snapshot for trend analysis (EPIC-010 Feature 3).

        Saves a point-in-time snapshot of key metrics to enable trend analysis.
        Snapshots are stored in ~/.loomgraph/metrics-history/

        Args:
            entity: Entity identifier (e.g., "project", "src/auth/user_service.py")
            overall_health: Overall health metrics from analyze()
        """
        try:
            from loomgraph.core.models import MetricsSnapshot
            from loomgraph.core.trends import TrendAnalyzer

            analyzer = TrendAnalyzer()

            # Extract key metrics from overall_health
            breakdown = overall_health.get("breakdown", {})
            metrics = {
                "total_score": overall_health.get("total_score", 100),
                "quality_score": breakdown.get("quality", 100),
                "topology_score": breakdown.get("topology", 100),
            }

            # Add git score if available (three-dimensional analysis)
            if "git" in breakdown:
                metrics["git_score"] = breakdown["git"]

            # Add issue counts by severity
            summary = overall_health.get("summary", {})
            metrics["p0_issues"] = summary.get("p0_issues", 0)
            metrics["p1_issues"] = summary.get("p1_issues", 0)
            metrics["p2_issues"] = summary.get("p2_issues", 0)

            # Create snapshot
            snapshot = MetricsSnapshot(
                entity=entity,
                entity_type="project",  # Project-level for now
                timestamp=datetime.now(UTC),
                metrics=metrics,
                workspace="default",  # TODO: get from context
            )

            # Save snapshot
            analyzer.save_snapshot(snapshot)

        except Exception as e:
            # Don't fail the analysis if snapshot save fails
            logger.warning(f"Failed to save metrics snapshot: {e}")
