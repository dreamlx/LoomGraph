"""Tests for v0.12.1 composite MCP tools (debt_audit / evolution_track /
sync_advice).

Each composite wraps 3-8 underlying `_async_*` cores. The tests mock
those cores so we exercise the **composition logic** (parallel gather,
error degradation, summary counts) without round-tripping to a real
SQLite workspace.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from loomgraph.mcp.tools import debt_audit as t_debt
from loomgraph.mcp.tools import evolution_track as t_evo
from loomgraph.mcp.tools import sync_advice as t_sync

# ---- debt_audit ---------------------------------------------------------

@pytest.mark.asyncio
async def test_debt_audit_runs_all_dimensions_in_parallel(monkeypatch):
    """All 6 core dimensions land as data; git skipped when not in repo."""
    async def fake_debt(**_): return {"score": 80}
    async def fake_deps(**_): return {"modules": []}
    async def fake_overview(**_): return {"modules": []}
    async def fake_topology(**_): return {"orphans": []}
    async def fake_info(_name, _opt): return {"entities": 100}
    async def fake_check(**_): return {"freshness_ratio": 0.95}

    with patch.object(t_debt, "_async_debt", side_effect=fake_debt), \
         patch.object(t_debt, "_async_deps", side_effect=fake_deps), \
         patch.object(t_debt, "_async_overview", side_effect=fake_overview), \
         patch.object(t_debt, "_async_topology", side_effect=fake_topology), \
         patch.object(t_debt, "_async_workspace_info", side_effect=fake_info), \
         patch.object(t_debt, "_async_check", side_effect=fake_check), \
         patch.object(t_debt, "_is_git_repo", return_value=False):
        contents = await t_debt.handle({"trends_top_n": 0})

    payload = json.loads(contents[0].text)
    assert payload["success"] is True
    dims = payload["data"]["dimensions"]
    # All 6 dims attempted, all succeed; git not added (no repo)
    assert set(dims) == {"debt", "deps", "overview", "topology", "workspace_info", "check"}
    assert all(d["error"] is None for d in dims.values())
    assert payload["data"]["summary"]["dimensions_succeeded"] == 6
    assert payload["data"]["git_enabled"] is False


@pytest.mark.asyncio
async def test_debt_audit_forwards_scope_to_debt_and_topology(monkeypatch):
    """scope (EPIC-014 #61) reaches both the debt and topology dimensions."""
    captured: dict[str, dict] = {}

    async def fake_debt(**kw):
        captured["debt"] = kw
        return {"score": 80}

    async def fake_topology(**kw):
        captured["topology"] = kw
        return {"orphans": []}

    async def fake_ok(**_):
        return {}

    async def fake_info(_name, _opt):
        return {"entities": 0}

    with patch.object(t_debt, "_async_debt", side_effect=fake_debt), \
         patch.object(t_debt, "_async_deps", side_effect=fake_ok), \
         patch.object(t_debt, "_async_overview", side_effect=fake_ok), \
         patch.object(t_debt, "_async_topology", side_effect=fake_topology), \
         patch.object(t_debt, "_async_workspace_info", side_effect=fake_info), \
         patch.object(t_debt, "_async_check", side_effect=fake_ok), \
         patch.object(t_debt, "_is_git_repo", return_value=False):
        contents = await t_debt.handle({"scope": "src/", "trends_top_n": 0})

    payload = json.loads(contents[0].text)
    assert payload["success"] is True
    assert captured["debt"]["scope"] == "src/"
    assert captured["topology"]["scope"] == "src/"


@pytest.mark.asyncio
async def test_debt_audit_degrades_per_dimension_not_whole_call(monkeypatch):
    """If one dimension raises, the others still land + report success."""
    async def fake_ok(*a, **kw): return {"ok": True}
    async def fake_boom(*a, **kw): raise RuntimeError("storage offline")

    with patch.object(t_debt, "_async_debt", side_effect=fake_ok), \
         patch.object(t_debt, "_async_deps", side_effect=fake_boom), \
         patch.object(t_debt, "_async_overview", side_effect=fake_ok), \
         patch.object(t_debt, "_async_topology", side_effect=fake_ok), \
         patch.object(t_debt, "_async_workspace_info", side_effect=fake_ok), \
         patch.object(t_debt, "_async_check", side_effect=fake_ok), \
         patch.object(t_debt, "_is_git_repo", return_value=False):
        contents = await t_debt.handle({"trends_top_n": 0})

    payload = json.loads(contents[0].text)
    assert payload["success"] is True  # top-level still success
    dims = payload["data"]["dimensions"]
    assert dims["deps"]["data"] is None
    assert "storage offline" in dims["deps"]["error"]
    assert dims["debt"]["data"] == {"ok": True}
    assert payload["data"]["summary"]["dimensions_succeeded"] == 5
    assert payload["data"]["summary"]["dimensions_attempted"] == 6


@pytest.mark.asyncio
async def test_debt_audit_fails_only_when_every_dim_fails(monkeypatch):
    async def fake_boom(*a, **kw): raise RuntimeError("workspace missing")
    with patch.object(t_debt, "_async_debt", side_effect=fake_boom), \
         patch.object(t_debt, "_async_deps", side_effect=fake_boom), \
         patch.object(t_debt, "_async_overview", side_effect=fake_boom), \
         patch.object(t_debt, "_async_topology", side_effect=fake_boom), \
         patch.object(t_debt, "_async_workspace_info", side_effect=fake_boom), \
         patch.object(t_debt, "_async_check", side_effect=fake_boom), \
         patch.object(t_debt, "_is_git_repo", return_value=False):
        contents = await t_debt.handle({"trends_top_n": 0})

    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "DEBT_AUDIT_FAILED"


# ---- evolution_track ----------------------------------------------------

@pytest.mark.asyncio
async def test_evolution_track_pairwise_compare_count():
    """3 workspaces produce 2 adjacent-pair compares."""
    async def fake_similar(**_): return {"results": [{"workspace": "ws1"}]}
    async def fake_compare(**_): return {"added": [], "removed": []}
    async def fake_graph(**_): return {"callers_count": 1, "callees_count": 0}

    with patch.object(t_evo, "_async_similar", side_effect=fake_similar), \
         patch.object(t_evo, "_async_compare", side_effect=fake_compare), \
         patch.object(t_evo, "_async_graph_query", side_effect=fake_graph):
        contents = await t_evo.handle({
            "entity": "AuthService",
            "workspaces": ["proj:v1", "proj:v2", "proj:v3"],
        })

    payload = json.loads(contents[0].text)
    assert payload["success"] is True
    assert len(payload["data"]["pairwise_compare"]) == 2
    assert payload["data"]["pairwise_compare"][0]["ws1"] == "proj:v1"
    assert payload["data"]["pairwise_compare"][0]["ws2"] == "proj:v2"
    assert len(payload["data"]["per_workspace_graph"]) == 3


@pytest.mark.asyncio
async def test_evolution_track_rejects_single_workspace():
    contents = await t_evo.handle({"entity": "Foo", "workspaces": ["only-one"]})
    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_evolution_track_individual_failures_dont_kill_call():
    async def fake_similar(**_): raise RuntimeError("similar broken")
    async def fake_compare(**_): return {"added": []}
    async def fake_graph(**_): return {"callers_count": 0}

    with patch.object(t_evo, "_async_similar", side_effect=fake_similar), \
         patch.object(t_evo, "_async_compare", side_effect=fake_compare), \
         patch.object(t_evo, "_async_graph_query", side_effect=fake_graph):
        contents = await t_evo.handle({
            "entity": "X", "workspaces": ["a", "b"],
        })
    payload = json.loads(contents[0].text)
    # Whole call still succeeds; similar dim shows error envelope
    assert payload["success"] is True
    assert payload["data"]["similar"]["error"] is not None
    assert payload["data"]["pairwise_compare"][0]["error"] is None


# ---- sync_advice --------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_advice_runs_3_dims_plus_impacts():
    async def fake_compare(**_): return {"added": ["A"], "removed": ["B"]}
    async def fake_debt(**_): return {"score": 75}
    async def fake_graph(**_): return {"callers_count": 5}

    with patch.object(t_sync, "_async_compare", side_effect=fake_compare), \
         patch.object(t_sync, "_async_debt", side_effect=fake_debt), \
         patch.object(t_sync, "_async_graph_query", side_effect=fake_graph):
        contents = await t_sync.handle({
            "upstream": "proj:main",
            "downstream": "proj:feature",
            "impact_entities": ["Foo", "Bar"],
        })

    payload = json.loads(contents[0].text)
    assert payload["success"] is True
    data = payload["data"]
    assert data["compare"]["error"] is None
    assert data["upstream_debt"]["data"]["score"] == 75
    assert data["downstream_debt"]["data"]["score"] == 75
    assert len(data["module_impacts"]) == 2
    assert {i["entity"] for i in data["module_impacts"]} == {"Foo", "Bar"}
    assert data["summary"]["dimensions_succeeded"] == 3  # compare + 2 debts


@pytest.mark.asyncio
async def test_sync_advice_rejects_same_workspace():
    contents = await t_sync.handle({
        "upstream": "proj:main", "downstream": "proj:main",
    })
    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_sync_advice_fails_when_all_dims_fail():
    async def fake_boom(**_): raise RuntimeError("workspace gone")
    with patch.object(t_sync, "_async_compare", side_effect=fake_boom), \
         patch.object(t_sync, "_async_debt", side_effect=fake_boom):
        contents = await t_sync.handle({
            "upstream": "a", "downstream": "b",
        })
    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "SYNC_ADVICE_FAILED"


# ---- Server registration regression -------------------------------------

def test_composite_tools_registered():
    """v0.12.1 composite tools must appear in the MCP registry."""
    from loomgraph.mcp.server import _TOOL_HANDLERS, _TOOL_SPECS

    expected = {
        "loomgraph_debt_audit",
        "loomgraph_evolution_track",
        "loomgraph_sync_advice",
    }
    assert expected.issubset(_TOOL_HANDLERS)
    names = {s.name for s in _TOOL_SPECS}
    assert expected.issubset(names)
