"""Tests for ``_async_graph_query`` — the callers/callees BFS in cli._search.

Covers #105: querying a ``class`` entity returned 0 callees because the class
entity itself owns no outgoing edges — the calls live on its methods
(``Class.method``). graph now aggregates method callees for class entities so
``graph TopologyAnalyzer`` shows what the class's methods call. callers are
unaffected (constructor edges already land on the class via codeindex #132).
"""

from __future__ import annotations

import pytest

from loomgraph.cli._search import _async_graph_query


class _MemStore:
    """Minimal in-memory store matching the dict shape _async_graph_query reads."""

    def __init__(self, entities: list[dict], relations: list[dict]) -> None:
        self._entities = entities
        self._relations = relations

    async def get_all_entities(self) -> list[dict]:
        return self._entities

    async def get_all_relations(self) -> list[dict]:
        return self._relations


def _patch_store(monkeypatch, entities, relations):
    store = _MemStore(entities, relations)
    monkeypatch.setattr(
        "loomgraph.cli._search.prepare_workspace_store",
        lambda ws: _async_return(("ws", store)),
    )
    return store


async def _async_return(value):
    return value


@pytest.mark.asyncio
async def test_class_callees_aggregate_methods(monkeypatch):
    """#105: querying a class returns its methods' callees, not 0."""
    entities = [
        {"entity_name": "app.Foo", "entity_type": "class", "source_id": "app/foo.py:1"},
        {"entity_name": "app.Foo.bar", "entity_type": "method", "source_id": "app/foo.py:2"},
        {"entity_name": "app.Foo.baz", "entity_type": "method", "source_id": "app/foo.py:5"},
        {"entity_name": "app.helper", "entity_type": "function", "source_id": "app/foo.py:9"},
        {"entity_name": "app.logger", "entity_type": "function", "source_id": "app/log.py:1"},
    ]
    # Foo.bar calls helper; Foo.baz calls logger. The class entity Foo owns NO edges.
    relations = [
        {"src_id": "app.Foo.bar", "tgt_id": "app.helper", "keywords": "CALLS"},
        {"src_id": "app.Foo.baz", "tgt_id": "app.logger", "keywords": "CALLS"},
    ]
    _patch_store(monkeypatch, entities, relations)

    result = await _async_graph_query("app.Foo", direction="both", relation_type="all")

    callees = {c["entity"] for c in result["callees"]}
    assert callees == {"app.helper", "app.logger"}, callees
    assert result["callees_count"] == 2


@pytest.mark.asyncio
async def test_class_with_direct_edges_keeps_them(monkeypatch):
    """A class that DOES own direct callees (e.g. via REFERENCES) keeps them
    alongside the aggregated method callees — aggregation is additive, deduped."""
    entities = [
        {"entity_name": "app.Foo", "entity_type": "class", "source_id": "app/foo.py:1"},
        {"entity_name": "app.Foo.run", "entity_type": "method", "source_id": "app/foo.py:2"},
        {"entity_name": "app.helper", "entity_type": "function", "source_id": "app/h.py:1"},
        {"entity_name": "app.config", "entity_type": "class", "source_id": "app/c.py:1"},
    ]
    relations = [
        # method callee
        {"src_id": "app.Foo.run", "tgt_id": "app.helper", "keywords": "CALLS"},
        # direct class callee (e.g. a REFERENCES edge already on the class)
        {"src_id": "app.Foo", "tgt_id": "app.config", "keywords": "REFERENCES"},
    ]
    _patch_store(monkeypatch, entities, relations)

    result = await _async_graph_query("app.Foo", direction="callees", relation_type="all")

    callees = {c["entity"] for c in result["callees"]}
    assert callees == {"app.helper", "app.config"}, callees


@pytest.mark.asyncio
async def test_function_callees_unchanged(monkeypatch):
    """Non-class entities keep exact-match BFS behaviour (no aggregation)."""
    entities = [
        {"entity_name": "app.main", "entity_type": "function", "source_id": "app/m.py:1"},
        {"entity_name": "app.helper", "entity_type": "function", "source_id": "app/h.py:1"},
    ]
    relations = [
        {"src_id": "app.main", "tgt_id": "app.helper", "keywords": "CALLS"},
    ]
    _patch_store(monkeypatch, entities, relations)

    result = await _async_graph_query("app.main", direction="callees", relation_type="all")

    assert {c["entity"] for c in result["callees"]} == {"app.helper"}


@pytest.mark.asyncio
async def test_class_callees_dedup_across_methods(monkeypatch):
    """Two methods calling the same target dedupe to one callee."""
    entities = [
        {"entity_name": "app.Foo", "entity_type": "class", "source_id": "app/foo.py:1"},
        {"entity_name": "app.Foo.a", "entity_type": "method", "source_id": "app/foo.py:2"},
        {"entity_name": "app.Foo.b", "entity_type": "method", "source_id": "app/foo.py:4"},
        {"entity_name": "app.shared", "entity_type": "function", "source_id": "app/s.py:1"},
    ]
    relations = [
        {"src_id": "app.Foo.a", "tgt_id": "app.shared", "keywords": "CALLS"},
        {"src_id": "app.Foo.b", "tgt_id": "app.shared", "keywords": "CALLS"},
    ]
    _patch_store(monkeypatch, entities, relations)

    result = await _async_graph_query("app.Foo", direction="callees", relation_type="all")

    assert result["callees_count"] == 1
    assert result["callees"][0]["entity"] == "app.shared"
