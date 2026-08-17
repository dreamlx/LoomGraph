"""CLI 使用摩擦修复的回归测试(外部项目 dogfood 反馈批次)。

- #165: `update` 在 diff 无受支持语言文件时短路(post-commit 场景大头)
- #163/#166-1: `-q` 后置报错带正确用法 hint
- #166-2: partial-graph warning 可按配置静默(`warnings.silence`)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main


def _git_repo_with_commits(repo: Path) -> None:
    """Two commits: first a .py file, second only non-source files."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"],
                   cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"],
                   cwd=repo, check=True, capture_output=True)
    (repo / "a.py").write_text("def foo():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "add a.py"],
                   cwd=repo, check=True, capture_output=True)
    # Second commit touches NO parsable source file (doc + shell).
    (repo / "README.md").write_text("docs only\n")
    (repo / ".husky").mkdir()
    (repo / ".husky" / "post-commit").write_text("#!/bin/sh\necho hi\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "docs+shell only"],
                   cwd=repo, check=True, capture_output=True)


# ─── #165: update short-circuits on no-source diffs ──────────────────────


def test_update_skips_when_diff_has_no_source_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Doc/config/shell-only commits must not pay the whole-tree re-export.

    Dogfood (BlueHawkLock): committing `.husky/post-commit` (diff with zero
    supported-language files) still cost the full ~9s export — the post-commit
    hook makes every docs/CI commit slow (#165).
    """
    import json

    from loomgraph.cli import _indexing

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_repo_with_commits(repo)
    monkeypatch.chdir(repo)

    def _boom(*a: object, **k: object) -> None:
        raise AssertionError("run_graph_export must not run on a no-source diff")

    monkeypatch.setattr(_indexing, "run_graph_export", _boom)
    monkeypatch.setattr(
        _indexing, "check_codeindex", lambda: {"installed": True},
    )

    runner = CliRunner()
    res = runner.invoke(main, ["update"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)["data"]
    assert data.get("skipped") is True, (
        f"docs/shell-only diff must short-circuit, got: {data}"
    )


def test_update_runs_when_diff_has_source_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A .py in the diff must NOT skip — regression guard against over-eager
    short-circuiting (silent no-update would be data loss)."""

    from loomgraph.cli import _indexing

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"],
                   cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"],
                   cwd=repo, check=True, capture_output=True)
    (repo / "a.py").write_text("def foo():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "add a.py"],
                   cwd=repo, check=True, capture_output=True)
    (repo / "a.py").write_text("def foo():\n    return 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "edit a.py"],
                   cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)

    called = {"export": False}

    def _fake_export(repo_path: Path) -> tuple:
        called["export"] = True
        # Minimal shape: the skip decision happens before export parsing
        # matters, so raise a distinctive error if ever reached deeply —
        # but we just need the call fact here.
        raise _indexing.GraphExportError("stop-here")

    monkeypatch.setattr(_indexing, "run_graph_export", _fake_export)
    monkeypatch.setattr(
        _indexing, "check_codeindex", lambda: {"installed": True},
    )

    runner = CliRunner()
    res = runner.invoke(main, ["update"])
    assert called["export"] is True, (
        ".py in diff must proceed to export, not skip (#165)"
    )
    # And the distinctive error surfaces (not a skipped:true success).
    assert '"skipped": true' not in res.output


# ─── #163/#166-1: -q after the subcommand gets a usage hint ─────────────


def test_quiet_after_subcommand_hint() -> None:
    """`loomgraph find x -q` must hint that -q is a global (pre-command) flag.

    Click's standard error is bare `No such option '-q'` — git/gh muscle
    memory puts global flags last, and the hook dogfood wrote it wrong on the
    first try (#163/#166).
    """
    runner = CliRunner()
    res = runner.invoke(main, ["find", "somequery", "-q"])
    assert res.exit_code != 0
    assert "before the command" in res.output, (
        f"-q usage error must carry the hint in the printed message, got: {res.output!r}"
    )


# ─── #166-2: partial-graph warnings can be silenced by config ────────────


def test_silence_warnings_filters_matching_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """warnings.silence substrings drop matching export warnings on both the
    stderr echo and the JSON `warning` field."""
    from loomgraph.cli._indexing import _silence_warnings
    from loomgraph.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(
        s.warnings, "silence", ["partial-graph"],
    )
    out = _silence_warnings(
        ["partial-graph: languages=[python] but repo has .ts files",
         "some other warning"]
    )
    assert out == ["some other warning"]


def test_silence_warnings_default_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from loomgraph.cli._indexing import _silence_warnings
    assert _silence_warnings(["partial-graph: x"]) == ["partial-graph: x"]


# ─── codex review (PR #170): config-only diffs must not skip ──────────────


