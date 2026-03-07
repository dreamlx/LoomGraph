"""Test codeindex → LoomGraph adapter."""

from pathlib import Path

from codeindex.parser import parse_file

from loomgraph.core.adapter import adapt_parse_result
from loomgraph.core.models import ParseResult


class TestAdaptParseResult:
    """Test adapt_parse_result function."""

    def test_adapt_python_file(self, temp_python_file: Path) -> None:
        """Test adapting a Python file parse result."""
        # Parse with codeindex
        ci_result = parse_file(temp_python_file)

        # Adapt to LoomGraph
        lg_result = adapt_parse_result(ci_result)

        # Verify result type
        assert isinstance(lg_result, ParseResult)
        assert lg_result.path == temp_python_file
        assert lg_result.error is None

    def test_symbols_preserved(self, temp_python_file: Path) -> None:
        """Test that symbols are correctly preserved."""
        ci_result = parse_file(temp_python_file)
        lg_result = adapt_parse_result(ci_result)

        # Should have class and its methods
        assert len(lg_result.symbols) >= 3  # UserService, login, _verify_password, create_user

        # Find UserService class
        user_service = next(
            (s for s in lg_result.symbols if s.name == "UserService"), None
        )
        assert user_service is not None
        assert user_service.kind == "class"
        assert "Service for user authentication" in user_service.docstring

        # Find login method
        login = next(
            (s for s in lg_result.symbols if s.name == "UserService.login"), None
        )
        assert login is not None
        assert login.kind == "method"
        assert "username: str" in login.signature
        assert "password: str" in login.signature

    def test_imports_preserved(self, temp_python_file: Path) -> None:
        """Test that imports are correctly preserved."""
        ci_result = parse_file(temp_python_file)
        lg_result = adapt_parse_result(ci_result)

        # Should have hashlib and typing imports
        modules = [i.module for i in lg_result.imports]
        assert "hashlib" in modules
        assert "typing" in modules

        # Check typing import has Optional
        typing_import = next(
            (i for i in lg_result.imports if i.module == "typing"), None
        )
        assert typing_import is not None
        assert "Optional" in typing_import.names

    def test_calls_empty_for_now(self, temp_python_file: Path) -> None:
        """Test that calls list is empty (not yet supported by codeindex)."""
        ci_result = parse_file(temp_python_file)
        lg_result = adapt_parse_result(ci_result)

        # Calls not supported yet
        assert lg_result.calls == []

    def test_inheritances_empty_for_now(self, temp_python_file: Path) -> None:
        """Test that inheritances list is empty (not yet supported by codeindex)."""
        ci_result = parse_file(temp_python_file)
        lg_result = adapt_parse_result(ci_result)

        # Inheritances not supported yet
        assert lg_result.inheritances == []

    def test_adapt_php_file(self, temp_php_file: Path) -> None:
        """Test adapting a PHP file parse result."""
        ci_result = parse_file(temp_php_file)
        lg_result = adapt_parse_result(ci_result)

        assert isinstance(lg_result, ParseResult)
        assert lg_result.error is None

        # Should have AuthService class
        auth_service = next(
            (s for s in lg_result.symbols if s.name == "AuthService"), None
        )
        assert auth_service is not None
        assert auth_service.kind == "class"

    def test_line_numbers_preserved(self, temp_python_file: Path) -> None:
        """Test that line numbers are correctly preserved."""
        ci_result = parse_file(temp_python_file)
        lg_result = adapt_parse_result(ci_result)

        # All symbols should have valid line numbers
        for symbol in lg_result.symbols:
            assert symbol.line_start > 0
            assert symbol.line_end >= symbol.line_start


class TestAdaptEdgeCases:
    """Test edge cases in adaptation."""

    def test_empty_file(self, tmp_path: Path) -> None:
        """Test adapting an empty file."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        ci_result = parse_file(empty_file)
        lg_result = adapt_parse_result(ci_result)

        assert lg_result.symbols == []
        assert lg_result.imports == []

    def test_file_with_only_imports(self, tmp_path: Path) -> None:
        """Test file with only import statements."""
        imports_file = tmp_path / "imports_only.py"
        imports_file.write_text("""
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict
""")

        ci_result = parse_file(imports_file)
        lg_result = adapt_parse_result(ci_result)

        assert lg_result.symbols == []
        # codeindex may split "from X import A, B, C" into separate imports
        assert len(lg_result.imports) >= 4
        modules = [i.module for i in lg_result.imports]
        assert "os" in modules
        assert "sys" in modules
        assert "pathlib" in modules
        assert "typing" in modules

    def test_file_with_syntax_error(self, tmp_path: Path) -> None:
        """Test handling of file with syntax error."""
        bad_file = tmp_path / "syntax_error.py"
        bad_file.write_text("""
def broken(
    # Missing closing paren
""")

        ci_result = parse_file(bad_file)
        lg_result = adapt_parse_result(ci_result)

        # Should still produce a result (tree-sitter is error-tolerant)
        assert isinstance(lg_result, ParseResult)
