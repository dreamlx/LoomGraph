"""Git hooks install — #128: template must resolve from the installed package.

Background: ``loomgraph hooks install`` failed on every wheel/pipx install with
``Hook template not found``. Double defect — (A) the template was never
force-included into the wheel, (B) the path logic assumed a source-tree layout
(``Path(__file__).parent×4 / "scripts/hooks"``) that only coincidentally works
under ``pip install -e .``. The blind spot: developers dogfood under editable
install where the path happens to resolve.

The guard test here is ``test_template_resolvable_from_package``: it asserts the
template is reachable via ``importlib.resources`` *from the package*, independent
of cwd / source tree — so editable and pipx installs are exercised identically.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli import _hooks
from loomgraph.cli._hooks import install_hook
from loomgraph.cli.main import main


def _init_git_repo(repo: Path) -> None:
    """Create a real git repo so `git rev-parse --git-path hooks` resolves."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo, check=True, capture_output=True,
    )


def test_template_resolvable_from_package() -> None:
    """Template must live inside the installed package, not the source tree.

    This is the editable-vs-pipx guard: under editable install the old
    ``Path(__file__).parent×4 / "scripts/hooks"`` path coincidentally resolves,
    hiding the bug. ``importlib.resources`` resolves identically regardless of
    install method.
    """
    template = files("loomgraph") / "_hooks_templates" / "post-commit"
    assert template.is_file(), "post-commit template missing from package"
    content = template.read_text()
    assert _hooks.LOOMGRAPH_MARKER in content


def test_install_hook_creates_executable_post_commit_default_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install_hook writes an executable post-commit carrying our marker.

    Uses a real git repo with NO core.hooksPath set (default .git/hooks) — so
    get_hooks_dir's real `git rev-parse` code path is exercised, not a stubbed
    fallback (which would normalize a broken fallback per codex review).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    assert install_hook("post-commit") is True

    hook_path = repo / ".git" / "hooks" / "post-commit"
    assert hook_path.exists()
    assert _hooks.LOOMGRAPH_MARKER in hook_path.read_text()
    # Executable bit set (post-commit must be runnable by git).
    assert hook_path.stat().st_mode & 0o111, "post-commit not executable"


