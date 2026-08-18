"""Tests for loomgraph.core.git module."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from loomgraph.core.git import (
    GitError,
    get_changed_files,
    get_current_branch,
    get_current_commit,
    get_staged_files,
    get_working_tree_files,
    is_git_repository,
    resolve_ref,
    worktree_add,
    worktree_remove,
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

    def test_includes_unstaged_working_tree_changes(self, tmp_path: Path) -> None:
        """Default (no until) must diff to the working tree, not HEAD.

        #175: the update skip gate diffs ``HEAD~1`` → working tree while the
        ingest set diffed ``HEAD~1..HEAD`` — an unstaged source edit passed
        the gate but never entered changed_files, leaving a silently stale
        graph. Staged changes are covered by the same endpoint.
        """
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path, capture_output=True,
        )

        (tmp_path / "file1.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path, capture_output=True,
        )
        (tmp_path / "file2.py").write_text("print('world')")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file2"],
            cwd=tmp_path, capture_output=True,
        )

        # Unstaged edit + staged new file on top of the commits
        (tmp_path / "file1.py").write_text("print('edited')")
        (tmp_path / "file3.py").write_text("print('staged')")
        subprocess.run(["git", "add", "file3.py"], cwd=tmp_path, capture_output=True)

        changed = get_changed_files(since="HEAD~1", repo_path=tmp_path)

        # file2 (committed since) + file1 (unstaged) + file3 (staged)
        assert {p.name for p in changed} == {"file1.py", "file2.py", "file3.py"}

    def test_explicit_until_still_ranges_two_commits(self, tmp_path: Path) -> None:
        """Explicit until= keeps the committed-range semantics."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path, capture_output=True,
        )

        (tmp_path / "file1.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path, capture_output=True,
        )
        (tmp_path / "file2.py").write_text("print('world')")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file2"],
            cwd=tmp_path, capture_output=True,
        )
        # Post-commit unstaged edit must NOT appear in the committed range
        (tmp_path / "file3.py").write_text("print('unstaged')")

        changed = get_changed_files(
            since="HEAD~1", until="HEAD", repo_path=tmp_path
        )

        assert [p.name for p in changed] == ["file2.py"]


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


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    def test_returns_branch_name(self, tmp_path: Path) -> None:
        """Should return the current branch name."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path, capture_output=True,
        )
        (tmp_path / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        branch = get_current_branch(tmp_path)
        assert branch == "main"

    def test_detached_head_raises_error(self, tmp_path: Path) -> None:
        """Should raise GitError on detached HEAD."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path, capture_output=True,
        )
        (tmp_path / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        # Detach HEAD
        subprocess.run(["git", "checkout", "--detach"], cwd=tmp_path, capture_output=True)

        with pytest.raises(GitError, match="Detached HEAD"):
            get_current_branch(tmp_path)

    def test_non_git_repo_raises_error(self, tmp_path: Path) -> None:
        """Should raise GitError for non-git directory."""
        with pytest.raises(GitError):
            get_current_branch(tmp_path)


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


def _init_repo_with_commit(path: Path) -> None:
    """Init a git repo in `path`, commit one tracked `a.py`, leave clean tree."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, capture_output=True)
    (path / "a.py").write_text("a = 1\n")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True)


class TestGetWorkingTreeFiles:
    """Tests for get_working_tree_files — MCP `refresh` working-tree source.

    Complementary to get_changed_files (committed HEAD~1..HEAD): this reads
    uncommitted edits + untracked files via `git status --porcelain`.
    """

    def test_raises_error_for_non_git_repo(self, tmp_path: Path) -> None:
        with pytest.raises(GitError, match="Not a git repository"):
            get_working_tree_files(repo_path=tmp_path)

    def test_returns_modified_tracked_file(self, tmp_path: Path) -> None:
        """Modified-but-uncommitted tracked file is included."""
        _init_repo_with_commit(tmp_path)
        (tmp_path / "a.py").write_text("a = 2\n")  # uncommitted modification
        result = get_working_tree_files(repo_path=tmp_path)
        assert Path("a.py") in result

    def test_includes_untracked_new_file(self, tmp_path: Path) -> None:
        """Untracked new file is included — the case `git diff HEAD` misses."""
        _init_repo_with_commit(tmp_path)
        (tmp_path / "new.py").write_text("x = 1\n")  # untracked
        result = get_working_tree_files(repo_path=tmp_path)
        assert Path("new.py") in result

    def test_excludes_deleted_file(self, tmp_path: Path) -> None:
        """Deleted tracked file excluded (nothing to re-export)."""
        _init_repo_with_commit(tmp_path)
        (tmp_path / "a.py").unlink()
        result = get_working_tree_files(repo_path=tmp_path)
        assert Path("a.py") not in result

    def test_clean_worktree_returns_empty(self, tmp_path: Path) -> None:
        _init_repo_with_commit(tmp_path)
        assert get_working_tree_files(repo_path=tmp_path) == []

    def test_extension_filter(self, tmp_path: Path) -> None:
        _init_repo_with_commit(tmp_path)
        (tmp_path / "new.py").write_text("x\n")
        (tmp_path / "new.txt").write_text("x\n")
        result = get_working_tree_files(repo_path=tmp_path, extensions={".py"})
        assert Path("new.py") in result
        assert Path("new.txt") not in result

    def test_include_untracked_false(self, tmp_path: Path) -> None:
        """include_untracked=False drops `??` entries but keeps modifications."""
        _init_repo_with_commit(tmp_path)
        (tmp_path / "new.py").write_text("x\n")  # untracked
        (tmp_path / "a.py").write_text("a = 2\n")  # modified tracked
        result = get_working_tree_files(repo_path=tmp_path, include_untracked=False)
        assert Path("a.py") in result
        assert Path("new.py") not in result


def _init_repo_with_commits(repo: Path, files_per_commit: list[dict[str, str]]) -> str:
    """Init a git repo + one commit per dict; returns HEAD's full sha."""
    subprocess.run(["git", "init", "-q"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=repo, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=repo, capture_output=True, check=True
    )
    for files in files_per_commit:
        for name, content in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "c"],
            cwd=repo, capture_output=True, check=True,
        )
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


