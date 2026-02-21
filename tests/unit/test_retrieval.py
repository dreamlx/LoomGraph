"""Tests for hybrid retrieval and iterative deep query."""

import pytest
from unittest.mock import AsyncMock

from loomgraph.core.retrieval import (
    QueryResult,
    _assemble_context,
    _plan_follow_ups,
    hybrid_query,
    iterative_deep_query,
)


class TestAssembleContext:
    """Tests for _assemble_context()."""

    def test_entities_and_relations(self) -> None:
        entities = [
            {"name": "foo", "entity_type": "function", "file_path": "a.py", "description": "does stuff"},
        ]
        relations = [
            {"src_id": "foo", "tgt_id": "bar", "keywords": "CALLS"},
        ]
        ctx = _assemble_context(entities, relations)
        assert "=== Matched Entities ===" in ctx
        assert "[function] foo" in ctx
        assert "=== Relations ===" in ctx
        assert "foo --CALLS--> bar" in ctx

    def test_deduplicates_relations(self) -> None:
        rels = [
            {"src_id": "a", "tgt_id": "b", "keywords": "CALLS"},
            {"src_id": "a", "tgt_id": "b", "keywords": "CALLS"},
        ]
        ctx = _assemble_context([], rels)
        assert ctx.count("a --CALLS--> b") == 1

    def test_includes_llm_response(self) -> None:
        ctx = _assemble_context([], [], llm_response="LLM says hello")
        assert "=== LightRAG Response ===" in ctx
        assert "LLM says hello" in ctx

    def test_empty(self) -> None:
        ctx = _assemble_context([], [])
        assert ctx == ""


class TestHybridQuery:
    """Tests for hybrid_query()."""

    @pytest.mark.asyncio
    async def test_basic_hybrid(self) -> None:
        mock_client = AsyncMock()
        mock_client.query.return_value = {"response": "foo is a function"}
        mock_client.get_all_entities.return_value = [
            {"entity_name": "foo", "entity_type": "function", "description": "does stuff", "file_path": "a.py"},
            {"entity_name": "bar", "entity_type": "function", "description": "helper", "file_path": "b.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "foo", "tgt_id": "bar", "keywords": "CALLS"},
        ]

        result = await hybrid_query(mock_client, "foo", top_k=5, depth=1)
        assert result.mode == "hybrid"
        assert any(e.get("name") == "foo" for e in result.entities)
        assert "=== Matched Entities ===" in result.context

    @pytest.mark.asyncio
    async def test_graph_traversal_expands(self) -> None:
        mock_client = AsyncMock()
        mock_client.query.return_value = {"response": ""}
        mock_client.get_all_entities.return_value = [
            {"entity_name": "login", "entity_type": "method", "description": "auth", "file_path": "auth.py"},
            {"entity_name": "db_query", "entity_type": "function", "description": "database", "file_path": "db.py"},
        ]
        mock_client.get_all_relations.return_value = [
            {"src_id": "login", "tgt_id": "db_query", "keywords": "CALLS"},
        ]

        result = await hybrid_query(mock_client, "login", top_k=5, depth=1)
        names = [e.get("name") for e in result.entities]
        assert "login" in names
        assert "db_query" in names  # expanded via BFS

    @pytest.mark.asyncio
    async def test_fallback_on_graph_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.query.return_value = {"response": "fallback text"}
        mock_client.get_all_entities.side_effect = Exception("connection refused")

        result = await hybrid_query(mock_client, "test")
        assert result.context == "fallback text"
        assert result.entities == []


class TestIterativeDeepQuery:
    """Tests for iterative_deep_query()."""

    @pytest.mark.asyncio
    async def test_stops_when_complete(self) -> None:
        mock_client = AsyncMock()
        mock_client.query.return_value = {"response": ""}
        mock_client.get_all_entities.return_value = []
        mock_client.get_all_relations.return_value = []

        # LLM says context is complete
        async def mock_llm(messages):
            return '{"sub_questions": ["q1"], "covered": ["q1"], "missing": [], "queries": [], "reason": "complete"}'

        result = await iterative_deep_query(
            mock_client, "test", "initial context",
            max_rounds=3, llm_fn=mock_llm,
        )
        assert result.rounds == 1  # No follow-ups needed
        assert "initial context" in result.context

    @pytest.mark.asyncio
    async def test_executes_follow_ups(self) -> None:
        mock_client = AsyncMock()
        mock_client.query.return_value = {"response": "extra info"}
        mock_client.get_all_entities.return_value = [
            {"entity_name": "helper", "entity_type": "function", "description": "helps", "file_path": "h.py"},
        ]
        mock_client.get_all_relations.return_value = []

        call_count = 0
        async def mock_llm(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '{"sub_questions": ["q1"], "covered": [], "missing": ["q1"], "queries": ["helper"], "reason": "need more"}'
            return '{"sub_questions": ["q1"], "covered": ["q1"], "missing": [], "queries": [], "reason": "done"}'

        result = await iterative_deep_query(
            mock_client, "test", "initial",
            max_rounds=2, llm_fn=mock_llm,
        )
        assert result.rounds == 2
        assert "Follow-up: helper" in result.context

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self) -> None:
        mock_client = AsyncMock()

        async def mock_llm(messages):
            raise Exception("LLM timeout")

        result = await iterative_deep_query(
            mock_client, "test", "initial",
            max_rounds=2, llm_fn=mock_llm,
        )
        assert result.rounds == 1  # Stopped after failure
        assert result.context == "initial"


class TestPlanFollowUps:
    """Tests for _plan_follow_ups()."""

    @pytest.mark.asyncio
    async def test_parses_json_response(self) -> None:
        async def mock_llm(messages):
            return '{"sub_questions": ["q1"], "covered": [], "missing": ["q1"], "queries": ["foo", "bar"], "reason": "need"}'

        result = await _plan_follow_ups("test", "ctx", llm_fn=mock_llm)
        assert result == ["foo", "bar"]

    @pytest.mark.asyncio
    async def test_auto_generates_from_missing(self) -> None:
        async def mock_llm(messages):
            return '{"sub_questions": ["q1"], "covered": [], "missing": ["the login function"], "queries": [], "reason": "need"}'

        result = await _plan_follow_ups("test", "ctx", llm_fn=mock_llm)
        assert len(result) == 1
        assert "login" in result[0]

    @pytest.mark.asyncio
    async def test_returns_empty_on_bad_json(self) -> None:
        async def mock_llm(messages):
            return "I don't know what to search for"

        result = await _plan_follow_ups("test", "ctx", llm_fn=mock_llm)
        assert result == []