def test_install_command_errors_when_all_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install must surface failure, not return success:true with count 0.

    Regression guard for the silent-success path that masked #128: when every
    hook is skipped, the command must report an error so future packaging
    regressions aren't swallowed.
    """
    repo = tmp_path / "repo"
    (repo / ".git" / "hooks").mkdir(parents=True)
    monkeypatch.setattr(_hooks, "find_git_repo", lambda: repo)

    def _boom(hook_name: str, force: bool = False) -> bool:
        raise FileNotFoundError(f"Hook template not found: {hook_name}")

    monkeypatch.setattr(_hooks, "install_hook", _boom)

    runner = CliRunner()
    res = runner.invoke(main, ["hooks", "install"])

    # Process-level failure contract, not just JSON body: a command that emits
    # success:false but exits 0 would still fool a shell/CI `&&` chain. Assert
    # the non-zero exit and the structured error code together.
    assert res.exit_code == 1, (
        f"install must exit 1 on total failure (got {res.exit_code})"
    )
    payload = json.loads(res.output)
    assert payload["success"] is False, (
        "install returned success:true despite all hooks failing — silent regression"
    )
    assert payload["error"]["code"] == "HOOK_INSTALL_FAILED", (
        f"expected HOOK_INSTALL_FAILED, got {payload['error'].get('code')}"
    )
    assert "skipped" in payload["data"] or "skipped" in str(payload.get("data", {}))


# ---------------------------------------------------------------------------
# core.hooksPath awareness (#130)
#
# Same blind spot as #128: a test that only exercises the default `.git/hooks`
# path passes while the bug persists. These set `core.hooksPath` explicitly and
# assert the hook lands where git actually reads it. Without this, `hooks
# install` reports success but the hook is dead (git ignores .git/hooks when a
# hooksPath is set).
# ---------------------------------------------------------------------------


def test_get_hooks_dir_respects_core_hooks_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_hooks_dir must honor `core.hooksPath`, not hardcode .git/hooks."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    custom_hooks = repo / ".myhooks"
    custom_hooks.mkdir()
    subprocess.run(
        ["git", "config", "core.hooksPath", ".myhooks"],
        cwd=repo, check=True, capture_output=True,
    )
    monkeypatch.chdir(repo)

    hooks_dir = _hooks.get_hooks_dir()

    assert hooks_dir == custom_hooks.resolve(), (
        f"get_hooks_dir ignored core.hooksPath: got {hooks_dir}, "
        f"expected {custom_hooks.resolve()}"
    )


def test_install_hook_lands_in_custom_hooks_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install_hook must write where git reads (core.hooksPath-aware)."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    custom_hooks = repo / ".myhooks"
    custom_hooks.mkdir()
    subprocess.run(
        ["git", "config", "core.hooksPath", ".myhooks"],
        cwd=repo, check=True, capture_output=True,
    )
    monkeypatch.chdir(repo)

    assert install_hook("post-commit") is True

    assert (custom_hooks / "post-commit").exists()
    assert _hooks.LOOMGRAPH_MARKER in (custom_hooks / "post-commit").read_text()
    assert not (repo / ".git" / "hooks" / "post-commit").exists(), (
        "install_hook wrote to .git/hooks which git ignores when "
        "core.hooksPath is set — the hook would be dead (#130)"
    )


def test_get_hooks_dir_does_not_fail_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_hooks_dir must raise on git failure, not silently fall back.

    A silent fallback to .git/hooks recreates the #130 dead-hook bug on any
    repo with a core.hooksPath set (codex review: fails-open). When git is
    unavailable or rev-parse errors, surface the failure so the install
    command reports HOOK_INSTALL_FAILED instead of installing a dead hook.
    """
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    # Force `git rev-parse` to fail as if git were missing from PATH.
    real_run = subprocess.run

    def _fail_git(*args: object, **kwargs: object) -> None:
        argv = args[0] if args else kwargs.get("args")
        if isinstance(argv, list) and argv[:1] == ["git"]:
            raise FileNotFoundError("git")
        return real_run(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_hooks.subprocess, "run", _fail_git)

    with pytest.raises(FileNotFoundError):
        _hooks.get_hooks_dir()


# ─── #164: husky v9 layout — `.husky/_` is a regenerable shim dir ────────


def test_get_hooks_dir_maps_husky_underscore_to_husky_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """husky v9: core.hooksPath=.husky/_ — install must land in .husky/, not _/.

    `.husky/_` is husky's *generated* shim dir: `husky` (npm prepare) wipes and
    rebuilds it on every install, silently deleting anything we put there. It
    also holds the shims husky uses to source the real user hooks — overwriting
    `.husky/_/post-commit` with our template breaks husky's chain for every
    other hook. The husky-v9 convention for user hooks is the `.husky/` root:
    the shim executes `.husky/<hook>`, which is where we must write (#164).
    """
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / ".husky" / "_").mkdir(parents=True)
    subprocess.run(
        ["git", "config", "core.hooksPath", ".husky/_"],
        cwd=repo, check=True, capture_output=True,
    )
    monkeypatch.chdir(repo)

    hooks_dir = _hooks.get_hooks_dir()
    assert hooks_dir == (repo / ".husky").resolve(), (
        f"husky v9 layout must map to .husky/ root (user-hook area), "
        f"got {hooks_dir} (#164)"
    )


def test_install_hook_husky_layout_lands_in_husky_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: on a husky v9 repo the hook file appears at .husky/post-commit."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / ".husky" / "_").mkdir(parents=True)
    subprocess.run(
        ["git", "config", "core.hooksPath", ".husky/_"],
        cwd=repo, check=True, capture_output=True,
    )
    monkeypatch.chdir(repo)

    assert install_hook("post-commit") is True

    assert (repo / ".husky" / "post-commit").exists(), (
        "hook must land in .husky/ root under husky v9 (#164)"
    )
    assert not (repo / ".husky" / "_" / "post-commit").exists(), (
        "hook must NOT overwrite the husky shim (#164)"
    )


