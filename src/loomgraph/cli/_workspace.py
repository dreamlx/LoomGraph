"""CLI commands for workspace management and cross-workspace analysis."""

from __future__ import annotations

import asyncio
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli.main import main


@main.group()
def workspace() -> None:
    """Manage workspaces."""
    pass


@workspace.command("list")
def workspace_list() -> None:
    """List all workspaces."""
    try:
        result = asyncio.run(_async_workspace_list())
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Workspace list failed: {e}",
            suggestion="Check service status with: loomgraph status",
        )


async def _async_workspace_list() -> dict[str, Any]:
    """Run async workspace list."""
    from loomgraph.storage.factory import create_graph_store

    store = await create_graph_store(workspace=None)
    workspaces = await store.list_workspaces()
    return {
        "workspaces": workspaces,
        "count": len(workspaces),
    }


@workspace.command("info")
@click.argument("name", default=None, required=False)
@click.option("--workspace", "-w", "ws_option", default=None, help="Workspace name (overrides NAME)")
def workspace_info(name: str | None, ws_option: str | None) -> None:
    """Show workspace details and statistics."""
    try:
        result = asyncio.run(_async_workspace_info(name, ws_option))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Workspace info failed: {e}",
            suggestion="Check service status with: loomgraph status",
        )


async def _async_workspace_info(name: str | None, ws_option: str | None) -> dict[str, Any]:
    """Run async workspace info."""
    from collections import Counter

    from loomgraph.storage.factory import create_graph_store

    # name argument takes priority, then -w option, then auto-detect
    ws_name = name or get_auto_workspace(ws_option)
    store = await create_graph_store(workspace=ws_name)

    entities = await store.get_all_entities()
    relations = await store.get_all_relations()

    entity_types: dict[str, int] = dict(Counter(
        e.get("entity_type", "unknown") for e in entities
    ))
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
    """Delete a workspace and all its data."""
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
            code=ErrorCode.STORAGE_ERROR,
            message=f"Workspace delete failed: {e}",
            suggestion="Check service status with: loomgraph status",
        )


async def _async_workspace_delete(name: str) -> dict[str, Any]:
    """Run async workspace delete.

    Unlinks the workspace's ``<name>.db`` file (plus sqlite WAL/SHM sidecars).
    ``list_workspaces`` enumerates ``*.db`` on disk, so removing the file is
    what actually retires the workspace — the previous behavior (opening the
    store and ``delete_all()``-ing the tables) left an empty ``.db`` shell
    that kept reappearing in ``workspace list`` (#95). Not opening a store
    also avoids creating a shell for a non-existent workspace name.
    """
    from pathlib import Path

    from loomgraph.core.config import get_settings
    from loomgraph.storage.factory import _resolve_db_path

    db_path = _resolve_db_path(get_settings().storage.db_path, name)
    removed: list[str] = []
    for candidate in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate.name)

    return {
        "deleted_workspace": name,
        "removed_files": removed,
        "message": (
            "Workspace deleted" if removed else "Workspace not found (nothing to delete)"
        ),
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
            code=ErrorCode.STORAGE_ERROR,
            message=f"Workspace comparison failed: {e}",
            suggestion="Check service status with: loomgraph status",
        )


async def _async_compare(ws1: str, ws2: str) -> dict[str, Any]:
    """Run async cross-workspace comparison."""
    from loomgraph.core.compare import CompareAnalyzer
    from loomgraph.storage.factory import create_graph_store

    store1 = await create_graph_store(workspace=ws1)
    store2 = await create_graph_store(workspace=ws2)

    analyzer = CompareAnalyzer(client1=store1, client2=store2, ws1=ws1, ws2=ws2)
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
            code=ErrorCode.STORAGE_ERROR,
            message=f"Similar entity search failed: {e}",
            suggestion="Check service status with: loomgraph status",
        )


async def _async_similar(
    entity: str, workspaces: str | None = None
) -> dict[str, Any]:
    """Run async cross-workspace similarity search."""
    from loomgraph.core.similar import SimilarAnalyzer
    from loomgraph.storage.factory import create_graph_store

    # Resolve workspace list
    if workspaces:
        ws_names = [w.strip() for w in workspaces.split(",")]
    else:
        discovery_store = await create_graph_store(workspace=None)
        ws_names = await discovery_store.list_workspaces()

    stores = [await create_graph_store(workspace=ws) for ws in ws_names]

    analyzer = SimilarAnalyzer(clients=stores, workspace_names=ws_names)
    result = await analyzer.analyze(entity)
    return result.to_dict()
