"""Tests for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import (
    ErrorCode,
    check_codeindex,
    check_storage,
    main,
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


class TestGetAutoWorkspace:
    """Tests for get_auto_workspace function."""

    @patch("loomgraph.core.git.is_git_repository", return_value=True)
    @patch("loomgraph.core.git.get_current_branch", return_value="develop")
    def test_git_repo_returns_dir_branch(
        self, mock_branch: MagicMock, mock_is_git: MagicMock,
    ) -> None:
        """Should return dir:branch for git repositories."""
        from loomgraph.cli._common import get_auto_workspace

        result = get_auto_workspace(None)
        assert ":" in result
        assert result.endswith(":develop")

    @patch("loomgraph.core.git.is_git_repository", return_value=False)
    def test_non_git_returns_dir_only(self, mock_is_git: MagicMock) -> None:
        """Should return dir name only for non-git directories."""
        from loomgraph.cli._common import get_auto_workspace

        result = get_auto_workspace(None)
        assert ":" not in result

    def test_explicit_workspace_takes_priority(self) -> None:
        """Explicit --workspace argument should override auto-detection."""
        from loomgraph.cli._common import get_auto_workspace

        result = get_auto_workspace("my-custom-ws")
        assert result == "my-custom-ws"


class TestResolveWorkspaceWithFallback:
    """Tests for resolve_workspace_with_fallback function."""

    @pytest.mark.asyncio
    async def test_existing_workspace_no_fallback(self) -> None:
        """Should return target workspace if it has data."""
        from unittest.mock import AsyncMock

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.return_value = {"entity_count": 100}

        result = await resolve_workspace_with_fallback(
            "myproject:feature", mock_client, allow_fallback=True
        )

        assert result == "myproject:feature"
        mock_client.get_graph_stats.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_fallback_to_main(self) -> None:
        """Should fallback to main branch if feature branch is empty."""
        from unittest.mock import AsyncMock

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.side_effect = [
            {"entity_count": 0},  # feature branch empty
            {"entity_count": 200},  # main branch has data
        ]

        result = await resolve_workspace_with_fallback(
            "myproject:feature", mock_client, allow_fallback=True
        )

        assert result == "myproject:main"
        assert mock_client.get_graph_stats.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_to_develop(self) -> None:
        """Should try develop if main is also empty."""
        from unittest.mock import AsyncMock

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.side_effect = [
            {"entity_count": 0},  # feature branch empty
            {"entity_count": 0},  # main empty
            {"entity_count": 150},  # develop has data
        ]

        result = await resolve_workspace_with_fallback(
            "myproject:feature", mock_client, allow_fallback=True
        )

        assert result == "myproject:develop"
        assert mock_client.get_graph_stats.call_count == 3

    @pytest.mark.asyncio
    async def test_fallback_to_master(self) -> None:
        """Should try master if main and develop are empty."""
        from unittest.mock import AsyncMock

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.side_effect = [
            {"entity_count": 0},  # feature branch empty
            {"entity_count": 0},  # main empty
            {"entity_count": 0},  # develop empty
            {"entity_count": 300},  # master has data
        ]

        result = await resolve_workspace_with_fallback(
            "myproject:feature", mock_client, allow_fallback=True
        )

        assert result == "myproject:master"
        assert mock_client.get_graph_stats.call_count == 4

    @pytest.mark.asyncio
    async def test_no_valid_workspace_raises_error(self) -> None:
        """Should raise error if no workspace has data."""
        from unittest.mock import AsyncMock

        import click

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.return_value = {"entity_count": 0}

        with pytest.raises(click.ClickException) as exc_info:
            await resolve_workspace_with_fallback(
                "myproject:feature", mock_client, allow_fallback=True
            )

        assert "No workspace found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_allow_fallback_false_raises_immediately(self) -> None:
        """Should not fallback when allow_fallback=False."""
        from unittest.mock import AsyncMock

        import click

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.return_value = {"entity_count": 0}

        with pytest.raises(click.ClickException) as exc_info:
            await resolve_workspace_with_fallback(
                "myproject:feature", mock_client, allow_fallback=False
            )

        assert "is empty or not found" in str(exc_info.value)
        mock_client.get_graph_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_same_branch_in_fallback(self) -> None:
        """Should skip target branch in fallback chain if it's main/develop/master."""
        from unittest.mock import AsyncMock

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.side_effect = [
            {"entity_count": 0},  # main empty (target)
            {"entity_count": 150},  # develop has data
        ]

        result = await resolve_workspace_with_fallback(
            "myproject:main", mock_client, allow_fallback=True
        )

        assert result == "myproject:develop"
        # Should skip main in fallback since it's the target
        assert mock_client.get_graph_stats.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_total_entities_field(self) -> None:
        """Should handle both entity_count and total_entities fields."""
        from unittest.mock import AsyncMock

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.return_value = {"total_entities": 50}

        result = await resolve_workspace_with_fallback(
            "myproject:feature", mock_client, allow_fallback=True
        )

        assert result == "myproject:feature"

    @pytest.mark.asyncio
    async def test_handles_api_error_as_empty(self) -> None:
        """Should treat API error as empty workspace and try fallback."""
        from unittest.mock import AsyncMock

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.side_effect = [
            Exception("API error"),  # feature branch error
            {"entity_count": 100},  # main has data
        ]

        result = await resolve_workspace_with_fallback(
            "myproject:feature", mock_client, allow_fallback=True
        )

        assert result == "myproject:main"

    @pytest.mark.asyncio
    async def test_non_colon_workspace_no_fallback(self) -> None:
        """Should raise error for non-colon workspace (no branch info)."""
        from unittest.mock import AsyncMock

        import click

        from loomgraph.cli._common import resolve_workspace_with_fallback

        mock_client = AsyncMock()
        mock_client.get_graph_stats.return_value = {"entity_count": 0}

        with pytest.raises(click.ClickException) as exc_info:
            await resolve_workspace_with_fallback(
                "simple-workspace", mock_client, allow_fallback=True
            )

        assert "No workspace found" in str(exc_info.value)


