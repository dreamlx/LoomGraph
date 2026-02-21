"""Tests for AST-based chunking and injection improvements."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from loomgraph.chunking import Chunk, chunk_file
from loomgraph.core.models import ParseResult, Symbol, Call
from loomgraph.core.injector import collect_kg_data
from loomgraph.core.mapper import map_symbol_to_entity


class TestChunkFile:
    """Tests for chunk_file()."""

    def test_splits_by_symbol(self) -> None:
        source = "import os\n\ndef foo():\n    pass\n\ndef bar():\n    return 1\n"
        pr = ParseResult(
            path=Path("app.py"),
            symbols=[
                Symbol(name="foo", kind="function", signature="def foo()",
                       docstring="", line_start=3, line_end=4),
                Symbol(name="bar", kind="function", signature="def bar()",
                       docstring="", line_start=6, line_end=7),
            ],
        )
        chunks = chunk_file(source, pr, "app")
        names = [c.symbol_name for c in chunks]
        assert "foo" in names
        assert "bar" in names

    def test_fallback_chunk_for_uncovered(self) -> None:
        source = "import os\nimport sys\n\ndef foo():\n    pass\n"
        pr = ParseResult(
            path=Path("app.py"),
            symbols=[
                Symbol(name="foo", kind="function", signature="def foo()",
                       docstring="", line_start=4, line_end=5),
            ],
        )
        chunks = chunk_file(source, pr, "app")
        fallback = [c for c in chunks if c.symbol_name == ""]
        assert len(fallback) == 1
        assert "import os" in fallback[0].content
    def test_empty_source(self) -> None:
        pr = ParseResult(path=Path("empty.py"), symbols=[])
        chunks = chunk_file("", pr, "empty")
        assert chunks == []

    def test_chunk_ids_deterministic(self) -> None:
        source = "def foo():\n    pass\n"
        pr = ParseResult(
            path=Path("a.py"),
            symbols=[
                Symbol(name="foo", kind="function", signature="def foo()",
                       docstring="", line_start=1, line_end=2),
            ],
        )
        c1 = chunk_file(source, pr, "a")
        c2 = chunk_file(source, pr, "a")
        assert c1[0].id == c2[0].id


class TestEntityDescription:
    """Tests for improved entity description format."""

    def test_includes_kind_prefix(self) -> None:
        sym = Symbol(name="login", kind="function",
                     signature="def login()", docstring="Auth user.",
                     line_start=1, line_end=5)
        entity = map_symbol_to_entity(sym, "auth.py", "python")
        desc = entity.entity_data["description"]
        assert desc.startswith("function: login")

    def test_truncates_long_docstring(self) -> None:
        long_doc = "x" * 500
        sym = Symbol(name="big", kind="class",
                     signature="class Big", docstring=long_doc,
                     line_start=1, line_end=10)
        entity = map_symbol_to_entity(sym, "big.py", "python")
        desc = entity.entity_data["description"]
        # docstring should be truncated to 200 chars
        assert long_doc not in desc
        assert "x" * 200 in desc


class TestRelationValidation:
    """Tests for relation endpoint pre-validation in collect_kg_data."""

    def test_drops_orphan_relations(self) -> None:
        pr = ParseResult(
            path=Path("src/app.py"),
            symbols=[
                Symbol(name="foo", kind="function", signature="def foo()",
                       docstring="", line_start=1, line_end=3),
            ],
            calls=[
                Call(caller="unknown_func", callee="also_unknown",
                     line=10, is_method=False),
            ],
        )
        entities, relations = collect_kg_data(pr)
        # The call relation has neither endpoint in known entities
        call_rels = [r for r in relations if r.get("keywords") == "CALLS"]
        assert len(call_rels) == 0

    def test_keeps_valid_relations(self) -> None:
        pr = ParseResult(
            path=Path("src/app.py"),
            symbols=[
                Symbol(name="foo", kind="function", signature="def foo()",
                       docstring="", line_start=1, line_end=3),
                Symbol(name="bar", kind="function", signature="def bar()",
                       docstring="", line_start=5, line_end=7),
            ],
            calls=[
                Call(caller="foo", callee="bar", line=2, is_method=False),
            ],
        )
        entities, relations = collect_kg_data(pr)
        call_rels = [r for r in relations if r.get("keywords") == "CALLS"]
        assert len(call_rels) == 1