# ─── #160: hook must update the workspace the user actually indexed ──────


def test_install_hook_injects_workspace_arg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install_hook(workspace=...) bakes `-w <name>` into the template.

    Without it the hook calls bare `loomgraph update`, which auto-detects
    `<repo-dir>:<branch>` — a different workspace than the fixed-name one the
    user indexed with `index -w <name>`, so the graph never updates the db
    the user queries (#160).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    assert install_hook("post-commit", workspace="hexforce-rn") is True

    content = (repo / ".git" / "hooks" / "post-commit").read_text()
    assert '-w hexforce-rn' in content, (
        "hook template must carry the workspace the user indexed (#160)"
    )
    # The bare call sites must consume the variable, not a hardcoded bare update.
    assert "update $WORKSPACE_ARG" in content


def test_install_hook_without_workspace_leaves_bare_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No workspace given → template keeps bare `update` (auto-detect, current default)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    assert install_hook("post-commit") is True

    content = (repo / ".git" / "hooks" / "post-commit").read_text()
    assert "update $WORKSPACE_ARG" in content
    # The variable stays empty (the -w <name> text in the comments is fine).
    assert 'WORKSPACE_ARG=""' in content
    assert 'WORKSPACE_ARG="-w' not in content


# ─── tee exit-code: $? after a pipe is tee's status, not update's ────────


def test_template_uses_pipestatus_not_dollar_question() -> None:
    """After `update | tee`, `$?` is tee's exit code — failures show ✓.

    The sync path must read bash's ${PIPESTATUS[0]} (first pipe element) so a
    failed update is reported as failed (found during #160 triage).
    """
    template = files("loomgraph") / "_hooks_templates" / "post-commit"
    content = template.read_text()
    assert "PIPESTATUS[0]" in content, (
        "sync path must use ${PIPESTATUS[0]} after `update | tee`"
    )
    assert 'EXIT_CODE=$?' not in content


# ─── codex review (PR #169): repin must rewrite, unsafe names must fail ────


def test_install_hook_repin_rewrites_existing_managed_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install -w on an ALREADY-installed managed hook must rewrite it.

    The #160 repair's primary audience is repos with a bare-update hook
    already installed — the early `already installed` return would report
    installed:true while silently leaving the bare `loomgraph update` in
    place (codex review BLOCKER).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    assert install_hook("post-commit") is True  # bare install (no -w)
    bare = (repo / ".git" / "hooks" / "post-commit").read_text()
    assert 'WORKSPACE_ARG=""' in bare  # variable stayed empty (unpinned)

    # Repin WITHOUT --force must rewrite the managed hook.
    assert install_hook("post-commit", workspace="hexforce-rn") is True
    content = (repo / ".git" / "hooks" / "post-commit").read_text()
    assert '-w hexforce-rn' in content, (
        "install -w must rewrite an existing managed hook, not no-op (codex BLOCKER)"
    )


def test_install_hook_rejects_unsafe_workspace_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Workspace names are baked into bash source — reject metacharacters.

    Spaces split into multiple args; quotes/$/backticks alter the executable
    script (codex review SHOULD-FIX). Workspace names come from repo dirs /
    branch names, where `:` `/` `.` `-` `_` are legitimate; everything else
    shell-active is not.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    with pytest.raises(ValueError):
        install_hook("post-commit", workspace="my ws")  # space
    with pytest.raises(ValueError):
        install_hook("post-commit", workspace='x"; rm -rf ~')  # quote
    with pytest.raises(ValueError):
        install_hook("post-commit", workspace="$(cmd)")  # substitution
    with pytest.raises(ValueError):
        install_hook("post-commit", workspace="")  # empty

    # Legitimate shapes pass (branch-bearing names include '/' and ':').
    assert install_hook("post-commit", workspace="loomgraph:feature/fix-160") is True
