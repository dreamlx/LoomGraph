"""Repository indexing pipeline.

This module implements the full indexing pipeline as defined in
docs/api/DATA_CONTRACT.md Section 5 (Full Rebuild Strategy).

Pipeline:
1. Scan code files in repository
2. Parse files using codeindex
3. Generate embeddings using Jina
4. Inject into LightRAG
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loomgraph.core.injector import inject_parse_result
from loomgraph.core.mapper import detect_language
from loomgraph.core.models import IndexResult, ParseResult

if TYPE_CHECKING:
    from loomgraph.embedding.base import EmbeddingClient

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
    rag: Any,  # LightRAG instance
    embedding_client: EmbeddingClient,
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
    3. Parse, embed, and inject each file

    Args:
        repo_path: Path to the repository
        rag: LightRAG instance with acreate_entity/acreate_relation
        embedding_client: Client for generating embeddings
        parse_file: Function to parse a file (from codeindex)
        clear_existing: Whether to delete existing data first
        batch_size: Number of files to process before progress callback
        on_progress: Optional callback(message, current, total)

    Returns:
        IndexResult with counts and any errors

    Example:
        >>> from lightrag import LightRAG
        >>> from codeindex import parse_file
        >>> rag = LightRAG(...)
        >>> embedding = JinaEmbeddingClient()
        >>> result = await index_repository("/repo", rag, embedding, parse_file)
        >>> print(f"Indexed {result.entities} entities")
    """
    repo = Path(repo_path)
    errors: list[str] = []
    skipped_files: list[str] = []

    # Step 1: Clear existing data if requested
    if clear_existing:
        try:
            await _clear_repo_entities(rag, str(repo))
            logger.info(f"Cleared existing entities for {repo}")
        except Exception as e:
            logger.warning(f"Failed to clear existing entities: {e}")
            errors.append(f"Clear failed: {e}")

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

            # Generate embeddings
            texts = [s.signature or s.name for s in result.symbols]
            embed_result = await embedding_client.embed(texts)
            embedding_map = {
                s.name: emb for s, emb in zip(result.symbols, embed_result.embeddings)
            }

            # Inject into LightRAG
            inject_result = await inject_parse_result(rag, result, embedding_map)
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


async def _clear_repo_entities(rag: Any, repo_path: str) -> None:
    """Clear all entities belonging to a repository.

    This queries for all entities with file_path starting with repo_path
    and removes them from the graph storage.

    Args:
        rag: LightRAG instance
        repo_path: Repository path prefix to match
    """
    # Note: This implementation depends on LightRAG's graph_storage API
    # The actual implementation may need adjustment based on LightRAG's API
    if hasattr(rag, "graph_storage") and hasattr(rag.graph_storage, "remove_nodes"):
        # Query entities by file_path prefix
        # This is a placeholder - actual query depends on LightRAG API
        entities = await _get_entities_by_file_prefix(rag, repo_path)
        if entities:
            node_ids = [e["entity_name"] for e in entities]
            await rag.graph_storage.remove_nodes(node_ids)
            logger.info(f"Removed {len(node_ids)} entities from {repo_path}")


async def _get_entities_by_file_prefix(rag: Any, prefix: str) -> list[dict[str, Any]]:
    """Get all entities with file_path starting with prefix.

    Note: This is a placeholder implementation. The actual query
    depends on LightRAG's graph storage query capabilities.
    """
    # Placeholder - actual implementation depends on LightRAG API
    # This might use:
    # - Direct Cypher query via Apache AGE
    # - LightRAG's query API
    # - Direct SQL query on the underlying tables
    return []


async def index_file(
    file_path: str | Path,
    rag: Any,
    embedding_client: EmbeddingClient,
    parse_file: Callable[[Path], ParseResult],
) -> IndexResult:
    """Index a single file.

    Useful for incremental updates in future versions.

    Args:
        file_path: Path to the file
        rag: LightRAG instance
        embedding_client: Embedding client
        parse_file: Parse function

    Returns:
        IndexResult for the single file
    """
    path = Path(file_path)
    language = detect_language(path)
    errors: list[str] = []

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

    # Embed
    texts = [s.signature or s.name for s in result.symbols]
    embed_result = await embedding_client.embed(texts)
    embedding_map = {s.name: emb for s, emb in zip(result.symbols, embed_result.embeddings)}

    # Inject
    inject_result = await inject_parse_result(rag, result, embedding_map)

    return IndexResult(
        repo_path=str(path.parent),
        files=1,
        entities=inject_result.entities,
        relations=inject_result.relations,
        errors=inject_result.errors,
    )
