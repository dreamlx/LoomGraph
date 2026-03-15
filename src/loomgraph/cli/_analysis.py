"""CLI commands for impact analysis, deps, overview, topology, and check."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import (
    ErrorCode,
    output_error,
    output_success,
    prepare_workspace_client,
)
from loomgraph.cli.main import main


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

    ws, client = await prepare_workspace_client(workspace)

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

    ws, client = await prepare_workspace_client(workspace)

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
    from loomgraph.core.overview import OverviewAnalyzer

    ws, client = await prepare_workspace_client(workspace)

    analyzer = OverviewAnalyzer(client=client, depth=depth)
    result = await analyzer.analyze(no_summary=no_summary)
    return result.to_dict()


@main.command()
@click.option("--hub-threshold", default=8, help="Min in-degree to flag as hub")
@click.option("--god-threshold", default=10, help="Min out-degree to flag as god function")
@click.option("--module", default=None, help="Module prefix filter (e.g. 'cli')")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def topology(hub_threshold: int, god_threshold: int, module: str | None, workspace: str | None) -> None:
    """Analyze knowledge graph topology for structural code smells.

    Detects orphan entities, hub fragility, god functions,
    placeholder modules, and cross-module coupling.
    """
    try:
        result = asyncio.run(
            _async_topology(hub_threshold, god_threshold, module, workspace)
        )
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Topology analysis failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_topology(
    hub_threshold: int,
    god_threshold: int,
    module: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run async topology analysis."""
    from loomgraph.core.topology import TopologyAnalyzer

    ws, client = await prepare_workspace_client(workspace)

    analyzer = TopologyAnalyzer(
        client=client,
        hub_threshold=hub_threshold,
        god_threshold=god_threshold,
        module=module,
    )
    result = await analyzer.analyze()
    return result.to_dict()


@main.command()
@click.option(
    "--repo-path",
    type=click.Path(exists=True),
    default=".",
    help="Base path for source_id file verification",
)
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def check(repo_path: str, workspace: str | None) -> None:
    """Check index freshness by verifying source_id file paths.

    Validates that entity source_ids reference files that still exist on disk.
    """
    try:
        result = asyncio.run(_async_check(repo_path, workspace))
        output_success(result)
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Check failed: {e}",
            suggestion="Check LightRAG status with: loomgraph status",
        )