class TestResolveRef:
    """EPIC-016 (#185) branch-diff 前置:任意 ref → 完整 commit sha。"""

    def test_branch_ref_returns_full_sha(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        sha = _init_repo_with_commits(repo, [{"a.py": "x = 1\n"}])

        assert resolve_ref(repo, "HEAD") == sha
        assert resolve_ref(repo, get_current_branch(repo)) == sha  # init 默认分支名不定

    def test_short_sha_and_annotated_tag_peel_to_commit(self, tmp_path: Path) -> None:
        """short sha 与 annotated tag 都要剥到 commit sha(^{commit})。"""
        repo = tmp_path / "repo"
        repo.mkdir()
        sha = _init_repo_with_commits(repo, [{"a.py": "x = 1\n"}])
        subprocess.run(
            ["git", "tag", "-a", "v1", "-m", "tag"],
            cwd=repo, capture_output=True, check=True,
        )

        assert resolve_ref(repo, sha[:8]) == sha
        assert resolve_ref(repo, "v1") == sha

    def test_unknown_ref_raises_with_ref_in_message(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo_with_commits(repo, [{"a.py": "x = 1\n"}])

        with pytest.raises(GitError, match="nope-ref"):
            resolve_ref(repo, "nope-ref")


class TestWorktree:
    """EPIC-016 (#185):worktree add --detach / remove。"""

    def test_add_detaches_at_sha_and_remove_cleans(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        sha = _init_repo_with_commits(repo, [{"a.py": "x = 1\n"}])
        wt = tmp_path / "wt"

        worktree_add(repo, wt, sha)
        # detach 到指定 sha:文件在、HEAD 是该 sha、无分支名
        assert (wt / "a.py").exists()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True
        )
        assert head.stdout.strip() == sha

        worktree_remove(repo, wt)
        assert not wt.exists()
        # worktree 元数据也清掉(list 只剩主 worktree)
        listing = subprocess.run(
            ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True
        )
        assert str(wt) not in listing.stdout

    def test_add_at_currently_checked_out_branch_succeeds(self, tmp_path: Path) -> None:
        """--detach 是承重墙:base ref 常是主 worktree 已 checkout 的分支,
        不 detach git 会拒绝 "already checked out"。"""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo_with_commits(repo, [{"a.py": "x = 1\n"}])
        branch = get_current_branch(repo)
        sha = resolve_ref(repo, branch)
        wt = tmp_path / "wt2"

        worktree_add(repo, wt, sha)  # 不 raise 即通过
        worktree_remove(repo, wt)

    def test_add_bad_sha_raises(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo_with_commits(repo, [{"a.py": "x = 1\n"}])

        with pytest.raises(GitError):
            worktree_add(repo, tmp_path / "wt3", "deadbeef")
