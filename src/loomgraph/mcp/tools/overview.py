"""MCP tool: `overview` — module summaries (optional LLM)."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._analysis import _async_overview
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

DEFAULT_DEPTH = 1

TOOL_SPEC = Tool(
    name="loomgraph_overview",
    title="Project / module overview",
    description=(
        "High-level overview of the workspace: per-module entity counts, "
        "key public surfaces, and (optionally) LLM-generated module "
        "summaries. Pass `no_summary=true` to skip the LLM and get only "
        "structural counts — fast and free."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "depth": {
                "type": "integer",
                "description": "Module hierarchy depth. Default 1.",
                "default": DEFAULT_DEPTH,
                "minimum": 1,
                "maximum": 4,
            },
            "no_summary": {
                "type": "boolean",
                "description": (
                    "Skip LLM-generated summaries (returns counts only). "
                    "Default false."
                ),
                "default": False,
            },
            "workspace": {"type": "string"},
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    depth = arguments.get("depth", DEFAULT_DEPTH)
    no_summary = arguments.get("no_summary", False)
    workspace = resolve_workspace(arguments)
    return await safe_call(
        lambda: _async_overview(
            depth=depth, workspace=workspace, no_summary=no_summary
        ),
        failure_code="OVERVIEW_FAILED",
        failure_hint=(
            "If the LLM fails, retry with `no_summary=true` for "
            "structural counts only."
        ),
    )
