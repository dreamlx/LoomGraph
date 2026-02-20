"""LoomGraph CLI - AI Agent Friendly Interface.

Design: CLI outputs JSON for machine parsing by AI Agent (Claude Code).
See docs/api/CLI_DESIGN.md for full specification.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import click

from loomgraph import __version__
from loomgraph.core.config import get_settings


def _setup_logging(verbose: bool, quiet: bool) -> None:
    """Configure logging to stderr only.

    Ensures JSON output on stdout is never polluted by log messages.
    """
    if quiet:
        logging.disable(logging.CRITICAL)
        return

    level = logging.DEBUG if verbose else logging.WARNING
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logging.root.handlers = [handler]
    logging.root.setLevel(level)


# ============================================
# Workspace Auto-Detection
# ============================================

def get_auto_workspace(workspace: str | None) -> str | None:
    """Get workspace, auto-detecting from current directory if not specified.

    Priority:
    1. Explicit --workspace argument
    2. Current directory name (auto-detect)

    Returns:
        Workspace name or None for default
    """
    if workspace:
        return workspace

    # Auto-detect from current directory name
    cwd = Path.cwd()
    return cwd.name


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
    GIT_ERROR = "GIT_ERROR"
    NO_CHANGES = "NO_CHANGES"


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


def check_lightrag_api(settings: Any) -> dict[str, Any]:
    """Check LightRAG API connectivity."""
    try:
        import httpx

        # trust_env=False to bypass system proxy (H200 is internal)
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            response = client.get(f"{settings.lightrag.api_url}/health")
        if response.status_code == 200:
            data = response.json()
            return {
                "connected": True,
                "status": data.get("status", "unknown"),
                "version": data.get("core_version", "unknown"),
                "url": settings.lightrag.api_url,
            }
        return {"connected": False, "error": f"HTTP {response.status_code}"}
    except ImportError:
        return {"connected": False, "error": "httpx not installed"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def check_embedding(settings: Any) -> dict[str, Any]:
    """Check embedding service availability."""
    try:
        import httpx

        # trust_env=False to bypass system proxy (H200 is internal)
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            response = client.get(f"{settings.embedding.base_url}/health")
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


# ============================================
# CLI Commands
# ============================================

@click.group()
@click.version_option(version=__version__, prog_name="loomgraph")
@click.option("--verbose", "-v", is_flag=True, help="Show debug logs on stderr")
@click.option("--quiet", "-q", is_flag=True, help="Suppress all non-JSON output")
def main(verbose: bool, quiet: bool) -> None:
    """LoomGraph: Enterprise Code Intelligence Engine.

    AI Agent friendly CLI for code indexing, search, and graph queries.
    All commands output JSON for machine parsing.
    """
    _setup_logging(verbose, quiet)


@main.command()
def status() -> None:
    """Check system status and dependencies.

    Returns status of all required dependencies:
    - codeindex: Code parsing tool
    - lightrag: LightRAG API service
    - embedding: Vector embedding service (optional, managed by LightRAG)
    """
    settings = get_settings()

    # Check all dependencies
    codeindex_status = check_codeindex()
    lightrag_status = check_lightrag_api(settings)
    embedding_status = check_embedding(settings)

    dependencies = {
        "codeindex": codeindex_status,
        "lightrag_api": lightrag_status,
        "embedding": embedding_status,
    }

    # Collect suggestions for missing dependencies
    suggestions: list[str] = []
    if not codeindex_status.get("installed"):
        suggestions.append("Install codeindex: pip install matrix-codeindex")
    if not lightrag_status.get("connected"):
        suggestions.append(f"Check LightRAG API at {settings.lightrag.api_url}")
    if not embedding_status.get("connected"):
        suggestions.append("Embedding service not reachable (may be managed by LightRAG)")

    data = {
        "version": __version__,
        "config": {
            "lightrag_url": settings.lightrag.api_url,
            "embedding_url": settings.embedding.base_url,
        },
        "dependencies": dependencies,
    }

    if not lightrag_status.get("connected"):
        output_partial_error(
            code=ErrorCode.DEPENDENCIES_MISSING,
            message="LightRAG API not available",
            suggestions=suggestions,
            data=data,
        )
    elif suggestions:
        # Non-critical issues
        data["warnings"] = suggestions
        output_success(data)
    else:
        output_success(data)


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
        result = asyncio.run(_async_index_pipeline(parse_results, clear, workspace))
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


async def _async_index_pipeline(
    parse_results: dict[str, Any],
    clear: bool,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run the async indexing pipeline.

    Two-pass batch approach via graph endpoints:
    1. Collect all entities and relations from all files
    2. Create all entities first, then all relations (solves cross-file ordering)
    """
    from loomgraph.core.injector import collect_kg_data
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

    # Pass 1: Collect all entities and relations from all files
    files_scanned = 0
    files_indexed = 0
    files_skipped = 0
    skipped_files: list[dict[str, str]] = []
    all_entities: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []

    results = parse_results.get("results", [])
    files_scanned = len(results)

    for file_result in results:
        path = Path(file_result.get("path", ""))

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
            all_entities.extend(entities)
            all_relations.extend(relations)
            files_indexed += 1
        except Exception as e:
            files_skipped += 1
            skipped_files.append({
                "path": str(path),
                "reason": "mapping_error",
                "detail": str(e),
            })

    # Pass 2: Create entities → stubs → relations via graph endpoints
    entities_created = 0
    relations_created = 0
    external_stubs = 0
    injection_errors: list[str] = []

    if all_entities or all_relations:
        try:
            kg_result = await client.batch_create_graph(all_entities, all_relations)
            details = kg_result.get("details", {})
            entities_created = details.get("entities_count", 0)
            relations_created = details.get("relationships_count", 0)
            external_stubs = details.get("external_stubs", 0)
            if kg_result.get("errors"):
                injection_errors.extend(kg_result["errors"])
        except LightRAGAPIError as e:
            injection_errors.append(f"Batch injection failed: {e.message}")
        except Exception as e:
            injection_errors.append(f"Batch injection failed: {e}")

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
    type=click.Choice(["local", "global", "hybrid", "naive"]),
    default="hybrid",
    help="LightRAG query mode",
)
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option("--limit", "-n", default=10, help="Number of results (not yet implemented)")
def search(query: str, mode: str, workspace: str | None, limit: int) -> None:
    """Search the code index using LightRAG.

    QUERY: Natural language query about the code
    """
    try:
        result = asyncio.run(_async_search(query, mode, workspace))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Search failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_search(query: str, mode: str, workspace: str | None = None) -> dict[str, Any]:
    """Run async search via LightRAG API."""
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    result = await client.query(query, mode=mode)

    return {
        "query": query,
        "mode": mode,
        "response": result.get("response", ""),
        "references": result.get("references", []),
    }


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
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def graph(entity_name: str, direction: str, depth: int, relation_type: str, workspace: str | None) -> None:
    """Query entity relationships in the graph.

    ENTITY_NAME: Name of the entity to query

    Note: Currently uses LightRAG query API. Direct graph traversal
    requires codeindex to output call relationships.
    """
    try:
        result = asyncio.run(_async_graph_query(entity_name, direction, relation_type, workspace))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Graph query failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_graph_query(
    entity_name: str,
    direction: str,
    relation_type: str,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run async graph query via LightRAG API."""
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    result: dict[str, Any] = {"entity": entity_name}

    # Build query based on direction
    if direction in ("callers", "both"):
        query = f"What functions or methods call {entity_name}?"
        callers_result = await client.query(query, mode="local")
        result["callers"] = {
            "query": query,
            "response": callers_result.get("response", ""),
        }

    if direction in ("callees", "both"):
        query = f"What functions or methods does {entity_name} call?"
        callees_result = await client.query(query, mode="local")
        result["callees"] = {
            "query": query,
            "response": callees_result.get("response", ""),
        }

    result["note"] = "Graph traversal uses LightRAG query. For precise call graph, codeindex needs to output call relationships."

    return result


@main.command()
@click.argument("target", default="HEAD")
@click.option("--staged", is_flag=True, help="Analyze staged changes instead of commit")
@click.option(
    "--base",
    default=None,
    help="Base branch/commit for range comparison (e.g., main..HEAD)",
)
@click.option("--depth", default=2, help="Caller traversal depth")
@click.option("--file", "file_path", type=click.Path(), help="Analyze specific file")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def impact(target: str, staged: bool, base: str | None, depth: int, file_path: str | None, workspace: str | None) -> None:
    """Analyze impact of code changes.

    TARGET: Commit reference (default: HEAD)

    Examples:
        loomgraph impact HEAD           # Analyze latest commit
        loomgraph impact --staged       # Analyze staged changes
        loomgraph impact main..HEAD     # Analyze branch diff
        loomgraph impact abc123         # Analyze specific commit
    """
    try:
        result = asyncio.run(_async_impact(target, staged, base, depth, file_path, workspace))

        # Add risk assessment
        from loomgraph.core.impact import RiskAssessor
        assessor = RiskAssessor()
        from loomgraph.core.impact import ImpactResult, ChangedSymbol, ChangeType, Caller

        # Reconstruct ImpactResult for risk assessment
        changed_symbols = [
            ChangedSymbol(
                name=s["name"],
                file=s["file"],
                change_type=ChangeType(s["change_type"]),
                lines_changed=s.get("lines_changed", 0),
            )
            for s in result.get("changed_symbols", [])
        ]
        direct_callers = [
            Caller(
                name=c["name"],
                file=c["file"],
                line=c.get("line", 0),
                depth=1,
            )
            for c in result.get("impact_analysis", {}).get("direct_callers", [])
        ]
        indirect_callers = [
            Caller(
                name=c["name"],
                file=c["file"],
                line=c.get("line", 0),
                depth=c.get("depth", 2),
            )
            for c in result.get("impact_analysis", {}).get("indirect_callers", [])
        ]

        impact_result = ImpactResult(
            commit=result.get("commit", ""),
            changed_symbols=changed_symbols,
            direct_callers=direct_callers,
            indirect_callers=indirect_callers,
            affected_modules=result.get("impact_analysis", {}).get("affected_modules", []),
            affected_tests=result.get("impact_analysis", {}).get("affected_tests", []),
        )

        risk = assessor.assess(impact_result)
        result["risk_assessment"] = risk.to_dict()

        output_success(result)

    except Exception as e:
        # Check if it's a git error
        error_msg = str(e)
        if "Invalid commit" in error_msg or "git" in error_msg.lower():
            output_error(
                code=ErrorCode.INVALID_INPUT,
                message=error_msg,
                suggestion="Check if the commit exists: git log --oneline",
            )
        else:
            output_error(
                code=ErrorCode.LIGHTRAG_ERROR,
                message=f"Impact analysis failed: {e}",
                suggestion="Check LightRAG status with: loomgraph status",
            )


async def _async_impact(
    target: str,
    staged: bool,
    base: str | None,
    depth: int,
    file_path: str | None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run async impact analysis."""
    from loomgraph.core.lightrag_client import LightRAGClient
    from loomgraph.core.impact import ImpactAnalyzer

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    analyzer = ImpactAnalyzer(
        lightrag_client=client,
        repo_path=Path("."),
        max_depth=depth,
    )

    if staged:
        result = await analyzer.analyze_staged()
    elif base:
        # Parse range like "main..HEAD"
        if ".." in target:
            parts = target.split("..")
            result = await analyzer.analyze_branch_diff(parts[0], parts[1] if len(parts) > 1 else "HEAD")
        else:
            result = await analyzer.analyze_branch_diff(base, target)
    else:
        result = await analyzer.analyze_commit(target)

    return result.to_dict()


@main.command()
@click.option("--since", default="HEAD~1", help="Git ref to compare from (default: HEAD~1)")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def update(since: str, workspace: str | None) -> None:
    """Warm update: index only changed files since last commit.

    Detects git changes and incrementally adds new entities/relations
    without clearing existing data.

    Examples:
        loomgraph update                 # Changes since last commit
        loomgraph update --since HEAD~3  # Changes in last 3 commits
        loomgraph update --since main    # Changes since branching from main
        loomgraph update --workspace erp # Update in specific workspace
    """
    import time

    from loomgraph.core.git import GitError, get_changed_files, get_current_commit, is_git_repository
    from loomgraph.core.indexer import CODE_EXTENSIONS

    start_time = time.time()
    repo_path = Path(".")

    # Check if in git repo
    if not is_git_repository(repo_path):
        output_error(
            code=ErrorCode.GIT_ERROR,
            message="Not a git repository",
            suggestion="Run this command from within a git repository",
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
        result = asyncio.run(_async_warm_update(changed_files, repo_path, workspace))
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Warm update failed: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["since"] = since
    result["current_commit"] = current_commit

    output_success(result)


async def _async_warm_update(
    changed_files: list[Path],
    repo_path: Path,
    workspace: str | None,
) -> dict[str, Any]:
    """Run async warm update pipeline.

    Two-pass batch approach via graph endpoints.
    """
    from loomgraph.core.injector import collect_kg_data
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

    files_indexed = 0
    files_skipped = 0
    errors: list[str] = []
    all_entities: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []

    # Pass 1: Parse all changed files and collect KG data
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
            all_entities.extend(entities)
            all_relations.extend(relations)
            files_indexed += 1
        except Exception as e:
            files_skipped += 1
            errors.append(f"Mapping failed {path}: {e}")

    # Pass 2: Create entities → stubs → relations via graph endpoints
    entities_created = 0
    relations_created = 0
    external_stubs = 0

    if all_entities or all_relations:
        try:
            kg_result = await client.batch_create_graph(all_entities, all_relations)
            details = kg_result.get("details", {})
            entities_created = details.get("entities_count", 0)
            relations_created = details.get("relationships_count", 0)
            external_stubs = details.get("external_stubs", 0)
            if kg_result.get("errors"):
                errors.extend(kg_result["errors"])
        except LightRAGAPIError as e:
            errors.append(f"Batch injection failed: {e.message}")
        except Exception as e:
            errors.append(f"Batch injection failed: {e}")

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



@main.command()
@click.option("--depth", "-d", default=2, help="Directory depth for module grouping")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def deps(depth: int, workspace: str | None) -> None:
    """Analyze module-level dependencies.

    Queries the knowledge graph to build a module dependency map.
    """
    try:
        result = asyncio.run(_async_deps(depth, workspace))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Dependency analysis failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_deps(depth: int, workspace: str | None = None) -> dict[str, Any]:
    """Run async dependency analysis."""
    from loomgraph.core.deps import DepsAnalyzer
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    analyzer = DepsAnalyzer(client=client, depth=depth)
    result = await analyzer.analyze()
    return result.to_dict()


@main.command()
@click.option("--depth", "-d", default=2, help="Directory depth for module grouping")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option("--no-summary", is_flag=True, help="Skip LLM module summaries")
def overview(depth: int, workspace: str | None, no_summary: bool) -> None:
    """Generate project module overview.

    Queries the knowledge graph for a high-level view of all modules,
    optionally including LLM-generated summaries.
    """
    try:
        result = asyncio.run(_async_overview(depth, workspace, no_summary))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Overview generation failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_overview(
    depth: int, workspace: str | None = None, no_summary: bool = False
) -> dict[str, Any]:
    """Run async overview analysis."""
    from loomgraph.core.lightrag_client import LightRAGClient
    from loomgraph.core.overview import OverviewAnalyzer

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    analyzer = OverviewAnalyzer(client=client, depth=depth)
    result = await analyzer.analyze(no_summary=no_summary)
    return result.to_dict()


@main.group()
def workspace() -> None:
    """Manage workspaces."""
    pass


@workspace.command("list")
def workspace_list() -> None:
    """List all workspaces.

    Returns all available workspaces from LightRAG.
    """
    try:
        result = asyncio.run(_async_workspace_list())
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Workspace list failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_workspace_list() -> dict[str, Any]:
    """Run async workspace list."""
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
    )

    workspaces = await client.list_workspaces()
    return {
        "workspaces": workspaces,
        "count": len(workspaces),
    }


@workspace.command("info")
@click.argument("name", default=None, required=False)
@click.option("--workspace", "-w", "ws_option", default=None, help="Workspace name (overrides NAME)")
def workspace_info(name: str | None, ws_option: str | None) -> None:
    """Show workspace details and statistics.

    NAME: Workspace name (default: auto-detect from current directory)
    """
    try:
        result = asyncio.run(_async_workspace_info(name, ws_option))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Workspace info failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_workspace_info(name: str | None, ws_option: str | None) -> dict[str, Any]:
    """Run async workspace info."""
    from collections import Counter

    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()

    # name argument takes priority, then -w option, then auto-detect
    ws_name = name or get_auto_workspace(ws_option)

    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=ws_name,
    )

    entities = await client.get_all_entities()
    relations = await client.get_all_relations()

    # Count entity types
    entity_types: dict[str, int] = dict(Counter(
        e.get("entity_type", "unknown") for e in entities
    ))

    # Count relation types
    relation_types: dict[str, int] = dict(Counter(
        r.get("keywords", r.get("relation_type", "unknown")) for r in relations
    ))

    return {
        "name": ws_name,
        "entities": len(entities),
        "relations": len(relations),
        "entity_types": entity_types,
        "relation_types": relation_types,
    }


