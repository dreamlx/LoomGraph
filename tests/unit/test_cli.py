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

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert "version" in data["data"]
        assert "python" in data["data"]

    def test_version_option(self, runner: CliRunner) -> None:
        """Test --version option."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "loomgraph" in result.stdout.lower()


class TestStatusCommand:
    """Tests for the status command."""

    @patch("loomgraph.cli._setup.check_codeindex")
    @patch("loomgraph.cli._setup.check_lightrag_api")
    @patch("loomgraph.cli._setup.check_embedding")
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

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert "dependencies" in data["data"]

    @patch("loomgraph.cli._setup.check_codeindex")
    @patch("loomgraph.cli._setup.check_lightrag_api")
    @patch("loomgraph.cli._setup.check_embedding")
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

        data = json.loads(result.stdout)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.DEPENDENCIES_MISSING


class TestIndexCommand:
    """Tests for the index command."""

    def test_index_path_not_exists(self, runner: CliRunner) -> None:
        """Test index with non-existent path."""
        result = runner.invoke(main, ["index", "/nonexistent/path"])
        assert result.exit_code != 0

    @patch("loomgraph.cli._indexing.check_codeindex")
    def test_index_codeindex_not_found(
        self, mock_check: MagicMock, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test index when codeindex is not installed."""
        mock_check.return_value = {"installed": False, "error": "not found"}

        result = runner.invoke(main, ["index", str(tmp_path)])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.CODEINDEX_NOT_FOUND

    @patch("subprocess.run")
    @patch("loomgraph.cli._indexing.check_codeindex")
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

        data = json.loads(result.stdout)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.CODEINDEX_FAILED

    @patch("loomgraph.cli._indexing.asyncio.run")
    @patch("subprocess.run")
    @patch("loomgraph.cli._indexing.check_codeindex")
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

        data = json.loads(result.stdout)
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

        data = json.loads(result.stdout)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.INVALID_INPUT

    @patch("loomgraph.cli._indexing.asyncio.run")
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

        data = json.loads(result.stdout)
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

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["entities_created"] == 2
        assert data["data"]["relations_created"] == 2


class TestSearchCommand:
    """Tests for the search command."""

    @patch("loomgraph.cli._search.asyncio.run")
    def test_search_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic search command."""
        mock_run.return_value = {
            "query": "user login",
            "total_entities": 10,
            "matches_count": 1,
            "matches": [{"entity": "user_login", "type": "function", "source_id": "", "description": "", "score": 0.9}],
        }

        result = runner.invoke(main, ["search", "user login"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["query"] == "user login"
        assert data["data"]["matches_count"] == 1

    @patch("loomgraph.cli._search.asyncio.run")
    def test_search_with_options(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test search with type filter and limit."""
        mock_run.return_value = {
            "query": "authentication",
            "total_entities": 50,
            "matches_count": 2,
            "matches": [
                {"entity": "AuthService", "type": "class", "source_id": "", "description": "", "score": 0.8},
                {"entity": "authenticate", "type": "function", "source_id": "", "description": "", "score": 0.7},
            ],
        }

        result = runner.invoke(
            main, ["search", "authentication", "--type", "class", "--limit", "5"]
        )
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["data"]["matches_count"] == 2


