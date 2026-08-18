"""#184: partial-graph 的机器可读 flag(option 2 修正版,exit 0 不变)。

parser-missing / language-fingerprint 两类 warning 意味着「图缺符号」——
区别于 advisory 类(resolved_ratio hint、test 污染提示是质量信号不是缺符号)。
成功 payload 加 `partial: true` 布尔,agent 解析 stdout JSON 一眼可判,无需
substring 匹配 `warning`。

MCP `_async_refresh` 此前把 warnings 喂完 0-entity gate 后直接丢弃(entity_count>0
时 result 里没有任何字段带出去)—— primary agent surface 上是**真·silent partial**,
这次一并透传(`warning` 字段,与 CLI 同名同构 + `partial` 布尔)。
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main

PARSER_MISSING = (
    "Parser library not installed for java: "
    "pip install tree-sitter-java (or pipx install 'loomgraph[java]')"
)


def _make_repo(tmp_path: Path, pattern: str = "src/f{}.py") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for i in range(10):
        p = repo / pattern.replace("{}", str(i))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n")
    return repo


def _patch_index_env(
    monkeypatch: pytest.MonkeyPatch, repo: Path, warnings: list[str]
) -> None:
    from loomgraph.cli import _indexing
    from loomgraph.core.graph_export_ingest import ImportSummary
    from loomgraph.core.models import EntityData

    monkeypatch.chdir(repo)
    monkeypatch.setattr(_indexing, "check_codeindex", lambda: {"installed": True})
    monkeypatch.setattr(
        _indexing,
        "run_graph_export",
        lambda r: (
            [EntityData("a", {}), EntityData("b", {})],
            [],
            ImportSummary(entity_count=2),
            list(warnings),
        ),
    )
    store = MagicMock()
    store.set_meta = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        AsyncMock(return_value=store),
    )
    monkeypatch.setattr(
        _indexing,
        "ingest",
        AsyncMock(return_value={
            "cleared": True, "entities_created": 2, "relations_created": 0,
            "resolved_ratio": None, "embedded": 0, "store_stats": {},
        }),
    )


# ─── CLI index ───────────────────────────────────────────────────────────────


class TestIndexPartialFlag:
    def test_true_on_parser_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_repo(tmp_path)
        _patch_index_env(monkeypatch, repo, [PARSER_MISSING])

        res = CliRunner().invoke(main, ["index", str(repo)])
        assert res.exit_code == 0, res.output
        data = json.loads(res.stdout)["data"]
        assert data["partial"] is True, data

    def test_true_on_fingerprint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TS repo, no .codeindex.yaml → fingerprint warning (#161)
        repo = _make_repo(tmp_path, "src/f{}.ts")
        _patch_index_env(monkeypatch, repo, [])

        res = CliRunner().invoke(main, ["index", str(repo)])
        assert res.exit_code == 0, res.output
        data = json.loads(res.stdout)["data"]
        assert data["partial"] is True, data

    def test_false_when_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_repo(tmp_path)
        _patch_index_env(monkeypatch, repo, [])

        res = CliRunner().invoke(main, ["index", str(repo)])
        assert res.exit_code == 0, res.output
        data = json.loads(res.stdout)["data"]
        assert data["partial"] is False, data

    def test_false_on_advisory_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolved_ratio hint 是质量 advisory,不是「缺符号」→ partial=False。"""
        from loomgraph.cli import _indexing

        repo = _make_repo(tmp_path)
        _patch_index_env(monkeypatch, repo, [])
        monkeypatch.setattr(
            _indexing,
            "ingest",
            AsyncMock(return_value={
                "cleared": True, "entities_created": 2, "relations_created": 100,
                "resolved_ratio": 0.0614, "embedded": 0, "store_stats": {},
            }),
        )

        res = CliRunner().invoke(main, ["index", str(repo)])
        assert res.exit_code == 0, res.output
        data = json.loads(res.stdout)["data"]
        assert "resolved_ratio" in data.get("warning", "")
        assert data["partial"] is False, data

    def test_false_when_silenced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """用户 silence 了 fingerprint warning(#166)= 声明「我知道了」→ partial 同步静默。"""
        from loomgraph.core.config import get_settings

        repo = _make_repo(tmp_path, "src/f{}.ts")
        _patch_index_env(monkeypatch, repo, [])
        monkeypatch.setattr(
            get_settings().warnings, "silence", ["source files, none indexed"],
        )

        res = CliRunner().invoke(main, ["index", str(repo)])
        assert res.exit_code == 0, res.output
        data = json.loads(res.stdout)["data"]
        assert not data.get("warning"), data.get("warning")
        assert data["partial"] is False, data


