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
    until: str | None = None,
    repo_path: Path | str = ".",
    extensions: set[str] | None = None,
) -> list[Path]:
    """Get list of changed files from ``since`` (default: to working tree).

    Without ``until`` the diff endpoint is the working tree — staged and
    unstaged changes are included alongside committed ones, matching the
    update skip gate (``_diff_names_with_deletions``). With ``until`` the
    diff is the committed range ``since..until`` (#175: the two endpoints
    disagreeing made dirty-tree updates silently skip the ingest set).

    Args:
        since: Starting commit reference (default: HEAD~1)
        until: Ending commit reference (default: None = working tree)
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
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", since]
        if until is not None:
            cmd.append(until)
        result = subprocess.run(
            cmd,
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
        raise GitError("git diff timed out") from None
    except FileNotFoundError:
        raise GitError("git command not found") from None


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
        raise GitError("git diff timed out") from None
    except FileNotFoundError:
        raise GitError("git command not found") from None


def get_working_tree_files(
    repo_path: Path | str = ".",
    *,
    include_untracked: bool = True,
    extensions: set[str] | None = None,
) -> list[Path]:
    """Get files with uncommitted working-tree changes (staged + unstaged +
    untracked), relative to repo root.

    Complementary to :func:`get_changed_files` (committed ``HEAD~1..HEAD``):
    pull-mode source for the MCP ``refresh`` tool — an agent editing a file
    without committing still gets a non-empty result. Uses
    ``git status --porcelain=v1 -z`` (``--no-renames`` so renames decompose
    into delete-old + new-untracked, sidestepping porcelain's double-segment
    rename format). ``git diff HEAD`` would miss untracked new files.

    Deleted files (``D``) are excluded — nothing to re-export.

    Args:
        repo_path: Repository path (default: current directory)
        include_untracked: Include untracked (``??``) files (default True)
        extensions: Filter by file extensions (e.g., {".py", ".java"})

    Returns:
        List of existing changed file paths (relative to repo root)

    Raises:
        GitError: If git command fails or not a git repository
    """
    repo = Path(repo_path)

    if not is_git_repository(repo):
        raise GitError(f"Not a git repository: {repo}")

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--no-renames"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise GitError("git status timed out") from None
    except FileNotFoundError:
        raise GitError("git command not found") from None

    if result.returncode != 0:
        raise GitError(f"git status failed: {result.stderr}")

    paths: list[Path] = []
    for entry in result.stdout.split("\0"):
        # porcelain v1: "XY <path>" — at least 4 chars (2 status + space + name)
        if len(entry) < 4:
            continue
        xy, path_str = entry[:2], entry[3:]
        if "D" in xy:  # deleted → skip (nothing to re-export)
            continue
        if xy == "??" and not include_untracked:
            continue
        paths.append(Path(path_str))

    if extensions:
        paths = [p for p in paths if p.suffix.lower() in extensions]

    existing = [p for p in paths if (repo / p).exists()]
    logger.info(f"Found {len(existing)} working-tree files")
    return existing


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
        raise GitError("git rev-parse timed out") from None
    except FileNotFoundError:
        raise GitError("git command not found") from None


def get_current_branch(repo_path: Path | str = ".") -> str:
    """Get the current git branch name.

    Args:
        repo_path: Repository path

    Returns:
        Branch name (e.g. 'main', 'develop')

    Raises:
        GitError: If git command fails or HEAD is detached
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            raise GitError(f"git rev-parse failed: {result.stderr}")

        branch = result.stdout.strip()
        if branch == "HEAD":
            raise GitError("Detached HEAD state: no branch name available")

        return branch

    except subprocess.TimeoutExpired as err:
        raise GitError("git rev-parse timed out") from err
    except FileNotFoundError as err:
        raise GitError("git command not found") from err

def resolve_ref(repo_path: Path | str, ref: str) -> str:
    """Resolve an arbitrary ref to its full commit sha (EPIC-016 branch-diff).

    ``^{commit}`` peels annotated tags to the commit they point at, so a tag,
    branch, short sha, or ``HEAD`` all resolve to the same 40-hex form.

    Args:
        repo_path: Repository path (or anywhere inside it)
        ref: Any git rev syntax (branch / tag / sha / HEAD)

    Returns:
        Full 40-character commit sha

    Raises:
        GitError: If the ref does not resolve (message names the ref)
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"git rev-parse timed out resolving {ref!r}") from None
    except FileNotFoundError:
        raise GitError("git command not found") from None

    if result.returncode != 0:
        raise GitError(
            f"cannot resolve ref {ref!r}: {result.stderr.strip() or 'unknown ref'}"
        )
    return result.stdout.strip()


def worktree_add(repo_path: Path | str, path: Path, sha: str) -> None:
    """Create a temporary worktree detached at ``sha`` (EPIC-016 branch-diff).

    ``--detach`` is load-bearing: the base ref of a branch-diff is frequently
    the branch already checked out in the main worktree, and git refuses to
    check the same branch out twice. A detached worktree at the resolved sha
    also pins the exact commit (same-input-same-output for the diff).

    Raises:
        GitError: If git worktree add fails (bad sha, path exists, ...)
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), sha],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise GitError("git worktree add timed out") from None
    except FileNotFoundError:
        raise GitError("git command not found") from None

    if result.returncode != 0:
        raise GitError(f"git worktree add failed: {result.stderr.strip()}")


def worktree_remove(repo_path: Path | str, path: Path) -> None:
    """Remove a worktree and its git metadata (EPIC-016 branch-diff).

    ``--force`` because the provisioning flow treats worktrees as disposable:
    a leftover dirty state must never block cleanup of our own temp dir.

    Raises:
        GitError: If git worktree remove fails
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise GitError("git worktree remove timed out") from None
    except FileNotFoundError:
        raise GitError("git command not found") from None

    if result.returncode != 0:
        raise GitError(f"git worktree remove failed: {result.stderr.strip()}")
