"""CLI commands for workspace management and cross-workspace analysis."""

from __future__ import annotations

import asyncio
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings


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
