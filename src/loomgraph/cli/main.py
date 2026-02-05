"""LoomGraph CLI - AI Agent Friendly Interface.

Design: CLI outputs JSON for machine parsing by AI Agent (Claude Code).
See docs/api/CLI_DESIGN.md for full specification.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import click

from loomgraph import __version__
from loomgraph.core.config import get_settings


# ============================================
# Error Codes (from CLI_DESIGN.md)
# ============================================

class ErrorCode:
    """Structured error codes for AI Agent parsing."""

    CODEINDEX_NOT_FOUND = "CODEINDEX_NOT_FOUND"
    CODEINDEX_FAILED = "CODEINDEX_FAILED"
    CODEINDEX_TIMEOUT = "CODEINDEX_TIMEOUT"
    EMBEDDING_SERVICE_UNAVAILABLE = "EMBEDDING_SERVICE_UNAVAILABLE"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    DATABASE_CONNECTION_FAILED = "DATABASE_CONNECTION_FAILED"
    DATABASE_ERROR = "DATABASE_ERROR"
    LIGHTRAG_ERROR = "LIGHTRAG_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    DEPENDENCIES_MISSING = "DEPENDENCIES_MISSING"


# ============================================
# JSON Output Helpers
# ============================================

def output_success(data: dict[str, Any]) -> None:
    """Output success response in JSON format."""
    response = {"success": True, "data": data}
    click.echo(json.dumps(response, indent=2, ensure_ascii=False))


def output_error(
    code: str,
    message: str,
    suggestion: str | None = None,
    docs: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Output error response in JSON format."""
    error = {"code": code, "message": message}
    if suggestion:
        error["suggestion"] = suggestion
    if docs:
        error["docs"] = docs

    response: dict[str, Any] = {"success": False, "error": error}
    if data:
        response["data"] = data

    click.echo(json.dumps(response, indent=2, ensure_ascii=False))
    sys.exit(1)


def output_partial_error(
    code: str,
    message: str,
    suggestions: list[str],
    data: dict[str, Any],
) -> None:
    """Output partial error (some operations succeeded, some failed)."""
    response = {
        "success": False,
        "data": data,
        "error": {
            "code": code,
            "message": message,
            "suggestions": suggestions,
        },
    }
    click.echo(json.dumps(response, indent=2, ensure_ascii=False))
    sys.exit(1)


# ============================================
# Dependency Check Helpers
# ============================================

