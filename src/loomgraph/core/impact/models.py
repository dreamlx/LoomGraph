"""Data models for impact analysis."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChangeType(Enum):
    """Type of change detected in a symbol."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class ChangedFile:
    """Represents a file that was changed in a commit."""

    path: str
    change_type: ChangeType
    added_lines: list[tuple[int, int]] = field(default_factory=list)
    deleted_lines: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "path": self.path,
            "change_type": self.change_type.value,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
        }


@dataclass
class ChangedSymbol:
    """Represents a code symbol that was changed."""

    name: str
    file: str
    change_type: ChangeType
    lines_changed: int = 0
    line_start: int = 0
    line_end: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "name": self.name,
            "file": self.file,
            "change_type": self.change_type.value,
            "lines_changed": self.lines_changed,
        }


@dataclass
class Caller:
    """Represents a function/method that calls a changed symbol."""

    name: str
    file: str
    line: int = 0
    depth: int = 1  # 1 = direct, 2+ = indirect

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result: dict[str, Any] = {
            "name": self.name,
            "file": self.file,
            "line": self.line,
        }
        if self.depth > 1:
            result["depth"] = self.depth
        return result


@dataclass
class RiskAssessment:
    """Risk assessment for a set of changes."""

    level: str  # "low", "medium", "high"
    reason: str
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "level": self.level,
            "reason": self.reason,
            "suggestions": self.suggestions,
        }


@dataclass
class ImpactResult:
    """Complete impact analysis result."""

    commit: str
    changed_symbols: list[ChangedSymbol]
    direct_callers: list[Caller] = field(default_factory=list)
    indirect_callers: list[Caller] = field(default_factory=list)
    affected_modules: list[str] = field(default_factory=list)
    affected_tests: list[str] = field(default_factory=list)
    risk_assessment: RiskAssessment | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result: dict[str, Any] = {
            "commit": self.commit,
            "changed_symbols": [s.to_dict() for s in self.changed_symbols],
            "impact_analysis": {
                "direct_callers": [c.to_dict() for c in self.direct_callers],
                "indirect_callers": [c.to_dict() for c in self.indirect_callers],
                "affected_modules": self.affected_modules,
                "affected_tests": self.affected_tests,
            },
        }
        if self.risk_assessment:
            result["risk_assessment"] = self.risk_assessment.to_dict()
        return result
