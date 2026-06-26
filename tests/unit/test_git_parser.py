"""Unit tests for GitLogParser."""

from pathlib import Path

import pytest

from loomgraph.core.git import GitError
from loomgraph.core.git_parser import GitLogParser


class TestGitLogParser:
    """Test git log parsing functionality."""

    def test_parse_git_log_with_numstat(self):
        """Test parsing git log --numstat output."""
        output = """abc123|alice|1704067800|fix: auth timeout
1       0       src/auth/user_service.py

def456|bob|1704154200|feat: add caching
10      5       src/cache/redis_client.py
2       1       src/config.py
"""
        parser = GitLogParser(Path("."))
        commits = parser._parse_log_output(output)

        assert len(commits) == 2
        assert commits[0]["sha"] == "abc123"
        assert commits[0]["author"] == "alice"
        assert commits[0]["message"] == "fix: auth timeout"
        assert "src/auth/user_service.py" in commits[0]["files"]
        assert commits[0]["stats"]["src/auth/user_service.py"] == {"added": 1, "deleted": 0}

        assert commits[1]["sha"] == "def456"
        assert commits[1]["author"] == "bob"
        assert len(commits[1]["files"]) == 2
        assert commits[1]["stats"]["src/cache/redis_client.py"] == {"added": 10, "deleted": 5}

    def test_parse_git_log_with_special_chars(self):
        """Test parsing commit messages with special characters."""
        output = """abc123|alice|1704067800|fix: 修复🐛权限问题
5       3       src/auth/permission.py
"""
        parser = GitLogParser(Path("."))
        commits = parser._parse_log_output(output)

        assert len(commits) == 1
        assert commits[0]["message"] == "fix: 修复🐛权限问题"
        assert commits[0]["author"] == "alice"

    def test_parse_git_log_empty_output(self):
        """Test parsing empty git log (no commits in time window)."""
        output = ""
        parser = GitLogParser(Path("."))
        commits = parser._parse_log_output(output)

        assert len(commits) == 0

    def test_parse_git_log_with_binary_files(self):
        """Test parsing git log with binary files (- - notation)."""
        output = """abc123|alice|1704067800|feat: add logo
-       -       assets/logo.png
10      5       src/config.py
"""
        parser = GitLogParser(Path("."))
        commits = parser._parse_log_output(output)

        assert len(commits) == 1
        # Binary files should be skipped or marked as 0/0
        assert "assets/logo.png" not in commits[0]["stats"] or commits[0]["stats"]["assets/logo.png"] == {"added": 0, "deleted": 0}
        assert commits[0]["stats"]["src/config.py"] == {"added": 10, "deleted": 5}

    def test_parse_commits_with_since(self, tmp_path):
        """Test parse_commits() with --since parameter."""
        # This test requires a real git repository
        # Will raise GitError when initializing with non-git dir
        with pytest.raises(GitError):
            GitLogParser(tmp_path)

    def test_detect_bug_fix_commits(self):
        """Test bug fix detection from commit messages."""
        output = """abc123|alice|1704067800|fix: auth timeout
1       0       src/auth/user_service.py

def456|bob|1704154200|feat: add caching
10      5       src/cache/redis_client.py

ghi789|charlie|1704240600|Fix memory leak in parser
3       2       src/parser.py
"""
        parser = GitLogParser(Path("."))
        commits = parser._parse_log_output(output)

        # Should detect "fix:" and "Fix" as bug fixes
        bug_fixes = [c for c in commits if parser._is_bug_fix(c["message"])]
        assert len(bug_fixes) == 2
        assert bug_fixes[0]["sha"] == "abc123"
        assert bug_fixes[1]["sha"] == "ghi789"

    def test_calculate_file_metrics(self):
        """Test aggregating commits into FileMetrics."""
        commits = [
            {
                "sha": "abc123",
                "author": "alice",
                "timestamp": 1704067800,
                "message": "fix: auth timeout",
                "files": ["src/auth/user_service.py"],
                "stats": {"src/auth/user_service.py": {"added": 10, "deleted": 5}},
            },
            {
                "sha": "def456",
                "author": "alice",
                "timestamp": 1704154200,
                "message": "feat: improve auth",
                "files": ["src/auth/user_service.py"],
                "stats": {"src/auth/user_service.py": {"added": 20, "deleted": 10}},
            },
            {
                "sha": "ghi789",
                "author": "bob",
                "timestamp": 1704240600,
                "message": "refactor: auth module",
                "files": ["src/auth/user_service.py"],
                "stats": {"src/auth/user_service.py": {"added": 5, "deleted": 15}},
            },
        ]

        parser = GitLogParser(Path("."))
        file_metrics = parser._aggregate_file_metrics(commits)

        assert "src/auth/user_service.py" in file_metrics
        metrics = file_metrics["src/auth/user_service.py"]

        assert metrics.source_id == "src/auth/user_service.py"
        assert metrics.change_frequency == 3
        assert set(metrics.authors) == {"alice", "bob"}
        assert metrics.primary_author == "alice"  # 2 commits
        assert metrics.total_commits == 3
        assert metrics.lines_added == 35  # 10 + 20 + 5
        assert metrics.lines_deleted == 30  # 5 + 10 + 15
        assert metrics.churn == 65  # 35 + 30
        assert metrics.bug_fix_count == 1  # "fix:" commit
        assert metrics.bug_fix_ratio == pytest.approx(1 / 3)
