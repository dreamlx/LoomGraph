"""`loomgraph codeindex <args>` passthrough — #132/#133 codex review #1.

The setup skill needs a stable entry point to invoke codeindex (generate
`.codeindex.yaml`, etc.) in loomgraph's *own* venv — not a PATH-resolved
`python`/`codeindex` that may hit a different install (#76 PATH-bypass class).
loomgraph already calls codeindex via `sys.executable -m codeindex.cli`
internally (graph_export_ingest.py); this command exposes that same pinned-env
invocation to users and skills.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from click.testing import CliRunner

from loomgraph.cli import _codeindex


class _FakeCompleted:
    """Stand-in for subprocess.run result."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode


def test_passthrough_uses_pinned_venv_python() -> None:
    """Must invoke `[sys.executable, -m, codeindex.cli, ...]`, never bare codeindex.

    A bare `codeindex` PATH lookup can hit a non-pinned install (pipx shadowing,
    #76). The whole point of this command is the pinned-env guarantee.
    """
    captured: list[list[str]] = []

    def _fake_run(args: list[str], **kwargs: object) -> _FakeCompleted:
        captured.append(args)
        return _FakeCompleted(returncode=0)

    with patch.object(_codeindex.subprocess, "run", _fake_run):
        result = CliRunner().invoke(
            _codeindex.main, ["codeindex", "init", "--yes"]
        )

    assert result.exit_code == 0, result.output
    args = captured[0]
    # First three args MUST be venv python + -m codeindex.cli — not "codeindex".
    assert args[0] == sys.executable, (
        f"passthrough must use sys.executable (pinned venv), got {args[0]!r}"
    )
    assert args[1:3] == ["-m", "codeindex.cli"], args[1:3]
    # User args forwarded verbatim after the module spec.
    assert args[3:] == ["init", "--yes"], args[3:]


def test_passthrough_forwards_exit_code() -> None:
    """A non-zero codeindex exit must surface as the command's exit code."""
    with patch.object(
        _codeindex.subprocess, "run",
        lambda *a, **kw: _FakeCompleted(returncode=2),
    ):
        result = CliRunner().invoke(_codeindex.main, ["codeindex", "init"])
    assert result.exit_code == 2


def test_passthrough_forwards_arbitrary_args() -> None:
    """Unknown options reach codeindex verbatim (e.g. --dry-run, --lang)."""
    captured: list[list[str]] = []

    def _fake_run(args: list[str], **kwargs: object) -> _FakeCompleted:
        captured.append(args)
        return _FakeCompleted(returncode=0)

    with patch.object(_codeindex.subprocess, "run", _fake_run):
        CliRunner().invoke(
            _codeindex.main,
            ["codeindex", "init", "--yes", "--force", "--lang", "en"],
        )
    assert captured[0][3:] == ["init", "--yes", "--force", "--lang", "en"]
