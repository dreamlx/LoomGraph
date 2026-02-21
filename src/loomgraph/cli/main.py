"""LoomGraph CLI - AI Agent Friendly Interface.

Design: CLI outputs JSON for machine parsing by AI Agent (Claude Code).
See docs/api/CLI_DESIGN.md for full specification.
"""

from __future__ import annotations

import click

from loomgraph import __version__
from loomgraph.cli._common import _setup_logging


@click.group()
@click.version_option(version=__version__, prog_name="loomgraph")
@click.option("--verbose", "-v", is_flag=True, help="Show debug logs on stderr")
@click.option("--quiet", "-q", is_flag=True, help="Suppress all non-JSON output")
def main(verbose: bool, quiet: bool) -> None:
    """LoomGraph: Enterprise Code Intelligence Engine.

    AI Agent friendly CLI for code indexing, search, and graph queries.
    All commands output JSON for machine parsing.
    """
    _setup_logging(verbose, quiet)


# Bottom imports trigger @main.command() registration in each submodule.
from loomgraph.cli import _analysis, _indexing, _search, _setup, _workspace  # noqa: E402, F401

# Backward-compatible re-exports (tests import these from loomgraph.cli.main)
from loomgraph.cli._common import (  # noqa: E402, F401
    ErrorCode,
    get_auto_workspace,
    output_error,
    output_partial_error,
    output_success,
)
from loomgraph.cli._deps_check import (  # noqa: E402, F401
    check_codeindex,
    check_embedding,
    check_lightrag_api,
)

if __name__ == "__main__":
    main()
