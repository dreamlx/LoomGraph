"""LoomGraph CLI - AI Agent Friendly Interface.

Design: CLI outputs JSON for machine parsing by AI Agent (Claude Code).
See docs/api/CLI_DESIGN.md for full specification.
"""

from __future__ import annotations

import click

from loomgraph import __version__
from loomgraph.cli._common import _setup_logging


class _QuietHintGroup(click.Group):
    """Group that annotates `-q`-after-subcommand usage errors (#163/#166).

    Click parses global options only before the subcommand; git/gh muscle
    memory puts them after, and the bare ``No such option '-q'`` cost a
    dogfood first-try on the post-commit hook. We don't reparse (fragile) —
    we amend the UsageError message in flight so whatever prints it (click's
    ``show()`` in standalone mode, or ``cli_entry``'s handler) carries the
    correct form.
    """

    def invoke(self, ctx: click.Context) -> object:
        try:
            return super().invoke(ctx)
        except click.exceptions.UsageError as exc:
            msg = exc.format_message()
            # click 8.3 formats the option error as `No such option: -q`,
            # 8.4 as `No such option '-q'` — match the bare substring for both.
            if "-q" in msg or "--quiet" in msg:
                exc.message = (
                    f"{msg}\n\n  Hint: -q/--quiet is a global flag — put it "
                    "before the command: loomgraph -q <command> [args]"
                )
            raise


@click.group(cls=_QuietHintGroup)
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
from loomgraph.cli import (  # noqa: E402, F401
    _analysis,
    _backfill,
    _codeindex,
    _debt,
    _hooks,
    _import_export,
    _indexing,
    _mcp,
    _search,
    _setup,
    _workspace,
)

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
    check_storage,
)


def cli_entry() -> None:
    """User-facing entrypoint.

    Wraps click's `main()` so a `ConfigSchemaError` (stale YAML) becomes a
    single-line stderr message instead of a pydantic stack trace.
    """
    import sys

    from loomgraph.core.config import ConfigSchemaError

    try:
        main(standalone_mode=False)
    except ConfigSchemaError as exc:
        sys.stderr.write(f"loomgraph: {exc}\n")
        sys.exit(2)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.exceptions.Abort:
        sys.stderr.write("Aborted!\n")
        sys.exit(1)


if __name__ == "__main__":
    cli_entry()
