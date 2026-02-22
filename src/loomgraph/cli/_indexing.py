"""CLI commands for indexing, embedding, and injection."""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings


@main.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--clear/--no-clear", default=True, help="Clear old data before indexing")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def index(repo_path: str, clear: bool, workspace: str | None) -> None:
    """Index a code repository (one-step pipeline).

    Calls: codeindex scan → embed → inject

    REPO_PATH: Directory path to index
    """
    import time

    start_time = time.time()
    repo = Path(repo_path).resolve()

    # Step 1: Check codeindex
    click.echo("[1/3] Checking codeindex installation...", err=True)
    codeindex_status = check_codeindex()
    if not codeindex_status.get("installed"):
        output_error(
            code=ErrorCode.CODEINDEX_NOT_FOUND,
            message="codeindex command not found in PATH",
            suggestion="Install codeindex: pip install matrix-codeindex",
            docs="https://github.com/dreamlx/codeindex#installation",
        )
        return

    # Step 2: Run codeindex scan
    click.echo(f"[2/3] Scanning {repo.name}/ with codeindex (this may take a while)...", err=True)
    try:
        result = subprocess.run(
            ["codeindex", "scan", str(repo), "--output", "json"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        if result.returncode != 0:
            output_error(
                code=ErrorCode.CODEINDEX_FAILED,
                message=f"codeindex scan failed: {result.stderr}",
                suggestion="Check codeindex logs for details",
            )
            return

        parse_results = json.loads(result.stdout)
        file_count = len(parse_results.get("results", []))
        click.echo(f"       Scan complete: {file_count} files parsed.", err=True)

    except subprocess.TimeoutExpired:
        output_error(
            code=ErrorCode.CODEINDEX_TIMEOUT,
            message="codeindex scan timed out after 5 minutes",
            suggestion="Try indexing a smaller directory",
        )
        return
    except json.JSONDecodeError as e:
        output_error(
            code=ErrorCode.CODEINDEX_FAILED,
            message=f"Failed to parse codeindex output: {e}",
            suggestion="Check codeindex version compatibility",
        )
        return
    except Exception as e:
        output_error(
            code=ErrorCode.CODEINDEX_FAILED,
            message=f"codeindex error: {e}",
        )
        return

    # Step 3: Run embed + inject asynchronously
    click.echo("[3/3] Injecting into LightRAG (entities → relations)...", err=True)
    try:
        result = asyncio.run(_async_index_pipeline(parse_results, clear, workspace, repo_path=repo))
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Pipeline error: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["repo_path"] = str(repo)
    click.echo(f"       Done in {result['duration_seconds']}s.", err=True)

    output_success(result)


async def _async_index_pipeline(
    parse_results: dict[str, Any],
    clear: bool,
    workspace: str | None = None,
    repo_path: Path | None = None,
) -> dict[str, Any]:
    """Run the async indexing pipeline via insert_custom_kg.

    Single-pass batch approach:
    1. Collect all entities, relations, and chunks from all files
    2. Create external stubs for missing targets
    3. Inject everything in one insert_custom_kg call

    Args:
        parse_results: Output from codeindex scan --output json
        clear: Whether to clear existing data before indexing
        workspace: Optional workspace name
        repo_path: Repo root path; if set, file paths are stored as relative paths
    """
    from loomgraph.core.injector import build_chunks, collect_kg_data, create_external_stubs
    from loomgraph.core.lightrag_client import LightRAGAPIError, LightRAGClient
    from loomgraph.core.models import (
        Call,
        Import,
        Inheritance,
        ParseResult,
        Symbol,
    )

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    # Step 0: Clear existing data if requested (Cold Rebuild)
    cleared = False
    if clear:
        try:
            await client.delete_all()
            cleared = True
        except LightRAGAPIError:
            pass  # Will be reported in result

    # Step 1: Collect all entities, relations, and chunks from all files
    files_scanned = 0
    files_indexed = 0
    files_skipped = 0
    skipped_files: list[dict[str, str]] = []
    all_entities: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []

    results = parse_results.get("results", [])
    files_scanned = len(results)

    for file_result in results:
        path = Path(file_result.get("path", ""))

        # Convert absolute path to relative (for clean source_id in graph)
        if repo_path and path.is_absolute():
            with contextlib.suppress(ValueError):
                path = path.relative_to(repo_path)

        if file_result.get("error"):
            files_skipped += 1
            skipped_files.append({
                "path": str(path),
                "reason": "parse_error",
                "detail": file_result["error"],
            })
            continue

        symbols = [
            Symbol(
                name=s.get("name", ""),
                kind=s.get("kind", ""),
                signature=s.get("signature", ""),
                docstring=s.get("docstring", ""),
                line_start=s.get("line_start", 0),
                line_end=s.get("line_end", 0),
            )
            for s in file_result.get("symbols", [])
        ]

        calls = [
            Call(
                caller=c.get("caller", ""),
                callee=c.get("callee", ""),
                line=c.get("line", 0),
                is_method=c.get("is_method", False),
            )
            for c in file_result.get("calls", [])
        ]

        inheritances = [
            Inheritance(
                child=i.get("child", ""),
                parent=i.get("parent", ""),
            )
            for i in file_result.get("inheritances", [])
        ]

        imports = [
            Import(
                module=i.get("module", ""),
                alias=i.get("alias"),
                names=i.get("names", []),
            )
            for i in file_result.get("imports", [])
        ]

        parse_result = ParseResult(
            path=path,
            symbols=symbols,
            calls=calls,
            inheritances=inheritances,
            imports=imports,
            module_docstring=file_result.get("module_docstring", ""),
            file_lines=file_result.get("file_lines", 0),
        )

        try:
            entities, relations = collect_kg_data(parse_result)
            chunks = build_chunks(parse_result)
            all_entities.extend(entities)
            all_relations.extend(relations)
            all_chunks.extend(chunks)
            files_indexed += 1
        except Exception as e:
            files_skipped += 1
            skipped_files.append({
                "path": str(path),
                "reason": "mapping_error",
                "detail": str(e),
            })

    # Step 2: Create external stubs for missing relation targets
    stubs = create_external_stubs(all_entities, all_relations)
    all_entities.extend(stubs)
    external_stubs = len(stubs)

    # Step 3: Single insert_custom_kg call
    entities_created = 0
    relations_created = 0
    injection_errors: list[str] = []

    if all_entities or all_relations:
        try:
            kg_result = await client.insert_custom_kg(
                all_entities, all_relations, all_chunks,
            )
            details = kg_result.get("details", {})
            entities_created = details.get("entities_count", len(all_entities))
            relations_created = details.get("relationships_count", len(all_relations))
        except LightRAGAPIError as e:
            injection_errors.append(f"insert_custom_kg failed: {e.message}")
        except Exception as e:
            injection_errors.append(f"insert_custom_kg failed: {e}")

    result: dict[str, Any] = {
        "mode": "cold_rebuild" if clear else "append",
        "files_scanned": files_scanned,
        "files_indexed": files_indexed,
        "files_skipped": files_skipped,
        "entities_created": entities_created,
        "relations_created": relations_created,
        "skipped_files": skipped_files,
    }

    if external_stubs:
        result["external_stubs"] = external_stubs

    if clear:
        result["cleared"] = cleared

    if injection_errors:
        result["injection_errors"] = injection_errors[:10]
        if len(injection_errors) > 10:
            result["injection_errors_total"] = len(injection_errors)

    return result


@main.command()
@click.argument("input_json", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option("--batch-size", default=32, help="Batch size for embedding")
def embed(input_json: str, output: str | None, batch_size: int) -> None:
    """Generate embeddings from ParseResult JSON.

    INPUT_JSON: codeindex scan output JSON file
    """
    # Load input
    try:
        with open(input_json) as f:
            parse_results = json.load(f)
    except json.JSONDecodeError as e:
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=f"Invalid JSON: {e}",
            suggestion="Ensure input is valid codeindex JSON output",
        )
        return
    except FileNotFoundError:
        output_error(
            code=ErrorCode.FILE_NOT_FOUND,
            message=f"File not found: {input_json}",
        )
        return

    # Run embedding
    try:
        result = asyncio.run(_async_embed(parse_results, batch_size))
    except Exception as e:
        output_error(
            code=ErrorCode.EMBEDDING_FAILED,
            message=f"Embedding failed: {e}",
            suggestion="Check embedding service status with: loomgraph status",
        )
        return

    # Output
    if output:
        with open(output, "w") as f:
            json.dump({"success": True, "data": result}, f, indent=2)
        output_success({"output_file": output, "count": result["count"]})
    else:
        output_success(result)


async def _async_embed(parse_results: dict[str, Any], batch_size: int) -> dict[str, Any]:
    """Run async embedding."""
    from loomgraph.core.config import get_settings
    from loomgraph.embedding.jina import JinaEmbeddingClient

    settings = get_settings()
    settings.embedding.batch_size = batch_size
    client = JinaEmbeddingClient(settings.embedding)

    # Collect all symbols
    texts: list[str] = []
    names: list[str] = []

    for file_result in parse_results.get("results", []):
        for symbol in file_result.get("symbols", []):
            name = symbol.get("name", "")
            signature = symbol.get("signature", name)
            texts.append(signature)
            names.append(name)

    if not texts:
        return {
            "embeddings": {},
            "model": settings.embedding.model,
            "dimension": settings.embedding.dimension,
            "count": 0,
        }

    # Generate embeddings
    result = await client.embed(texts)

    # Build output
    embeddings = dict(zip(names, result.embeddings, strict=False))

    return {
        "embeddings": embeddings,
        "model": result.model,
        "dimension": len(result.embeddings[0]) if result.embeddings else 0,
        "count": len(embeddings),
    }


@main.command()
@click.argument("parse_json", type=click.Path(exists=True))
@click.argument("embeddings_json", type=click.Path(exists=True))
@click.option("--clear/--no-clear", default=False, help="Clear old data first")
def inject(parse_json: str, embeddings_json: str, clear: bool) -> None:
    """Inject ParseResult + Embeddings into LightRAG.

    PARSE_JSON: codeindex scan output
    EMBEDDINGS_JSON: embed command output
    """
    # Load inputs
    try:
        with open(parse_json) as f:
            parse_results = json.load(f)
        with open(embeddings_json) as f:
            embeddings_data = json.load(f)
    except json.JSONDecodeError as e:
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=f"Invalid JSON: {e}",
        )
        return
    except FileNotFoundError as e:
        output_error(
            code=ErrorCode.FILE_NOT_FOUND,
            message=f"File not found: {e}",
        )
        return

    # Extract embeddings
    embeddings = embeddings_data.get("data", {}).get("embeddings", {})
    if not embeddings and "embeddings" in embeddings_data:
        embeddings = embeddings_data["embeddings"]

    # Run injection
    try:
        result = asyncio.run(_async_inject(parse_results, embeddings, clear))
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Injection failed: {e}",
            suggestion="Check database connection with: loomgraph status",
        )
        return

    output_success(result)


