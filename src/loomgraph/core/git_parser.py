"""Git log parser for extracting commit history metrics.

This module provides GitLogParser for parsing git log output
and aggregating file-level metrics for technical debt analysis.
"""

import logging
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from loomgraph.core.git import GitError, is_git_repository
from loomgraph.core.models import FileMetrics

logger = logging.getLogger(__name__)


class _CommitStats(TypedDict):
    """Per-file numstat within one commit."""

    added: int
    deleted: int


class _CommitData(TypedDict):
    """One parsed commit (header line + its numstat lines)."""

    sha: str
    author: str
    timestamp: int
    message: str
    files: list[str]
    stats: dict[str, _CommitStats]


class _FileAcc(TypedDict):
    """Per-file aggregation accumulator (mypy: kills the heterogeneous
    dict-value union that used to fan out ~60 errors)."""

    commits: list[_CommitData]
    authors: set[str]
    author_counts: defaultdict[str, int]
    bug_fixes: int
    lines_added: int
    lines_deleted: int
    first_seen: datetime | None
    last_seen: datetime | None


class GitLogParser:
    """Parse git log to extract file-level metrics."""

    def __init__(self, repo_path: Path | str):
        """Initialize parser.

        Args:
            repo_path: Path to git repository root

        Raises:
            GitError: If path is not a git repository
        """
        self.repo_path = Path(repo_path)
        if not is_git_repository(self.repo_path):
            raise GitError(f"Not a git repository: {self.repo_path}")

    def parse_commits(self, since: str = "3 months") -> list[_CommitData]:
        """Parse git log for commits in time window.

        Args:
            since: Time window (e.g., "3 months", "6 months", "1 year")

        Returns:
            List of commit dicts with keys:
                - sha: Commit hash
                - author: Author name
                - timestamp: Unix timestamp
                - message: Commit message
                - files: List of changed file paths
                - stats: Dict[file_path, {added: int, deleted: int}]

        Raises:
            GitError: If git command fails
        """
        try:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    f"--since={since}",
                    "--format=%H|%an|%at|%s",
                    "--numstat",
                ],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise GitError(f"git log failed: {result.stderr}")

            return self._parse_log_output(result.stdout)

        except subprocess.TimeoutExpired as e:
            raise GitError(f"git log timeout after 30s: {e}") from e
        except FileNotFoundError as e:
            raise GitError(f"git command not found: {e}") from e

    def _parse_log_output(self, output: str) -> list[_CommitData]:
        """Parse git log --numstat output into structured commits.

        Format:
            abc123|alice|1704067800|fix: auth timeout
            1       0       src/auth/user_service.py

            def456|bob|1704154200|feat: add caching
            10      5       src/cache/redis_client.py
            2       1       src/config.py

        Args:
            output: Raw git log output

        Returns:
            List of commit dicts
        """
        commits: list[_CommitData] = []
        current_commit: _CommitData | None = None

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Commit header: sha|author|timestamp|message
            if "|" in line and not line.startswith("\t"):
                # Save previous commit
                if current_commit:
                    commits.append(current_commit)

                parts = line.split("|", 3)
                if len(parts) == 4:
                    sha, author, timestamp_str, message = parts
                    current_commit = {
                        "sha": sha,
                        "author": author,
                        "timestamp": int(timestamp_str),
                        "message": message,
                        "files": [],
                        "stats": {},
                    }

            # File stats: added\tdeleted\tfile_path (or multiple spaces)
            elif current_commit:
                # Split by whitespace (tabs or spaces)
                parts = line.split(None, 2)
                if len(parts) == 3:
                    added_str, deleted_str, file_path = parts

                    # Validate first two fields are numbers or "-"
                    if not ((added_str.isdigit() or added_str == "-") and
                            (deleted_str.isdigit() or deleted_str == "-")):
                        continue

                    # Handle binary files (- -)
                    if added_str == "-" or deleted_str == "-":
                        added, deleted = 0, 0
                    else:
                        added = int(added_str)
                        deleted = int(deleted_str)

                    current_commit["files"].append(file_path)
                    current_commit["stats"][file_path] = {
                        "added": added,
                        "deleted": deleted,
                    }

        # Save last commit
        if current_commit:
            commits.append(current_commit)

        return commits

    def _is_bug_fix(self, message: str) -> bool:
        """Detect if commit is a bug fix.

        Args:
            message: Commit message

        Returns:
            True if message indicates bug fix
        """
        bug_patterns = [
            r"^fix:",
            r"^Fix\s",
            r"^bugfix:",
            r"^hotfix:",
            r"\bfix\b.*\bbug\b",
            r"\bfix\b.*\bissue\b",
        ]

        return any(re.search(pattern, message, re.IGNORECASE) for pattern in bug_patterns)

    def _aggregate_file_metrics(self, commits: list[_CommitData]) -> dict[str, FileMetrics]:
        """Aggregate commits into FileMetrics.

        Args:
            commits: List of commit dicts from parse_commits()

        Returns:
            Dict mapping file_path → FileMetrics
        """
        def _new_file_acc() -> _FileAcc:
            return {
                "commits": [],
                "authors": set(),
                "author_counts": defaultdict(int),
                "bug_fixes": 0,
                "lines_added": 0,
                "lines_deleted": 0,
                "first_seen": None,
                "last_seen": None,
            }

        # Aggregate data per file
        file_data: defaultdict[str, _FileAcc] = defaultdict(_new_file_acc)

        for commit in commits:
            commit_time = datetime.fromtimestamp(commit["timestamp"])
            is_bug_fix = self._is_bug_fix(commit["message"])

            for file_path in commit["files"]:
                data = file_data[file_path]
                data["commits"].append(commit)
                data["authors"].add(commit["author"])
                data["author_counts"][commit["author"]] += 1

                if is_bug_fix:
                    data["bug_fixes"] += 1

                stats = commit["stats"].get(file_path, {"added": 0, "deleted": 0})
                data["lines_added"] += stats["added"]
                data["lines_deleted"] += stats["deleted"]

                # Track first and last modification
                if data["first_seen"] is None or commit_time < data["first_seen"]:
                    data["first_seen"] = commit_time
                if data["last_seen"] is None or commit_time > data["last_seen"]:
                    data["last_seen"] = commit_time

        # Convert to FileMetrics
        now = datetime.now()
        result = {}

        for file_path, data in file_data.items():
            # Find primary author (most commits)
            primary_author = max(data["author_counts"].items(), key=lambda x: x[1])[0]

            total_commits = len(data["commits"])
            bug_fix_ratio = data["bug_fixes"] / total_commits if total_commits > 0 else 0.0

            last_modified = data["last_seen"] or now
            last_modified_days = (now - last_modified).days

            created_at = data["first_seen"] or now
            age_days = (now - created_at).days

            result[file_path] = FileMetrics(
                source_id=file_path,
                change_frequency=total_commits,
                last_modified=last_modified,
                last_modified_days=last_modified_days,
                authors=sorted(data["authors"]),
                primary_author=primary_author,
                bug_fix_count=data["bug_fixes"],
                total_commits=total_commits,
                bug_fix_ratio=bug_fix_ratio,
                lines_added=data["lines_added"],
                lines_deleted=data["lines_deleted"],
                churn=data["lines_added"] + data["lines_deleted"],
                created_at=created_at,
                age_days=age_days,
            )

        return result
