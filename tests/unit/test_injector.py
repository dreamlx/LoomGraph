"""Unit tests for the injector module."""

from pathlib import Path
from typing import Any

import pytest

from loomgraph.core.injector import inject_parse_result, inject_parse_results_batch
from loomgraph.core.models import Call, Import, Inheritance, ParseResult, Symbol


class MockLightRAGClient:
    """Mock LightRAG HTTP client for testing."""

    def __init__(self):
        self.entities: list[dict[str, Any]] = []
        self.relations: list[dict[str, Any]] = []
        self.entity_error: Exception | None = None
        self.relation_error: Exception | None = None
        self._entity_call_count = 0
        self._entity_error_on_call: int | None = None

    async def create_entity(self, entity_name: str, entity_data: dict[str, Any]) -> dict[str, Any]:
        self._entity_call_count += 1
        if self._entity_error_on_call and self._entity_call_count == self._entity_error_on_call:
            raise Exception("Database error")
        if self.entity_error:
            raise self.entity_error
        self.entities.append({"name": entity_name, "data": entity_data})
        return {"status": "success", "message": f"Entity '{entity_name}' created"}

    async def create_relation(
        self, source_entity: str, target_entity: str, relation_data: dict[str, Any]
    ) -> dict[str, Any]:
        if self.relation_error:
            raise self.relation_error
        self.relations.append({
            "src": source_entity,
            "tgt": target_entity,
            "data": relation_data,
        })
        return {"status": "success", "message": "Relation created"}


@pytest.fixture
def mock_client() -> MockLightRAGClient:
    """Create a mock LightRAG client."""
    return MockLightRAGClient()


@pytest.fixture
def sample_parse_result() -> ParseResult:
    """Create a sample ParseResult for testing."""
    return ParseResult(
        path=Path("src/auth/service.py"),
        symbols=[
            Symbol(
                name="UserService",
                kind="class",
                signature="class UserService:",
                docstring="Service for user operations.",
                line_start=5,
                line_end=50,
            ),
            Symbol(
                name="UserService.login",
                kind="method",
                signature="def login(self, username: str, password: str) -> bool",
                docstring="Authenticate user.",
                line_start=12,
                line_end=25,
            ),
        ],
        calls=[
            Call(
                caller="UserService.login",
                callee="db.find_user",
                line=15,
                is_method=True,
            ),
        ],
        inheritances=[
            Inheritance(child="UserService", parent="BaseService"),
        ],
        imports=[
            Import(module="hashlib", alias=None, names=[]),
        ],
        module_docstring="Auth service module.",
        file_lines=100,
    )


