"""Unit tests for the injector module."""

from pathlib import Path
from typing import Any

import pytest

from loomgraph.core.injector import (
    build_chunks,
    create_external_stubs,
    inject_parse_result,
    inject_parse_results_batch,
)
from loomgraph.core.models import Call, Import, Inheritance, ParseResult, Symbol


class MockGraphStore:
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
def mock_client() -> MockGraphStore:
    """Create a mock LightRAG client."""
    return MockGraphStore()


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
        self, mock_client: MockGraphStore, sample_parse_result: ParseResult
    ) -> None:
        """Should inject all symbols as entities."""
        result = await inject_parse_result(mock_client, sample_parse_result)

        # 2 symbols + 1 module entity = 3 entities total in mock
        # But result.entities only counts symbols
        assert result.entities == 2
        assert len(mock_client.entities) == 3  # includes module entity

        # First entity is the module, second is UserService
        module_entity = mock_client.entities[0]
        assert module_entity["data"]["entity_type"] == "module"

        class_entity = mock_client.entities[1]
        assert class_entity["name"] == "UserService"
        assert class_entity["data"]["entity_type"] == "class"

    @pytest.mark.asyncio
    async def test_inject_call_relations(
        self, mock_client: MockGraphStore, sample_parse_result: ParseResult
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
        self, mock_client: MockGraphStore, sample_parse_result: ParseResult
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
        self, mock_client: MockGraphStore, sample_parse_result: ParseResult
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
        self, mock_client: MockGraphStore, sample_parse_result: ParseResult
    ) -> None:
        """Should continue and record errors when entity injection fails."""
        # Fail on third call (1=module, 2=UserService, 3=UserService.login)
        mock_client._entity_error_on_call = 3

        result = await inject_parse_result(mock_client, sample_parse_result)

        assert result.entities == 1
        assert len(result.errors) >= 1
        assert "UserService.login" in result.errors[0]

    @pytest.mark.asyncio
    async def test_inject_handles_relation_error(
        self, mock_client: MockGraphStore, sample_parse_result: ParseResult
    ) -> None:
        """Should continue and record errors when relation injection fails."""
        mock_client.relation_error = Exception("Relation error")

        result = await inject_parse_result(mock_client, sample_parse_result)

        assert result.entities == 2  # Symbol entities should still be injected
        assert result.relations == 0
        assert len(result.errors) == 3  # 1 call + 1 inheritance + 1 import


