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

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


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


class DebtAnalyzer:
    """
    Technical Debt Analyzer

    Combines codeindex static analysis with LoomGraph graph topology
    to provide comprehensive technical debt analysis.

    Usage:
        analyzer = DebtAnalyzer()
        result = await analyzer.analyze(codeindex_data=codeindex_json)
    """

    def __init__(self) -> None:
        self.issues: list[DebtIssue] = []

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
        self, codeindex_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Main analysis entry point.

        Combines codeindex static analysis with LoomGraph graph topology.

        Args:
            codeindex_data: Optional codeindex JSON output

        Returns:
            Debt report in standardized format (ADR-012)
        """
        # Step 1: Import codeindex data (if provided)
        imported_data = None
        if codeindex_data:
            imported_data = self.import_codeindex_data(codeindex_data)

        # Step 2: Analyze issues from codeindex data
        if imported_data:
            await self._analyze_codeindex_issues(imported_data)

        # Step 3: Analyze graph topology (future: integrate with TopologyAnalyzer)
        # await self._analyze_topology_issues()

        # Step 4: Calculate overall health
        overall_health = self._calculate_overall_health()

        # Step 5: Generate report
        return {
            "schema_version": "1.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "project": "unknown",  # TODO: detect from workspace
            "generator": {
                "tool": "loomgraph",
                "version": "0.9.0",  # TODO: get from package version
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

    def _lookup_maintainability(self, data: CodeindexData, path: str) -> float:
        """Lookup maintainability score from codeindex data."""
        for score_data in data.maintainability_scores:
            if score_data["path"] == path:
                return score_data["score"]
        return 5.0  # Default mid-range score

    def _calculate_overall_health(self) -> dict[str, Any]:
        """Calculate overall health score from issues."""
        p0_issues = sum(1 for i in self.issues if i.severity == "P0")
        p1_issues = sum(1 for i in self.issues if i.severity == "P1")
        p2_issues = sum(1 for i in self.issues if i.severity == "P2")

        # Simple scoring: 100 - (P0*10 + P1*5 + P2*1)
        total_score = max(0, 100 - (p0_issues * 10 + p1_issues * 5 + p2_issues * 1))

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

        return {
            "total_score": total_score,
            "grade": grade,
            "breakdown": {
                "topology": 0,  # TODO: integrate TopologyAnalyzer
                "quality": total_score,
                "test_coverage": 0,
                "maintainability": 0,
            },
            "summary": {
                "total_entities": 0,
                "p0_issues": p0_issues,
                "p1_issues": p1_issues,
                "p2_issues": p2_issues,
            },
        }

    def _issue_to_dict(self, issue: DebtIssue) -> dict[str, Any]:
        """Convert DebtIssue to dict for JSON serialization."""
        return {
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
