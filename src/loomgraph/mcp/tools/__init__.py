"""LoomGraph MCP tool implementations.

Each tool module exports:
  - `TOOL_SPEC: mcp.types.Tool` — declarative schema
  - `async def handle(arguments: dict) -> list[mcp.types.TextContent]` — the handler

The handler MUST return TextContent whose `text` is a JSON-encoded
response of shape `{"success": bool, "data": ...}` or
`{"success": false, "error": {...}}`, mirroring the CLI output
convention so AI agents see a consistent surface across CLI and MCP.
"""

from __future__ import annotations
