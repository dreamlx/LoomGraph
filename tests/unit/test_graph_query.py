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


# ---------------------------------------------------------------------------
# #113: unresolved/ambiguous edges target a call expression (dst_raw), not an
# in-repo entity. Surfacing them yields phantom callees (source_id=""). graph
# now defaults to trusted (resolved) edges only; --include-unresolved brings
# the low-trust edges back for raw-call inspection.
# ---------------------------------------------------------------------------

def _phantom_fixture():
    """app.output_error calls one real callee plus two phantom (dst_raw) ones.

    - resolved   → app.real_callee  (in entities table, source_id populated)
    - unresolved → click.echo       (dst_raw call expr, no matching entity)
    - ambiguous  → json.dumps       (dst_raw call expr, no matching entity)
    """
    entities = [
        {"entity_name": "app.output_error", "entity_type": "function",
         "source_id": "app/cli.py:1"},
        {"entity_name": "app.real_callee", "entity_type": "function",
         "source_id": "app/cli.py:9"},
    ]
    relations = [
        {"src_id": "app.output_error", "tgt_id": "app.real_callee",
         "keywords": "CALLS", "resolution_qualifier": "resolved"},
        {"src_id": "app.output_error", "tgt_id": "click.echo",
         "keywords": "CALLS", "resolution_qualifier": "unresolved"},
        {"src_id": "app.output_error", "tgt_id": "json.dumps",
         "keywords": "CALLS", "resolution_qualifier": "ambiguous"},
    ]
    return entities, relations


@pytest.mark.asyncio
async def test_phantom_unresolved_callees_filtered_by_default(monkeypatch):
    """#113: unresolved/ambiguous callees are phantom (target not in entities)
    — filtered out by default so real callees aren't drowned out."""
    entities, relations = _phantom_fixture()
    _patch_store(monkeypatch, entities, relations)

    result = await _async_graph_query(
        "app.output_error", direction="callees", relation_type="all"
    )

    callees = {c["entity"] for c in result["callees"]}
    assert callees == {"app.real_callee"}, callees
    assert result["callees_count"] == 1
    # No phantom (source_id="") entries leak through.
    assert all(c["source_id"] for c in result["callees"])


@pytest.mark.asyncio
async def test_include_unresolved_flag_keeps_phantom_edges(monkeypatch):
    """#113: --include-unresolved brings back the dst_raw callees (still
    marked source_id="" since their target isn't an in-repo entity)."""
    entities, relations = _phantom_fixture()
    _patch_store(monkeypatch, entities, relations)

    result = await _async_graph_query(
        "app.output_error", direction="callees", relation_type="all",
        include_unresolved=True,
    )

    callees = {c["entity"] for c in result["callees"]}
    assert callees == {"app.real_callee", "click.echo", "json.dumps"}, callees
    assert result["callees_count"] == 3
    # Phantom entries keep dst_raw as entity name, source_id stays empty.
    phantom = {c["entity"]: c["source_id"] for c in result["callees"]}
    assert phantom["click.echo"] == ""
    assert phantom["json.dumps"] == ""


@pytest.mark.asyncio
async def test_ambiguous_filtered_by_default(monkeypatch):
    """#113: ambiguous edges are same-name guesses (wrong for dynamic
    dispatch, #101) — filtered by default alongside unresolved."""
    entities = [
        {"entity_name": "app.foo", "entity_type": "function", "source_id": "app/f.py:1"},
    ]
    relations = [
        # an ambiguous edge whose tgt happens to match no entity (typical)
        {"src_id": "app.foo", "tgt_id": "db.exec", "keywords": "CALLS",
         "resolution_qualifier": "ambiguous"},
    ]
    _patch_store(monkeypatch, entities, relations)

    result = await _async_graph_query(
        "app.foo", direction="callees", relation_type="all"
    )

    assert result["callees_count"] == 0

    # Escape hatch surfaces it.
    result_inc = await _async_graph_query(
        "app.foo", direction="callees", relation_type="all",
        include_unresolved=True,
    )
    assert {c["entity"] for c in result_inc["callees"]} == {"db.exec"}


@pytest.mark.asyncio
async def test_missing_qualifier_treated_as_resolved(monkeypatch):
    """#113: relations without resolution_qualifier (old data / pre-#113
    fixtures) are treated as resolved — never accidentally filtered. Guards
    the four #105 tests above, which carry no qualifier."""
    entities = [
        {"entity_name": "app.main", "entity_type": "function", "source_id": "app/m.py:1"},
        {"entity_name": "app.helper", "entity_type": "function", "source_id": "app/h.py:1"},
    ]
    relations = [
        # No resolution_qualifier key at all.
        {"src_id": "app.main", "tgt_id": "app.helper", "keywords": "CALLS"},
    ]
    _patch_store(monkeypatch, entities, relations)

    result = await _async_graph_query(
        "app.main", direction="callees", relation_type="all"
    )

    assert {c["entity"] for c in result["callees"]} == {"app.helper"}
