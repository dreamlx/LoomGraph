"""MCP composite tool: `loomgraph_debt_audit` — 10-dimension debt report.

Mirrors what the `/loomgraph-debt-radar` skill orchestrates today (7-8
sequential CLI subprocesses), but:
- Runs all dimensions in parallel via asyncio.gather
- Returns structured dict per dimension; agent composes the prose
- Gracefully degrades when a dimension fails (git not present, no
  historical snapshots, etc.) — top-level `success=true` if any
  dimension produced data

Each dimension lands as `{data: <dict>|null, error: <str>|null}` so the
consumer can render mixed-state reports without crashing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._analysis import _async_check, _async_deps, _async_overview, _async_topology
from loomgraph.cli._debt import _async_debt
from loomgraph.cli._workspace import _async_workspace_info
from loomgraph.mcp.tools._common import error_response, resolve_workspace, success_response
from loomgraph.mcp.tools.git_metrics import gather

TOOL_SPEC = Tool(
    name="loomgraph_debt_audit",
    title="10-dimension technical debt audit",
    description=(
        "Run the complete loomgraph technical-debt audit in ONE call: "
        "static debt scoring + topology smells + git hotspots + module "
        "dependencies + workspace stats + index freshness + (optionally) "
        "trend forecasts for top-N hotspots. Returns structured data per "
        "dimension; the calling agent composes the narrative.\n\n"
        "Replaces the multi-step `/loomgraph-debt-radar` skill flow with "
        "a single MCP call. ~10× faster (parallel) and ensures consistent "
        "dimension coverage across runs. Dimensions that can't be "
        "computed (e.g. no git, no historical snapshots) come back as "
        "`{data: null, error: <reason>}` rather than failing the whole "
        "report."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": (
                    "Source directory for the static analysis layer "
                    "(passed to codeindex tech-debt). Default: cwd."
                ),
                "default": ".",
            },
            "with_git": {
                "type": "boolean",
                "description": (
                    "Enable git-history dimensions (hotspots, bus factor, "
                    "defect magnets). Defaults to true; auto-disables if "
                    "the path isn't a git repo."
                ),
                "default": True,
            },
            "git_since": {
                "type": "string",
                "description": "Git history window (default: '3 months').",
                "default": "3 months",
            },
            "trends_top_n": {
                "type": "integer",
                "description": (
                    "How many top-hotspot files to also run trends "
                    "analysis on. Trends needs ≥3 historical snapshots; "
                    "results are best-effort. Default 3; set 0 to skip."
                ),
                "default": 3,
                "minimum": 0,
                "maximum": 10,
            },
            "workspace": {
                "type": "string",
                "description": "Override the workspace to query.",
            },
        },
    },
)


async def _gather_named(named_coros: list[tuple[str, Any]]) -> dict[str, dict[str, Any]]:
    """Run named coroutines concurrently; each lands as `{data, error}`."""
    results = await asyncio.gather(
        *(c for _, c in named_coros), return_exceptions=True
    )
    out: dict[str, dict[str, Any]] = {}
    for (name, _), res in zip(named_coros, results, strict=True):
        if isinstance(res, BaseException):
            out[name] = {"data": None, "error": f"{type(res).__name__}: {res}"}
        else:
            out[name] = {"data": res, "error": None}
    return out


async def _trends_for_hotspots(
    git_dim: dict[str, Any] | None, top_n: int, workspace: str | None
) -> list[dict[str, Any]]:
    """Best-effort trends for the top-N hotspot files. Skips silently when
    historical snapshots are insufficient (the common case before the
    project has been audited a few times)."""
    if top_n <= 0 or not git_dim or not git_dim.get("data"):
        return []
    hotspots = git_dim["data"].get("hotspots") or []
    top = [h["file"] for h in hotspots[:top_n] if h.get("file")]
    if not top:
        return []

    from loomgraph.core.trends import TrendAnalyzer

    def _run_one(entity: str) -> dict[str, Any]:
        analyzer = TrendAnalyzer()
        try:
            r = analyzer.analyze(
                entity=entity, metric_name="complexity",
                months=6, workspace=workspace,
            )
            return {
                "entity": r.entity,
                "metric": r.metric_name,
                "trend_direction": r.regression.trend_direction,
                "slope": round(r.regression.slope, 4),
                "r_squared": round(r.regression.r_squared, 3),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"entity": entity, "error": f"{type(exc).__name__}: {exc}"}

    return await asyncio.gather(*[asyncio.to_thread(_run_one, e) for e in top])


def _is_git_repo(path: str) -> bool:
    return (Path(path) / ".git").exists() or (
        # Look up to 5 parents
        any((Path(path).resolve().parents[i] / ".git").exists() for i in range(5))
        if Path(path).exists()
        else False
    )


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    source_path = arguments.get("source_path", ".")
    with_git_arg = arguments.get("with_git", True)
    git_since = arguments.get("git_since", "3 months")
    trends_top_n = int(arguments.get("trends_top_n", 3))
    workspace = resolve_workspace(arguments)

    git_enabled = with_git_arg and _is_git_repo(source_path)

    # Schedule parallel dimensions
    named: list[tuple[str, Any]] = [
        ("debt", _async_debt(
            codeindex_data_path=None,
            output_format="json",
            workspace=workspace,
            module=None,
            scope=None,
            skip_topology=False,
            with_git=git_enabled,
            git_since=git_since,
        )),
        ("deps", _async_deps(depth=2, workspace=workspace)),
        ("overview", _async_overview(depth=1, workspace=workspace, no_summary=True)),
        ("topology", _async_topology(
            hub_threshold=10, god_threshold=10, module=None, workspace=workspace,
        )),
        ("workspace_info", _async_workspace_info(workspace, None)),
        ("check", _async_check(repo_path=source_path, workspace=workspace)),
    ]
    if git_enabled:
        named.append(("git_metrics", gather(source_path, git_since)))

    try:
        dims = await _gather_named(named)
    except Exception as exc:  # noqa: BLE001
        return error_response(
            code="DEBT_AUDIT_FAILED",
            message=f"{type(exc).__name__}: {exc}",
            suggestion="Run `loomgraph workspace info` to confirm the workspace is indexed.",
        )

    trends = await _trends_for_hotspots(dims.get("git_metrics"), trends_top_n, workspace)

    dim_count = sum(1 for d in dims.values() if d.get("error") is None)
    if dim_count == 0:
        return error_response(
            code="DEBT_AUDIT_FAILED",
            message="All dimensions failed — workspace likely not indexed.",
            suggestion="Run `loomgraph index .` then retry.",
        )

    return success_response({
        "workspace": workspace,
        "git_enabled": git_enabled,
        "dimensions": dims,
        "trends": trends,
        "summary": {
            "dimensions_succeeded": dim_count,
            "dimensions_attempted": len(dims),
            "trends_attempted": len(trends),
            "trends_with_data": sum(
                1 for t in trends if not t.get("error")
            ),
        },
    })
