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
from loomgraph.mcp.tools import search as t_search

# ---- Registration --------------------------------------------------------

EXPECTED_TOOLS = {
    "loomgraph_find",
    "loomgraph_search",
    "loomgraph_graph",
    "loomgraph_topology",
    "loomgraph_impact",
    "loomgraph_deps",
    "loomgraph_overview",
    # Debt-surface read primitives (#62) — standalone, also in the composite
    "loomgraph_debt",
    "loomgraph_check",
    "loomgraph_git_metrics",
    "loomgraph_workspace_list",
    "loomgraph_workspace_info",
}


def test_all_read_tools_registered():
    """Every Phase 1+2 read tool must be discoverable from the registry."""
    assert set(_TOOL_HANDLERS) >= EXPECTED_TOOLS
    names = {spec.name for spec in _TOOL_SPECS}
    assert EXPECTED_TOOLS.issubset(names)


def test_no_write_tools_exposed():
    """Per EPIC-013 scope, write-side tools (index/update/import-export)
    must NOT appear in the MCP surface — they require codeindex on the
    runtime path and have side effects. This is a regression guard."""
    forbidden = {
        "loomgraph_index",
        "loomgraph_update",
        "loomgraph_import_export",
    }
    assert forbidden.isdisjoint(_TOOL_HANDLERS), (
        f"Write tools must stay CLI-only: leaked {forbidden & set(_TOOL_HANDLERS)}"
    )


def test_tool_specs_have_required_fields():
    """Schema sanity — every tool must have a description + inputSchema."""
    for spec in _TOOL_SPECS:
        assert spec.description, f"tool {spec.name} missing description"
        assert spec.input_schema, f"tool {spec.name} missing inputSchema"
        assert spec.input_schema.get("type") == "object"
        # `properties` must define at least the required ones
        props = spec.input_schema.get("properties", {})
        for req in spec.input_schema.get("required", []):
            assert req in props, f"{spec.name}: required '{req}' missing from properties"


def test_build_server_constructs_without_error():
    """No stdio call — just verify the Server object is constructible."""
    server = build_server()
    assert server.name == "loomgraph"


def test_build_server_version_tracks_package():
    """Server version must come from __version__, not a hardcoded constant.

    Regression guard for the drift where SERVER_VERSION was pinned to a
    literal that lagged the installed package (0.15.0 install reported
    0.15.3). The Server advertises loomgraph.__version__ so MCP clients see
    the real installed version.
    """
    from loomgraph import __version__

    server = build_server()
    assert server.version == __version__
    assert server.version != "0.15.3" or __version__ == "0.15.3"  # not hardcoded


async def test_git_metrics_handle_errors_on_non_git_path(tmp_path):
    """git_metrics primitive returns a structured error on a non-repo path (#62)."""
    import json

    from loomgraph.mcp.tools import git_metrics as t_git_metrics

    result = await t_git_metrics.handle({"source_path": str(tmp_path)})
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "GIT_METRICS_FAILED"


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
async def test_search_handler_forwards_arguments_and_envelopes_success():
    fake_result = {
        "query": "where are hotspots",
        "mode": "semantic",
        "matches_count": 1,
        "matches": [{"entity": "DebtAnalyzer"}],
    }

    async def fake_async_search(**kwargs):
        assert kwargs["query"] == "where are hotspots"
        assert kwargs["entity_type"] is None
        assert kwargs["limit"] == 20
        assert kwargs["workspace"] is None
        return fake_result

    with patch.object(t_search, "_async_search", side_effect=fake_async_search):
        contents = await t_search.handle({"query": "where are hotspots"})

    payload = json.loads(contents[0].text)
    assert payload["success"] is True
    assert payload["data"] == fake_result


@pytest.mark.asyncio
async def test_search_handler_passes_workspace_through():
    async def fake_async_search(**kwargs):
        return {"workspace_seen": kwargs.get("workspace")}

    with patch.object(t_search, "_async_search", side_effect=fake_async_search):
        contents = await t_search.handle(
            {"query": "x", "workspace": "explicit-ws"}
        )

    payload = json.loads(contents[0].text)
    assert payload["data"]["workspace_seen"] == "explicit-ws"


