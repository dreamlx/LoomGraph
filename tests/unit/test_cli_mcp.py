"""CLI contract tests for Claude Code MCP activation guidance."""

from __future__ import annotations

from click.testing import CliRunner

from loomgraph.cli.main import main


def test_install_config_prints_scope_aware_claude_command() -> None:
    """Default guidance must not require editing a legacy JSON config."""
    result = CliRunner().invoke(main, ["mcp", "install-config"])

    assert result.exit_code == 0, result.output
    assert "claude mcp add --scope local loomgraph -- loomgraph mcp serve" in result.output
    assert "claude mcp get loomgraph" in result.output
    assert "mcp.json" not in result.output


def test_install_config_scope_changes_printed_claude_command() -> None:
    """The caller chooses the Claude Code configuration scope explicitly."""
    result = CliRunner().invoke(
        main, ["mcp", "install-config", "--scope", "project"]
    )

    assert result.exit_code == 0, result.output
    assert "claude mcp add --scope project loomgraph -- loomgraph mcp serve" in result.output


def test_install_config_path_keeps_explicit_static_json_export(tmp_path) -> None:
    """JSON output remains available only when a caller explicitly asks for it."""
    path = tmp_path / "mcp.json"
    result = CliRunner().invoke(
        main, ["mcp", "install-config", "--path", str(path)]
    )

    assert result.exit_code == 0, result.output
    assert path.exists()
    assert '"loomgraph"' in path.read_text(encoding="utf-8")
