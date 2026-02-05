"""Data models for LoomGraph.

These models define the internal data structures used for mapping
between codeindex output and LightRAG input.
"""

from dataclasses import dataclass, field
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