async def _async_inject(
    parse_results: dict[str, Any],
    embeddings: dict[str, list[float]],
    clear: bool,
) -> dict[str, Any]:
    """Run async injection into LightRAG."""
    import time

    start_time = time.time()

    # Note: Full LightRAG integration pending
    # For now, count what would be injected
    entities_created = 0
    relations_created = 0
    entities_updated = 0

    for file_result in parse_results.get("results", []):
        symbols = file_result.get("symbols", [])
        calls = file_result.get("calls", [])
        inheritances = file_result.get("inheritances", [])
        imports = file_result.get("imports", [])

        entities_created += len(symbols)
        relations_created += len(calls) + len(inheritances) + len(imports)

    duration = time.time() - start_time

    return {
        "entities_created": entities_created,
        "relations_created": relations_created,
        "entities_updated": entities_updated,
        "duration_seconds": round(duration, 2),
    }


@main.command()
@click.option("--since", default="HEAD~1", help="Git ref to compare from (default: HEAD~1)")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option("--files", default=None, help="Comma-separated list of files to update (skips git detection)")
@click.option("--lightrag-url", default=None, help="Override LightRAG API URL from config")
@click.option("--embedding-url", default=None, help="Override embedding API URL from config")
def update(
    since: str,
    workspace: str | None,
    files: str | None,
    lightrag_url: str | None,
    embedding_url: str | None,
) -> None:
    """Warm update: index only changed files since last commit.

    Detects git changes and incrementally adds new entities/relations
    without clearing existing data.

    Examples:
        loomgraph update                 # Changes since last commit
        loomgraph update --since HEAD~3  # Changes in last 3 commits
        loomgraph update --since main    # Changes since branching from main
        loomgraph update --workspace erp # Update in specific workspace
        loomgraph update --files src/foo.py,src/bar.py  # Specific files (CI/CD)
    """
    import time

    from loomgraph.core.git import (
        GitError,
        get_changed_files,
        get_current_commit,
        is_git_repository,
    )
    from loomgraph.core.indexer import CODE_EXTENSIONS

    start_time = time.time()
    repo_path = Path(".")
    current_commit = None

    # If --files provided, parse and use directly (skip git detection)
    if files:
        changed_files = [Path(f.strip()) for f in files.split(",")]
        # Validate files exist
        for file_path in changed_files:
            full_path = repo_path / file_path
            if not full_path.exists():
                output_error(
                    code=ErrorCode.INVALID_INPUT,
                    message=f"File not found: {file_path}",
                    suggestion="Check file paths and ensure they exist",
                )
                return
    else:
        # Git-based detection (original flow)
        # Check if in git repo
        if not is_git_repository(repo_path):
            output_error(
                code=ErrorCode.GIT_ERROR,
                message="Not a git repository",
                suggestion="Run this command from within a git repository or use --files",
            )
            return

        # Get current commit for reference
        try:
            current_commit = get_current_commit(repo_path)
        except GitError as e:
            output_error(
                code=ErrorCode.GIT_ERROR,
                message=str(e),
            )
            return

        # Get changed files
        try:
            changed_files = get_changed_files(
                since=since,
                repo_path=repo_path,
                extensions=CODE_EXTENSIONS,
            )
        except GitError as e:
            output_error(
                code=ErrorCode.GIT_ERROR,
                message=str(e),
                suggestion="Check if the git reference exists: git log --oneline",
            )
            return

    if not changed_files:
        output_success({
            "mode": "warm",
            "message": "No code files changed",
            "since": since,
            "current_commit": current_commit,
            "files_changed": 0,
        })
        return

    # Check codeindex
    codeindex_status = check_codeindex()
    if not codeindex_status.get("installed"):
        output_error(
            code=ErrorCode.CODEINDEX_NOT_FOUND,
            message="codeindex command not found",
            suggestion="Install codeindex: pip install matrix-codeindex",
        )
        return

    # Run warm update pipeline
    try:
        result = asyncio.run(
            _async_warm_update(
                changed_files,
                repo_path,
                workspace,
                lightrag_url=lightrag_url,
                embedding_url=embedding_url,
            )
        )
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Warm update failed: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    if not files:  # Only add git info if git-based
        result["since"] = since
        result["current_commit"] = current_commit

    output_success(result)


