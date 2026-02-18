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
    check_lightrag_api,
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
    @patch("loomgraph.cli.main.check_lightrag_api")
    @patch("loomgraph.cli.main.check_embedding")
    def test_status_all_ok(
        self,
        mock_embedding: MagicMock,
        mock_lightrag: MagicMock,
        mock_codeindex: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test status when all dependencies are available."""
        mock_codeindex.return_value = {"installed": True, "version": "1.0.0"}
        mock_lightrag.return_value = {"connected": True, "status": "healthy", "version": "1.0.0"}
        mock_embedding.return_value = {"connected": True, "model": "jina"}

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert "dependencies" in data["data"]

    @patch("loomgraph.cli.main.check_codeindex")
    @patch("loomgraph.cli.main.check_lightrag_api")
    @patch("loomgraph.cli.main.check_embedding")
    def test_status_lightrag_unavailable(
        self,
        mock_embedding: MagicMock,
        mock_lightrag: MagicMock,
        mock_codeindex: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test status when LightRAG API is not available."""
        mock_codeindex.return_value = {"installed": True, "version": "1.0.0"}
        mock_lightrag.return_value = {"connected": False, "error": "connection refused"}
        mock_embedding.return_value = {"connected": True, "model": "jina"}

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 1

        data = json.loads(result.output)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.DEPENDENCIES_MISSING


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

    @patch("loomgraph.cli.main.asyncio.run")
    @patch("subprocess.run")
    @patch("loomgraph.cli.main.check_codeindex")
    def test_index_success(
        self,
        mock_check: MagicMock,
        mock_subprocess: MagicMock,
        mock_asyncio: MagicMock,
        runner: CliRunner,
        tmp_path: Path,
        sample_parse_results: dict[str, Any],
    ) -> None:
        """Test successful index."""
        mock_check.return_value = {"installed": True, "version": "1.0.0"}
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(sample_parse_results),
            stderr="",
        )
        mock_asyncio.return_value = {
            "files_scanned": 1,
            "files_indexed": 1,
            "files_skipped": 0,
            "entities_created": 2,
            "relations_created": 2,
            "skipped_files": [],
        }

        result = runner.invoke(main, ["index", str(tmp_path)])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert data["data"]["files_scanned"] == 1
        assert data["data"]["entities_created"] == 2
        assert data["data"]["relations_created"] == 2


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

    @patch("loomgraph.cli.main.asyncio.run")
    def test_search_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic search command."""
        mock_run.return_value = {
            "query": "user login",
            "mode": "hybrid",
            "response": "Found user login function",
            "references": [],
        }

        result = runner.invoke(main, ["search", "user login"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert data["data"]["query"] == "user login"
        assert data["data"]["mode"] == "hybrid"

    @patch("loomgraph.cli.main.asyncio.run")
    def test_search_with_options(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test search with options."""
        mock_run.return_value = {
            "query": "authentication",
            "mode": "local",
            "response": "Authentication methods found",
            "references": [],
        }

        result = runner.invoke(
            main, ["search", "authentication", "--mode", "local", "--limit", "5"]
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["data"]["mode"] == "local"


class TestGraphCommand:
    """Tests for the graph command."""

    @patch("loomgraph.cli.main.asyncio.run")
    def test_graph_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic graph query."""
        mock_run.return_value = {
            "entity": "UserService.login",
            "callers": {"query": "...", "response": "Found callers"},
            "callees": {"query": "...", "response": "Found callees"},
            "note": "Graph traversal uses LightRAG query.",
        }

        result = runner.invoke(main, ["graph", "UserService.login"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert data["data"]["entity"] == "UserService.login"
        assert "callers" in data["data"]
        assert "callees" in data["data"]

    @patch("loomgraph.cli.main.asyncio.run")
    def test_graph_callers_only(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test graph query for callers only."""
        mock_run.return_value = {
            "entity": "func",
            "callers": {"query": "...", "response": "Found callers"},
            "note": "Graph traversal uses LightRAG query.",
        }

        result = runner.invoke(
            main, ["graph", "func", "--direction", "callers"]
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "callers" in data["data"]
        assert "callees" not in data["data"]

    @patch("loomgraph.cli.main.asyncio.run")
    def test_graph_with_relation_type(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test graph query with relation type filter."""
        mock_run.return_value = {
            "entity": "MyClass",
            "callers": {"query": "...", "response": ""},
            "callees": {"query": "...", "response": ""},
            "note": "Graph traversal uses LightRAG query.",
        }

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

    @patch("httpx.Client")
    def test_check_lightrag_api_connected(self, mock_client_class: MagicMock) -> None:
        """Test LightRAG API check when connected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "core_version": "1.4.9",
        }
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        from loomgraph.core.config import get_settings
        settings = get_settings()
        result = check_lightrag_api(settings)

        assert result["connected"] is True
        assert result["status"] == "healthy"

    @patch("httpx.Client")
    def test_check_lightrag_api_error(self, mock_client_class: MagicMock) -> None:
        """Test LightRAG API check when connection fails."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        from loomgraph.core.config import get_settings
        settings = get_settings()
        result = check_lightrag_api(settings)

        assert result["connected"] is False
        assert "error" in result


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


class TestDepsCommand:
    """Tests for the deps command."""

    @patch("loomgraph.cli.main.asyncio.run")
    def test_deps_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic deps command."""
        mock_run.return_value = {
            "modules": ["src/cli", "src/core"],
            "dependencies": [
                {"from": "src/cli", "to": "src/core", "count": 15, "types": {"CALLS": 8, "IMPORTS": 7}},
            ],
            "stats": {"total_modules": 2, "total_dependencies": 1, "total_entities": 150, "total_relations": 574},
        }

        result = runner.invoke(main, ["deps"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert "src/cli" in data["data"]["modules"]
        assert len(data["data"]["dependencies"]) == 1

    @patch("loomgraph.cli.main.asyncio.run")
    def test_deps_with_depth(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test deps command with --depth option."""
        mock_run.return_value = {
            "modules": ["src"],
            "dependencies": [],
            "stats": {"total_modules": 1, "total_dependencies": 0, "total_entities": 10, "total_relations": 5},
        }

        result = runner.invoke(main, ["deps", "--depth", "1"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True

    @patch("loomgraph.cli.main.asyncio.run")
    def test_deps_error(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test deps command error handling."""
        mock_run.side_effect = Exception("Connection refused")

        result = runner.invoke(main, ["deps"])
        assert result.exit_code == 1

        data = json.loads(result.output)
        assert data["success"] is False
        assert "Connection refused" in data["error"]["message"]

    def test_deps_help(self, runner: CliRunner) -> None:
        """Test deps command help."""
        result = runner.invoke(main, ["deps", "--help"])
        assert result.exit_code == 0
        assert "--depth" in result.output


class TestOverviewCommand:
    """Tests for the overview command."""

    @patch("loomgraph.cli.main.asyncio.run")
    def test_overview_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic overview command."""
        mock_run.return_value = {
            "modules": [
                {
                    "name": "src/core",
                    "entity_count": 50,
                    "entities_by_type": {"class": 5, "function": 20},
                    "top_entities": ["LightRAGClient"],
                    "files": ["lightrag_client.py"],
                    "summary": "Core engine module",
                },
            ],
            "dependency_graph": {
                "modules": ["src/core"],
                "dependencies": [],
                "stats": {"total_modules": 1, "total_dependencies": 0, "total_entities": 50, "total_relations": 100},
            },
        }

        result = runner.invoke(main, ["overview"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True
        assert len(data["data"]["modules"]) == 1
        assert data["data"]["modules"][0]["name"] == "src/core"

    @patch("loomgraph.cli.main.asyncio.run")
    def test_overview_no_summary(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test overview with --no-summary flag."""
        mock_run.return_value = {
            "modules": [],
            "dependency_graph": {
                "modules": [],
                "dependencies": [],
                "stats": {"total_modules": 0, "total_dependencies": 0, "total_entities": 0, "total_relations": 0},
            },
        }

        result = runner.invoke(main, ["overview", "--no-summary"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["success"] is True

    def test_overview_help(self, runner: CliRunner) -> None:
        """Test overview command help."""
        result = runner.invoke(main, ["overview", "--help"])
        assert result.exit_code == 0
        assert "--no-summary" in result.output
        assert "--depth" in result.output