@pytest.mark.asyncio
async def test_search_handler_not_indexed_returns_typed_error():
    """VectorsNotIndexedError → EMBEDDING_NOT_INDEXED (not generic SEARCH_FAILED),
    so a client gets the actionable 'enable embedding + reindex' signal."""
    from loomgraph.cli._search import VectorsNotIndexedError

    async def boom(**kwargs):
        raise VectorsNotIndexedError("proj:main")

    with patch.object(t_search, "_async_search", side_effect=boom):
        contents = await t_search.handle({"query": "x"})

    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "EMBEDDING_NOT_INDEXED"
    assert "proj:main" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_search_handler_wraps_other_exceptions_into_error_envelope():
    async def boom(**kwargs):
        raise RuntimeError("embed service down")

    with patch.object(t_search, "_async_search", side_effect=boom):
        contents = await t_search.handle({"query": "x"})

    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "SEARCH_FAILED"
    assert "suggestion" in payload["error"]


@pytest.mark.asyncio
async def test_graph_handler_forwards_defaults():
    async def fake_async_graph(**kwargs):
        assert kwargs["entity_name"] == "Foo.bar"
        assert kwargs["direction"] == "both"
        assert kwargs["relation_type"] == "all"
        assert kwargs["workspace"] is None
        assert kwargs["include_unresolved"] is False
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


@pytest.mark.asyncio
async def test_graph_handler_forwards_include_unresolved():
    """#113: include_unresolved must propagate to _async_graph_query."""
    async def fake_async_graph(**kwargs):
        return {"include_unresolved": kwargs["include_unresolved"]}

    with patch.object(t_graph, "_async_graph_query", side_effect=fake_async_graph):
        contents = await t_graph.handle(
            {"entity_name": "Foo.bar", "include_unresolved": True}
        )

    payload = json.loads(contents[0].text)
    assert payload["data"]["include_unresolved"] is True


# ---- Phase 2 handler smoke tests (mocked) --------------------------------

@pytest.mark.asyncio
async def test_topology_handler_forwards_thresholds():
    from loomgraph.mcp.tools import topology as t_topology

    async def fake(**kwargs):
        return {"hub_count": kwargs["hub_threshold"], "god_count": kwargs["god_threshold"]}

    with patch.object(t_topology, "_async_topology", side_effect=fake):
        contents = await t_topology.handle(
            {"hub_threshold": 5, "god_threshold": 8}
        )
    payload = json.loads(contents[0].text)
    assert payload["data"]["hub_count"] == 5
    assert payload["data"]["god_count"] == 8


@pytest.mark.asyncio
async def test_impact_handler_default_target_is_head():
    from loomgraph.mcp.tools import impact as t_impact

    async def fake(**kwargs):
        return {"target_seen": kwargs["target"], "depth_seen": kwargs["depth"]}

    with patch.object(t_impact, "_async_impact", side_effect=fake):
        contents = await t_impact.handle({})
    payload = json.loads(contents[0].text)
    assert payload["data"]["target_seen"] == "HEAD"
    assert payload["data"]["depth_seen"] == 2


@pytest.mark.asyncio
async def test_deps_handler_passes_depth():
    from loomgraph.mcp.tools import deps as t_deps

    async def fake(**kwargs):
        return {"depth_seen": kwargs["depth"]}

    with patch.object(t_deps, "_async_deps", side_effect=fake):
        contents = await t_deps.handle({"depth": 3})
    payload = json.loads(contents[0].text)
    assert payload["data"]["depth_seen"] == 3


@pytest.mark.asyncio
async def test_overview_handler_no_summary_passthrough():
    from loomgraph.mcp.tools import overview as t_overview

    async def fake(**kwargs):
        return {"no_summary_seen": kwargs["no_summary"]}

    with patch.object(t_overview, "_async_overview", side_effect=fake):
        contents = await t_overview.handle({"no_summary": True})
    payload = json.loads(contents[0].text)
    assert payload["data"]["no_summary_seen"] is True


@pytest.mark.asyncio
async def test_workspace_list_handler_calls_async_list():
    from loomgraph.mcp.tools import workspace as t_workspace

    async def fake():
        return {"workspaces": ["a", "b"], "count": 2}

    with patch.object(t_workspace, "_async_workspace_list", side_effect=fake):
        contents = await t_workspace.list_handle({})
    payload = json.loads(contents[0].text)
    assert payload["data"]["count"] == 2


@pytest.mark.asyncio
async def test_workspace_info_handler_forwards_name():
    from loomgraph.mcp.tools import workspace as t_workspace

    async def fake(name, ws_option):
        return {"name_seen": name}

    with patch.object(t_workspace, "_async_workspace_info", side_effect=fake):
        contents = await t_workspace.info_handle({"name": "proj:main"})
    payload = json.loads(contents[0].text)
    assert payload["data"]["name_seen"] == "proj:main"