@workspace.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation (required for AI Agent use)")
def workspace_delete(name: str, yes: bool) -> None:
    """Delete a workspace and all its data.

    NAME: Workspace name to delete

    Requires --yes flag to confirm deletion (AI Agent friendly, no interactive prompt).
    """
    if not yes:
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=f"Refusing to delete workspace '{name}' without confirmation",
            suggestion=f"Add --yes flag: loomgraph workspace delete {name} --yes",
        )
        return

    try:
        result = asyncio.run(_async_workspace_delete(name))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Workspace delete failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_workspace_delete(name: str) -> dict[str, Any]:
    """Run async workspace delete."""
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=name,
    )

    await client.delete_all()

    return {
        "deleted_workspace": name,
        "message": "Workspace deleted",
    }


# ─── Cross-workspace comparison ─────────────────────────────────


@main.command()
@click.option("--ws1", required=True, help="First workspace name")
@click.option("--ws2", required=True, help="Second workspace name")
def compare(ws1: str, ws2: str) -> None:
    """Compare entities and relations between two workspaces."""
    try:
        result = asyncio.run(_async_compare(ws1, ws2))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Workspace comparison failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_compare(ws1: str, ws2: str) -> dict[str, Any]:
    """Run async cross-workspace comparison."""
    from loomgraph.core.compare import CompareAnalyzer
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client1 = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=ws1,
    )
    client2 = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=ws2,
    )

    analyzer = CompareAnalyzer(client1=client1, client2=client2, ws1=ws1, ws2=ws2)
    result = await analyzer.analyze()
    return result.to_dict()


