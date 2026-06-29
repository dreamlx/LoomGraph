"""MCP tool: `impact` — change-impact analysis from git diff."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._analysis import _async_impact
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

DEFAULT_DEPTH = 2

TOOL_SPEC = Tool(
    name="loomgraph_impact",
    title="Change-impact analysis",
    description=(
        "Deterministically analyze the impact of a code change: given a "
        "git ref / staged diff / single file, return all entities that "
        "would be affected via the call graph up to N hops. Read-only "
        "wrt the workspace; uses `git diff` to identify changed entities "
        "then walks edges. Best to call AFTER you have a concrete "
        "ref or file path."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "Git ref (e.g. `HEAD`, `main..feature/x`) or commit SHA. "
                    "Required if `staged` is false and `file_path` is unset."
                ),
            },
            "staged": {
                "type": "boolean",
                "description": "Analyze staged changes instead of a ref.",
                "default": False,
            },
            "base": {
                "type": "string",
                "description": (
                    "Optional base ref to diff against (defaults to merge-base)."
                ),
            },
            "depth": {
                "type": "integer",
                "description": "Caller-chain depth to walk. Default 2.",
                "default": DEFAULT_DEPTH,
                "minimum": 1,
                "maximum": 10,
            },
            "file_path": {
                "type": "string",
                "description": "Analyze impact of changes to a specific file.",
            },
            "workspace": {"type": "string"},
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    target = arguments.get("target", "HEAD")
    staged = arguments.get("staged", False)
    base = arguments.get("base")
    depth = arguments.get("depth", DEFAULT_DEPTH)
    file_path = arguments.get("file_path")
    workspace = resolve_workspace(arguments)
    return await safe_call(
        lambda: _async_impact(
            target=target,
            staged=staged,
            base=base,
            depth=depth,
            file_path=file_path,
            workspace=workspace,
        ),
        failure_code="IMPACT_FAILED",
        failure_hint=(
            "Verify the ref / staged diff exists: `git status` / "
            "`git rev-parse <target>`."
        ),
    )
