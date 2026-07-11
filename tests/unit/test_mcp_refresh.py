"""MCP `refresh` tool — reactive working-tree re-index (#66 push/pull gap).

`_async_refresh` is the async core (lives in cli/_indexing.py next to
`_async_update`); the MCP `handle` + TOOL_SPEC wrapper lands alongside it.
These tests cover the core's branching: force_full cold rebuild, path-scoped
incremental, working-tree incremental (incl. untracked), noop on clean tree,
and non-git whole-tree fallback. MCP envelope + registration tests are added
in the same module once the tool wrapper exists.
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from loomgraph.cli._indexing import _async_refresh


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Patch `_async_refresh`'s deps with controllable mocks.

    Defaults: git repo, clean working tree, empty export. Each test overrides
    the return_value it cares about.
    """
    from loomgraph.io.export_reader import ImportSummary

    ns = types.SimpleNamespace()
    ns.store = MagicMock()
    ns.store.insert_custom_kg = AsyncMock()
    ns.store.get_graph_stats = AsyncMock(return_value={"entities": 0, "relations": 0})
    ns.create = AsyncMock(return_value=ns.store)
    ns.export = MagicMock(return_value=([], [], ImportSummary(), []))
    ns.is_git = MagicMock(return_value=True)
    ns.worktree = MagicMock(return_value=[])
    ns.incr = AsyncMock(
        return_value={
            "incremental": True,
            "changed_files": [],
            "entities_created": 0,
            "relations_created": 0,
            "embedded": 0,
            "gc_source_ids": 0,
            "store_stats": {},
        }
    )
    ns.ingest = AsyncMock(
        return_value={
            "cleared": False,
            "entities_created": 0,
            "relations_created": 0,
            "embedded": 0,
            "store_stats": {},
        }
    )
    monkeypatch.setattr("loomgraph.storage.factory.create_graph_store", ns.create)
    monkeypatch.setattr("loomgraph.cli._indexing.run_graph_export", ns.export)
    monkeypatch.setattr("loomgraph.cli._indexing.is_git_repository", ns.is_git)
    monkeypatch.setattr("loomgraph.cli._indexing.get_working_tree_files", ns.worktree)
    monkeypatch.setattr("loomgraph.cli._indexing.ingest_incremental", ns.incr)
    monkeypatch.setattr("loomgraph.cli._indexing.ingest", ns.ingest)
    return ns