@main.command()
@click.option("--entity", "-e", required=True, help="Entity name to search")
@click.option(
    "--workspaces", "-w", default=None,
    help="Comma-separated workspace names (default: all)",
)
def similar(entity: str, workspaces: str | None) -> None:
    """Find similar entities across workspaces."""
    try:
        result = asyncio.run(_async_similar(entity, workspaces))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Similar entity search failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_similar(
    entity: str, workspaces: str | None = None
) -> dict[str, Any]:
    """Run async cross-workspace similarity search."""
    from loomgraph.core.lightrag_client import LightRAGClient
    from loomgraph.core.similar import SimilarAnalyzer

    settings = get_settings()

    # Resolve workspace list
    if workspaces:
        ws_names = [w.strip() for w in workspaces.split(",")]
    else:
        # Fetch all workspaces from LightRAG
        temp_client = LightRAGClient(
            base_url=settings.lightrag.api_url,
            timeout=settings.lightrag.api_timeout,
        )
        ws_names = await temp_client.list_workspaces()

    # Create a client per workspace
    clients = [
        LightRAGClient(
            base_url=settings.lightrag.api_url,
            timeout=settings.lightrag.api_timeout,
            workspace=ws,
        )
        for ws in ws_names
    ]

    analyzer = SimilarAnalyzer(clients=clients, workspace_names=ws_names)
    result = await analyzer.analyze(entity)
    return result.to_dict()


