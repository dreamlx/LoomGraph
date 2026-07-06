"""MCP tool: `loomgraph_debt` — debt score (topology + git layers).

Side-effect-free read. The codeindex *static* layer (giant_files /
test_smells) needs a JSON file the MCP caller rarely has on hand, so
this primitive runs the topology + git dimensions only — same shape the
`loomgraph_debt_audit` composite uses for its `debt` dimension. For the
full static layer use `loomgraph debt --codeindex-data <file>` CLI (#62).
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from loomgraph.cli._debt import _async_debt
from loomgraph.mcp.tools._common import resolve_workspace, safe_call

TOOL_SPEC = Tool(
    name="loomgraph_debt",
    title="Technical debt score (topology + git)",
    description=(
        "Multi-dimensional debt score for the workspace: topology smells "
        "(orphans/hubs/gods), coupling, and optionally git hotspots. This "
        "is the `debt` dimension of `loomgraph_debt_audit` exposed as a "
        "single primitive. The codeindex static layer (giant_files / "
        "test_smells) needs a JSON input the MCP caller rarely has — use "
        "`loomgraph debt --codeindex-data` CLI for that; this tool runs "
        "topology + git only."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "description": (
                    "Absolute path-prefix filter (e.g. 'src/'); excludes "
                    "docs/scripts/tests. Wins over module (#61)."
                ),
            },
            "module": {"type": "string", "description": "Deprecated — prefer scope."},
            "workspace": {"type": "string"},
            "with_git": {"type": "boolean", "default": False},
            "git_since": {"type": "string", "default": "3 months"},
            "skip_topology": {"type": "boolean", "default": False},
        },
    },
)


async def handle(arguments: dict[str, Any]) -> list[TextContent]:
    workspace = resolve_workspace(arguments)
    return await safe_call(
        lambda: _async_debt(
            codeindex_data_path=None,
            output_format="json",
            workspace=workspace,
            module=arguments.get("module"),
            scope=arguments.get("scope"),
            skip_topology=arguments.get("skip_topology", False),
            with_git=arguments.get("with_git", False),
            git_since=arguments.get("git_since", "3 months"),
        ),
        failure_code="DEBT_FAILED",
        failure_hint="Confirm the workspace is indexed: `loomgraph workspace info`.",
    )
