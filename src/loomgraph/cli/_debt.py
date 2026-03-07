"""CLI commands for technical debt analysis."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import (
    ErrorCode,
    get_auto_workspace,
    output_error,
    output_success,
)
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings
from loomgraph.core.debt_analyzer import DebtAnalyzer
from loomgraph.core.lightrag_client import LightRAGClient


@main.command()
@click.option(
    "--codeindex-data",
    type=click.Path(exists=True, path_type=Path),
    help="Path to codeindex tech-debt JSON output file",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown", "console"]),
    default="json",
    help="Output format (default: json)",
)
@click.option(
    "--workspace",
    "-w",
    default=None,
    help="Workspace name for topology analysis (default: auto-detect from directory)",
)
@click.option(
    "--module",
    default=None,
    help="Module filter for topology analysis (e.g., 'cli' for src/cli/)",
)
@click.option(
    "--skip-topology",
    is_flag=True,
    help="Skip graph topology analysis (faster, codeindex-only)",
)
@click.option(
    "--with-git",
    is_flag=True,
    help="Enable git metrics analysis (EPIC-010 Feature 2)",
)
@click.option(
    "--git-since",
    default="3 months",
    help="Time window for git analysis (default: '3 months')",
)
def debt(
    codeindex_data: Path | None,
    output_format: str,
    workspace: str | None,
    module: str | None,
    skip_topology: bool,
    with_git: bool,
    git_since: str,
) -> None:
    """Analyze technical debt from codeindex data.

    Combines codeindex static analysis with LoomGraph graph topology
    and optionally git history metrics (EPIC-010 Feature 2).

    Examples:
        # Analyze from codeindex output only (fast)
        codeindex tech-debt ./src > debt.json
        loomgraph debt --codeindex-data debt.json --skip-topology

        # Full analysis with topology (requires indexed workspace)
        loomgraph debt --codeindex-data debt.json

        # Three-dimensional analysis (quality + topology + git)
        loomgraph debt --codeindex-data debt.json --with-git

        # Custom git time window
        loomgraph debt --codeindex-data debt.json --with-git --git-since "6 months"

        # Different output formats
        loomgraph debt --codeindex-data debt.json --format console
        loomgraph debt --codeindex-data debt.json --format markdown > report.md

        # Module-specific topology analysis
        loomgraph debt --codeindex-data debt.json --module cli
    """
    try:
        result = asyncio.run(
            _async_debt(
                codeindex_data, output_format, workspace, module, skip_topology, with_git, git_since
            )
        )
        output_success(result)

    except FileNotFoundError as e:
        output_error(ErrorCode.FILE_NOT_FOUND, str(e))
    except json.JSONDecodeError as e:
        output_error(ErrorCode.INVALID_INPUT, f"Invalid JSON in codeindex data: {e}")
    except Exception as e:
        output_error(ErrorCode.INVALID_INPUT, f"Debt analysis failed: {e}")


async def _async_debt(
    codeindex_data_path: Path | None,
    output_format: str,
    workspace: str | None,
    module: str | None,
    skip_topology: bool,
    with_git: bool,
    git_since: str,
) -> dict[str, Any]:
    """Async implementation of debt analysis.

    Args:
        codeindex_data_path: Optional path to codeindex JSON output
        output_format: Output format (json, markdown, console)
        workspace: Workspace name for topology analysis
        module: Module filter for topology analysis
        skip_topology: Skip topology analysis if True
        with_git: Enable git metrics analysis (EPIC-010 Feature 2)
        git_since: Time window for git analysis

    Returns:
        Debt report in requested format

    Raises:
        FileNotFoundError: If codeindex_data_path doesn't exist
        json.JSONDecodeError: If codeindex data is invalid JSON
    """
    # Load codeindex data if provided
    codeindex_data = None
    if codeindex_data_path:
        with open(codeindex_data_path) as f:
            codeindex_data = json.load(f)

    # Initialize LightRAG client for topology analysis (unless skipped)
    client = None
    if not skip_topology:
        settings = get_settings()
        workspace_name = get_auto_workspace(workspace)
        client = LightRAGClient(
            base_url=settings.lightrag.api_url,
            timeout=settings.lightrag.api_timeout,
            workspace=workspace_name,
        )

    # Analyze debt
    analyzer = DebtAnalyzer(client=client)
    report = await analyzer.analyze(
        codeindex_data=codeindex_data,
        module=module,
        with_git=with_git,
        git_since=git_since,
    )

    # Format output
    if output_format == "json":
        return report
    elif output_format == "markdown":
        return _format_markdown(report)
    else:  # console
        return _format_console(report)


def _format_markdown(report: dict[str, Any]) -> dict[str, Any]:
    """Format debt report as Markdown.

    Args:
        report: Debt report dict

    Returns:
        Dict with 'content' key containing Markdown string
    """
    md_lines = []

    # Header
    md_lines.append("# Technical Debt Analysis Report")
    md_lines.append("")
    md_lines.append(f"**Generated**: {report['timestamp']}")
    md_lines.append(f"**Project**: {report['project']}")
    md_lines.append("")

    # Overall Health
    health = report["overall_health"]
    md_lines.append("## Overall Health")
    md_lines.append("")
    md_lines.append(f"**Score**: {health['total_score']}/100 (Grade: {health['grade']})")
    md_lines.append("")
    md_lines.append("### Summary")
    md_lines.append(
        f"- **P0 Issues** (Critical): {health['summary']['p0_issues']}"
    )
    md_lines.append(f"- **P1 Issues** (High): {health['summary']['p1_issues']}")
    md_lines.append(f"- **P2 Issues** (Medium): {health['summary']['p2_issues']}")
    md_lines.append("")

    # Issues by Severity
    issues = report["issues"]
    for severity in ["P0", "P1", "P2"]:
        severity_issues = [i for i in issues if i["severity"] == severity]
        if not severity_issues:
            continue

        severity_label = {"P0": "Critical", "P1": "High", "P2": "Medium"}[severity]
        md_lines.append(f"## {severity_label} Priority Issues")
        md_lines.append("")

        for issue in severity_issues:
            md_lines.append(f"### {issue['id']}: {issue['entity']}")
            md_lines.append("")
            md_lines.append(f"**Category**: {issue['category']}")
            md_lines.append(f"**Type**: {issue['entity_type']}")
            md_lines.append(
                f"**Location**: {issue['location'].get('file', 'N/A')}"
            )
            if issue["suggestion"]:
                md_lines.append(f"**Suggestion**: {issue['suggestion']}")
            md_lines.append("")

    # Recommendations
    if report.get("recommendations"):
        md_lines.append("## Recommendations")
        md_lines.append("")
        for rec in report["recommendations"]:
            md_lines.append(f"- {rec}")
        md_lines.append("")

    return {"content": "\n".join(md_lines)}


def _format_console(report: dict[str, Any]) -> dict[str, Any]:
    """Format debt report for console output.

    Args:
        report: Debt report dict

    Returns:
        Dict with 'message' key containing formatted string
    """
    lines = []

    # Overall Health
    health = report["overall_health"]
    lines.append("=== Technical Debt Analysis ===")
    lines.append("")
    lines.append(
        f"Overall Score: {health['total_score']}/100 (Grade: {health['grade']})"
    )
    lines.append("")
    lines.append(
        f"P0 (Critical): {health['summary']['p0_issues']}  "
        f"P1 (High): {health['summary']['p1_issues']}  "
        f"P2 (Medium): {health['summary']['p2_issues']}"
    )
    lines.append("")

    # Issues summary
    issues = report["issues"]
    if issues:
        lines.append(f"Total Issues: {len(issues)}")
        lines.append("")

        # Group by category
        by_category: dict[str, list[dict]] = {}
        for issue in issues:
            cat = issue["category"]
            by_category.setdefault(cat, []).append(issue)

        for category, cat_issues in sorted(by_category.items()):
            lines.append(f"  {category}: {len(cat_issues)}")

    else:
        lines.append("No technical debt issues detected!")

    return {"message": "\n".join(lines), "report": report}
