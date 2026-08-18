"""EPIC-016 (#185) PR3:branch-diff CLI 单元层 —— range 解析 + workspace 决策表。

provisioning 语义(方向见 #185 决策表):候选名 `<repo>:<ref>`(sanitize),
meta 打标 `provisioned_by="branch-diff"`;同 ref 同 sha → reused(跳过索引),
同 ref 异 sha → rebuilt(原地重建),非 tag 且非空(用户库/sanitize 碰撞)→
fallback 名 `<名>-<sha[:7]>`,永不 clobber 非 tag 的库。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from loomgraph.cli._branch_diff import _decide_workspace, _parse_ref_range
from loomgraph.core.config import reset_settings
from loomgraph.storage.factory import create_graph_store

SHA = "a" * 40
SHA2 = "b" * 40


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    reset_settings()
    yield
    reset_settings()


def _storage_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "LOOMGRAPH_STORAGE__DB_PATH", str(tmp_path / "{workspace}.db")
    )
    reset_settings()


# ─── _parse_ref_range ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("main..feature", ("main", "feature")),
        ("v0.19.0..HEAD", ("v0.19.0", "HEAD")),
        ("a..b..c", None),        # 恰一个 ".." 才合法
        ("main...feature", None), # 三点是 git 对称 diff 语法,拒绝
        ("main", None),
        ("..feature", None),
        ("main..", None),
    ],
)
def test_parse_ref_range(value: str, expected: tuple[str, str] | None) -> None:
    assert _parse_ref_range(value) == expected


# ─── _decide_workspace 决策表 ────────────────────────────────────────────────


async def test_fresh_name_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _storage_at(tmp_path, monkeypatch)
    name, action = await _decide_workspace("repo", "main", SHA)
    assert name == "repo:main"
    assert action == "created"


async def test_tagged_same_ref_same_sha_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _storage_at(tmp_path, monkeypatch)
    store = await create_graph_store(workspace="repo:main")
    await store.set_meta("provisioned_by", "branch-diff")
    await store.set_meta("provisioned_ref", "main")
    await store.set_meta("provisioned_sha", SHA)
    await store.close()

    name, action = await _decide_workspace("repo", "main", SHA)
    assert (name, action) == ("repo:main", "reused")


async def test_tagged_same_ref_moved_sha_rebuilt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """分支移动 → 原地 rebuild(tag 过的 cache 是一次性制品,陈旧 diff 不可用)。"""
    _storage_at(tmp_path, monkeypatch)
    store = await create_graph_store(workspace="repo:main")
    await store.set_meta("provisioned_by", "branch-diff")
    await store.set_meta("provisioned_ref", "main")
    await store.set_meta("provisioned_sha", SHA)
    await store.close()

    name, action = await _decide_workspace("repo", "main", SHA2)
    assert (name, action) == ("repo:main", "rebuilt")


async def test_untagged_nonempty_falls_back_to_sha_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用户自己的库(非 tag、非空)永不 clobber → fallback 名。"""
    _storage_at(tmp_path, monkeypatch)
    store = await create_graph_store(workspace="repo:main")
    await store.insert_custom_kg(
        [{"entity_name": "a.b", "entity_type": "function"}], [], []
    )
    await store.close()

    name, action = await _decide_workspace("repo", "main", SHA)
    assert (name, action) == (f"repo:main-{SHA[:7]}", "created")


async def test_tagged_different_ref_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sanitize 碰撞(feature/x 与 feature-x 同名):我们自己的两个 cache 也不
    互相 clobber——tag 的 ref 不同 → fallback 名。"""
    _storage_at(tmp_path, monkeypatch)
    store = await create_graph_store(workspace="repo:feature-x")
    await store.set_meta("provisioned_by", "branch-diff")
    await store.set_meta("provisioned_ref", "feature/x")
    await store.set_meta("provisioned_sha", SHA)
    await store.close()

    name, action = await _decide_workspace("repo", "feature-x", SHA2)
    assert (name, action) == (f"repo:feature-x-{SHA2[:7]}", "created")


async def test_ref_slash_sanitized_in_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ref 含 /(feature/x):候选名经 db-path sanitize 成 feature-x(#99)。"""
    _storage_at(tmp_path, monkeypatch)
    name, action = await _decide_workspace("repo", "feature/x", SHA)
    assert (name, action) == ("repo:feature-x", "created")