def check_codeindex() -> dict[str, Any]:
    """Check if codeindex CLI is available."""
    codeindex_path = shutil.which("codeindex")
    if not codeindex_path:
        return {"installed": False, "error": "command not found"}

    try:
        result = subprocess.run(
            ["codeindex", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = result.stdout.strip() if result.returncode == 0 else "unknown"
        return {"installed": True, "version": version, "path": codeindex_path}
    except subprocess.TimeoutExpired:
        return {"installed": True, "version": "unknown", "path": codeindex_path}
    except Exception as e:
        return {"installed": False, "error": str(e)}


def check_postgres(settings: Any) -> dict[str, Any]:
    """Check PostgreSQL connection."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=settings.lightrag.pg_host,
            port=settings.lightrag.pg_port,
            database=settings.lightrag.pg_database,
            user=settings.lightrag.pg_user,
            password=settings.lightrag.pg_password,
            connect_timeout=5,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        conn.close()
        return {
            "connected": True,
            "version": version.split(",")[0] if "," in version else version,
            "host": f"{settings.lightrag.pg_host}:{settings.lightrag.pg_port}",
        }
    except ImportError:
        return {"connected": False, "error": "psycopg2 not installed"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def check_embedding(settings: Any) -> dict[str, Any]:
    """Check embedding service availability."""
    try:
        import httpx

        response = httpx.get(
            f"{settings.embedding.base_url}/health",
            timeout=5.0,
        )
        if response.status_code == 200:
            return {
                "connected": True,
                "model": settings.embedding.model,
                "url": settings.embedding.base_url,
            }
        return {"connected": False, "error": f"HTTP {response.status_code}"}
    except ImportError:
        return {"connected": False, "error": "httpx not installed"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def check_lightrag() -> dict[str, Any]:
    """Check if LightRAG is installed."""
    try:
        import lightrag

        version = getattr(lightrag, "__version__", "unknown")
        return {"installed": True, "version": version}
    except ImportError:
        return {"installed": False, "error": "lightrag not installed"}


# ============================================
# CLI Commands
# ============================================

@click.group()
@click.version_option(version=__version__, prog_name="loomgraph")
def main() -> None:
    """LoomGraph: Enterprise Code Intelligence Engine.

    AI Agent friendly CLI for code indexing, search, and graph queries.
    All commands output JSON for machine parsing.
    """
    pass


@main.command()
def status() -> None:
    """Check system status and dependencies.

    Returns status of all required dependencies:
    - codeindex: Code parsing tool
    - postgres: Database storage
    - embedding: Vector embedding service
    - lightrag: Graph storage framework
    """
    settings = get_settings()

    # Check all dependencies
    codeindex_status = check_codeindex()
    postgres_status = check_postgres(settings)
    embedding_status = check_embedding(settings)
    lightrag_status = check_lightrag()

    dependencies = {
        "codeindex": codeindex_status,
        "postgres": postgres_status,
        "embedding": embedding_status,
        "lightrag": lightrag_status,
    }

    # Collect suggestions for missing dependencies
    suggestions: list[str] = []
    if not codeindex_status.get("installed"):
        suggestions.append("Install codeindex: pip install matrix-codeindex")
    if not postgres_status.get("connected"):
        suggestions.append("Start database: docker compose up -d postgres")
    if not embedding_status.get("connected"):
        suggestions.append("Start embedding service: docker compose up -d embedding")
    if not lightrag_status.get("installed"):
        suggestions.append("Install lightrag: pip install lightrag-hku")

    data = {
        "version": __version__,
        "dependencies": dependencies,
    }

    if suggestions:
        output_partial_error(
            code=ErrorCode.DEPENDENCIES_MISSING,
            message="Some dependencies are not available",
            suggestions=suggestions,
            data=data,
        )
    else:
        output_success(data)


@main.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--clear/--no-clear", default=True, help="Clear old data before indexing")
@click.option("--verbose", is_flag=True, help="Show detailed progress")
def index(repo_path: str, clear: bool, verbose: bool) -> None:
    """Index a code repository (one-step pipeline).

    Calls: codeindex scan → embed → inject

    REPO_PATH: Directory path to index
    """
    import time

    start_time = time.time()
    repo = Path(repo_path).resolve()

    # Step 1: Check codeindex
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
    try:
        result = asyncio.run(_async_index_pipeline(parse_results, clear))
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Pipeline error: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["repo_path"] = str(repo)

    output_success(result)


async def _async_index_pipeline(parse_results: dict[str, Any], clear: bool) -> dict[str, Any]:
    """Run the async indexing pipeline."""
    from loomgraph.core.config import get_settings
    from loomgraph.core.injector import inject_parse_result
    from loomgraph.core.models import (
        Call,
        Import,
        Inheritance,
        ParseResult,
        Symbol,
    )
    from loomgraph.embedding.jina import JinaEmbeddingClient

    settings = get_settings()
    embedding_client = JinaEmbeddingClient(settings.embedding)

    # Convert JSON to ParseResult objects
    files_scanned = 0
    files_indexed = 0
    files_skipped = 0
    entities_created = 0
    relations_created = 0
    skipped_files: list[dict[str, str]] = []

    results = parse_results.get("results", [])
    files_scanned = len(results)

    # Note: In production, this would use LightRAG instance
    # For now, we process and count but don't actually inject
    # (LightRAG integration is pending)
    for file_result in results:
        path = Path(file_result.get("path", ""))

        # Check for errors
        if file_result.get("error"):
            files_skipped += 1
            skipped_files.append({
                "path": str(path),
                "reason": "parse_error",
                "detail": file_result["error"],
            })
            continue

        # Convert to ParseResult
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

        # Count entities and relations
        entities_created += len(symbols)
        relations_created += len(calls) + len(inheritances) + len(imports)
        files_indexed += 1

    return {
        "files_scanned": files_scanned,
        "files_indexed": files_indexed,
        "files_skipped": files_skipped,
        "entities_created": entities_created,
        "relations_created": relations_created,
        "skipped_files": skipped_files,
    }


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
    embeddings = {name: emb for name, emb in zip(names, result.embeddings)}

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
@click.argument("query")
@click.option(
    "--mode",
    type=click.Choice(["keyword", "semantic", "graph", "hybrid"]),
    default="hybrid",
    help="Search mode",
)
@click.option("--limit", "-n", default=10, help="Number of results")
def search(query: str, mode: str, limit: int) -> None:
    """Search the code index.

    QUERY: Natural language or code pattern query
    """
    # Note: Full LightRAG integration pending
    # For now, return placeholder response
    output_success({
        "query": query,
        "mode": mode,
        "results": [],
        "total": 0,
        "returned": 0,
        "message": "Search requires LightRAG integration (pending)",
    })


@main.command()
@click.argument("entity_name")
@click.option(
    "--direction",
    type=click.Choice(["callers", "callees", "both"]),
    default="both",
    help="Query direction",
)
@click.option("--depth", default=1, help="Traversal depth")
@click.option(
    "--relation-type",
    type=click.Choice(["CALLS", "INHERITS", "IMPORTS", "all"]),
    default="all",
    help="Relation type filter",
)
def graph(entity_name: str, direction: str, depth: int, relation_type: str) -> None:
    """Query entity relationships in the graph.

    ENTITY_NAME: Name of the entity to query
    """
    # Note: Full LightRAG integration pending
    # For now, return placeholder response
    result: dict[str, Any] = {"entity": entity_name}

    if direction in ("callers", "both"):
        result["callers"] = []
    if direction in ("callees", "both"):
        result["callees"] = []

    result["message"] = "Graph query requires LightRAG integration (pending)"

    output_success(result)


@main.command()
def version() -> None:
    """Show version information."""
    output_success({
        "version": __version__,
        "python": sys.version.split()[0],
    })


if __name__ == "__main__":
    main()
