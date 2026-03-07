"""Data models for LoomGraph.

These models define the internal data structures used for mapping
between codeindex output and LightRAG input.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================
# codeindex Input Types (for type hints)
# ============================================
# These mirror the codeindex data structures.
# In production, these would be imported from matrix-codeindex.


@dataclass
class Symbol:
    """Code symbol extracted by codeindex."""

    name: str  # "UserService.login"
    kind: str  # "function", "class", "method"
    signature: str  # "def login(self, username: str, password: str) -> bool"
    docstring: str  # "Authenticate user..."
    line_start: int  # 12
    line_end: int  # 25


@dataclass
class Call:
    """Function call relationship extracted by codeindex."""

    caller: str  # "UserService.login"
    callee: str  # "db.find_user"
    line: int  # 15
    is_method: bool  # True


@dataclass
class Inheritance:
    """Class inheritance relationship extracted by codeindex."""

    child: str  # "UserService"
    parent: str  # "BaseService"


@dataclass
class Import:
    """Import statement extracted by codeindex."""

    module: str  # "os.path"
    alias: str | None  # "osp" or None
    names: list[str]  # ["join", "exists"] or []


@dataclass
class ParseResult:
    """Complete parse result from codeindex."""

    path: Path
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    inheritances: list[Inheritance] = field(default_factory=list)
    module_docstring: str = ""
    file_lines: int = 0
    error: str | None = None


# ============================================
# LoomGraph Internal Types
# ============================================


@dataclass
class InjectResult:
    """Result of injecting a parse result into LightRAG."""

    file_path: str
    entities: int
    relations: int
    errors: list[str] = field(default_factory=list)


@dataclass
class IndexResult:
    """Result of indexing a repository."""

    repo_path: str
    files: int
    entities: int
    relations: int
    errors: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)


# ============================================
# Mapped Types (for LightRAG)
# ============================================


@dataclass
class EntityData:
    """Entity data prepared for LightRAG acreate_entity()."""

    entity_name: str
    entity_data: dict[str, Any]


@dataclass
class RelationData:
    """Relation data prepared for LightRAG acreate_relation()."""

    src_id: str
    tgt_id: str
    edge_data: dict[str, Any]


# ============================================
# Git Metrics Types (EPIC-010)
# ============================================


@dataclass
class FileMetrics:
    """File-level git metrics for technical debt analysis.

    Attributes:
        source_id: File path (e.g., "src/auth/user_service.py")
        change_frequency: Number of commits in time window
        last_modified: Last modification timestamp
        last_modified_days: Days since last modification
        authors: List of contributors
        primary_author: Main contributor (highest commit count)
        bug_fix_count: Number of bug fix commits
        total_commits: Total number of commits
        bug_fix_ratio: bug_fix_count / total_commits
        lines_added: Total lines added
        lines_deleted: Total lines deleted
        churn: lines_added + lines_deleted
        created_at: First commit timestamp
        age_days: Days since first commit
    """

    source_id: str
    change_frequency: int
    last_modified: datetime
    last_modified_days: int
    authors: list[str]
    primary_author: str | None
    bug_fix_count: int
    total_commits: int
    bug_fix_ratio: float
    lines_added: int
    lines_deleted: int
    churn: int
    created_at: datetime
    age_days: int


@dataclass
class Hotspot:
    """High-frequency change file (system fragile point).

    Hotspot score = change_frequency × log10(churn + 1) × 10

    Attributes:
        file: File path
        change_freq: Number of commits
        lines: Total lines of code (current)
        hotspot_score: 0-100, higher = more critical
        rank: Priority rank (1 = highest risk)
    """

    file: str
    change_freq: int
    lines: int
    hotspot_score: int
    rank: int


@dataclass
class BusFactor:
    """Knowledge silo risk analysis.

    Attributes:
        file: File path
        owner: Primary contributor
        contributors: Number of contributors
        ownership_ratio: owner_commits / total_commits
        total_commits: Total number of commits
        risk_level: "critical" (1 contributor) | "high" (2, >70%) | "medium"
    """

    file: str
    owner: str
    contributors: int
    ownership_ratio: float
    total_commits: int
    risk_level: str  # "critical" | "high" | "medium"


@dataclass
class GitMetricsResult:
    """Complete git metrics analysis result.

    Attributes:
        repo_path: Repository root path
        since: Time window (e.g., "3 months")
        analyzed_at: Analysis timestamp
        file_metrics: FileMetrics indexed by source_id
        hotspots: High-frequency change files (sorted by score)
        bus_factor: Knowledge silo risks (sorted by risk level)
        summary: Aggregated statistics
    """

    repo_path: Path
    since: str
    analyzed_at: datetime
    file_metrics: dict[str, FileMetrics]
    hotspots: list[Hotspot]
    bus_factor: list[BusFactor]
    summary: dict[str, Any]