def test_update_runs_when_diff_touches_codeindex_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `.codeindex.yaml`-only commit changes what the graph WOULD contain
    (languages:) — skipping the export on it serves a stale graph as
    success:true (codex review BLOCKER: fail-loud violation)."""
    from loomgraph.cli import _indexing

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"],
                   cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"],
                   cwd=repo, check=True, capture_output=True)
    (repo / "a.py").write_text("def foo():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "add a.py"],
                   cwd=repo, check=True, capture_output=True)
    # Config-only second commit — no source file touched.
    (repo / ".codeindex.yaml").write_text("languages: [typescript]\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "switch languages"],
                   cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)

    called = {"export": False}

    def _fake_export(repo_path: Path) -> tuple:
        called["export"] = True
        raise _indexing.GraphExportError("stop-here")

    monkeypatch.setattr(_indexing, "run_graph_export", _fake_export)
    monkeypatch.setattr(
        _indexing, "check_codeindex", lambda: {"installed": True},
    )

    runner = CliRunner()
    res = runner.invoke(main, ["update"])
    assert called["export"] is True, (
        ".codeindex.yaml-only diff must NOT skip — it changes the graph (#165 BLOCKER)"
    )
    assert '"skipped": true' not in res.output


# ─── codex review: silence must not eat the zero-export diagnosis ────────


def test_silence_warnings_ignores_blank_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty/whitespace pattern is `'' in anything` == match-everything —
    it would silence ALL warnings including safety diagnostics (codex
    SHOULD-FIX). Blank entries are dropped instead."""
    from loomgraph.cli._indexing import _silence_warnings
    from loomgraph.core.config import get_settings

    monkeypatch.setattr(get_settings().warnings, "silence", ["", "  "])
    assert _silence_warnings(["partial-graph: x", "another"]) == [
        "partial-graph: x", "another"
    ]


# ─── codex re-review: config diff must REBUILD, not just re-export ───────


def _repo_with_commits(repo: Path, second_commit_files: dict[str, str]) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"],
                   cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"],
                   cwd=repo, check=True, capture_output=True)
    (repo / "a.py").write_text("def foo():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"],
                   cwd=repo, check=True, capture_output=True)
    for name, content in second_commit_files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "second"],
                   cwd=repo, check=True, capture_output=True)


def _patch_update_env(monkeypatch, repo: Path) -> dict:
    """Wire update's collaborators: healthy export, real git, fake store/ingest."""
    from unittest.mock import AsyncMock, MagicMock

    from loomgraph.cli import _indexing
    from loomgraph.core.graph_export_ingest import ImportSummary

    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        _indexing, "check_codeindex", lambda: {"installed": True},
    )
    monkeypatch.setattr(
        _indexing, "run_graph_export",
        lambda r: ([], [], ImportSummary(entity_count=2), []),
    )
    store = MagicMock()
    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        AsyncMock(return_value=store),
    )
    ingest = AsyncMock(return_value={
        "cleared": True, "entities_created": 2, "relations_created": 0,
        "embedded": 0, "store_stats": {},
    })
    monkeypatch.setattr(_indexing, "ingest", ingest)
    incr = AsyncMock(return_value={
        "entities_created": 0, "relations_created": 0, "embedded": 0,
        "store_stats": {},
    })
    monkeypatch.setattr(_indexing, "ingest_incremental", incr)
    return {"ingest": ingest, "incr": incr}


def test_config_only_diff_rebuilds_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config-only diff must trigger a CLEAR REBUILD, not a no-op incremental.

    Re-export alone is not enough (codex re-review BLOCKER): the incremental
    ingest only touches entities whose source_id is in changed_files — a
    .codeindex.yaml is no entity's source, so the export ran, nothing was
    ingested, and update returned success over a stale graph."""
    import json

    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_commits(repo, {".codeindex.yaml": "languages: [typescript]\n"})
    m = _patch_update_env(monkeypatch, repo)

    res = CliRunner().invoke(main, ["update"])
    assert res.exit_code == 0, res.output
    m["ingest"].assert_awaited_once()
    assert m["ingest"].call_args.kwargs.get("clear") is True, (
        "config change must clear-rebuild (languages: reshapes the whole graph)"
    )
    m["incr"].assert_not_awaited()
    data = json.loads(res.stdout)["data"]
    assert data["mode"] == "config_rebuild"


def test_mixed_source_and_config_diff_also_rebuilds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diff mixing source + config still rebuilds — the config may re-shape
    files the source diff alone wouldn't touch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_commits(repo, {
        "a.py": "def foo():\n    return 1\n",
        ".codeindex.yaml": "languages: [typescript]\n",
    })
    m = _patch_update_env(monkeypatch, repo)

    res = CliRunner().invoke(main, ["update"])
    assert res.exit_code == 0, res.output
    m["ingest"].assert_awaited_once()
    assert m["ingest"].call_args.kwargs.get("clear") is True
    m["incr"].assert_not_awaited()


def test_deleted_config_diff_rebuilds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting .codeindex.yaml is a graph-affecting event too — but git
    --diff-filter=ACMR drops deletions, which made it read as an EMPTY diff
    and skip (codex re-review). The gate must see deletions (ACMRD)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    # Base commit carries the config so the second commit can delete it.
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"],
                   cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"],
                   cwd=repo, check=True, capture_output=True)
    (repo / "a.py").write_text("def foo():\n    pass\n")
    (repo / ".codeindex.yaml").write_text("languages: [typescript]\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"],
                   cwd=repo, check=True, capture_output=True)
    (repo / ".codeindex.yaml").unlink()
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "drop config"],
                   cwd=repo, check=True, capture_output=True)
    m = _patch_update_env(monkeypatch, repo)

    res = CliRunner().invoke(main, ["update"])
    assert res.exit_code == 0, res.output
    m["ingest"].assert_awaited_once()
    assert m["ingest"].call_args.kwargs.get("clear") is True
