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


def _point_hooks_dir_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Make ``find_git_repo``/``get_hooks_dir`` resolve to a temp git repo."""
    repo = tmp_path / "repo"
    (repo / ".git" / "hooks").mkdir(parents=True)
    monkeypatch.setattr(_hooks, "find_git_repo", lambda: repo)
    return repo


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


def test_install_hook_creates_executable_post_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install_hook writes an executable post-commit carrying our marker."""
    repo = _point_hooks_dir_at(tmp_path, monkeypatch)

    result = install_hook("post-commit")

    assert result is True
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
