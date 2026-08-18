"""Symbol extraction from changed files."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loomgraph.core.impact.models import ChangedFile, ChangedSymbol, ChangeType


class ExtractorError(Exception):
    """Exception raised for extraction errors."""

    pass


@dataclass
class ChangedSymbolExtractor:
    """Extracts code symbols from changed files.

    Uses codeindex to parse files and identify which symbols
    were affected by the changes.
    """

    repo_path: Path = Path(".")

    def extract_from_files(self, files: list[ChangedFile]) -> list[ChangedSymbol]:
        """Extract changed symbols from a list of changed files.

        Args:
            files: List of ChangedFile objects

        Returns:
            List of ChangedSymbol objects
        """
        symbols: list[ChangedSymbol] = []

        for file in files:
            file_symbols = self._extract_from_file(file)
            symbols.extend(file_symbols)

        return symbols

    def _extract_from_file(self, file: ChangedFile) -> list[ChangedSymbol]:
        """Extract changed symbols from a single file.

        Args:
            file: ChangedFile object

        Returns:
            List of ChangedSymbol objects
        """
        file_path = self.repo_path / file.path

        # For deleted files, we can't parse them
        if file.change_type == ChangeType.DELETED:
            # Try to get the file content from git
            return self._extract_from_deleted_file(file)

        # For new files, all symbols are "added"
        if file.change_type == ChangeType.ADDED:
            return self._extract_all_symbols(file_path, file, ChangeType.ADDED)

        # For modified files, find symbols that overlap with changed lines
        return self._extract_modified_symbols(file_path, file)

    def _extract_from_deleted_file(self, file: ChangedFile) -> list[ChangedSymbol]:
        """Extract symbols from a deleted file using git show.

        Args:
            file: ChangedFile object for a deleted file

        Returns:
            List of ChangedSymbol representing deleted symbols
        """
        # For now, just return a placeholder
        # TODO: Parse from git show HEAD~1:path
        return [
            ChangedSymbol(
                name=f"<deleted:{Path(file.path).stem}>",
                file=file.path,
                change_type=ChangeType.DELETED,
                lines_changed=0,
            )
        ]

    def _extract_all_symbols(
        self, file_path: Path, file: ChangedFile, change_type: ChangeType
    ) -> list[ChangedSymbol]:
        """Extract all symbols from a file (for new files).

        Args:
            file_path: Path to the file
            file: ChangedFile object
            change_type: The change type to assign

        Returns:
            List of ChangedSymbol objects
        """
        if not file_path.exists():
            return []

        symbols_data = self._run_codeindex(file_path)
        result: list[ChangedSymbol] = []

        for symbol in symbols_data:
            result.append(
                ChangedSymbol(
                    name=symbol.get("name", ""),
                    file=file.path,
                    change_type=change_type,
                    line_start=symbol.get("line_start", 0),
                    line_end=symbol.get("line_end", 0),
                    lines_changed=symbol.get("line_end", 0)
                    - symbol.get("line_start", 0)
                    + 1,
                )
            )

        return result

    def _extract_modified_symbols(
        self, file_path: Path, file: ChangedFile
    ) -> list[ChangedSymbol]:
        """Extract symbols that were modified in a file.

        Args:
            file_path: Path to the file
            file: ChangedFile object with line ranges

        Returns:
            List of ChangedSymbol objects
        """
        if not file_path.exists():
            return []

        symbols_data = self._run_codeindex(file_path)
        result: list[ChangedSymbol] = []

        # Combine added and deleted lines to get all changed ranges
        changed_ranges = file.added_lines + file.deleted_lines

        for symbol in symbols_data:
            symbol_start = symbol.get("line_start", 0)
            symbol_end = symbol.get("line_end", 0)

            # Check if symbol overlaps with any changed range
            for range_start, range_end in changed_ranges:
                if self._ranges_overlap(
                    symbol_start, symbol_end, range_start, range_end
                ):
                    result.append(
                        ChangedSymbol(
                            name=symbol.get("name", ""),
                            file=file.path,
                            change_type=ChangeType.MODIFIED,
                            line_start=symbol_start,
                            line_end=symbol_end,
                            lines_changed=self._count_changed_lines(
                                symbol_start, symbol_end, changed_ranges
                            ),
                        )
                    )
                    break  # Don't add same symbol multiple times

        return result

    def _ranges_overlap(
        self, start1: int, end1: int, start2: int, end2: int
    ) -> bool:
        """Check if two line ranges overlap.

        Args:
            start1, end1: First range
            start2, end2: Second range

        Returns:
            True if ranges overlap
        """
        return start1 <= end2 and start2 <= end1

    def _count_changed_lines(
        self, symbol_start: int, symbol_end: int, ranges: list[tuple[int, int]]
    ) -> int:
        """Count how many lines in a symbol were changed.

        Args:
            symbol_start: Symbol start line
            symbol_end: Symbol end line
            ranges: List of changed line ranges

        Returns:
            Number of changed lines within the symbol
        """
        count = 0
        for range_start, range_end in ranges:
            # Find overlap
            overlap_start = max(symbol_start, range_start)
            overlap_end = min(symbol_end, range_end)
            if overlap_start <= overlap_end:
                count += overlap_end - overlap_start + 1
        return count

    def _run_codeindex(self, file_path: Path) -> list[dict[str, Any]]:
        """Run codeindex CLI to get symbols from a file.

        Uses codeindex parse CLI command for loose coupling.
        See: https://github.com/dreamlx/codeindex docs/guides/loomgraph-integration.md

        Args:
            file_path: Path to the file

        Returns:
            List of symbol dicts from codeindex
        """
        try:
            # Invoke via the venv python (`sys.executable -m codeindex.cli`),
            # never a bare `codeindex` PATH lookup — otherwise a stale codeindex
            # elsewhere on PATH (e.g. pipx) shadows the pinned `ai-codeindex`
            # dep (#76 PATH bypass; #120, same class as the graph-export entry).
            result = subprocess.run(
                [sys.executable, "-m", "codeindex.cli", "parse", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Exit code 1 = file not found, 2 = unsupported type, 3 = parse error
            if result.returncode in (1, 2):
                return []

            # Parse JSON output
            data = json.loads(result.stdout)

            # Return symbols list (format matches codeindex v0.13.0+)
            return list(data.get("symbols", []))

        except subprocess.TimeoutExpired:
            return []
        except json.JSONDecodeError:
            return []
        except FileNotFoundError:
            # codeindex not installed
            return []
        except Exception:
            return []
