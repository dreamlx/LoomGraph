"""CLI commands for status, setup, and utility operations."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import click

from loomgraph import __version__
from loomgraph.cli._common import (
    ErrorCode,
    get_auto_workspace,
    output_error,
    output_partial_error,
    output_success,
)
from loomgraph.cli._deps_check import check_codeindex, check_embedding, check_storage
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings


@main.command()
def status() -> None:
    """Check system status and dependencies.

    Returns status of all required dependencies:
    - codeindex: Code parsing tool
    - storage: SQLite + sqlite-vec local backend
    - embedding: Jina Code V2 embedding service (optional, only needed for vec0)
    """
    settings = get_settings()

    codeindex_status = check_codeindex()
    storage_status = check_storage(settings)
    embedding_status = check_embedding(settings)

    dependencies = {
        "codeindex": codeindex_status,
        "storage": storage_status,
        "embedding": embedding_status,
    }

    suggestions: list[str] = []
    if not codeindex_status.get("installed"):
        suggestions.append("Install codeindex: pip install ai-codeindex")
    if not storage_status.get("connected"):
        suggestions.append(
            "Storage backend unavailable; check sqlite-vec install"
        )
    if not embedding_status.get("connected"):
        suggestions.append(
            "Embedding service not reachable (semantic search vec0 will be empty)"
        )

    # Workspace context: pull stats from local SqliteGraphStore if available.
    current_ws = get_auto_workspace(None)
    ws_context: dict[str, Any] = {"name": current_ws}
    if storage_status.get("connected"):
        try:
            import asyncio

            from loomgraph.storage.factory import create_graph_store

            async def _stats() -> dict[str, Any]:
                store = await create_graph_store(workspace=current_ws)
                try:
                    return await store.get_graph_stats()
                finally:
                    close = getattr(store, "close", None)
                    if close is not None:
                        await close()

            stats = asyncio.run(_stats())
            ws_context["entities"] = stats.get("entity_count", 0)
            ws_context["relations"] = stats.get("relation_count", 0)
        except Exception:
            ws_context["entities"] = "unknown"

    data: dict[str, Any] = {
        "version": __version__,
        "workspace": ws_context,
        "config": {
            "storage_backend": settings.storage.backend,
            "db_path_template": settings.storage.db_path,
            "embedding_url": settings.embedding.api_url,
            "llm_provider": settings.llm.provider,
        },
        "dependencies": dependencies,
    }

    if not storage_status.get("connected"):
        output_partial_error(
            code=ErrorCode.DEPENDENCIES_MISSING,
            message="Storage backend unavailable",
            suggestions=suggestions,
            data=data,
        )
    elif suggestions:
        data["warnings"] = suggestions
        output_success(data)
    else:
        output_success(data)


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
