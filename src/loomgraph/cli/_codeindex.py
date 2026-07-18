"""CLI passthrough: `loomgraph codeindex <args>` — run codeindex in loomgraph's venv.

Why this exists (#132 / codex review #1): the setup skill and users need a
stable entry point to invoke codeindex (e.g. ``codeindex init`` to generate
``.codeindex.yaml``). A PATH-resolved ``codeindex`` / ``python`` can hit a
different install than the one loomgraph pinned (#76 PATH-bypass class — a
stale pipx codeindex silently shadowing the pinned dep). loomgraph already
calls codeindex via ``sys.executable -m codeindex.cli`` internally
(graph_export_ingest.py); this command exposes that same pinned-env invocation.

It is a thin passthrough: stdout/stderr/exit-code are codeindex's own (NOT
loomgraph JSON). That's intentional — ``codeindex init`` etc. have their own
human-facing output.
"""

from __future__ import annotations

import subprocess
import sys

import click

from .main import main


@main.command(
    "codeindex",
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def codeindex(args: tuple[str, ...]) -> None:
    """Run a codeindex command in loomgraph's own (pinned) Python environment.

    Thin passthrough — forwards stdout/stderr/exit-code from codeindex verbatim.
    Use this (not a bare ``codeindex`` or ``python -m codeindex.cli``) so the
    invocation matches the codeindex version loomgraph actually depends on.

    Examples:
        loomgraph codeindex init --yes        # generate .codeindex.yaml
        loomgraph codeindex init --dry-run    # preview what init would change
        loomgraph codeindex --version
    """
    if not args:
        click.echo(
            "Usage: loomgraph codeindex <command> [args...]\n"
            "Thin passthrough to codeindex in loomgraph's pinned venv.\n"
            "See `loomgraph codeindex --help` (forwards to codeindex's help).",
            err=True,
        )
        sys.exit(1)

    # [sys.executable, -m, codeindex.cli, ...user args] — pinned venv, never PATH.
    cmd = [sys.executable, "-m", "codeindex.cli", *args]
    completed = subprocess.run(cmd)
    sys.exit(completed.returncode)
