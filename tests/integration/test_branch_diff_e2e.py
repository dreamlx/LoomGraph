"""EPIC-016 (#185) branch-diff E2E:真 git repo → 真 worktree → 真 codeindex 导出
→ 真 diff。

场景构造(base commit → feature 分支):
- 删 `foo` 且 mod_b **不改动**(调用方还在、被调方没了)→ broken_chain
- `bar` 只改 body → content_changed(图形状没变)
- 新目录 `sub/mod_c.py` 的 `baz` 调 `bar` → new_chain + module_delta("sub")

再验证 provisioning 生命周期:rerun → reused;分支前进 → rebuilt;退出后无
`loomgraph-bd-*` tmpdir 残留、`git worktree list` 复原。

Skipped when codeindex is not importable in the venv(CI runs unit+contract only)。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main
from loomgraph.core.config import reset_settings

pytestmark = pytest.mark.integration

requires_codeindex = pytest.mark.skipif(
    importlib.util.find_spec("codeindex") is None,
    reason="codeindex not installed in this venv",
)


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr}")
    return proc.stdout


def _seed_repo(repo: Path) -> str:
    """base commit(mod_a.foo/bar + mod_b.caller 调 foo/bar),返回默认分支名。"""
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "mod_a.py").write_text(
        "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"
    )
    (repo / "mod_b.py").write_text(
        "from mod_a import bar, foo\n\n\ndef caller():\n    return foo() + bar()\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def _seed_feature(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feature")
    # 删 foo;mod_b 保持原样(悬挂 foo() 调用——调用方还在、被调方没了)。
    # bar 改 body 并新增对新 helper twenti 的调用(存活函数开始调新人 → new_chain)
    (repo / "mod_a.py").write_text(
        "def bar():\n    return twenti()\n\n\ndef twenti():\n    return 20\n"
    )
    sub = repo / "sub"
    sub.mkdir()
    (sub / "mod_c.py").write_text(
        "from mod_a import bar\n\n\ndef baz():\n    return bar()\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feature")


@pytest.fixture
def bd_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    base_branch = _seed_repo(repo)
    _seed_feature(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv(
        "LOOMGRAPH_STORAGE__DB_PATH", str(tmp_path / "{workspace}.db")
    )
    reset_settings()
    _git(repo, "checkout", "-q", base_branch)  # 回 base 分支(命令从 cwd 跑)
    return repo


def _bd_tmpdirs() -> set[Path]:
    return {
        p for p in Path(tempfile.gettempdir()).glob("loomgraph-bd-*") if p.exists()
    }


@requires_codeindex
def test_branch_diff_e2e_full_lifecycle(bd_env: Path, tmp_path: Path) -> None:
    base_branch = _git(bd_env, "rev-parse", "--abbrev-ref", "HEAD").strip()
    tmp_before = _bd_tmpdirs()

    res = CliRunner().invoke(main, ["branch-diff", f"{base_branch}..feature"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)["data"]

    # provisioning:双侧全新 created,workspace 名按 ref
    assert data["base"]["provisioned"] == "created"
    assert data["head"]["provisioned"] == "created"
    assert data["base"]["workspace"] == f"repo:{base_branch}"
    assert data["head"]["workspace"] == "repo:feature"

    diff = data["diff"]
    # 断链:caller(存活)→ foo(消失);mod_b 未改,base 边 resolved、head 边悬挂
    broken = [(c["src"], c["tgt"]) for c in diff["broken_chains"]]
    assert ("mod_b.caller", "mod_a.foo") in broken, broken
    assert any(e["name"] == "mod_a.foo" for e in diff["entities_removed"])
    # L2:bar body 变了 → content_changed;caller 未动 → 不在
    changed = {c["name"] for c in diff["content_changed"]}
    assert "mod_a.bar" in changed, changed
    assert "mod_b.caller" not in changed
    # 新链(存活函数新增调用):bar → twenti;新文件 baz→bar 只进 edges_added
    new = [(c["src"], c["tgt"]) for c in diff["new_chains"]]
    assert ("mod_a.bar", "mod_a.twenti") in new, new
    added_edges = [(c["src"], c["tgt"]) for c in diff["edges_added"]]
    assert ("sub.mod_c.baz", "mod_a.bar") in added_edges, added_edges
    delta = {d["module"]: d for d in diff["module_delta"]}
    assert delta.get("sub", {}).get("edges_added", 0) >= 1

    # rerun:双侧 reused(零成本短路)
    res2 = CliRunner().invoke(main, ["branch-diff", f"{base_branch}..feature"])
    assert res2.exit_code == 0, res2.output
    data2 = json.loads(res2.stdout)["data"]
    assert data2["base"]["provisioned"] == "reused"
    assert data2["head"]["provisioned"] == "reused"

    # 分支前进:feature 移动 → rebuilt(原地重建)
    _git(bd_env, "checkout", "-q", "feature")
    (bd_env / "mod_a.py").write_text(
        "def bar():\n    return 21\n\ndef extra():\n    return 0\n"
    )
    _git(bd_env, "add", "-A")
    _git(bd_env, "commit", "-q", "-m", "advance")
    _git(bd_env, "checkout", "-q", base_branch)
    res3 = CliRunner().invoke(main, ["branch-diff", f"{base_branch}..feature"])
    assert res3.exit_code == 0, res3.output
    data3 = json.loads(res3.stdout)["data"]
    assert data3["base"]["provisioned"] == "reused"   # base 没动
    assert data3["head"]["provisioned"] == "rebuilt"  # head 分支移动

    # 清理:无 tmpdir 残留、worktree 复原
    assert _bd_tmpdirs() == tmp_before
    listing = _git(bd_env, "worktree", "list")
    assert "feature" not in listing.splitlines()[1:]


@requires_codeindex
def test_branch_diff_bad_ref_and_range(bd_env: Path) -> None:
    res = CliRunner().invoke(main, ["branch-diff", "nope..main"])
    assert res.exit_code == 1
    assert "nope" in res.stdout  # 错误消息点名 ref

    res = CliRunner().invoke(main, ["branch-diff", "main"])
    assert res.exit_code == 1
    assert "Invalid ref range" in res.stdout


@requires_codeindex
def test_index_at_ref_e2e_provisions_queryable_snapshot(bd_env: Path) -> None:
    """#190: historical ref indexing persists a queryable workspace."""
    base_branch = _git(bd_env, "rev-parse", "--abbrev-ref", "HEAD").strip()

    res = CliRunner().invoke(main, ["index", "--at-ref", base_branch])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)["data"]
    assert data["mode"] == "at_ref"
    assert data["workspace"] == f"repo:{base_branch}"
    assert data["provisioned"] == "created"

    find_res = CliRunner().invoke(
        main,
        ["find", "mod_a.foo", "--workspace", f"repo:{base_branch}"],
    )
    assert find_res.exit_code == 0, find_res.output
    find_data = json.loads(find_res.stdout)["data"]
    assert any(match["entity"] == "mod_a.foo" for match in find_data["matches"])