class TestInjectParseResult:
    """Tests for inject_parse_result()."""

    @pytest.mark.asyncio
    async def test_inject_entities(
        self, mock_client: MockLightRAGClient, sample_parse_result: ParseResult
    ) -> None:
        """Should inject all symbols as entities."""
        result = await inject_parse_result(mock_client, sample_parse_result)

        assert result.entities == 2
        assert len(mock_client.entities) == 2

        # Verify first entity
        first_entity = mock_client.entities[0]
        assert first_entity["name"] == "UserService"
        assert first_entity["data"]["entity_type"] == "class"

    @pytest.mark.asyncio
    async def test_inject_call_relations(
        self, mock_client: MockLightRAGClient, sample_parse_result: ParseResult
    ) -> None:
        """Should inject call relations."""
        result = await inject_parse_result(mock_client, sample_parse_result)

        # 1 call + 1 inheritance + 1 import = 3 relations
        assert result.relations == 3

        # Find the CALLS relation
        calls_relation = next(
            (r for r in mock_client.relations if r["data"].get("keywords") == "CALLS"),
            None,
        )
        assert calls_relation is not None
        assert calls_relation["src"] == "UserService.login"
        assert calls_relation["tgt"] == "db.find_user"

    @pytest.mark.asyncio
    async def test_inject_inheritance_relations(
        self, mock_client: MockLightRAGClient, sample_parse_result: ParseResult
    ) -> None:
        """Should inject inheritance relations."""
        await inject_parse_result(mock_client, sample_parse_result)

        # Find the INHERITS relation
        inherits_relation = next(
            (r for r in mock_client.relations if r["data"].get("keywords") == "INHERITS"),
            None,
        )
        assert inherits_relation is not None
        assert inherits_relation["src"] == "UserService"
        assert inherits_relation["tgt"] == "BaseService"

    @pytest.mark.asyncio
    async def test_inject_import_relations(
        self, mock_client: MockLightRAGClient, sample_parse_result: ParseResult
    ) -> None:
        """Should inject import relations."""
        await inject_parse_result(mock_client, sample_parse_result)

        # Find the IMPORTS relation
        imports_relation = next(
            (r for r in mock_client.relations if r["data"].get("keywords") == "IMPORTS"),
            None,
        )
        assert imports_relation is not None
        assert imports_relation["tgt"] == "hashlib"

    @pytest.mark.asyncio
    async def test_inject_handles_entity_error(
        self, mock_client: MockLightRAGClient, sample_parse_result: ParseResult
    ) -> None:
        """Should continue and record errors when entity injection fails."""
        # Fail on second call
        mock_client._entity_error_on_call = 2

        result = await inject_parse_result(mock_client, sample_parse_result)

        assert result.entities == 1
        assert len(result.errors) >= 1
        assert "UserService.login" in result.errors[0]

    @pytest.mark.asyncio
    async def test_inject_handles_relation_error(
        self, mock_client: MockLightRAGClient, sample_parse_result: ParseResult
    ) -> None:
        """Should continue and record errors when relation injection fails."""
        mock_client.relation_error = Exception("Relation error")

        result = await inject_parse_result(mock_client, sample_parse_result)

        assert result.entities == 2  # Entities should still be injected
        assert result.relations == 0
        assert len(result.errors) == 3  # 1 call + 1 inheritance + 1 import


class TestInjectParseResultsBatch:
    """Tests for inject_parse_results_batch()."""

    @pytest.mark.asyncio
    async def test_batch_inject_multiple_files(self, mock_client: MockLightRAGClient) -> None:
        """Should inject multiple parse results."""
        results = [
            ParseResult(
                path=Path("file1.py"),
                symbols=[
                    Symbol(
                        name="func1",
                        kind="function",
                        signature="def func1():",
                        docstring="",
                        line_start=1,
                        line_end=3,
                    )
                ],
            ),
            ParseResult(
                path=Path("file2.py"),
                symbols=[
                    Symbol(
                        name="func2",
                        kind="function",
                        signature="def func2():",
                        docstring="",
                        line_start=1,
                        line_end=3,
                    )
                ],
            ),
        ]

        inject_results = await inject_parse_results_batch(mock_client, results)

        assert len(inject_results) == 2
        assert inject_results[0].file_path == "file1.py"
        assert inject_results[1].file_path == "file2.py"
        assert len(mock_client.entities) == 2

    @pytest.mark.asyncio
    async def test_batch_skips_files_with_parse_errors(
        self, mock_client: MockLightRAGClient
    ) -> None:
        """Should skip files with parse errors."""
        results = [
            ParseResult(
                path=Path("good.py"),
                symbols=[
                    Symbol(
                        name="func",
                        kind="function",
                        signature="def func():",
                        docstring="",
                        line_start=1,
                        line_end=3,
                    )
                ],
            ),
            ParseResult(
                path=Path("bad.py"),
                error="Syntax error at line 5",
            ),
        ]

        inject_results = await inject_parse_results_batch(mock_client, results)

        assert len(inject_results) == 2
        assert inject_results[0].entities == 1
        assert inject_results[1].entities == 0
        assert "Parse error" in inject_results[1].errors[0]
        assert len(mock_client.entities) == 1
