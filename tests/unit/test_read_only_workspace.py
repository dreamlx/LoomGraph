"""#235: read-only workspace queries must not create SQLite files."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from loomgraph.cli._common import prepare_workspace_store
from loomgraph.cli._indexing import _async_index
from loomgraph.cli._search import _async_find
from loomgraph.cli._workspace import _async_workspace_info, _async_workspace_list
from loomgraph.cli.main import main
from loomgraph.core.config import reset_settings
from loomgraph.storage.factory import create_graph_store


@pytest.fixture(autouse=True)
def reset_global_settings() -> None:
    reset_settings()
    yield
    reset_settings()


def _configure_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "LOOMGRAPH_STORAGE__DB_PATH", str(tmp_path / "{workspace}.db")
    )
    reset_settings()


async def _workspace_names() -> list[str]:
    result = await _async_workspace_list()
    return result["workspaces"]


@pytest.mark.parametrize(
    "args",
    [
        ["find", "needle", "--workspace", "project:missing"],
        ["search", "needle", "--workspace", "project:missing"],
        ["graph", "needle", "--workspace", "project:missing"],
        ["topology", "--workspace", "project:missing"],
        ["deps", "--workspace", "project:missing"],
        ["impact", "HEAD", "--workspace", "project:missing"],
        ["overview", "--no-summary", "--workspace", "project:missing"],
        ["check", "--workspace", "project:missing"],
        ["workspace", "info", "--workspace", "project:missing"],
    ],
)
def test_read_only_commands_do_not_create_missing_workspace(
    args: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every shared-query entry point fails cleanly without a ghost workspace."""
    _configure_storage(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, args)

    assert result.exit_code == 1
    assert json.loads(result.stdout)["success"] is False
    assert list(tmp_path.glob("*.db")) == []
    listed = CliRunner().invoke(main, ["workspace", "list"])
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["data"]["workspaces"] == []


async def test_auto_detected_missing_workspace_does_not_create_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh Git branch follows the same no-create path as explicit ``-w``."""
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "loomgraph.cli._common.get_auto_workspace",
        lambda _workspace: "project:fresh-branch",
    )

    with pytest.raises(click.ClickException, match="No workspace found"):
        await prepare_workspace_store()
    with pytest.raises(click.ClickException, match="not found"):
        await _async_workspace_info(None, None)

    assert list(tmp_path.glob("*.db")) == []
    assert await _workspace_names() == []


async def test_existing_main_workspace_remains_a_read_only_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unindexed branch uses its indexed main workspace without a shell."""
    _configure_storage(tmp_path, monkeypatch)
    main_store = await create_graph_store("project:main")
    try:
        await main_store.insert_custom_kg(
            [{"entity_name": "pkg.needle", "entity_type": "function"}], [], []
        )
    finally:
        await main_store.close()

    direct_ws, direct_store = await prepare_workspace_store("project:main")
    try:
        assert direct_ws == "project:main"
    finally:
        await direct_store.close()

    info = await _async_workspace_info("project:main", None)
    assert info["entities"] == 1

    resolved, store = await prepare_workspace_store("project:feature")
    try:
        assert resolved == "project:main"
        assert [e["entity_name"] for e in await store.get_all_entities()] == [
            "pkg.needle"
        ]
    finally:
        await store.close()

    found = await _async_find("needle", workspace="project:feature")
    assert [match["entity"] for match in found["matches"]] == ["pkg.needle"]
    assert not (tmp_path / "project:feature.db").exists()
    assert await _workspace_names() == ["project:main"]


async def test_indexing_still_explicitly_creates_its_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The no-create rule is limited to query preparation, not indexing."""
    _configure_storage(tmp_path, monkeypatch)

    await _async_index([], [], "project:created", clear=False)

    assert (tmp_path / "project:created.db").exists()
    assert await _workspace_names() == ["project:created"]