async def _async_warm_update(
    changed_files: list[Path],
    repo_path: Path,
    workspace: str | None,
    lightrag_url: str | None = None,
    embedding_url: str | None = None,
) -> dict[str, Any]:
    """Run async warm update pipeline via delete_by_source + insert_custom_kg.

    Three-step approach:
    1. Parse changed files, collect entities/relations/chunks
    2. Delete old data for changed files (delete_by_source)
    3. Re-inject via single insert_custom_kg call
    """
    from loomgraph.core.injector import build_chunks, collect_kg_data, create_external_stubs
    from loomgraph.core.lightrag_client import LightRAGAPIError, LightRAGClient
    from loomgraph.core.models import (
        Call,
        Import,
        Inheritance,
        ParseResult,
        Symbol,
    )

    settings = get_settings()
    # Use provided URLs or fall back to config
    api_url = lightrag_url if lightrag_url else settings.lightrag.api_url
    client = LightRAGClient(
        base_url=api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    files_indexed = 0
    files_skipped = 0
    errors: list[str] = []
    all_entities: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []
    source_ids: list[str] = []

    # Step 1: Parse all changed files and collect KG data
    for file_path in changed_files:
        full_path = repo_path / file_path

        if not full_path.exists():
            files_skipped += 1
            errors.append(f"File not found: {file_path}")
            continue

        try:
            result = subprocess.run(
                ["codeindex", "parse", str(full_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                files_skipped += 1
                errors.append(f"Parse failed: {file_path}")
                continue

            file_result = json.loads(result.stdout)

        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            files_skipped += 1
            errors.append(f"Parse error {file_path}: {e}")
            continue

        if file_result.get("error"):
            files_skipped += 1
            errors.append(f"Parse error: {file_result.get('error')}")
            continue

        path = Path(file_result.get("file_path", str(full_path)))

        symbols = [
            Symbol(
                name=s.get("name", ""),
                kind=s.get("kind", ""),
                signature=s.get("signature", ""),
                docstring=s.get("docstring", ""),
                line_start=s.get("line_start", 0),
                line_end=s.get("line_end", 0),
            )
            for s in file_result.get("symbols", [])
        ]

        calls = [
            Call(
                caller=c.get("caller", ""),
                callee=c.get("callee", ""),
                line=c.get("line", 0),
                is_method=c.get("is_method", False),
            )
            for c in file_result.get("calls", [])
        ]

        inheritances = [
            Inheritance(
                child=i.get("child", ""),
                parent=i.get("parent", ""),
            )
            for i in file_result.get("inheritances", [])
        ]

        imports = [
            Import(
                module=i.get("module", ""),
                alias=i.get("alias"),
                names=i.get("names", []),
            )
            for i in file_result.get("imports", [])
        ]

        parse_result = ParseResult(
            path=path,
            symbols=symbols,
            calls=calls,
            inheritances=inheritances,
            imports=imports,
            module_docstring=file_result.get("module_docstring", ""),
            file_lines=file_result.get("file_lines", 0),
        )

        try:
            entities, relations = collect_kg_data(parse_result)
            chunks = build_chunks(parse_result)
            all_entities.extend(entities)
            all_relations.extend(relations)
            all_chunks.extend(chunks)
            source_ids.append(str(path))
            files_indexed += 1
        except Exception as e:
            files_skipped += 1
            errors.append(f"Mapping failed {path}: {e}")

    # Step 2: Delete old data for changed files
    if source_ids:
        try:
            await client.delete_by_source(source_ids)
        except LightRAGAPIError as e:
            errors.append(f"delete_by_source failed: {e.message}")
        except Exception as e:
            errors.append(f"delete_by_source failed: {e}")

    # Step 3: Create external stubs + single insert_custom_kg call
    stubs = create_external_stubs(all_entities, all_relations)
    all_entities.extend(stubs)
    external_stubs = len(stubs)

    entities_created = 0
    relations_created = 0

    if all_entities or all_relations:
        try:
            kg_result = await client.insert_custom_kg(
                all_entities, all_relations, all_chunks,
            )
            details = kg_result.get("details", {})
            entities_created = details.get("entities_count", len(all_entities))
            relations_created = details.get("relationships_count", len(all_relations))
        except LightRAGAPIError as e:
            errors.append(f"insert_custom_kg failed: {e.message}")
        except Exception as e:
            errors.append(f"insert_custom_kg failed: {e}")

    result: dict[str, Any] = {
        "mode": "warm",
        "files_changed": len(changed_files),
        "files_indexed": files_indexed,
        "files_skipped": files_skipped,
        "entities_created": entities_created,
        "relations_created": relations_created,
    }

    if external_stubs:
        result["external_stubs"] = external_stubs

    if errors:
        result["errors"] = errors[:5]
        if len(errors) > 5:
            result["errors_total"] = len(errors)

    return result
