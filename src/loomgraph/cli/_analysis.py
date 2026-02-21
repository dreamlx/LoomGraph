"""CLI commands for impact analysis, deps, and overview."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings


@main.command()
@click.argument("target", default="HEAD")
@click.option("--staged", is_flag=True, help="Analyze staged changes instead of commit")
@click.option(
    "--base",
    default=None,
    help="Base branch/commit for range comparison (e.g., main..HEAD)",
)
@click.option("--depth", default=2, help="Caller traversal depth")
@click.option("--file", "file_path", type=click.Path(), help="Analyze specific file")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def impact(target: str, staged: bool, base: str | None, depth: int, file_path: str | None, workspace: str | None) -> None:
    """Analyze impact of code changes.

    TARGET: Commit reference (default: HEAD)

    Examples:
        loomgraph impact HEAD           # Analyze latest commit
        loomgraph impact --staged       # Analyze staged changes
        loomgraph impact main..HEAD     # Analyze branch diff
        loomgraph impact abc123         # Analyze specific commit
    """
    try:
        result = asyncio.run(_async_impact(target, staged, base, depth, file_path, workspace))

        # Add risk assessment
        from loomgraph.core.impact import RiskAssessor
        assessor = RiskAssessor()
        from loomgraph.core.impact import Caller, ChangedSymbol, ChangeType, ImpactResult

        # Reconstruct ImpactResult for risk assessment
        changed_symbols = [
            ChangedSymbol(
                name=s["name"],
                file=s["file"],
                change_type=ChangeType(s["change_type"]),
                lines_changed=s.get("lines_changed", 0),
            )
            for s in result.get("changed_symbols", [])
        ]
        direct_callers = [
            Caller(
                name=c["name"],
                file=c["file"],
                line=c.get("line", 0),
                depth=1,
            )
            for c in result.get("impact_analysis", {}).get("direct_callers", [])
        ]
        indirect_callers = [
            Caller(
                name=c["name"],
                file=c["file"],
                line=c.get("line", 0),
                depth=c.get("depth", 2),
            )
            for c in result.get("impact_analysis", {}).get("indirect_callers", [])
        ]

        impact_result = ImpactResult(
            commit=result.get("commit", ""),
            changed_symbols=changed_symbols,
            direct_callers=direct_callers,
            indirect_callers=indirect_callers,
            affected_modules=result.get("impact_analysis", {}).get("affected_modules", []),
            affected_tests=result.get("impact_analysis", {}).get("affected_tests", []),
        )

        risk = assessor.assess(impact_result)
        result["risk_assessment"] = risk.to_dict()

        output_success(result)

    except Exception as e:
        # Check if it's a git error
        error_msg = str(e)
        if "Invalid commit" in error_msg or "git" in error_msg.lower():
            output_error(
                code=ErrorCode.INVALID_INPUT,
                message=error_msg,
                suggestion="Check if the commit exists: git log --oneline",
            )
        else:
            output_error(
                code=ErrorCode.LIGHTRAG_ERROR,
                message=f"Impact analysis failed: {e}",
                suggestion="Check LightRAG status with: loomgraph status",
            )


async def _async_impact(
    target: str,
    staged: bool,
    base: str | None,
    depth: int,
    file_path: str | None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run async impact analysis."""
    from loomgraph.core.impact import ImpactAnalyzer
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    analyzer = ImpactAnalyzer(
        lightrag_client=client,
        repo_path=Path("."),
        max_depth=depth,
    )

    if staged:
        result = await analyzer.analyze_staged()
    elif base:
        # Parse range like "main..HEAD"
        if ".." in target:
            parts = target.split("..")
            result = await analyzer.analyze_branch_diff(parts[0], parts[1] if len(parts) > 1 else "HEAD")
        else:
            result = await analyzer.analyze_branch_diff(base, target)
    else:
        result = await analyzer.analyze_commit(target)

    return result.to_dict()


@main.command()
@click.option("--depth", "-d", default=2, help="Directory depth for module grouping")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def deps(depth: int, workspace: str | None) -> None:
    """Analyze module-level dependencies.

    Queries the knowledge graph to build a module dependency map.
    """
    try:
        result = asyncio.run(_async_deps(depth, workspace))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Dependency analysis failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_deps(depth: int, workspace: str | None = None) -> dict[str, Any]:
    """Run async dependency analysis."""
    from loomgraph.core.deps import DepsAnalyzer
    from loomgraph.core.lightrag_client import LightRAGClient

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    analyzer = DepsAnalyzer(client=client, depth=depth)
    result = await analyzer.analyze()
    return result.to_dict()


@main.command()
@click.option("--depth", "-d", default=2, help="Directory depth for module grouping")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option("--no-summary", is_flag=True, help="Skip LLM module summaries")
def overview(depth: int, workspace: str | None, no_summary: bool) -> None:
    """Generate project module overview.

    Queries the knowledge graph for a high-level view of all modules,
    optionally including LLM-generated summaries.
    """
    try:
        result = asyncio.run(_async_overview(depth, workspace, no_summary))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Overview generation failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_overview(
    depth: int, workspace: str | None = None, no_summary: bool = False
) -> dict[str, Any]:
    """Run async overview analysis."""
    from loomgraph.core.lightrag_client import LightRAGClient
    from loomgraph.core.overview import OverviewAnalyzer

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=get_auto_workspace(workspace),
    )

    analyzer = OverviewAnalyzer(client=client, depth=depth)
    result = await analyzer.analyze(no_summary=no_summary)
    return result.to_dict()
