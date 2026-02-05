"""Unit tests for the injector module."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from loomgraph.core.injector import inject_parse_result, inject_parse_results_batch
from loomgraph.core.models import Call, Import, Inheritance, ParseResult, Symbol


@pytest.fixture
def mock_rag() -> MagicMock:
    """Create a mock LightRAG instance."""
    rag = MagicMock()
    rag.acreate_entity = AsyncMock()
    rag.acreate_relation = AsyncMock()
    return rag


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
        self, mock_rag: MagicMock, sample_parse_result: ParseResult
    ) -> None:
        """Should inject all symbols as entities."""
        result = await inject_parse_result(mock_rag, sample_parse_result)

        assert result.entities == 2
        assert mock_rag.acreate_entity.call_count == 2

        # Verify first entity call
        first_call = mock_rag.acreate_entity.call_args_list[0]
        assert first_call[0][0] == "UserService"  # entity_name
        assert first_call[0][1]["entity_type"] == "class"

    @pytest.mark.asyncio
    async def test_inject_call_relations(
        self, mock_rag: MagicMock, sample_parse_result: ParseResult
    ) -> None:
        """Should inject call relations."""
        result = await inject_parse_result(mock_rag, sample_parse_result)

        # 1 call + 1 inheritance + 1 import = 3 relations
        assert result.relations == 3

        # Find the CALLS relation
        for call in mock_rag.acreate_relation.call_args_list:
            if call[0][2].get("relation_type") == "CALLS":
                assert call[0][0] == "UserService.login"  # src_id
                assert call[0][1] == "db.find_user"  # tgt_id
                break

    @pytest.mark.asyncio
    async def test_inject_inheritance_relations(
        self, mock_rag: MagicMock, sample_parse_result: ParseResult
    ) -> None:
        """Should inject inheritance relations."""
        await inject_parse_result(mock_rag, sample_parse_result)

        # Find the INHERITS relation
        for call in mock_rag.acreate_relation.call_args_list:
            if call[0][2].get("relation_type") == "INHERITS":
                assert call[0][0] == "UserService"  # child
                assert call[0][1] == "BaseService"  # parent
                break

    @pytest.mark.asyncio
    async def test_inject_import_relations(
        self, mock_rag: MagicMock, sample_parse_result: ParseResult
    ) -> None:
        """Should inject import relations."""
        await inject_parse_result(mock_rag, sample_parse_result)

        # Find the IMPORTS relation
        for call in mock_rag.acreate_relation.call_args_list:
            if call[0][2].get("relation_type") == "IMPORTS":
                assert call[0][1] == "hashlib"  # imported module
                break

    @pytest.mark.asyncio
    async def test_inject_with_embeddings(
        self, mock_rag: MagicMock, sample_parse_result: ParseResult
    ) -> None:
        """Should include pre-computed embeddings in entity data."""
        embeddings = {
            "UserService": [0.1, 0.2, 0.3],
            "UserService.login": [0.4, 0.5, 0.6],
        }

        await inject_parse_result(mock_rag, sample_parse_result, embeddings)

        # Check that embeddings were included
        for call in mock_rag.acreate_entity.call_args_list:
            entity_name = call[0][0]
            entity_data = call[0][1]
            assert "embedding" in entity_data
            assert entity_data["embedding"] == embeddings[entity_name]

    @pytest.mark.asyncio
    async def test_inject_handles_entity_error(
        self, mock_rag: MagicMock, sample_parse_result: ParseResult
    ) -> None:
        """Should continue and record errors when entity injection fails."""
        mock_rag.acreate_entity.side_effect = [
            None,  # First entity succeeds
            Exception("Database error"),  # Second entity fails
        ]

        result = await inject_parse_result(mock_rag, sample_parse_result)

        assert result.entities == 1
        assert len(result.errors) == 1
        assert "UserService.login" in result.errors[0]

    @pytest.mark.asyncio
    async def test_inject_handles_relation_error(
        self, mock_rag: MagicMock, sample_parse_result: ParseResult
    ) -> None:
        """Should continue and record errors when relation injection fails."""
        mock_rag.acreate_relation.side_effect = Exception("Relation error")

        result = await inject_parse_result(mock_rag, sample_parse_result)

        assert result.entities == 2  # Entities should still be injected
        assert result.relations == 0
        assert len(result.errors) == 3  # 1 call + 1 inheritance + 1 import


class TestInjectParseResultsBatch:
    """Tests for inject_parse_results_batch()."""

    @pytest.mark.asyncio
    async def test_batch_inject_multiple_files(self, mock_rag: MagicMock) -> None:
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

        inject_results = await inject_parse_results_batch(mock_rag, results)

        assert len(inject_results) == 2
        assert inject_results[0].file_path == "file1.py"
        assert inject_results[1].file_path == "file2.py"
        assert mock_rag.acreate_entity.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_skips_files_with_parse_errors(self, mock_rag: MagicMock) -> None:
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

        inject_results = await inject_parse_results_batch(mock_rag, results)

        assert len(inject_results) == 2
        assert inject_results[0].entities == 1
        assert inject_results[1].entities == 0
        assert "Parse error" in inject_results[1].errors[0]
        assert mock_rag.acreate_entity.call_count == 1