class TestInjectParseResultsBatch:
    """Tests for inject_parse_results_batch()."""

    @pytest.mark.asyncio
    async def test_batch_inject_multiple_files(self, mock_client: MockGraphStore) -> None:
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
        # 2 files × (1 module + 1 symbol) = 4 entities
        assert len(mock_client.entities) == 4

    @pytest.mark.asyncio
    async def test_batch_skips_files_with_parse_errors(
        self, mock_client: MockGraphStore
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
        assert inject_results[0].entities == 1  # 1 symbol (module not counted)
        assert inject_results[1].entities == 0
        assert "Parse error" in inject_results[1].errors[0]
        # 1 good file × (1 module + 1 symbol) = 2 entities
        assert len(mock_client.entities) == 2


class TestBuildChunks:
    """Tests for build_chunks()."""

    def test_normal_file(self, sample_parse_result: ParseResult) -> None:
        """Should build a single chunk with signatures and docstrings."""
        chunks = build_chunks(sample_parse_result)

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk["source_id"] == "src/auth/service.py"
        assert chunk["full_doc_id"] == "src/auth/service.py"
        assert chunk["chunk_order_index"] == 0
        assert chunk["tokens"] > 0
        # Should contain module docstring
        assert "Auth service module." in chunk["content"]
        # Should contain symbol signatures
        assert "class UserService:" in chunk["content"]
        assert "def login" in chunk["content"]

    def test_file_with_docstrings(self) -> None:
        """Should include truncated docstrings."""
        result = ParseResult(
            path=Path("src/foo.py"),
            symbols=[
                Symbol(
                    name="important_func",
                    kind="function",
                    signature="def important_func(x: int) -> str",
                    docstring="A" * 300,  # longer than 200 chars
                    line_start=1,
                    line_end=10,
                ),
            ],
            module_docstring="",
        )

        chunks = build_chunks(result)
        chunk = chunks[0]
        # Docstring should be truncated to 200 chars
        assert len("A" * 300) > 200
        assert "A" * 200 in chunk["content"]
        # But the full 300 should not be there
        assert "A" * 300 not in chunk["content"]

    def test_empty_symbols(self) -> None:
        """Should produce a chunk even with no symbols."""
        result = ParseResult(
            path=Path("src/empty.py"),
            symbols=[],
            module_docstring="",
        )

        chunks = build_chunks(result)

        assert len(chunks) == 1
        # Fallback: content should be the file path
        assert chunks[0]["content"] == "src/empty.py"

    def test_with_module_docstring_only(self) -> None:
        """Should include module docstring."""
        result = ParseResult(
            path=Path("src/mod.py"),
            symbols=[],
            module_docstring="This is a module for doing things.",
        )

        chunks = build_chunks(result)

        assert "This is a module for doing things." in chunks[0]["content"]

    def test_symbol_without_signature(self) -> None:
        """Should fallback to kind + name when no signature."""
        result = ParseResult(
            path=Path("src/test.py"),
            symbols=[
                Symbol(
                    name="MY_CONSTANT",
                    kind="variable",
                    signature="",
                    docstring="",
                    line_start=1,
                    line_end=1,
                ),
            ],
        )

        chunks = build_chunks(result)
        assert "variable MY_CONSTANT" in chunks[0]["content"]


class TestCreateExternalStubs:
    """Tests for create_external_stubs()."""

    def test_creates_stubs_for_missing_targets(self) -> None:
        """Should create stubs for relation targets not in entities."""
        entities = [
            {"entity_name": "MyClass", "entity_type": "class"},
            {"entity_name": "my_func", "entity_type": "function"},
        ]
        relations = [
            {"src_id": "MyClass", "tgt_id": "BaseClass", "keywords": "INHERITS"},
            {"src_id": "my_func", "tgt_id": "os.path.join", "keywords": "CALLS"},
        ]

        stubs = create_external_stubs(entities, relations)

        assert len(stubs) == 2
        stub_names = {s["entity_name"] for s in stubs}
        assert "BaseClass" in stub_names
        assert "os.path.join" in stub_names

        for stub in stubs:
            assert stub["entity_type"] == "external"
            assert stub["source_id"] == "external"
            assert "External dependency:" in stub["description"]

    def test_no_stubs_when_all_known(self) -> None:
        """Should return empty list when all relation targets exist."""
        entities = [
            {"entity_name": "A", "entity_type": "class"},
            {"entity_name": "B", "entity_type": "class"},
        ]
        relations = [
            {"src_id": "A", "tgt_id": "B", "keywords": "CALLS"},
        ]

        stubs = create_external_stubs(entities, relations)

        assert stubs == []

    def test_empty_relations(self) -> None:
        """Should return empty list with no relations."""
        entities = [{"entity_name": "A", "entity_type": "class"}]

        stubs = create_external_stubs(entities, [])

        assert stubs == []

    def test_no_duplicate_stubs(self) -> None:
        """Should not create duplicate stubs for the same missing entity."""
        entities = [{"entity_name": "A", "entity_type": "class"}]
        relations = [
            {"src_id": "A", "tgt_id": "External", "keywords": "CALLS"},
            {"src_id": "A", "tgt_id": "External", "keywords": "IMPORTS"},
        ]

        stubs = create_external_stubs(entities, relations)

        assert len(stubs) == 1
        assert stubs[0]["entity_name"] == "External"

    def test_stub_for_missing_src(self) -> None:
        """Should also create stubs for missing src_id entities."""
        entities = [{"entity_name": "B", "entity_type": "class"}]
        relations = [
            {"src_id": "Unknown", "tgt_id": "B", "keywords": "CALLS"},
        ]

        stubs = create_external_stubs(entities, relations)

        assert len(stubs) == 1
        assert stubs[0]["entity_name"] == "Unknown"
