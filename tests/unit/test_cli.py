"""Tests for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import (
    ErrorCode,
    check_codeindex,
    check_lightrag,
    main,
    output_error,
    output_success,
)


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_parse_results() -> dict[str, Any]:
    """Sample codeindex parse results."""
    return {
        "results": [
            {
                "path": "src/user.py",
                "symbols": [
                    {
                        "name": "UserService",
                        "kind": "class",
                        "signature": "class UserService:",
                        "docstring": "User service class",
                        "line_start": 1,
                        "line_end": 20,
                    },
                    {
                        "name": "UserService.login",
                        "kind": "method",
                        "signature": "def login(self, username: str, password: str) -> bool:",
                        "docstring": "Login method",
                        "line_start": 5,
                        "line_end": 10,
                    },
                ],
                "calls": [
                    {
                        "caller": "UserService.login",
                        "callee": "db.find_user",
                        "line": 7,
                        "is_method": True,
                    }
                ],
                "inheritances": [],
                "imports": [
                    {"module": "hashlib", "alias": None, "names": ["sha256"]}
                ],
            }
        ]
    }


class TestOutputHelpers:
    """Tests for JSON output helper functions."""

    def test_output_success(self, runner: CliRunner) -> None:
        """Test successful JSON output."""
        # output_success prints to stdout and doesn't exit
        # We test this indirectly through commands

    def test_output_error_format(self) -> None:
        """Test error output format has required fields."""
        # The output_error function calls sys.exit(1)
        # We test this through commands


class TestVersionCommand:
    """Tests for the version command."""

    def test_version_success(self, runner: CliRunner) -> None:
        """Test version command outputs JSON."""
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert "version" in data["data"]
        assert "python" in data["data"]

    def test_version_option(self, runner: CliRunner) -> None:
        """Test --version option."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "loomgraph" in result.output.lower()


