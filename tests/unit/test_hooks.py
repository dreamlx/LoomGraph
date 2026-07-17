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