@main.command("install-skills")
def install_skills() -> None:
    """Install LoomGraph skills to ~/.claude/skills/.

    Copies bundled skills from the wheel package to the Claude Code
    skills directory. Safe to run multiple times (overwrites existing).
    """
    # Locate bundled _skills directory
    skills_src = Path(__file__).parent.parent / "_skills"
    if not skills_src.exists():
        output_error(
            code=ErrorCode.FILE_NOT_FOUND,
            message="Bundled skills not found in package",
            suggestion="Reinstall loomgraph: pip install --force-reinstall loomgraph",
        )
        return

    skills_dest = Path.home() / ".claude" / "skills"
    skills_dest.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for skill_dir in skills_src.iterdir():
        if skill_dir.is_dir() and not skill_dir.name.startswith("."):
            dest = skills_dest / skill_dir.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill_dir, dest)
            installed.append(skill_dir.name)

    output_success({
        "skills_installed": installed,
        "skills_dir": str(skills_dest),
        "count": len(installed),
    })


@main.command("setup-config")
@click.option(
    "--lightrag-url",
    prompt="LightRAG API URL",
    help="LightRAG API endpoint URL",
)
@click.option(
    "--embedding-url",
    prompt="Embedding API URL (leave empty if managed by LightRAG)",
    default="",
    help="Embedding service URL (optional)",
)
def setup_config(lightrag_url: str, embedding_url: str) -> None:
    """Generate LoomGraph configuration file interactively.

    Creates ~/.config/loomgraph/config.yaml with service connection settings.
    """
    import yaml as _yaml

    config: dict[str, Any] = {
        "lightrag": {
            "api_url": lightrag_url,
            "api_timeout": 30.0,
        },
    }

    if embedding_url:
        config["embedding"] = {
            "base_url": embedding_url,
        }

    config_dir = Path.home() / ".config" / "loomgraph"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"

    with open(config_path, "w") as f:
        _yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    output_success({
        "config_path": str(config_path),
        "lightrag_url": lightrag_url,
        "embedding_url": embedding_url or "(managed by LightRAG)",
    })


@main.command()
def version() -> None:
    """Show version information."""
    output_success({
        "version": __version__,
        "python": sys.version.split()[0],
    })


if __name__ == "__main__":
    main()
