"""MCP composite tool: `loomgraph_branch_diff`.

The CLI's branch-diff command is the canonical orchestration. This adapter
reuses its ref provisioning and analyzer kernels while keeping the MCP
response identical to the CLI's `data` payload.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._branch_diff import _async_branch_diff, _provision_ref
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.core.git import is_git_repository, resolve_ref
from loomgraph.mcp.tools._common import (
    error_response,
    safe_call,
)

TOOL_SPEC = Tool(
    name="loomgraph_branch_diff",
    title="Structural diff between two git refs",
    description=(
        "Provision two git refs as isolated snapshot workspaces and return "
        "the same structural diff as `loomgraph branch-diff A..B`: added and "
        "removed entities/edges, broken and new call chains, content changes, "
        "and module coupling delta. The first call may take minutes on a "
        "large repository because each missing ref is cold-indexed; reruns "
        "reuse unchanged snapshots and are fast. This is a write-capable "
        "MCP tool and requires codeindex. Provisioning is idempotent: a "
        "moved ref is rebuilt so stale diffs are never returned."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "base_ref": {
                "type": "string",
                "description": "Base git ref (branch, tag, commit, or HEAD).",
            },
            "head_ref": {
                "type": "string",
                "description": "Head git ref (branch, tag, commit, or HEAD).",
            },
            "repo_path": {
                "type": "string",
                "description": "Git repository path. Defaults to the MCP server cwd.",
                "default": ".",
            },
        },
        "required": ["base_ref", "head_ref"],
    },
)


async def _run_branch_diff(
    base_ref: str, head_ref: str, repo_path: str = "."
) -> dict[str, Any]:
    """Run branch-diff's provisioning + analyzer kernels off the MCP loop."""
    repo = Path(repo_path).resolve()
    if not is_git_repository(repo):
        raise ValueError(f"Not a git repository: {repo}")

    codeindex_status = await asyncio.to_thread(check_codeindex)
    if not codeindex_status.get("installed"):
        raise RuntimeError(
            "codeindex not found in the loomgraph environment; "
            "install ai-codeindex before calling loomgraph_branch_diff"
        )

    start = time.time()
    base_sha, head_sha = await asyncio.gather(
        asyncio.to_thread(resolve_ref, repo, base_ref),
        asyncio.to_thread(resolve_ref, repo, head_ref),
    )
    repo_dir = repo.name.lower()

    # _provision_ref is intentionally the exact CLI kernel. It owns the
    # decision table (created/reused/rebuilt/fallback) and uses asyncio.run
    # internally, so run each invocation in a worker thread from this async
    # MCP handler. Sequential provisioning avoids two cold SQLite writers
    # competing for the same storage directory.
    base_info = await asyncio.to_thread(
        _provision_ref, repo, repo_dir, base_ref, base_sha
    )
    head_info = await asyncio.to_thread(
        _provision_ref, repo, repo_dir, head_ref, head_sha
    )
    diff = await _async_branch_diff(
        base_info["workspace"], head_info["workspace"]
    )
    return {
        "base": base_info,
        "head": head_info,
        "diff": diff,
        "duration_seconds": round(time.time() - start, 2),
    }


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    base_ref = str(arguments.get("base_ref") or "").strip()
    head_ref = str(arguments.get("head_ref") or "").strip()
    if not base_ref or not head_ref:
        return error_response(
            code="INVALID_INPUT",
            message="base_ref and head_ref are required.",
        )
    repo_path = str(arguments.get("repo_path") or ".")
    return await safe_call(
        lambda: _run_branch_diff(base_ref, head_ref, repo_path),
        failure_code="BRANCH_DIFF_FAILED",
        failure_hint=(
            "Check that both refs exist and codeindex is installed; "
            "rerun after the first cold snapshot completes."
        ),
    )