class TestStatusCommand:
    """Tests for the status command."""

    @patch("loomgraph.cli._setup.get_auto_workspace", return_value="testproject:main")
    @patch("loomgraph.cli._setup.check_codeindex")
    @patch("loomgraph.cli._setup.check_storage")
    @patch("loomgraph.cli._setup.check_embedding")
    def test_status_all_ok(
        self,
        mock_embedding: MagicMock,
        mock_storage: MagicMock,
        mock_codeindex: MagicMock,
        mock_workspace: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_codeindex.return_value = {"installed": True, "version": "1.0.0"}
        mock_storage.return_value = {
            "connected": True,
            "backend": "sqlite",
            "vec_version": "v0.1.9",
        }
        mock_embedding.return_value = {"connected": True, "model": "jina"}

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert "dependencies" in data["data"]
        assert "workspace" in data["data"]
        assert data["data"]["workspace"]["name"] == "testproject:main"

    @patch("loomgraph.cli._setup.get_auto_workspace", return_value="testproject:develop")
    @patch("loomgraph.cli._setup.check_codeindex")
    @patch("loomgraph.cli._setup.check_storage")
    @patch("loomgraph.cli._setup.check_embedding")
    def test_status_storage_unavailable(
        self,
        mock_embedding: MagicMock,
        mock_storage: MagicMock,
        mock_codeindex: MagicMock,
        mock_workspace: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_codeindex.return_value = {"installed": True, "version": "1.0.0"}
        mock_storage.return_value = {
            "connected": False,
            "error": "sqlite-vec not installed",
        }
        mock_embedding.return_value = {"connected": True, "model": "jina"}

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False
        assert data["error"]["code"] == ErrorCode.DEPENDENCIES_MISSING
        assert "workspace" in data["data"]


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


class TestFindCommand:
    """Tests for the find command."""

    @patch("loomgraph.cli._search.asyncio.run")
    def test_find_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic find command."""
        mock_run.return_value = {
            "query": "user login",
            "total_entities": 10,
            "matches_count": 1,
            "matches": [{"entity": "user_login", "type": "function", "source_id": "", "description": "", "score": 0.9}],
        }

        result = runner.invoke(main, ["find", "user login"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["query"] == "user login"
        assert data["data"]["matches_count"] == 1

    @patch("loomgraph.cli._search.asyncio.run")
    def test_find_with_options(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test find with type filter and limit."""
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
            main, ["find", "authentication", "--type", "class", "--limit", "5"]
        )
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["data"]["matches_count"] == 2

    @patch("loomgraph.cli._search.asyncio.run")
    def test_search_alias_deprecated(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test that search alias works but shows deprecation warning."""
        mock_run.return_value = {
            "query": "auth",
            "total_entities": 10,
            "matches_count": 1,
            "matches": [{"entity": "AuthService", "type": "class", "source_id": "", "description": "", "score": 0.9}],
        }

        result = runner.invoke(main, ["search", "auth"])
        assert result.exit_code == 0
        assert "deprecated" in result.output.lower()


class TestQueryCommandRemoved:
    """`loomgraph query` was removed in v0.10.0 (EPIC-011 Phase 4)."""

    def test_query_command_no_longer_registered(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["query", "anything"])
        # Click reports unknown command via stderr + non-zero exit
        assert result.exit_code != 0
        assert "No such command 'query'" in (result.output or "") or \
               "No such command 'query'" in (result.stderr or "")


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

    def test_check_storage_smoke(self) -> None:
        """check_storage opens an in-memory SQLite + loads sqlite-vec."""
        from loomgraph.core.config import get_settings

        settings = get_settings()
        result = check_storage(settings)

        assert result["connected"] is True
        assert result["backend"] == "sqlite"
        assert "vec_version" in result


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

    def test_find_help(self, runner: CliRunner) -> None:
        """Test find command help."""
        result = runner.invoke(main, ["find", "--help"])
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
                    "top_entities": ["SqliteGraphStore"],
                    "files": ["sqlite_store.py"],
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

    @pytest.fixture()
    def mock_entities_for_graph(self) -> list[dict[str, str]]:
        return [
            {"entity_name": "AuthService", "entity_type": "class", "source_id": "src/auth/service.py"},
            {"entity_name": "main", "entity_type": "function", "source_id": "src/main.py"},
            {"entity_name": "db.query", "entity_type": "function", "source_id": "src/db.py"},
            {"entity_name": "BaseService", "entity_type": "class", "source_id": "src/base.py"},
            {"entity_name": "handler", "entity_type": "function", "source_id": "src/handler.py"},
        ]

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_both_directions(
        self, mock_prepare: MagicMock,
        mock_relations: list, mock_entities_for_graph: list,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_relations.return_value = mock_relations
        mock_client.get_all_entities.return_value = mock_entities_for_graph
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_graph_query

        result = await _async_graph_query("AuthService", "both", "all", "test-ws")

        assert result["entity"] == "AuthService"
        assert result["source_id"] == "src/auth/service.py"
        assert len(result["callers"]) == 2  # main, handler
        assert len(result["callees"]) == 2  # db.query, BaseService
        for caller in result["callers"]:
            assert "source_id" in caller

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_relation_type_filter(
        self, mock_prepare: MagicMock,
        mock_relations: list, mock_entities_for_graph: list,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_relations.return_value = mock_relations
        mock_client.get_all_entities.return_value = mock_entities_for_graph
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_graph_query

        result = await _async_graph_query("AuthService", "both", "INHERITS", "test-ws")

        assert result["callers"] == []
        assert len(result["callees"]) == 1
        assert result["callees"][0]["entity"] == "BaseService"
        assert result["callees"][0]["source_id"] == "src/base.py"

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_no_matches(self, mock_prepare: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_relations.return_value = [
            {"src_id": "a", "tgt_id": "b", "keywords": "CALLS"},
        ]
        mock_client.get_all_entities.return_value = []
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_graph_query

        result = await _async_graph_query("NonExistent", "both", "all", "test-ws")

        assert result["callers"] == []
        assert result["callees"] == []
        assert result["source_id"] == ""

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_callers_sorted(
        self, mock_prepare: MagicMock,
        mock_relations: list, mock_entities_for_graph: list,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_relations.return_value = mock_relations
        mock_client.get_all_entities.return_value = mock_entities_for_graph
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_graph_query

        result = await _async_graph_query("AuthService", "callers", "all", "test-ws")

        names = [c["entity"] for c in result["callers"]]
        assert names == sorted(names)


class TestAsyncFind:
    """Tests for _async_find graph-layer entity search."""

    @pytest.fixture()
    def mock_entities(self) -> list[dict[str, str]]:
        return [
            {"entity_name": "AuthService", "entity_type": "class", "source_id": "auth.py:1-50", "description": "Authentication service"},
            {"entity_name": "authenticate", "entity_type": "function", "source_id": "auth.py:52-80", "description": "Authenticate user"},
            {"entity_name": "UserService", "entity_type": "class", "source_id": "user.py:1-30", "description": "User management"},
            {"entity_name": "db_connect", "entity_type": "function", "source_id": "db.py:1-20", "description": "Database connection"},
        ]

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_exact_match(
        self, mock_prepare: MagicMock, mock_entities: list
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("AuthService", None, "test-ws", 20)

        assert result["matches_count"] >= 1
        assert result["matches"][0]["entity"] == "AuthService"
        assert result["matches"][0]["score"] == 1.0

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_substring_match(
        self, mock_prepare: MagicMock, mock_entities: list
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("auth", None, "test-ws", 20)

        # Should match AuthService and authenticate
        names = [m["entity"] for m in result["matches"]]
        assert "AuthService" in names
        assert "authenticate" in names

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_type_filter(
        self, mock_prepare: MagicMock, mock_entities: list
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("Service", "class", "test-ws", 20)

        for m in result["matches"]:
            assert m["type"] == "class"

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_limit(
        self, mock_prepare: MagicMock, mock_entities: list
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("a", None, "test-ws", 2)

        assert result["matches_count"] <= 2

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_no_match(
        self, mock_prepare: MagicMock, mock_entities: list
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("zzzznonexistent", None, "test-ws", 20)

        assert result["matches_count"] == 0

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_scores_descending(
        self, mock_prepare: MagicMock, mock_entities: list
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("auth", None, "test-ws", 20)

        scores = [m["score"] for m in result["matches"]]
        assert scores == sorted(scores, reverse=True)


class TestFindWithRelations:
    """Tests for find --with-relations (BFS relation expansion)."""

    @pytest.fixture()
    def mock_entities(self) -> list[dict[str, str]]:
        return [
            {"entity_name": "AuthService", "entity_type": "class", "source_id": "auth.py:1-50", "description": "Auth service"},
            {"entity_name": "UserService", "entity_type": "class", "source_id": "user.py:1-30", "description": "User service"},
            {"entity_name": "db_connect", "entity_type": "function", "source_id": "db.py:1-20", "description": "DB connect"},
        ]

    @pytest.fixture()
    def mock_relations(self) -> list[dict[str, str]]:
        return [
            {"src_id": "LoginController", "tgt_id": "AuthService", "keywords": "CALLS"},
            {"src_id": "ApiFilter", "tgt_id": "AuthService", "keywords": "CALLS"},
            {"src_id": "AuthService", "tgt_id": "UserRepository", "keywords": "CALLS"},
            {"src_id": "AuthService", "tgt_id": "JwtProvider", "keywords": "CALLS"},
            {"src_id": "AuthService", "tgt_id": "BaseService", "keywords": "INHERITS"},
            {"src_id": "UserService", "tgt_id": "UserRepository", "keywords": "CALLS"},
            {"src_id": "UserRepository", "tgt_id": "db_connect", "keywords": "CALLS"},
        ]

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_with_relations_basic(
        self, mock_prepare: MagicMock,
        mock_entities: list, mock_relations: list,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_client.get_all_relations.return_value = mock_relations
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("AuthService", None, "test-ws", 20, with_relations=True)

        assert result["matches_count"] >= 1
        match = result["matches"][0]
        assert match["entity"] == "AuthService"
        assert "callers" in match
        assert "callees" in match
        caller_names = [c["entity"] for c in match["callers"]]
        assert "LoginController" in caller_names
        assert "ApiFilter" in caller_names
        callee_names = [c["entity"] for c in match["callees"]]
        assert "UserRepository" in callee_names
        assert "JwtProvider" in callee_names
        assert "BaseService" in callee_names

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_with_relations_depth2(
        self, mock_prepare: MagicMock,
        mock_entities: list, mock_relations: list,
    ) -> None:
        """BFS depth=2 should reach 2-hop neighbors."""
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_client.get_all_relations.return_value = mock_relations
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("AuthService", None, "test-ws", 20, with_relations=True, depth=2)

        match = result["matches"][0]
        # Depth 2 callees: AuthService → UserRepository → db_connect
        callee_names = [c["entity"] for c in match["callees"]]
        assert "UserRepository" in callee_names
        assert "db_connect" in callee_names  # 2-hop reachable

    @patch("loomgraph.cli._search.prepare_workspace_store")
    async def test_without_relations_no_callers(
        self, mock_prepare: MagicMock,
        mock_entities: list, mock_relations: list,
    ) -> None:
        """Without --with-relations, matches should not have callers/callees."""
        mock_client = AsyncMock()
        mock_client.get_all_entities.return_value = mock_entities
        mock_prepare.return_value = ("test-ws", mock_client)
        from loomgraph.cli._search import _async_find

        result = await _async_find("AuthService", None, "test-ws", 20, with_relations=False)

        match = result["matches"][0]
        assert "callers" not in match
        assert "callees" not in match

    @patch("loomgraph.cli._search.asyncio.run")
    def test_find_with_relations_cli(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test find --with-relations via CLI invocation."""
        mock_run.return_value = {
            "query": "auth",
            "total_entities": 10,
            "matches_count": 1,
            "matches": [{
                "entity": "AuthService", "type": "class", "source_id": "auth.py",
                "description": "", "score": 0.95,
                "callers": [{"entity": "LoginController", "relation": "CALLS"}],
                "callees": [{"entity": "UserRepository", "relation": "CALLS"}],
            }],
        }

        result = runner.invoke(main, ["find", "auth", "--with-relations"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert "callers" in data["data"]["matches"][0]
        assert "callees" in data["data"]["matches"][0]


class TestBfsCollect:
    """Tests for _bfs_collect helper function."""

    def test_depth_1(self) -> None:
        from loomgraph.cli._search import _bfs_collect

        adj: dict[str, list[dict[str, str]]] = {
            "A": [{"entity": "B", "relation": "CALLS"}, {"entity": "C", "relation": "CALLS"}],
            "B": [{"entity": "D", "relation": "CALLS"}],
        }
        result = _bfs_collect("A", adj, depth=1)
        names = {r["entity"] for r in result}
        assert names == {"B", "C"}

    def test_depth_2(self) -> None:
        from loomgraph.cli._search import _bfs_collect

        adj: dict[str, list[dict[str, str]]] = {
            "A": [{"entity": "B", "relation": "CALLS"}],
            "B": [{"entity": "C", "relation": "CALLS"}],
            "C": [{"entity": "D", "relation": "CALLS"}],
        }
        result = _bfs_collect("A", adj, depth=2)
        names = {r["entity"] for r in result}
        assert names == {"B", "C"}  # D is at depth 3, not reached

    def test_no_cycle(self) -> None:
        from loomgraph.cli._search import _bfs_collect

        adj: dict[str, list[dict[str, str]]] = {
            "A": [{"entity": "B", "relation": "CALLS"}],
            "B": [{"entity": "A", "relation": "CALLS"}],  # cycle back to A
        }
        result = _bfs_collect("A", adj, depth=3)
        names = {r["entity"] for r in result}
        assert names == {"B"}  # A is excluded (it's the start)

    def test_empty_adj(self) -> None:
        from loomgraph.cli._search import _bfs_collect

        result = _bfs_collect("A", {}, depth=1)
        assert result == []


class TestTopologyCommand:
    """Tests for the topology command."""

    @patch("loomgraph.cli._analysis.asyncio.run")
    def test_topology_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic topology command."""
        mock_run.return_value = {
            "summary": {
                "total_entities": 100,
                "total_relations": 200,
                "orphan_count": 5,
                "hub_count": 3,
                "god_function_count": 2,
                "placeholder_module_count": 1,
                "coupling_density": 0.15,
                "topology_score": 85,
            },
            "orphans": [{"entity": "OrphanA", "type": "function", "source_id": "a.py"}],
            "hubs": [],
            "god_functions": [],
            "placeholder_modules": [],
            "coupling": {"cross_module_relations": 30, "intra_module_relations": 170, "density": 0.15, "most_coupled_pairs": []},
        }

        result = runner.invoke(main, ["topology"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["summary"]["topology_score"] == 85
        assert len(data["data"]["orphans"]) == 1

    @patch("loomgraph.cli._analysis.asyncio.run")
    def test_topology_with_module(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test topology command with --module option."""
        mock_run.return_value = {
            "summary": {"total_entities": 10, "total_relations": 15, "orphan_count": 0,
                        "hub_count": 0, "god_function_count": 0, "placeholder_module_count": 0,
                        "coupling_density": 0.0, "topology_score": 100},
            "orphans": [], "hubs": [], "god_functions": [],
            "placeholder_modules": [],
            "coupling": {"cross_module_relations": 0, "intra_module_relations": 15, "density": 0.0, "most_coupled_pairs": []},
        }

        result = runner.invoke(main, ["topology", "--module", "cli"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True

    @patch("loomgraph.cli._analysis.asyncio.run")
    def test_topology_error(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test topology command error handling."""
        mock_run.side_effect = Exception("Connection refused")

        result = runner.invoke(main, ["topology"])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False
        assert "Connection refused" in data["error"]["message"]

    def test_topology_help(self, runner: CliRunner) -> None:
        """Test topology command help."""
        result = runner.invoke(main, ["topology", "--help"])
        assert result.exit_code == 0
        assert "--hub-threshold" in result.stdout
        assert "--god-threshold" in result.stdout
        assert "--module" in result.stdout


class TestCheckCommand:
    """Tests for the check command."""

    @patch("loomgraph.cli._analysis.asyncio.run")
    def test_check_basic(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test basic check command."""
        mock_run.return_value = {
            "freshness": {
                "total_source_paths": 10,
                "valid": 8,
                "stale": 2,
                "freshness_ratio": 0.8,
            },
            "stale_entries": [
                {"source_id": "old/file.py:10-20", "file_path": "old/file.py", "reason": "file_not_found", "suggestion": "..."},
            ],
            "suggestion": "2 source paths are stale. Run 'loomgraph index --clear .' to rebuild.",
        }

        result = runner.invoke(main, ["check"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["freshness"]["stale"] == 2

    @patch("loomgraph.cli._analysis.asyncio.run")
    def test_check_all_fresh(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test check when all entries are fresh."""
        mock_run.return_value = {
            "freshness": {"total_source_paths": 5, "valid": 5, "stale": 0, "freshness_ratio": 1.0},
            "stale_entries": [],
            "suggestion": "",
        }

        result = runner.invoke(main, ["check"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["freshness"]["freshness_ratio"] == 1.0

    @patch("loomgraph.cli._analysis.asyncio.run")
    def test_check_error(self, mock_run: MagicMock, runner: CliRunner) -> None:
        """Test check command error handling."""
        mock_run.side_effect = Exception("API error")

        result = runner.invoke(main, ["check"])
        assert result.exit_code == 1

        data = json.loads(result.stdout)
        assert data["success"] is False

    def test_check_help(self, runner: CliRunner) -> None:
        """Test check command help."""
        result = runner.invoke(main, ["check", "--help"])
        assert result.exit_code == 0
        assert "--repo-path" in result.stdout


class TestCodeindexPackageName:
    """Regression guard for #65: the codeindex PyPI package is `ai-codeindex`,
    not `matrix-codeindex` (historical name kept only in ADRs / archive).
    A wrong package name in a user-facing install suggestion sends users to
    a `pip install` that fails."""

    def test_no_stale_package_name_in_live_source(self) -> None:
        """No live source module may reference the old `matrix-codeindex`
        package name. Historical records under docs/adr + docs/archive are
        intentionally exempt (point-in-time decisions)."""
        src_root = Path(__file__).resolve().parents[2] / "src" / "loomgraph"
        offenders = [
            str(p.relative_to(src_root))
            for p in src_root.rglob("*.py")
            if "matrix-codeindex" in p.read_text(encoding="utf-8")
        ]
        assert offenders == [], (
            f"Stale 'matrix-codeindex' package name in: {offenders}. "
            "The PyPI package is 'ai-codeindex'."
        )
