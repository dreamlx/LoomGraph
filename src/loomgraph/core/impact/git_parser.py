"""Git diff parsing utilities."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from loomgraph.core.impact.models import ChangeType, ChangedFile


class GitError(Exception):
    """Exception raised for git command errors."""

    pass


@dataclass
class GitDiffParser:
    """Parser for git diff output.

    Parses git diff output to extract changed files and line ranges.
    """

    repo_path: Path = Path(".")

    def _run_git(self, *args: str) -> str:
        """Run a git command and return output."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), *args],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise GitError(f"git {' '.join(args)} failed: {result.stderr}")
            return result.stdout
        except subprocess.TimeoutExpired:
            raise GitError(f"git {' '.join(args)} timed out")
        except FileNotFoundError:
            raise GitError("git command not found")

    def get_changed_files_for_commit(self, commit: str = "HEAD") -> list[ChangedFile]:
        """Get list of changed files for a commit.

        Args:
            commit: Commit reference (default: HEAD)

        Returns:
            List of ChangedFile objects
        """
        # Validate commit
        try:
            self._run_git("rev-parse", "--verify", commit)
        except GitError:
            raise GitError(f"Invalid commit: {commit}")

        # Get diff with parent
        if commit == "HEAD":
            diff_output = self._run_git("diff", "HEAD~1..HEAD", "--unified=0")
        else:
            diff_output = self._run_git("diff", f"{commit}~1..{commit}", "--unified=0")

        return self._parse_diff(diff_output)

    def get_staged_changes(self) -> list[ChangedFile]:
        """Get list of staged (cached) changes.

        Returns:
            List of ChangedFile objects
        """
        diff_output = self._run_git("diff", "--cached", "--unified=0")
        return self._parse_diff(diff_output)

    def get_branch_diff(self, base: str, head: str = "HEAD") -> list[ChangedFile]:
        """Get diff between two branches/commits.

        Args:
            base: Base branch/commit
            head: Head branch/commit (default: HEAD)

        Returns:
            List of ChangedFile objects
        """
        diff_output = self._run_git("diff", f"{base}..{head}", "--unified=0")
        return self._parse_diff(diff_output)

    def get_file_diff(self, file_path: str, commit: str = "HEAD") -> list[ChangedFile]:
        """Get diff for a specific file.

        Args:
            file_path: Path to file
            commit: Commit reference (default: HEAD)

        Returns:
            List of ChangedFile objects (will have 0 or 1 element)
        """
        diff_output = self._run_git(
            "diff", f"{commit}~1..{commit}", "--unified=0", "--", file_path
        )
        return self._parse_diff(diff_output)

    def _parse_diff(self, diff_output: str) -> list[ChangedFile]:
        """Parse git diff output into ChangedFile objects.

        Args:
            diff_output: Raw git diff output

        Returns:
            List of ChangedFile objects
        """
        files: list[ChangedFile] = []
        current_file: ChangedFile | None = None

        # Pattern to match diff header
        # diff --git a/path/to/file b/path/to/file
        file_pattern = re.compile(r"^diff --git a/(.+) b/(.+)$")

        # Pattern to match hunk header
        # @@ -start,count +start,count @@
        hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

        # Pattern to match new/deleted file mode
        new_file_pattern = re.compile(r"^new file mode")
        deleted_file_pattern = re.compile(r"^deleted file mode")

        lines = diff_output.split("\n")
        is_new_file = False
        is_deleted_file = False

        for line in lines:
            # Check for new diff section
            file_match = file_pattern.match(line)
            if file_match:
                # Save previous file if exists
                if current_file:
                    files.append(current_file)

                # Determine change type (will be updated if new/deleted)
                current_file = ChangedFile(
                    path=file_match.group(2),
                    change_type=ChangeType.MODIFIED,
                )
                is_new_file = False
                is_deleted_file = False
                continue

            # Check for new/deleted file
            if current_file:
                if new_file_pattern.match(line):
                    is_new_file = True
                    current_file.change_type = ChangeType.ADDED
                    continue
                if deleted_file_pattern.match(line):
                    is_deleted_file = True
                    current_file.change_type = ChangeType.DELETED
                    continue

            # Parse hunk header
            hunk_match = hunk_pattern.match(line)
            if hunk_match and current_file:
                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2) or 1)
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4) or 1)

                if old_count > 0 and not is_new_file:
                    current_file.deleted_lines.append(
                        (old_start, old_start + old_count - 1)
                    )
                if new_count > 0 and not is_deleted_file:
                    current_file.added_lines.append(
                        (new_start, new_start + new_count - 1)
                    )

        # Don't forget the last file
        if current_file:
            files.append(current_file)

        return files

    def has_changes(self) -> bool:
        """Check if there are any uncommitted changes.

        Returns:
            True if there are changes, False otherwise
        """
        status = self._run_git("status", "--porcelain")
        return bool(status.strip())

    def get_current_commit(self) -> str:
        """Get the current commit hash.

        Returns:
            Short commit hash
        """
        return self._run_git("rev-parse", "--short", "HEAD").strip()
