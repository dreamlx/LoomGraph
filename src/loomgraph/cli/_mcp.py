"""CLI command: `loomgraph mcp serve` — start the MCP stdio server.

This is the production entry point referenced from `~/.claude/mcp.json`
(or equivalent) so Claude Code / Cursor / Codex can launch loomgraph
as a native MCP server.

The server itself is in `loomgraph.mcp.server`; this module is
only the click wiring.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, output_error
from loomgraph.cli.main import main


@main.group()
def mcp() -> None:
    """MCP server commands.

    LoomGraph speaks the Model Context Protocol so AI agents can call
    `find` / `graph` / `topology` / `impact` / `deps` / `overview` /
    `workspace_*` as native tools (no CLI subprocess overhead).
    """


@mcp.command("serve")
@click.option(
    "--default-workspace",
    default=None,
    help=(
        "Workspace name to use when a tool call omits the `workspace` "
        "argument. Equivalent to setting LOOMGRAPH_MCP_DEFAULT_WORKSPACE."
    ),
)
def serve(default_workspace: str | None) -> None:
    """Start the MCP server over stdio."""
    try:
        from loomgraph.mcp import server as mcp_server
        from loomgraph.mcp.tools._common import DEFAULT_WORKSPACE_ENV
    except ImportError as exc:
        output_error(
            code=ErrorCode.DEPENDENCIES_MISSING,
            message=f"MCP SDK not installed: {exc}",
            suggestion="pip install loomgraph[mcp] or pipx inject loomgraph mcp",
        )
        return

    if default_workspace:
        import os
        os.environ[DEFAULT_WORKSPACE_ENV] = default_workspace

    # Logs to stderr only — stdout is the MCP protocol channel.
    import logging
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="loomgraph-mcp [%(levelname)s] %(message)s",
    )
    asyncio.run(mcp_server.serve_stdio())


@mcp.command("install-config")
@click.option(
    "--path",
    default=None,
    help="Path to Claude Code MCP config (default: ~/.claude/mcp.json).",
)
def install_config(path: str | None) -> None:
    """Print or write the Claude Code MCP config entry for loomgraph.

    By default prints to stdout so the user can copy-paste; pass a
    --path to merge it in-place.
    """
    import json
    from pathlib import Path

    entry = {
        "loomgraph": {
            "command": "loomgraph",
            "args": ["mcp", "serve"],
        }
    }
    snippet = json.dumps({"mcpServers": entry}, indent=2)

    if path is None:
        click.echo("# Add this to your Claude Code MCP config")
        click.echo("# (default location: ~/.claude/mcp.json)")
        click.echo(snippet)
        return

    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except json.JSONDecodeError:
            output_error(
                code=ErrorCode.INVALID_INPUT,
                message=f"Existing config at {p} is not valid JSON.",
                suggestion="Inspect manually or delete the file before retrying.",
            )
            return

    servers = existing.setdefault("mcpServers", {})
    servers["loomgraph"] = entry["loomgraph"]
    p.write_text(json.dumps(existing, indent=2))
    click.echo(f"✓ Wrote loomgraph entry to {p}")
