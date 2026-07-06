"""workspace delete — #95: must remove the .db file, not just clear tables.

`list_workspaces` enumerates `*.db` on disk, so a delete that only drops the
in-db tables leaves an empty shell that keeps reappearing in `workspace list`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from loomgraph.cli._workspace import _async_workspace_delete
from loomgraph.core.config import reset_settings
from loomgraph.storage.factory import create_graph_store


@pytest.fixture(autouse=True)
def reset_global_settings() -> None:
    reset_settings()
    yield
    reset_settings()


def _storage_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "LOOMGRAPH_STORAGE__DB_PATH", str(tmp_path / "{workspace}.db")
    )
    reset_settings()


async def test_workspace_delete_removes_db_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """delete must unlink <name>.db (the file), not just drop its tables."""
    _storage_at(tmp_path, monkeypatch)
    store = await create_graph_store(workspace="deleteme")
    await store.insert_custom_kg(
        [{"entity_name": "a.b", "entity_type": "function"}], [], []
    )
    await store.close()
    db_file = tmp_path / "deleteme.db"
    assert db_file.exists()  # precondition

    await _async_workspace_delete("deleteme")

    assert not db_file.exists()
    assert not (tmp_path / "deleteme.db-wal").exists()
    assert not (tmp_path / "deleteme.db-shm").exists()


async def test_workspace_delete_drops_from_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After delete, the workspace no longer appears in list_workspaces."""
    _storage_at(tmp_path, monkeypatch)
    s1 = await create_graph_store(workspace="keep")
    await s1.close()
    s2 = await create_graph_store(workspace="gone")
    await s2.close()
    disc = await create_graph_store(workspace=None)
    listed = await disc.list_workspaces()
    await disc.close()
    assert "gone" in listed and "keep" in listed

    await _async_workspace_delete("gone")

    disc2 = await create_graph_store(workspace=None)
    listed2 = await disc2.list_workspaces()
    await disc2.close()
    assert "gone" not in listed2
    assert "keep" in listed2  # sibling untouched


async def test_workspace_delete_idempotent_on_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting a workspace that doesn't exist is a no-op success (no shell
    created, no error)."""
    _storage_at(tmp_path, monkeypatch)
    result = await _async_workspace_delete("never_existed")
    assert result["deleted_workspace"] == "never_existed"
    assert not (tmp_path / "never_existed.db").exists()