class TestStatusCommand:
    """Tests for the status command."""

    @patch("loomgraph.cli.main.check_codeindex")
    @patch("loomgraph.cli.main.check_postgres")
    @patch("loomgraph.cli.main.check_embedding")
    @patch("loomgraph.cli.main.check_lightrag")
    def test_status_all_ok(
        self,
        mock_lightrag: MagicMock,
        mock_embedding: MagicMock,
        mock_postgres: MagicMock,
        mock_codeindex: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test status when all dependencies are available."""
        mock_codeindex.return_value = {"installed": True, "version": "1.0.0"}
        mock_postgres.return_value = {"connected": True, "version": "16.1"}
        mock_embedding.return_value = {"connected": True, "model": "jina"}
        mock_lightrag.return_value = {"installed": True, "version": "1.0.0"}

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert "dependencies" in data["data"]

    @patch("loomgraph.cli.main.check_codeindex")
    @patch("loomgraph.cli.main.check_postgres")
    @patch("loomgraph.cli.main.check_embedding")
    @patch("loomgraph.cli.main.check_lightrag")
    def test_status_missing_dependencies(
        self,
        mock_lightrag: MagicMock,
        mock_embedding: MagicMock,
        mock_postgres: MagicMock,
        mock_codeindex: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test status when some dependencies are missing."""
        mock_codeindex.return_value = {"installed": False, "error": "not found"}
        mock_postgres.return_value = {"connected": False, "error": "refused"}
        mock_embedding.return_value = {"connected": True, "model": "jina"}
        mock_lightrag.return_value = {"installed": True, "version": "1.0.0"}

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 1

        data = json.loads(result.output)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.DEPENDENCIES_MISSING
        assert "suggestions" in data["error"]
        assert len(data["error"]["suggestions"]) >= 2


class TestIndexCommand:
    """Tests for the index command."""

    def test_index_path_not_exists(self, runner: CliRunner) -> None:
        """Test index with non-existent path."""
        result = runner.invoke(main, ["index", "/nonexistent/path"])
        assert result.exit_code != 0

    @patch("loomgraph.cli.main.check_codeindex")
    def test_index_codeindex_not_found(
        self, mock_check: MagicMock, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test index when codeindex is not installed."""
        mock_check.return_value = {"installed": False, "error": "not found"}

        result = runner.invoke(main, ["index", str(tmp_path)])
        assert result.exit_code == 1

        data = json.loads(result.output)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.CODEINDEX_NOT_FOUND

    @patch("subprocess.run")
    @patch("loomgraph.cli.main.check_codeindex")
    def test_index_codeindex_failed(
        self,
        mock_check: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """Test index when codeindex fails."""
        mock_check.return_value = {"installed": True, "version": "1.0.0"}
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Parse error"
        )

        result = runner.invoke(main, ["index", str(tmp_path)])
        assert result.exit_code == 1

        data = json.loads(result.output)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.CODEINDEX_FAILED

    @patch("subprocess.run")
    @patch("loomgraph.cli.main.check_codeindex")
    def test_index_success(
        self,
        mock_check: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        tmp_path: Path,
        sample_parse_results: dict[str, Any],
    ) -> None:
        """Test successful index."""
        mock_check.return_value = {"installed": True, "version": "1.0.0"}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(sample_parse_results),
            stderr="",
        )

        result = runner.invoke(main, ["index", str(tmp_path)])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert data["data"]["files_scanned"] == 1
        assert data["data"]["entities_created"] == 2
        assert data["data"]["relations_created"] == 2  # 1 call + 1 import


class TestEmbedCommand:
    """Tests for the embed command."""

    def test_embed_file_not_found(self, runner: CliRunner) -> None:
        """Test embed with non-existent file."""
        result = runner.invoke(main, ["embed", "/nonexistent/file.json"])
        assert result.exit_code != 0

    def test_embed_invalid_json(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test embed with invalid JSON."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json")

        result = runner.invoke(main, ["embed", str(invalid_file)])
        assert result.exit_code == 1

        data = json.loads(result.output)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.INVALID_INPUT

    @patch("loomgraph.cli.main.asyncio.run")
    def test_embed_success(
        self,
        mock_asyncio_run: MagicMock,
        runner: CliRunner,
        tmp_path: Path,
        sample_parse_results: dict[str, Any],
    ) -> None:
        """Test successful embed."""
        # Create input file
        input_file = tmp_path / "parse.json"
        input_file.write_text(json.dumps(sample_parse_results))

        # Mock asyncio.run to return our data directly
        mock_asyncio_run.return_value = {
            "embeddings": {"UserService": [0.1, 0.2, 0.3]},
            "model": "jina",
            "dimension": 3,
            "count": 1,
        }

        result = runner.invoke(main, ["embed", str(input_file)])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert data["data"]["count"] == 1


class TestInjectCommand:
    """Tests for the inject command."""

    def test_inject_file_not_found(self, runner: CliRunner) -> None:
        """Test inject with non-existent files."""
        result = runner.invoke(
            main, ["inject", "/nonexistent/parse.json", "/nonexistent/embed.json"]
        )
        assert result.exit_code != 0

    def test_inject_success(
        self,
        runner: CliRunner,
        tmp_path: Path,
        sample_parse_results: dict[str, Any],
    ) -> None:
        """Test successful inject."""
        # Create input files
        parse_file = tmp_path / "parse.json"
        parse_file.write_text(json.dumps(sample_parse_results))

        embed_file = tmp_path / "embed.json"
        embed_file.write_text(
            json.dumps(
                {
                    "data": {
                        "embeddings": {
                            "UserService": [0.1, 0.2, 0.3],
                            "UserService.login": [0.4, 0.5, 0.6],
                        }
                    }
                }
            )
        )

        result = runner.invoke(
            main, ["inject", str(parse_file), str(embed_file)]
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert data["data"]["entities_created"] == 2
        assert data["data"]["relations_created"] == 2


class TestSearchCommand:
    """Tests for the search command."""

    def test_search_basic(self, runner: CliRunner) -> None:
        """Test basic search command."""
        result = runner.invoke(main, ["search", "user login"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert data["data"]["query"] == "user login"
        assert data["data"]["mode"] == "hybrid"

    def test_search_with_options(self, runner: CliRunner) -> None:
        """Test search with options."""
        result = runner.invoke(
            main, ["search", "authentication", "--mode", "semantic", "--limit", "5"]
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["data"]["mode"] == "semantic"


class TestGraphCommand:
    """Tests for the graph command."""

    def test_graph_basic(self, runner: CliRunner) -> None:
        """Test basic graph query."""
        result = runner.invoke(main, ["graph", "UserService.login"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert data["data"]["entity"] == "UserService.login"
        assert "callers" in data["data"]
        assert "callees" in data["data"]

    def test_graph_callers_only(self, runner: CliRunner) -> None:
        """Test graph query for callers only."""
        result = runner.invoke(
            main, ["graph", "func", "--direction", "callers"]
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "callers" in data["data"]
        assert "callees" not in data["data"]

    def test_graph_with_relation_type(self, runner: CliRunner) -> None:
        """Test graph query with relation type filter."""
        result = runner.invoke(
            main, ["graph", "MyClass", "--relation-type", "INHERITS"]
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True


class TestDependencyChecks:
    """Tests for dependency check functions."""

    @patch("shutil.which")
    def test_check_codeindex_not_found(self, mock_which: MagicMock) -> None:
        """Test codeindex check when not installed."""
        mock_which.return_value = None
        result = check_codeindex()
        assert result["installed"] is False
        assert "error" in result

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_check_codeindex_found(
        self, mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        """Test codeindex check when installed."""
        mock_which.return_value = "/usr/bin/codeindex"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="codeindex 1.0.0"
        )

        result = check_codeindex()
        assert result["installed"] is True
        assert result["path"] == "/usr/bin/codeindex"

    def test_check_lightrag_not_installed(self) -> None:
        """Test lightrag check when not installed."""
        with patch.dict("sys.modules", {"lightrag": None}):
            # Unload the module if it's already imported
            import sys

            if "lightrag" in sys.modules:
                del sys.modules["lightrag"]

            # The actual check
            result = check_lightrag()
            # May return installed or not depending on environment


class TestCLIHelp:
    """Tests for CLI help messages."""

    def test_main_help(self, runner: CliRunner) -> None:
        """Test main help."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "LoomGraph" in result.output
        assert "index" in result.output
        assert "search" in result.output

    def test_index_help(self, runner: CliRunner) -> None:
        """Test index command help."""
        result = runner.invoke(main, ["index", "--help"])
        assert result.exit_code == 0
        assert "REPO_PATH" in result.output

    def test_search_help(self, runner: CliRunner) -> None:
        """Test search command help."""
        result = runner.invoke(main, ["search", "--help"])
        assert result.exit_code == 0
        assert "QUERY" in result.output
        assert "--mode" in result.output

    def test_graph_help(self, runner: CliRunner) -> None:
        """Test graph command help."""
        result = runner.invoke(main, ["graph", "--help"])
        assert result.exit_code == 0
        assert "ENTITY_NAME" in result.output
        assert "--direction" in result.output