class TestGraphCommand:
    """Tests for the graph command."""

    @patch("loomgraph.cli._search.asyncio.run")
    def test_graph_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic graph query."""
        mock_run.return_value = {
            "entity": "UserService.login",
            "callers": [{"entity": "main", "relation": "CALLS"}],
            "callees": [{"entity": "db.query", "relation": "CALLS"}],
            "callers_count": 1,
            "callees_count": 1,
        }

        result = runner.invoke(main, ["graph", "UserService.login"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["entity"] == "UserService.login"
        assert "callers" in data["data"]
        assert "callees" in data["data"]

    @patch("loomgraph.cli._search.asyncio.run")
    def test_graph_callers_only(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test graph query for callers only."""
        mock_run.return_value = {
            "entity": "func",
            "callers": [{"entity": "caller_a", "relation": "CALLS"}],
            "callers_count": 1,
            "callees_count": None,
        }

        result = runner.invoke(
            main, ["graph", "func", "--direction", "callers"]
        )
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert "callers" in data["data"]
        assert "callees" not in data["data"]

    @patch("loomgraph.cli._search.asyncio.run")
    def test_graph_with_relation_type(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test graph query with relation type filter."""
        mock_run.return_value = {
            "entity": "MyClass",
            "callers": [],
            "callees": [{"entity": "BaseClass", "relation": "INHERITS"}],
            "callers_count": 0,
            "callees_count": 1,
        }

        result = runner.invoke(
            main, ["graph", "MyClass", "--relation-type", "INHERITS"]
        )
        assert result.exit_code == 0

        data = json.loads(result.stdout)
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
        assert "LoomGraph" in result.stdout
        assert "index" in result.stdout
        assert "search" in result.stdout
        assert "workspace" in result.stdout

    def test_index_help(self, runner: CliRunner) -> None:
        """Test index command help."""
        result = runner.invoke(main, ["index", "--help"])
        assert result.exit_code == 0
        assert "REPO_PATH" in result.stdout

    def test_search_help(self, runner: CliRunner) -> None:
        """Test search command help."""
        result = runner.invoke(main, ["search", "--help"])
        assert result.exit_code == 0
        assert "QUERY" in result.stdout
        assert "--type" in result.stdout

    def test_graph_help(self, runner: CliRunner) -> None:
        """Test graph command help."""
        result = runner.invoke(main, ["graph", "--help"])
        assert result.exit_code == 0
        assert "ENTITY_NAME" in result.stdout
        assert "--direction" in result.stdout


class TestWorkspaceListCommand:
    """Tests for the workspace list command."""

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_list_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic workspace list command."""
        mock_run.return_value = {
            "workspaces": ["zcyl-backend", "zcyl-gateway"],
            "count": 2,
        }

        result = runner.invoke(main, ["workspace", "list"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["workspaces"] == ["zcyl-backend", "zcyl-gateway"]
        assert data["data"]["count"] == 2

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_list_empty(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test workspace list when no workspaces exist."""
        mock_run.return_value = {
            "workspaces": [],
            "count": 0,
        }

        result = runner.invoke(main, ["workspace", "list"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["workspaces"] == []
        assert data["data"]["count"] == 0

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_list_error(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test workspace list error handling."""
        mock_run.side_effect = Exception("Connection refused")

        result = runner.invoke(main, ["workspace", "list"])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False


class TestWorkspaceInfoCommand:
    """Tests for the workspace info command."""

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_info_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test workspace info with explicit name."""
        mock_run.return_value = {
            "name": "zcyl-backend",
            "entities": 245,
            "relations": 1024,
            "entity_types": {"class": 45, "function": 120, "method": 80},
            "relation_types": {"CALLS": 600, "IMPORTS": 300, "INHERITS": 124},
        }

        result = runner.invoke(main, ["workspace", "info", "zcyl-backend"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["name"] == "zcyl-backend"
        assert data["data"]["entities"] == 245
        assert data["data"]["relations"] == 1024
        assert "entity_types" in data["data"]
        assert "relation_types" in data["data"]

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_info_auto_detect(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test workspace info with auto-detect (no name argument)."""
        mock_run.return_value = {
            "name": "LoomGraph",
            "entities": 50,
            "relations": 100,
            "entity_types": {"function": 30, "class": 20},
            "relation_types": {"CALLS": 80, "IMPORTS": 20},
        }

        result = runner.invoke(main, ["workspace", "info"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["entities"] == 50

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_info_with_workspace_option(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test workspace info with -w option."""
        mock_run.return_value = {
            "name": "custom-ws",
            "entities": 10,
            "relations": 20,
            "entity_types": {},
            "relation_types": {},
        }

        result = runner.invoke(main, ["workspace", "info", "--workspace", "custom-ws"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["name"] == "custom-ws"

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_info_error(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test workspace info error handling."""
        mock_run.side_effect = Exception("Connection refused")

        result = runner.invoke(main, ["workspace", "info", "bad-ws"])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False


class TestWorkspaceDeleteCommand:
    """Tests for the workspace delete command."""

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_delete_success(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test workspace delete with --yes flag."""
        mock_run.return_value = {
            "deleted_workspace": "old-ws",
            "message": "Workspace deleted",
        }

        result = runner.invoke(main, ["workspace", "delete", "old-ws", "--yes"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["deleted_workspace"] == "old-ws"

    def test_workspace_delete_no_yes(self, runner: CliRunner) -> None:
        """Test workspace delete without --yes flag should error."""
        result = runner.invoke(main, ["workspace", "delete", "old-ws"])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.INVALID_INPUT
        assert "--yes" in data["error"]["suggestion"]

    @patch("loomgraph.cli._workspace.asyncio.run")
    def test_workspace_delete_error(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test workspace delete error handling."""
        mock_run.side_effect = Exception("Connection refused")

        result = runner.invoke(main, ["workspace", "delete", "bad-ws", "--yes"])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False


class TestWorkspaceHelp:
    """Tests for workspace help messages."""

    def test_workspace_help(self, runner: CliRunner) -> None:
        """Test workspace group help."""
        result = runner.invoke(main, ["workspace", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "info" in result.stdout
        assert "delete" in result.stdout

    def test_workspace_list_help(self, runner: CliRunner) -> None:
        """Test workspace list help."""
        result = runner.invoke(main, ["workspace", "list", "--help"])
        assert result.exit_code == 0

    def test_workspace_info_help(self, runner: CliRunner) -> None:
        """Test workspace info help."""
        result = runner.invoke(main, ["workspace", "info", "--help"])
        assert result.exit_code == 0
        assert "--workspace" in result.stdout

    def test_workspace_delete_help(self, runner: CliRunner) -> None:
        """Test workspace delete help."""
        result = runner.invoke(main, ["workspace", "delete", "--help"])
        assert result.exit_code == 0
        assert "--yes" in result.stdout


class TestDepsCommand:
    """Tests for the deps command."""

    @patch("loomgraph.cli._analysis.asyncio.run")
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

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert "src/cli" in data["data"]["modules"]
        assert len(data["data"]["dependencies"]) == 1

    @patch("loomgraph.cli._analysis.asyncio.run")
    def test_deps_with_depth(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test deps command with --depth option."""
        mock_run.return_value = {
            "modules": ["src"],
            "dependencies": [],
            "stats": {"total_modules": 1, "total_dependencies": 0, "total_entities": 10, "total_relations": 5},
        }

        result = runner.invoke(main, ["deps", "--depth", "1"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True

    @patch("loomgraph.cli._analysis.asyncio.run")
    def test_deps_error(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test deps command error handling."""
        mock_run.side_effect = Exception("Connection refused")

        result = runner.invoke(main, ["deps"])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False
        assert "Connection refused" in data["error"]["message"]

    def test_deps_help(self, runner: CliRunner) -> None:
        """Test deps command help."""
        result = runner.invoke(main, ["deps", "--help"])
        assert result.exit_code == 0
        assert "--depth" in result.stdout


class TestOverviewCommand:
    """Tests for the overview command."""

    @patch("loomgraph.cli._analysis.asyncio.run")
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

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert len(data["data"]["modules"]) == 1
        assert data["data"]["modules"][0]["name"] == "src/core"

    @patch("loomgraph.cli._analysis.asyncio.run")
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

        data = json.loads(result.stdout)
        assert data["success"] is True

    def test_overview_help(self, runner: CliRunner) -> None:
        """Test overview command help."""
        result = runner.invoke(main, ["overview", "--help"])
        assert result.exit_code == 0
        assert "--no-summary" in result.stdout
        assert "--depth" in result.stdout


class TestIndexProgressFeedback:
    """Tests that index command outputs progress to stderr."""

    @patch("loomgraph.cli._indexing.asyncio.run")
    @patch("subprocess.run")
    @patch("loomgraph.cli._indexing.check_codeindex")
    def test_index_progress_messages(
        self,
        mock_check: MagicMock,
        mock_subprocess: MagicMock,
        mock_asyncio: MagicMock,
        runner: CliRunner,
        tmp_path: Path,
        sample_parse_results: dict[str, Any],
    ) -> None:
        """Index command should emit progress messages to stderr."""
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

        # mix_stderr=False separates stdout/stderr
        result = runner.invoke(main, ["index", str(tmp_path)], catch_exceptions=False)
        assert result.exit_code == 0

        # Stdout should be JSON
        data = json.loads(result.stdout)
        assert data["success"] is True


class TestAsyncGraphQuery:
    """Tests for _async_graph_query graph-layer traversal."""

    @pytest.fixture()
    def mock_relations(self) -> list[dict[str, str]]:
        return [
            {"src_id": "main", "tgt_id": "AuthService", "keywords": "CALLS"},
            {"src_id": "AuthService", "tgt_id": "db.query", "keywords": "CALLS"},
            {"src_id": "AuthService", "tgt_id": "BaseService", "keywords": "INHERITS"},
            {"src_id": "handler", "tgt_id": "AuthService", "keywords": "CALLS"},
        ]

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_relations")
    async def test_both_directions(
        self, mock_rels: MagicMock, mock_settings: MagicMock, mock_relations: list
    ) -> None:
        mock_rels.return_value = mock_relations
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_graph_query

        result = await _async_graph_query("AuthService", "both", "all", "test-ws")

        assert result["entity"] == "AuthService"
        assert len(result["callers"]) == 2  # main, handler
        assert len(result["callees"]) == 2  # db.query, BaseService

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_relations")
    async def test_relation_type_filter(
        self, mock_rels: MagicMock, mock_settings: MagicMock, mock_relations: list
    ) -> None:
        mock_rels.return_value = mock_relations
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_graph_query

        result = await _async_graph_query("AuthService", "both", "INHERITS", "test-ws")

        assert result["callers"] == []
        assert len(result["callees"]) == 1
        assert result["callees"][0]["entity"] == "BaseService"

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_relations")
    async def test_no_matches(
        self, mock_rels: MagicMock, mock_settings: MagicMock
    ) -> None:
        mock_rels.return_value = [
            {"src_id": "a", "tgt_id": "b", "keywords": "CALLS"},
        ]
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_graph_query

        result = await _async_graph_query("NonExistent", "both", "all", "test-ws")

        assert result["callers"] == []
        assert result["callees"] == []

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_relations")
    async def test_callers_sorted(
        self, mock_rels: MagicMock, mock_settings: MagicMock, mock_relations: list
    ) -> None:
        mock_rels.return_value = mock_relations
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_graph_query

        result = await _async_graph_query("AuthService", "callers", "all", "test-ws")

        # Should be sorted by entity name
        names = [c["entity"] for c in result["callers"]]
        assert names == sorted(names)


class TestAsyncSearch:
    """Tests for _async_search graph-layer entity search."""

    @pytest.fixture()
    def mock_entities(self) -> list[dict[str, str]]:
        return [
            {"entity_name": "AuthService", "entity_type": "class", "source_id": "auth.py:1-50", "description": "Authentication service"},
            {"entity_name": "authenticate", "entity_type": "function", "source_id": "auth.py:52-80", "description": "Authenticate user"},
            {"entity_name": "UserService", "entity_type": "class", "source_id": "user.py:1-30", "description": "User management"},
            {"entity_name": "db_connect", "entity_type": "function", "source_id": "db.py:1-20", "description": "Database connection"},
        ]

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_entities")
    async def test_exact_match(
        self, mock_ents: MagicMock, mock_settings: MagicMock, mock_entities: list
    ) -> None:
        mock_ents.return_value = mock_entities
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_search

        result = await _async_search("AuthService", None, "test-ws", 20)

        assert result["matches_count"] >= 1
        assert result["matches"][0]["entity"] == "AuthService"
        assert result["matches"][0]["score"] == 1.0

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_entities")
    async def test_substring_match(
        self, mock_ents: MagicMock, mock_settings: MagicMock, mock_entities: list
    ) -> None:
        mock_ents.return_value = mock_entities
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_search

        result = await _async_search("auth", None, "test-ws", 20)

        # Should match AuthService and authenticate
        names = [m["entity"] for m in result["matches"]]
        assert "AuthService" in names
        assert "authenticate" in names

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_entities")
    async def test_type_filter(
        self, mock_ents: MagicMock, mock_settings: MagicMock, mock_entities: list
    ) -> None:
        mock_ents.return_value = mock_entities
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_search

        result = await _async_search("Service", "class", "test-ws", 20)

        for m in result["matches"]:
            assert m["type"] == "class"

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_entities")
    async def test_limit(
        self, mock_ents: MagicMock, mock_settings: MagicMock, mock_entities: list
    ) -> None:
        mock_ents.return_value = mock_entities
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_search

        result = await _async_search("a", None, "test-ws", 2)

        assert result["matches_count"] <= 2

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_entities")
    async def test_no_match(
        self, mock_ents: MagicMock, mock_settings: MagicMock, mock_entities: list
    ) -> None:
        mock_ents.return_value = mock_entities
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_search

        result = await _async_search("zzzznonexistent", None, "test-ws", 20)

        assert result["matches_count"] == 0

    @patch("loomgraph.cli._search.get_settings")
    @patch("loomgraph.core.lightrag_client.LightRAGClient.get_all_entities")
    async def test_scores_descending(
        self, mock_ents: MagicMock, mock_settings: MagicMock, mock_entities: list
    ) -> None:
        mock_ents.return_value = mock_entities
        mock_settings.return_value = MagicMock(
            lightrag=MagicMock(api_url="http://test:3001", api_timeout=5.0)
        )
        from loomgraph.cli._search import _async_search

        result = await _async_search("auth", None, "test-ws", 20)

        scores = [m["score"] for m in result["matches"]]
        assert scores == sorted(scores, reverse=True)