# ─── CLI update ──────────────────────────────────────────────────────────────


class TestUpdatePartialFlag:
    def test_true_on_parser_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loomgraph.cli import _indexing
        from loomgraph.core.graph_export_ingest import ImportSummary
        from loomgraph.core.models import EntityData

        repo = _make_repo(tmp_path)
        monkeypatch.chdir(repo)
        monkeypatch.setattr(_indexing, "check_codeindex", lambda: {"installed": True})
        monkeypatch.setattr(
            _indexing,
            "run_graph_export",
            lambda r: (
                [EntityData("a", {}), EntityData("b", {})],
                [],
                ImportSummary(entity_count=2),
                [PARSER_MISSING],
            ),
        )
        store = MagicMock()
        store.get_meta = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "loomgraph.storage.factory.create_graph_store",
            AsyncMock(return_value=store),
        )
        monkeypatch.setattr(
            _indexing,
            "_async_update",
            AsyncMock(return_value={"mode": "whole_tree_upsert", "entities_created": 2}),
        )

        # --files → forced whole-tree(跳过 git diff 机器)
        res = CliRunner().invoke(main, ["update", "--files", "src/f0.py"])
        assert res.exit_code == 0, res.output
        data = json.loads(res.stdout)["data"]
        assert data["partial"] is True, data


# ─── MCP refresh:warnings 透传 + partial ────────────────────────────────────


@pytest.fixture
def refresh_fakes(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    from loomgraph.io.export_reader import ImportSummary

    ns = types.SimpleNamespace()
    ns.store = MagicMock()
    ns.store.get_meta = AsyncMock(return_value=None)
    ns.create = AsyncMock(return_value=ns.store)
    ns.export = MagicMock(
        return_value=([object()], [], ImportSummary(entity_count=3), [])
    )
    ns.worktree = MagicMock(return_value=[Path("src/f0.py")])
    ns.incr = AsyncMock(
        return_value={
            "incremental": True, "changed_files": ["src/f0.py"],
            "entities_created": 1, "relations_created": 0,
            "embedded": 0, "gc_source_ids": 0, "store_stats": {},
        }
    )
    monkeypatch.setattr("loomgraph.storage.factory.create_graph_store", ns.create)
    monkeypatch.setattr("loomgraph.cli._indexing.run_graph_export", ns.export)
    monkeypatch.setattr("loomgraph.cli._indexing.is_git_repository", lambda r: True)
    monkeypatch.setattr(
        "loomgraph.cli._indexing.get_working_tree_files", ns.worktree
    )
    monkeypatch.setattr("loomgraph.cli._indexing.ingest_incremental", ns.incr)
    return ns


async def test_refresh_carries_warnings_and_partial(
    refresh_fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    """entity_count>0 的 partial export:warnings 必须进 result(此前真·silent)。"""
    from loomgraph.io.export_reader import ImportSummary

    refresh_fakes.export.return_value = (
        [object()], [], ImportSummary(entity_count=3), [PARSER_MISSING],
    )

    from loomgraph.cli._indexing import _async_refresh

    result = await _async_refresh(workspace="ws", repo=tmp_path, path=None,
                                  force_full=False)
    assert result["partial"] is True, result
    assert "tree-sitter-java" in result.get("warning", ""), result


async def test_refresh_clean_partial_false(
    refresh_fakes: types.SimpleNamespace, tmp_path: Path
) -> None:
    from loomgraph.cli._indexing import _async_refresh

    result = await _async_refresh(workspace="ws", repo=tmp_path, path=None,
                                  force_full=False)
    assert result["partial"] is False, result
