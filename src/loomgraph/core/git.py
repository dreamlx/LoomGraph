"""Git integration for detecting changed files.

This module provides utilities for detecting file changes in git repositories,
used by the Warm Update strategy.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Exception raised when git operations fail."""

    pass


def is_git_repository(path: Path | str = ".") -> bool:
    """Check if the given path is inside a git repository.

    Args:
        path: Directory to check (default: current directory)

    Returns:
        True if inside a git repository, False otherwise
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_changed_files(
    since: str = "HEAD~1",
    until: str = "HEAD",
    repo_path: Path | str = ".",
    extensions: set[str] | None = None,
) -> list[Path]:
    """Get list of changed files between two commits.

    Args:
        since: Starting commit reference (default: HEAD~1)
        until: Ending commit reference (default: HEAD)
        repo_path: Repository path (default: current directory)
        extensions: Filter by file extensions (e.g., {".py", ".java"})

    Returns:
        List of changed file paths (relative to repo root)

    Raises:
        GitError: If git command fails
    """
    repo = Path(repo_path)

    if not is_git_repository(repo):
        raise GitError(f"Not a git repository: {repo}")

    try:
        # Get changed files between commits
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", since, until],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Try without until (for staged changes or single commit)
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACMR", since],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=30,
            )

        if result.returncode != 0:
            raise GitError(f"git diff failed: {result.stderr}")

        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

        # Convert to Path objects
        paths = [Path(f) for f in files]

        # Filter by extension if specified
        if extensions:
            paths = [p for p in paths if p.suffix.lower() in extensions]

        # Filter to only existing files (exclude deleted)
        existing_paths = []
        for p in paths:
            full_path = repo / p
            if full_path.exists():
                existing_paths.append(p)

        logger.info(f"Found {len(existing_paths)} changed files since {since}")
        return existing_paths

    except subprocess.TimeoutExpired:
        raise GitError("git diff timed out")
    except FileNotFoundError:
        raise GitError("git command not found")


def get_staged_files(
    repo_path: Path | str = ".",
    extensions: set[str] | None = None,
) -> list[Path]:
    """Get list of staged (added to index) files.

    Args:
        repo_path: Repository path (default: current directory)
        extensions: Filter by file extensions

    Returns:
        List of staged file paths

    Raises:
        GitError: If git command fails
    """
    repo = Path(repo_path)

    if not is_git_repository(repo):
        raise GitError(f"Not a git repository: {repo}")

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached", "--diff-filter=ACMR"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise GitError(f"git diff --cached failed: {result.stderr}")

        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        paths = [Path(f) for f in files]

        if extensions:
            paths = [p for p in paths if p.suffix.lower() in extensions]

        return paths

    except subprocess.TimeoutExpired:
        raise GitError("git diff timed out")
    except FileNotFoundError:
        raise GitError("git command not found")


def get_current_commit(repo_path: Path | str = ".") -> str:
    """Get the current commit SHA.

    Args:
        repo_path: Repository path

    Returns:
        Short commit SHA (7 characters)

    Raises:
        GitError: If git command fails
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            raise GitError(f"git rev-parse failed: {result.stderr}")

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        raise GitError("git rev-parse timed out")
    except FileNotFoundError:
        raise GitError("git command not found")
