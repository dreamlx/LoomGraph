"""Repository indexing pipeline.

This module implements the full indexing pipeline as defined in
docs/api/DATA_CONTRACT.md Section 5 (Full Rebuild Strategy).

Pipeline:
1. Scan code files in repository
2. Parse files using codeindex
3. Inject into LightRAG via HTTP API
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from loomgraph.core.injector import inject_parse_result
from loomgraph.core.lightrag_client import LightRAGClient
from loomgraph.core.models import IndexResult, ParseResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# File extensions to index
CODE_EXTENSIONS: set[str] = {
    # Python
    ".py",
    ".pyi",
    # JavaScript/TypeScript
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    # Java/Kotlin
    ".java",
    ".kt",
    ".kts",
    # Go
    ".go",
    # Rust
    ".rs",
    # Ruby
    ".rb",
    # PHP
    ".php",
    # C/C++
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    # C#
    ".cs",
    # Swift
    ".swift",
    # Scala
    ".scala",
}

# Directories to skip
SKIP_DIRS: set[str] = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    "node_modules",
    "vendor",
    "venv",
    ".venv",
    "env",
    ".env",
    "build",
    "dist",
    "target",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    ".coverage",
    "htmlcov",
    "eggs",
    "*.egg-info",
}


def scan_code_files(
    repo_path: str | Path,
    extensions: set[str] | None = None,
    skip_dirs: set[str] | None = None,
) -> list[Path]:
    """Scan repository for code files.

    Args:
        repo_path: Path to the repository root
        extensions: File extensions to include (default: CODE_EXTENSIONS)
        skip_dirs: Directory names to skip (default: SKIP_DIRS)

    Returns:
        List of code file paths
    """
    repo = Path(repo_path)
    exts = extensions or CODE_EXTENSIONS
    skip = skip_dirs or SKIP_DIRS

    files: list[Path] = []

    for path in repo.rglob("*"):
        # Skip directories
        if path.is_dir():
            continue

        # Skip files in excluded directories
        if any(part in skip for part in path.parts):
            continue

        # Include only code files
        if path.suffix.lower() in exts:
            files.append(path)

    # Sort for deterministic ordering
    files.sort()
    logger.info(f"Found {len(files)} code files in {repo_path}")
    return files


async def index_repository(
    repo_path: str | Path,
    client: LightRAGClient,
    parse_file: Callable[[Path], ParseResult],
    *,
    clear_existing: bool = True,
    batch_size: int = 10,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> IndexResult:
    """Index a repository using the full rebuild strategy.

    MVP Strategy (ADR-006):
    1. Delete all existing entities for this repo (if clear_existing=True)
    2. Scan all code files
    3. Parse and inject each file

    Args:
        repo_path: Path to the repository
        client: LightRAGClient for HTTP API calls
        parse_file: Function to parse a file (from codeindex)
        clear_existing: Whether to delete existing data first (not implemented in MVP)
        batch_size: Number of files to process before progress callback
        on_progress: Optional callback(message, current, total)

    Returns:
        IndexResult with counts and any errors

    Example:
        >>> from loomgraph.core import LightRAGClient
        >>> from codeindex import parse_file
        >>> client = LightRAGClient("http://localhost:3001")
        >>> result = await index_repository("/repo", client, parse_file)
        >>> print(f"Indexed {result.entities} entities")
    """
    repo = Path(repo_path)
    errors: list[str] = []
    skipped_files: list[str] = []

    # Step 1: Clear existing data if requested
    # Note: MVP doesn't implement clearing, just log a warning
    if clear_existing:
        logger.warning("clear_existing=True but clearing is not implemented in MVP")

    # Step 2: Scan code files
    files = scan_code_files(repo)
    total_files = len(files)
    total_entities = 0
    total_relations = 0

    if on_progress:
        on_progress("Scanning complete", 0, total_files)

    # Step 3: Process each file
    for i, file_path in enumerate(files):
        try:
            # Parse file
            result = parse_file(file_path)

            if result.error:
                logger.warning(f"Parse error in {file_path}: {result.error}")
                skipped_files.append(str(file_path))
                continue

            if not result.symbols:
                # No symbols to index
                continue

            # Inject into LightRAG via HTTP API
            inject_result = await inject_parse_result(client, result)
            total_entities += inject_result.entities
            total_relations += inject_result.relations
            errors.extend(inject_result.errors)

            # Progress callback
            if on_progress and (i + 1) % batch_size == 0:
                on_progress(f"Processing {file_path.name}", i + 1, total_files)

        except Exception as e:
            error_msg = f"Failed to index {file_path}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            skipped_files.append(str(file_path))

    if on_progress:
        on_progress("Indexing complete", total_files, total_files)

    return IndexResult(
        repo_path=str(repo),
        files=total_files - len(skipped_files),
        entities=total_entities,
        relations=total_relations,
        errors=errors,
        skipped_files=skipped_files,
    )


async def index_file(
    file_path: str | Path,
    client: LightRAGClient,
    parse_file: Callable[[Path], ParseResult],
) -> IndexResult:
    """Index a single file.

    Useful for incremental updates in future versions.

    Args:
        file_path: Path to the file
        client: LightRAGClient for HTTP API
        parse_file: Parse function

    Returns:
        IndexResult for the single file
    """
    path = Path(file_path)

    # Parse
    result = parse_file(path)
    if result.error:
        return IndexResult(
            repo_path=str(path.parent),
            files=0,
            entities=0,
            relations=0,
            errors=[f"Parse error: {result.error}"],
            skipped_files=[str(path)],
        )

    if not result.symbols:
        return IndexResult(
            repo_path=str(path.parent),
            files=1,
            entities=0,
            relations=0,
        )

    # Inject via HTTP API
    inject_result = await inject_parse_result(client, result)

    return IndexResult(
        repo_path=str(path.parent),
        files=1,
        entities=inject_result.entities,
        relations=inject_result.relations,
        errors=inject_result.errors,
    )