async def test_refresh_incremental_uses_working_tree(
    fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """Git repo, no path → ingest_incremental over get_working_tree_files."""
    fakes.is_git.return_value = True
    fakes.worktree.return_value = [Path("src/a.py")]

    result = await _async_refresh(
        workspace="ws", repo=tmp_path, path=None, force_full=False
    )

    assert result["mode"] == "warm_incremental"
    fakes.export.assert_called_once()
    assert fakes.incr.call_args.kwargs["changed_files"] == {"src/a.py"}
    fakes.ingest.assert_not_called()


async def test_refresh_passes_untracked_through_to_incremental(
    fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """Untracked file returned by get_working_tree_files reaches ingest_incremental.

    (get_working_tree_files itself is tested in test_git.py to use
    `git status --porcelain`, which catches untracked; here we pin the
    pass-through so refresh never silently drops them.)
    """
    fakes.is_git.return_value = True
    fakes.worktree.return_value = [Path("brand_new.py")]

    await _async_refresh(workspace="ws", repo=tmp_path, path=None, force_full=False)

    assert fakes.incr.call_args.kwargs["changed_files"] == {"brand_new.py"}


async def test_refresh_force_full_clears_and_rebuilds(
    fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """force_full=True → ingest(clear=True) cold rebuild; incremental skipped."""
    fakes.ingest.return_value = {
        "cleared": True,
        "entities_created": 5,
        "relations_created": 0,
        "embedded": 0,
        "store_stats": {},
    }

    result = await _async_refresh(
        workspace="ws", repo=tmp_path, path=None, force_full=True
    )

    assert result["mode"] == "cold_rebuild"
    assert fakes.ingest.call_args.kwargs["clear"] is True
    fakes.incr.assert_not_called()
    fakes.worktree.assert_not_called()  # force_full short-circuits before worktree scan


async def test_refresh_path_file_scoped(
    fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """path=<file> → changed_files == {that file} exactly."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text("x = 1\n")

    result = await _async_refresh(
        workspace="ws", repo=tmp_path, path="src/auth.py", force_full=False
    )

    assert result["mode"] == "warm_incremental"
    assert fakes.incr.call_args.kwargs["changed_files"] == {"src/auth.py"}
    fakes.worktree.assert_not_called()  # path takes precedence over working-tree scan


async def test_refresh_path_dir_prefix_expands(
    fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """path=<dir> → changed_files ⊆ existing files under that dir."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth").mkdir()
    (tmp_path / "src" / "auth" / "x.py").write_text("x\n")
    (tmp_path / "src" / "auth" / "y.py").write_text("y\n")

    result = await _async_refresh(
        workspace="ws", repo=tmp_path, path="src/auth", force_full=False
    )

    changed = fakes.incr.call_args.kwargs["changed_files"]
    assert changed == {"src/auth/x.py", "src/auth/y.py"}
    assert result["mode"] == "warm_incremental"


async def test_refresh_path_not_found_raises(
    fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """Non-existent path → ValueError (the MCP handle's safe_call turns this
    into a REFRESH_FAILED envelope)."""
    with pytest.raises(ValueError, match="path not found"):
        await _async_refresh(
            workspace="ws", repo=tmp_path, path="nope.py", force_full=False
        )
    fakes.export.assert_not_called()  # bailed before codeindex export


async def test_refresh_noop_when_clean(
    fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """Clean working tree, no path → mode=noop, codeindex export NOT run."""
    fakes.is_git.return_value = True
    fakes.worktree.return_value = []  # nothing changed

    result = await _async_refresh(
        workspace="ws", repo=tmp_path, path=None, force_full=False
    )

    assert result["mode"] == "noop"
    assert result["changed_files"] == []
    fakes.export.assert_not_called()
    fakes.incr.assert_not_called()


async def test_refresh_non_git_falls_back_to_whole_tree(
    fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """Non-git + no path → whole-tree upsert (ingest clear=False)."""
    fakes.is_git.return_value = False

    result = await _async_refresh(
        workspace="ws", repo=tmp_path, path=None, force_full=False
    )

    assert result["mode"] == "whole_tree_upsert"
    assert fakes.ingest.call_args.kwargs["clear"] is False
    fakes.incr.assert_not_called()
    fakes.worktree.assert_not_called()


async def test_refresh_mcp_envelope_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """handle() wraps the core result in {success: True, data: ...}."""
    from loomgraph.mcp.tools import refresh

    monkeypatch.setattr(
        "loomgraph.mcp.tools.refresh._async_refresh",
        AsyncMock(return_value={"mode": "noop", "changed_files": [], "workspace": "ws"}),
    )

    result = await refresh.handle({})

    assert len(result) == 1 and result[0].type == "text"
    body = json.loads(result[0].text)
    assert body["success"] is True
    assert body["data"]["mode"] == "noop"


async def test_refresh_mcp_envelope_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Core exception → {success: False, error: {code: REFRESH_FAILED, suggestion}}."""
    from loomgraph.mcp.tools import refresh

    monkeypatch.setattr(
        "loomgraph.mcp.tools.refresh._async_refresh",
        AsyncMock(side_effect=FileNotFoundError("codeindex not found")),
    )

    result = await refresh.handle({})

    body = json.loads(result[0].text)
    assert body["success"] is False
    assert body["error"]["code"] == "REFRESH_FAILED"
    assert "codeindex" in body["error"]["suggestion"]


def test_refresh_tool_spec_registered() -> None:
    """The tool must be registered in the server's spec list (wiring guard)."""
    from loomgraph.mcp.server import _TOOL_SPECS

    names = [t.name for t in _TOOL_SPECS]
    assert "loomgraph_refresh" in names, f"refresh missing from {names}"
