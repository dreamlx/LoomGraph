"""Core module: configuration, git, and graph-store data models."""

from loomgraph.core.config import Settings, get_settings
from loomgraph.core.git import (
    GitError,
    get_changed_files,
    get_current_branch,
    get_current_commit,
    is_git_repository,
)
from loomgraph.core.models import EntityData, RelationData

__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Git
    "GitError",
    "is_git_repository",
    "get_changed_files",
    "get_current_branch",
    "get_current_commit",
    # Models
    "EntityData",
    "RelationData",
]
