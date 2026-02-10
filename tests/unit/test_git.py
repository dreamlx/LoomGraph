"""Tests for loomgraph.core.git module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loomgraph.core.git import (
    GitError,
    get_changed_files,
    get_current_commit,
    get_staged_files,
    is_git_repository,
)


class TestIsGitRepository:
    """Tests for is_git_repository function."""

    def test_returns_true_for_git_repo(self, tmp_path: Path) -> None:
        """Should return True when in a git repository."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        assert is_git_repository(tmp_path) is True

    def test_returns_false_for_non_git_dir(self, tmp_path: Path) -> None:
        """Should return False when not in a git repository."""
        assert is_git_repository(tmp_path) is False

    def test_handles_timeout(self) -> None:
        """Should return False on timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=5)
            assert is_git_repository(".") is False


class TestGetChangedFiles:
    """Tests for get_changed_files function."""

    def test_raises_error_for_non_git_repo(self, tmp_path: Path) -> None:
        """Should raise GitError for non-git directory."""
        with pytest.raises(GitError, match="Not a git repository"):
            get_changed_files(repo_path=tmp_path)

    def test_returns_changed_files(self, tmp_path: Path) -> None:
        """Should return list of changed files."""
        # Initialize git repo with commits
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial file and commit
        (tmp_path / "file1.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create second file and commit
        (tmp_path / "file2.py").write_text("print('world')")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file2"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Get changed files
        changed = get_changed_files(since="HEAD~1", repo_path=tmp_path)

        assert len(changed) == 1
        assert changed[0] == Path("file2.py")

    def test_filters_by_extension(self, tmp_path: Path) -> None:
        """Should filter files by extension."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Initial commit
        (tmp_path / "init.txt").write_text("init")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        # Add files with different extensions
        (tmp_path / "code.py").write_text("python")
        (tmp_path / "code.java").write_text("java")
        (tmp_path / "readme.md").write_text("markdown")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add files"], cwd=tmp_path, capture_output=True)

        # Filter by .py extension only
        changed = get_changed_files(
            since="HEAD~1",
            repo_path=tmp_path,
            extensions={".py"},
        )

        assert len(changed) == 1
        assert changed[0] == Path("code.py")


class TestGetCurrentCommit:
    """Tests for get_current_commit function."""

    def test_returns_commit_sha(self, tmp_path: Path) -> None:
        """Should return short commit SHA."""
        # Initialize git repo with commit
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )
        (tmp_path / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        commit = get_current_commit(tmp_path)

        assert len(commit) == 7  # Short SHA
        assert commit.isalnum()


class TestGetStagedFiles:
    """Tests for get_staged_files function."""

    def test_returns_staged_files(self, tmp_path: Path) -> None:
        """Should return list of staged files."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        # Create and stage a file (don't commit)
        (tmp_path / "staged.py").write_text("code")
        subprocess.run(["git", "add", "staged.py"], cwd=tmp_path, capture_output=True)

        staged = get_staged_files(repo_path=tmp_path)

        assert len(staged) == 1
        assert staged[0] == Path("staged.py")
