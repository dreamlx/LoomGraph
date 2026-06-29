"""Tests for the MCP server skeleton + Phase 1 tools (find + graph).

We can't easily test the stdio loop end-to-end inside pytest, so we
exercise:
- `build_server()` produces a Server with the expected tools registered
- Each tool's `handle()` function returns a JSON-encoded TextContent
  response that follows the {"success": bool, "data"/"error": ...} shape
- The shared `_common.resolve_workspace` honors per-call > env var > None
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from loomgraph.mcp.server import _TOOL_HANDLERS, _TOOL_SPECS, build_server
from loomgraph.mcp.tools import _common
from loomgraph.mcp.tools import find as t_find
from loomgraph.mcp.tools import graph as t_graph

# ---- Registration --------------------------------------------------------

def test_phase1_tools_registered():
    """Both Phase 1 tools must be discoverable from the registry."""
    assert "loomgraph_find" in _TOOL_HANDLERS
    assert "loomgraph_graph" in _TOOL_HANDLERS
    names = {spec.name for spec in _TOOL_SPECS}
    assert {"loomgraph_find", "loomgraph_graph"}.issubset(names)


def test_tool_specs_have_required_fields():
    """Schema sanity — every tool must have a description + inputSchema."""
    for spec in _TOOL_SPECS:
        assert spec.description, f"tool {spec.name} missing description"
        assert spec.inputSchema, f"tool {spec.name} missing inputSchema"
        assert spec.inputSchema.get("type") == "object"
        # `properties` must define at least the required ones
        props = spec.inputSchema.get("properties", {})
        for req in spec.inputSchema.get("required", []):
            assert req in props, f"{spec.name}: required '{req}' missing from properties"


def test_build_server_constructs_without_error():
    """No stdio call — just verify the Server object is constructible."""
    server = build_server()
    assert server.name == "loomgraph"


# ---- Workspace resolution ------------------------------------------------

def test_resolve_workspace_per_call_wins():
    with patch.dict(os.environ, {_common.DEFAULT_WORKSPACE_ENV: "from-env"}):
        assert _common.resolve_workspace({"workspace": "from-call"}) == "from-call"


def test_resolve_workspace_env_fallback():
    with patch.dict(os.environ, {_common.DEFAULT_WORKSPACE_ENV: "from-env"}):
        assert _common.resolve_workspace({}) == "from-env"


def test_resolve_workspace_none_when_no_source(monkeypatch):
    monkeypatch.delenv(_common.DEFAULT_WORKSPACE_ENV, raising=False)
    assert _common.resolve_workspace({}) is None


# ---- Response envelope ---------------------------------------------------

def test_success_response_shape():
    contents = _common.success_response({"answer": 42})
    assert len(contents) == 1
    payload = json.loads(contents[0].text)
    assert payload == {"success": True, "data": {"answer": 42}}


def test_error_response_shape():
    contents = _common.error_response(
        "FIND_FAILED", "no such workspace", suggestion="run loomgraph index ."
    )
    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "FIND_FAILED"
    assert payload["error"]["message"] == "no such workspace"
    assert payload["error"]["suggestion"] == "run loomgraph index ."


# ---- Tool handlers (mocked async cores) ----------------------------------

@pytest.mark.asyncio
async def test_find_handler_forwards_arguments_and_envelopes_success():
    """Verify the tool handler hands its arguments to the async core
    correctly and shapes the response into {success: true, data}."""
    fake_result = {
        "query": "Foo",
        "matches_count": 2,
        "matches": [{"entity": "Foo"}, {"entity": "FooBar"}],
    }

    async def fake_async_find(**kwargs):
        # confirm forwarded names match _async_find's signature exactly
        assert kwargs["query"] == "Foo"
        assert kwargs["entity_type"] is None
        assert kwargs["limit"] == 20
        assert kwargs["with_relations"] is False
        assert kwargs["workspace"] is None
        return fake_result

    with patch.object(t_find, "_async_find", side_effect=fake_async_find):
        contents = await t_find.handle({"query": "Foo"})

    payload = json.loads(contents[0].text)
    assert payload["success"] is True
    assert payload["data"] == fake_result


@pytest.mark.asyncio
async def test_find_handler_passes_workspace_through():
    async def fake_async_find(**kwargs):
        return {"workspace_seen": kwargs.get("workspace")}

    with patch.object(t_find, "_async_find", side_effect=fake_async_find):
        contents = await t_find.handle(
            {"query": "Foo", "workspace": "explicit-ws"}
        )

    payload = json.loads(contents[0].text)
    assert payload["data"]["workspace_seen"] == "explicit-ws"


@pytest.mark.asyncio
async def test_find_handler_wraps_exceptions_into_error_envelope():
    async def boom(**kwargs):
        raise RuntimeError("workspace not indexed")

    with patch.object(t_find, "_async_find", side_effect=boom):
        contents = await t_find.handle({"query": "Foo"})

    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "FIND_FAILED"
    assert "RuntimeError" in payload["error"]["message"]
    assert "workspace not indexed" in payload["error"]["message"]
    assert "suggestion" in payload["error"]


@pytest.mark.asyncio
async def test_graph_handler_forwards_defaults():
    async def fake_async_graph(**kwargs):
        assert kwargs["entity_name"] == "Foo.bar"
        assert kwargs["direction"] == "both"
        assert kwargs["relation_type"] == "all"
        assert kwargs["workspace"] is None
        return {"callers_count": 0, "callees_count": 0}

    with patch.object(t_graph, "_async_graph_query", side_effect=fake_async_graph):
        contents = await t_graph.handle({"entity_name": "Foo.bar"})

    payload = json.loads(contents[0].text)
    assert payload["success"] is True


@pytest.mark.asyncio
async def test_graph_handler_respects_explicit_direction():
    async def fake_async_graph(**kwargs):
        return {"direction_seen": kwargs["direction"]}

    with patch.object(t_graph, "_async_graph_query", side_effect=fake_async_graph):
        contents = await t_graph.handle(
            {"entity_name": "Foo.bar", "direction": "callers"}
        )

    payload = json.loads(contents[0].text)
    assert payload["data"]["direction_seen"] == "callers"
