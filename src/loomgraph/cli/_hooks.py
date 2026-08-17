"""Git hooks management for loomgraph."""

from __future__ import annotations

import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

import click

from .main import main

LOOMGRAPH_MARKER = "# loomgraph-managed hook"
SUPPORTED_HOOKS = ["post-commit"]


def find_git_repo() -> Path:
    """Find git repository from current directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    raise ValueError("Not in a git repository")


def get_hooks_dir() -> Path:
    """Get the hooks directory git actually reads.

    Honors ``core.hooksPath`` (set by husky, shared-hook setups, or this repo's
    own ``.githooks/``): when it's set, git reads ONLY that dir and ignores
    ``.git/hooks`` entirely — installing to ``.git/hooks`` would be a dead hook
    (#130). We ask git directly via ``git rev-parse --git-path hooks``, which
    respects ``core.hooksPath`` and returns ``.git/hooks`` when unset.

    Does NOT fail open: if git is unavailable or rev-parse errors, we raise
    rather than silently fall back to ``.git/hooks`` — a silent fallback would
    recreate the #130 dead-hook bug on any repo with a hooksPath set (codex
    review). The caller (``install`` command) surfaces this as
    ``HOOK_INSTALL_FAILED``.
    """
    repo_root = find_git_repo()
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    # rev-parse returns a path relative to the repo root (or absolute);
    # resolve it to an absolute path either way.
    hooks_dir = (repo_root / result.stdout.strip()).resolve()

    # husky v9 layout (#164): core.hooksPath points at `.husky/_`, husky's
    # *generated* shim dir — `husky` (npm prepare) wipes and rebuilds it on
    # every install, silently deleting our hook, and overwriting a shim there
    # breaks husky's chain for every other hook. The husky convention for user
    # hooks is the `.husky/` root (the shim sources `.husky/<hook>`), so map
    # `_` up to its parent.
    try:
        rel = hooks_dir.relative_to(repo_root)
    except ValueError:
        rel = None  # hooks dir outside the repo (shared-hooks setups): use as-is
    if rel is not None and len(rel.parts) == 2 and rel.parts[0] == ".husky" and rel.parts[1] == "_":
        hooks_dir = hooks_dir.parent

    hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir


def is_installed(hook_name: str) -> bool:
    """Check if hook is installed."""
    hooks_dir = get_hooks_dir()
    hook_path = hooks_dir / hook_name

    if not hook_path.exists():
        return False

    content = hook_path.read_text()
    return LOOMGRAPH_MARKER in content


def install_hook(hook_name: str, force: bool = False, workspace: str | None = None) -> bool:
    """Install hook from template.

    ``workspace`` (#160): bakes ``-w <name>`` into the hook so ``update`` hits
    the workspace the user actually indexed (typically a fixed-name one created
    by ``loomgraph index -w <name>``). Without it the hook's bare
    ``loomgraph update`` auto-detects ``<repo-dir>:<branch>`` — a different db.
    """
    if hook_name not in SUPPORTED_HOOKS:
        raise ValueError(f"Unsupported hook: {hook_name}")

    hooks_dir = get_hooks_dir()
    hook_path = hooks_dir / hook_name

    # Check if already installed
    if hook_path.exists() and not force:
        content = hook_path.read_text()
        if LOOMGRAPH_MARKER in content:
            return True  # Already installed
        else:
            # Backup existing custom hook
            backup_path = hooks_dir / f"{hook_name}.backup"
            shutil.copy2(hook_path, backup_path)

    # Resolve template from inside the installed package — works identically
    # for editable / wheel / pipx installs. The template lives at
    # src/loomgraph/_hooks_templates/ and ships inside the wheel. The old
    # source-tree path (Path(__file__).parent×4 / "scripts/hooks") only
    # coincidentally resolved under editable install, masking the bug (#128).
    template_path = files("loomgraph") / "_hooks_templates" / hook_name

    if not template_path.is_file():
        raise FileNotFoundError(f"Hook template not found in package: {hook_name}")

    content = template_path.read_text()
    if workspace:
        content = content.replace(
            'WORKSPACE_ARG=""', f'WORKSPACE_ARG="-w {workspace}"'
        )

    hook_path.write_text(content)
    hook_path.chmod(0o755)  # Make executable

    return True


def uninstall_hook(hook_name: str, restore_backup: bool = True) -> bool:
    """Uninstall hook and optionally restore backup."""
    hooks_dir = get_hooks_dir()
    hook_path = hooks_dir / hook_name

    if not hook_path.exists():
        return False

    content = hook_path.read_text()
    if LOOMGRAPH_MARKER not in content:
        return False  # Not a loomgraph hook

    # Remove hook
    hook_path.unlink()

    # Restore backup if exists and requested
    if restore_backup:
        backup_path = hooks_dir / f"{hook_name}.backup"
        if backup_path.exists():
            shutil.move(backup_path, hook_path)

    return True


@main.group()
def hooks() -> None:
    """Manage git hooks for automatic knowledge graph updates."""
    pass


@hooks.command()
@click.option("--all", "install_all", is_flag=True, help="Install all supported hooks")
@click.option("--force", is_flag=True, help="Overwrite existing hooks")
@click.option(
    "-w", "--workspace",
    help=(
        "Bake this workspace name into the hook (#160). Required when the repo "
        "was indexed with a fixed name (loomgraph index -w <name>) — otherwise "
        "the hook's update auto-detects <repo>:<branch>, a different db."
    ),
)
def install(install_all: bool, force: bool, workspace: str | None) -> None:
    """Install post-commit hook for automatic updates.

    Examples:
        loomgraph hooks install                     # Install post-commit hook
        loomgraph hooks install -w myname           # Pin the hook's workspace (#160)
        loomgraph hooks install --all               # Install all hooks
        loomgraph hooks install --force -w myname   # Overwrite + repin
    """
    from ._setup import ErrorCode
    from .main import output_error, output_success

    try:
        repo_root = find_git_repo()
    except ValueError as e:
        output_error(
            code=ErrorCode.GIT_ERROR,
            message=str(e),
            suggestion="Run this command from within a git repository",
        )
        return

    hooks_to_install = SUPPORTED_HOOKS if install_all else ["post-commit"]
    installed = []
    skipped = []

    for hook_name in hooks_to_install:
        try:
            if install_hook(hook_name, force=force, workspace=workspace):
                installed.append(hook_name)
        except Exception as e:
            skipped.append({"hook": hook_name, "error": str(e)})

    result = {
        "repo_path": str(repo_root),
        "installed": installed,
        "installed_count": len(installed),
    }

    if skipped:
        result["skipped"] = skipped

    # Surface total failure as an error rather than success:true — otherwise a
    # packaging regression (e.g. missing wheel template, #128) is silently
    # swallowed and users walk away believing the hook was installed.
    if not installed:
        output_error(
            code=ErrorCode.HOOK_INSTALL_FAILED,
            message=f"No hooks installed ({len(skipped)} failed)",
            suggestion=(
                "Check the 'skipped' errors. If the template is missing, "
                "reinstall loomgraph to get a package with hook templates."
            ),
            data=result,
        )
        return

    output_success(result)


@hooks.command()
@click.option("--all", "uninstall_all", is_flag=True, help="Uninstall all hooks")
@click.option("--no-restore", is_flag=True, help="Don't restore backup hooks")
def uninstall(uninstall_all: bool, no_restore: bool) -> None:
    """Uninstall loomgraph hooks.

    Examples:
        loomgraph hooks uninstall            # Uninstall post-commit
        loomgraph hooks uninstall --all      # Uninstall all
        loomgraph hooks uninstall --no-restore  # Don't restore backup
    """
    from ._setup import ErrorCode
    from .main import output_error, output_success

    try:
        repo_root = find_git_repo()
    except ValueError as e:
        output_error(
            code=ErrorCode.GIT_ERROR,
            message=str(e),
            suggestion="Run this command from within a git repository",
        )
        return

    hooks_to_remove = SUPPORTED_HOOKS if uninstall_all else ["post-commit"]
    uninstalled = []

    for hook_name in hooks_to_remove:
        if uninstall_hook(hook_name, restore_backup=not no_restore):
            uninstalled.append(hook_name)

    output_success({
        "repo_path": str(repo_root),
        "uninstalled": uninstalled,
        "uninstalled_count": len(uninstalled),
    })


@hooks.command()
def status() -> None:
    """Check hooks installation status.

    Example:
        loomgraph hooks status
    """
    from ._setup import ErrorCode
    from .main import output_error, output_success

    try:
        repo_root = find_git_repo()
    except ValueError as e:
        output_error(
            code=ErrorCode.GIT_ERROR,
            message=str(e),
            suggestion="Run this command from within a git repository",
        )
        return

    hooks_status = []
    for hook_name in SUPPORTED_HOOKS:
        hooks_status.append({
            "hook": hook_name,
            "installed": is_installed(hook_name),
        })

    output_success({
        "repo_path": str(repo_root),
        "hooks": hooks_status,
    })