async def _async_check(
    repo_path: str,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run async index freshness check."""
    ws, client = await prepare_workspace_client(workspace)

    # Try server-side get_source_ids first, fallback to get_all_entities
    try:
        source_ids = await client.get_source_ids()
    except Exception:
        entities = await client.get_all_entities()
        source_ids = list({e.get("source_id", "") for e in entities if e.get("source_id")})

    base = Path(repo_path)
    valid = 0
    stale = 0
    stale_entries: list[dict[str, Any]] = []
    seen_files: set[str] = set()

    for sid in source_ids:
        if not sid or sid == "external":
            continue
        # Strip line number suffix like ":10-20"
        file_path = re.sub(r":\d+(-\d+)?$", "", sid)
        if file_path in seen_files:
            continue
        seen_files.add(file_path)

        if (base / file_path).exists():
            valid += 1
        else:
            stale += 1
            stale_entries.append({
                "source_id": sid,
                "file_path": file_path,
                "reason": "file_not_found",
                "suggestion": "Run 'loomgraph update' or 'loomgraph index --clear .'",
            })

    total = valid + stale
    freshness_ratio = valid / total if total > 0 else 1.0

    suggestion = ""
    if stale > 0:
        suggestion = (
            f"{stale} source paths are stale. "
            "Run 'loomgraph index --clear .' to rebuild."
        )

    return {
        "freshness": {
            "total_source_paths": total,
            "valid": valid,
            "stale": stale,
            "freshness_ratio": round(freshness_ratio, 3),
        },
        "stale_entries": stale_entries,
        "suggestion": suggestion,
    }


@main.command("git-metrics")
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option("--since", default="3 months", help="Time window (e.g., '3 months', '6 months', '1 year')")
@click.option("--output", "-o", type=click.Path(), help="Save results to JSON file")
def git_metrics(path: str, since: str, output: str | None) -> None:
    """Analyze git history metrics for technical debt.

    PATH: Repository root path (default: current directory)

    Examples:
        loomgraph git-metrics ./src               # Analyze src directory
        loomgraph git-metrics --since "6 months"  # 6-month window
        loomgraph git-metrics --output metrics.json  # Save to file
    """
    try:
        from loomgraph.core.git_metrics import GitMetricsAnalyzer

        analyzer = GitMetricsAnalyzer(Path(path), since=since)
        result = analyzer.analyze()

        # Convert to dict for JSON serialization
        output_data = {
            "repo_path": str(result.repo_path),
            "since": result.since,
            "analyzed_at": result.analyzed_at.isoformat(),
            "summary": result.summary,
            "hotspots": [
                {
                    "file": h.file,
                    "change_freq": h.change_freq,
                    "hotspot_score": h.hotspot_score,
                    "rank": h.rank,
                }
                for h in result.hotspots
            ],
            "bus_factor": [
                {
                    "file": bf.file,
                    "owner": bf.owner,
                    "contributors": bf.contributors,
                    "risk_level": bf.risk_level,
                }
                for bf in result.bus_factor
            ],
            "file_metrics": {
                file_path: {
                    "change_frequency": fm.change_frequency,
                    "last_modified_days": fm.last_modified_days,
                    "authors": fm.authors,
                    "primary_author": fm.primary_author,
                    "bug_fix_count": fm.bug_fix_count,
                    "bug_fix_ratio": round(fm.bug_fix_ratio, 3),
                    "churn": fm.churn,
                    "age_days": fm.age_days,
                }
                for file_path, fm in result.file_metrics.items()
            },
        }

        # Save to file if --output specified
        if output:
            import json

            with open(output, "w") as f:
                json.dump(output_data, f, indent=2)

            output_success(
                {
                    "message": f"Git metrics saved to {output}",
                    "hotspots": len(result.hotspots),
                    "bus_factor_critical": result.summary.get("bus_factor_critical", 0),
                }
            )
        else:
            # Output to console
            output_success(output_data)

    except Exception as e:
        output_error(f"Git metrics analysis failed: {e}", ErrorCode.OPERATION_FAILED)


@main.command("trends")
@click.option("--entity", "-e", required=True, help="Entity identifier (e.g., 'src/auth/user_service.py')")
@click.option("--metric", "-m", default="complexity", help="Metric to analyze (default: complexity)")
@click.option("--months", default=6, help="Number of months to analyze (default: 6)")
@click.option("--workspace", "-w", default=None, help="Filter by workspace (default: all)")
def trends(entity: str, metric: str, months: int, workspace: str | None) -> None:
    """Analyze code complexity trends over time (EPIC-010 Feature 3).

    Requires historical snapshots collected by running 'loomgraph debt' multiple times.

    Examples:
        loomgraph trends -e "src/auth/user_service.py"           # Analyze complexity trend
        loomgraph trends -e "src/core/" -m "coupling" --months 12  # 12-month coupling trend
        loomgraph trends -e "src/api/" -w "myproject:main"        # Workspace-specific trend
    """
    try:
        from loomgraph.core.trends import TrendAnalyzer

        analyzer = TrendAnalyzer()

        # Analyze trend
        result = analyzer.analyze(
            entity=entity,
            metric_name=metric,
            months=months,
            workspace=workspace,
        )

        # Format output
        output_data = {
            "entity": result.entity,
            "entity_type": result.entity_type,
            "metric_name": result.metric_name,
            "time_range": result.time_range,
            "regression": {
                "slope": round(result.regression.slope, 4),
                "intercept": round(result.regression.intercept, 2),
                "r_squared": round(result.regression.r_squared, 3),
                "trend_direction": result.regression.trend_direction,
            },
            "forecast": round(result.forecast, 2),
            "alert": result.alert,
            "data_points": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "value": p.value,
                    "label": p.label,
                }
                for p in result.data_points
            ],
            "chart": result.chart,
        }

        output_success(output_data)

    except ValueError as e:
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=str(e),
            suggestion="Run 'loomgraph debt' multiple times over weeks/months to collect trend data.",
        )
    except Exception as e:
        output_error(
            code=ErrorCode.LIGHTRAG_ERROR,
            message=f"Trend analysis failed: {e}",
        )
