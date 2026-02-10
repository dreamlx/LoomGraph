"""Unit tests for the mapper module.

Tests the LightRAG API convention mapping (confirmed 2025-02-04):
- entity_data: entity_type, description (concat), source_id, file_path
- edge_data: keywords (relation_type), description, weight, source_id
"""

import pytest

from loomgraph.core.mapper import (
    detect_language,
    map_call_to_relation,
    map_import_to_relation,
    map_inheritance_to_relation,
    map_symbol_to_entity,
)
from loomgraph.core.models import Call, Import, Inheritance, Symbol


class TestDetectLanguage:
    """Tests for detect_language()."""

    @pytest.mark.parametrize(
        "file_path,expected",
        [
            ("src/auth/service.py", "python"),
            ("src/auth/service.pyi", "python"),
            ("src/utils.js", "javascript"),
            ("components/Button.jsx", "javascript"),
            ("src/utils.ts", "typescript"),
            ("components/Button.tsx", "typescript"),
            ("Main.java", "java"),
            ("main.go", "go"),
            ("lib.rs", "rust"),
            ("app.rb", "ruby"),
            ("index.php", "php"),
            ("main.c", "c"),
            ("main.cpp", "cpp"),
            ("Program.cs", "csharp"),
            ("App.swift", "swift"),
            ("unknown.xyz", "unknown"),
        ],
    )
    def test_detect_language_from_extension(self, file_path: str, expected: str) -> None:
        """Should detect language from file extension."""
        assert detect_language(file_path) == expected

    def test_detect_language_case_insensitive(self) -> None:
        """Should handle uppercase extensions."""
        assert detect_language("main.PY") == "python"
        assert detect_language("App.JS") == "javascript"


class TestMapSymbolToEntity:
    """Tests for map_symbol_to_entity()."""

    def test_map_method_symbol(self) -> None:
        """Should map method symbol to entity data with concatenated description."""
        symbol = Symbol(
            name="UserService.login",
            kind="method",
            signature="def login(self, username: str, password: str) -> bool",
            docstring="Authenticate user with credentials.",
            line_start=12,
            line_end=25,
        )

        entity = map_symbol_to_entity(symbol, "src/auth/service.py", "python")

        assert entity.entity_name == "UserService.login"
        assert entity.entity_data["entity_type"] == "method"
        # LightRAG convention: description concatenates signature + docstring + location
        assert "def login" in entity.entity_data["description"]
        assert "Authenticate user" in entity.entity_data["description"]
        assert "Python" in entity.entity_data["description"]
        assert entity.entity_data["source_id"] == "src/auth/service.py:12-25"
        assert entity.entity_data["file_path"] == "src/auth/service.py"
        # LightRAG convention: no separate signature/language/line fields
        assert "embedding" not in entity.entity_data

    def test_map_class_symbol(self) -> None:
        """Should map class symbol to entity data."""
        symbol = Symbol(
            name="UserService",
            kind="class",
            signature="class UserService:",
            docstring="Service for user operations.",
            line_start=5,
            line_end=50,
        )

        entity = map_symbol_to_entity(symbol, "src/auth/service.py", "python")

        assert entity.entity_name == "UserService"
        assert entity.entity_data["entity_type"] == "class"
        assert "Service for user operations" in entity.entity_data["description"]

    def test_map_symbol_without_docstring(self) -> None:
        """Should generate description from signature when no docstring."""
        symbol = Symbol(
            name="helper_func",
            kind="function",
            signature="def helper_func(x: int) -> int:",
            docstring="",  # Empty docstring
            line_start=1,
            line_end=3,
        )

        entity = map_symbol_to_entity(symbol, "utils.py", "python")

        # LightRAG convention: description has signature + location
        assert "def helper_func" in entity.entity_data["description"]
        assert "Python" in entity.entity_data["description"]


class TestMapCallToRelation:
    """Tests for map_call_to_relation()."""

    def test_map_method_call(self) -> None:
        """Should map method call to relation data with keywords field."""
        call = Call(
            caller="UserService.login",
            callee="db.find_user",
            line=15,
            is_method=True,
        )

        rel = map_call_to_relation(call, "src/auth/service.py")

        assert rel.src_id == "UserService.login"
        assert rel.tgt_id == "db.find_user"
        # LightRAG convention: use keywords for relation_type
        assert rel.edge_data["keywords"] == "CALLS"
        assert rel.edge_data["weight"] == 1.0
        assert rel.edge_data["source_id"] == "src/auth/service.py:15"
        # LightRAG convention: description explains the relation
        assert "calls" in rel.edge_data["description"]
        assert "line 15" in rel.edge_data["description"]

    def test_map_function_call(self) -> None:
        """Should map function call to relation data."""
        call = Call(
            caller="process_data",
            callee="validate",
            line=42,
            is_method=False,
        )

        rel = map_call_to_relation(call, "pipeline.py")

        assert rel.src_id == "process_data"
        assert rel.tgt_id == "validate"
        assert rel.edge_data["keywords"] == "CALLS"


class TestMapInheritanceToRelation:
    """Tests for map_inheritance_to_relation()."""

    def test_map_single_inheritance(self) -> None:
        """Should map inheritance to relation data with keywords field."""
        inh = Inheritance(child="UserService", parent="BaseService")

        rel = map_inheritance_to_relation(inh, "src/auth/service.py")

        assert rel.src_id == "UserService"
        assert rel.tgt_id == "BaseService"
        # LightRAG convention: use keywords for relation_type
        assert rel.edge_data["keywords"] == "INHERITS"
        assert rel.edge_data["weight"] == 1.0
        assert rel.edge_data["source_id"] == "src/auth/service.py"
        # LightRAG convention: description explains the relation
        assert "inherits" in rel.edge_data["description"]


class TestMapImportToRelation:
    """Tests for map_import_to_relation()."""

    def test_map_from_import_with_names(self) -> None:
        """Should map 'from X import a, b' to multiple relations."""
        imp = Import(
            module="os.path",
            alias=None,
            names=["join", "exists"],
        )

        rels = map_import_to_relation(imp, "src.utils", "src/utils.py")

        assert len(rels) == 2
        assert rels[0].src_id == "src.utils"
        assert rels[0].tgt_id == "os.path.join"
        # LightRAG convention: use keywords for relation_type
        assert rels[0].edge_data["keywords"] == "IMPORTS"
        assert rels[1].tgt_id == "os.path.exists"
        # LightRAG convention: description explains the import
        assert "from os.path import join" in rels[0].edge_data["description"]

    def test_map_simple_import(self) -> None:
        """Should map 'import X' to single relation."""
        imp = Import(
            module="json",
            alias=None,
            names=[],
        )

        rels = map_import_to_relation(imp, "src.parser", "src/parser.py")

        assert len(rels) == 1
        assert rels[0].src_id == "src.parser"
        assert rels[0].tgt_id == "json"
        assert "import json" in rels[0].edge_data["description"]

    def test_map_aliased_import(self) -> None:
        """Should map 'import X as Y' with alias in description."""
        imp = Import(
            module="numpy",
            alias="np",
            names=[],
        )

        rels = map_import_to_relation(imp, "analysis", "analysis.py")

        assert len(rels) == 1
        assert rels[0].tgt_id == "numpy"
        # LightRAG convention: alias in description, not separate field
        assert "as np" in rels[0].edge_data["description"]
