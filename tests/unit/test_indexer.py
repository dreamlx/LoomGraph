"""Unit tests for the indexer module."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from loomgraph.core.indexer import index_file, index_repository, scan_code_files
from loomgraph.core.models import ParseResult, Symbol
from loomgraph.embedding.base import EmbeddingResult


@pytest.fixture
def temp_repo() -> Path:
    """Create a temporary repository structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # Create Python files
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("def main(): pass")
        (repo / "src" / "utils.py").write_text("def helper(): pass")

        # Create JS file
        (repo / "src" / "index.js").write_text("function init() {}")

        # Create a file to skip
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "pkg.js").write_text("// skip me")

        # Create non-code file
        (repo / "README.md").write_text("# Readme")

        yield repo


@pytest.fixture
def mock_rag() -> MagicMock:
    """Create mock LightRAG instance."""
    rag = MagicMock()
    rag.acreate_entity = AsyncMock()
    rag.acreate_relation = AsyncMock()
    rag.graph_storage = MagicMock()
    rag.graph_storage.remove_nodes = AsyncMock()
    return rag


@pytest.fixture
def mock_embedding_client() -> MagicMock:
    """Create mock embedding client."""
    client = MagicMock()
    client.embed = AsyncMock(
        return_value=EmbeddingResult(embeddings=[[0.1] * 768], model="test")
    )
    return client


@pytest.fixture
def mock_parse_file() -> MagicMock:
    """Create mock parse function."""

    def parse(path: Path) -> ParseResult:
        return ParseResult(
            path=path,
            symbols=[
                Symbol(
                    name=f"func_{path.stem}",
                    kind="function",
                    signature=f"def func_{path.stem}(): pass",
                    docstring="",
                    line_start=1,
                    line_end=1,
                )
            ],
        )

    return parse


class TestScanCodeFiles:
    """Tests for scan_code_files()."""

    def test_scan_finds_python_files(self, temp_repo: Path) -> None:
        """Should find Python files."""
        files = scan_code_files(temp_repo)
        py_files = [f for f in files if f.suffix == ".py"]
        assert len(py_files) == 2

    def test_scan_finds_js_files(self, temp_repo: Path) -> None:
        """Should find JavaScript files."""
        files = scan_code_files(temp_repo)
        js_files = [f for f in files if f.suffix == ".js"]
        assert len(js_files) == 1  # Only src/index.js, not node_modules

    def test_scan_skips_node_modules(self, temp_repo: Path) -> None:
        """Should skip node_modules directory."""
        files = scan_code_files(temp_repo)
        node_files = [f for f in files if "node_modules" in str(f)]
        assert len(node_files) == 0

    def test_scan_skips_non_code_files(self, temp_repo: Path) -> None:
        """Should skip non-code files like README.md."""
        files = scan_code_files(temp_repo)
        md_files = [f for f in files if f.suffix == ".md"]
        assert len(md_files) == 0

    def test_scan_custom_extensions(self, temp_repo: Path) -> None:
        """Should respect custom extensions."""
        files = scan_code_files(temp_repo, extensions={".py"})
        assert all(f.suffix == ".py" for f in files)

    def test_scan_returns_sorted_paths(self, temp_repo: Path) -> None:
        """Should return sorted paths for deterministic ordering."""
        files = scan_code_files(temp_repo)
        assert files == sorted(files)


class TestIndexRepository:
    """Tests for index_repository()."""

    @pytest.mark.asyncio
    async def test_index_repository_basic(
        self,
        temp_repo: Path,
        mock_rag: MagicMock,
        mock_embedding_client: MagicMock,
        mock_parse_file: MagicMock,
    ) -> None:
        """Should index all code files in repository."""
        result = await index_repository(
            temp_repo,
            mock_rag,
            mock_embedding_client,
            mock_parse_file,
            clear_existing=False,
        )

        # 2 Python + 1 JS = 3 files with symbols
        assert result.files == 3
        assert result.entities == 3
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_index_repository_with_parse_error(
        self,
        temp_repo: Path,
        mock_rag: MagicMock,
        mock_embedding_client: MagicMock,
    ) -> None:
        """Should handle parse errors gracefully."""
        call_count = 0

        def parse_with_error(path: Path) -> ParseResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ParseResult(path=path, error="Syntax error")
            return ParseResult(
                path=path,
                symbols=[
                    Symbol(
                        name="func",
                        kind="function",
                        signature="def func(): pass",
                        docstring="",
                        line_start=1,
                        line_end=1,
                    )
                ],
            )

        result = await index_repository(
            temp_repo,
            mock_rag,
            mock_embedding_client,
            parse_with_error,
            clear_existing=False,
        )

        assert len(result.skipped_files) == 1
        assert result.files == 2  # 3 total - 1 skipped

    @pytest.mark.asyncio
    async def test_index_repository_progress_callback(
        self,
        temp_repo: Path,
        mock_rag: MagicMock,
        mock_embedding_client: MagicMock,
        mock_parse_file: MagicMock,
    ) -> None:
        """Should call progress callback."""
        progress_calls: list[tuple[str, int, int]] = []

        def on_progress(msg: str, current: int, total: int) -> None:
            progress_calls.append((msg, current, total))

        await index_repository(
            temp_repo,
            mock_rag,
            mock_embedding_client,
            mock_parse_file,
            clear_existing=False,
            batch_size=1,  # Callback every file
            on_progress=on_progress,
        )

        # Should have start and end callbacks at minimum
        assert len(progress_calls) >= 2
        assert progress_calls[0][0] == "Scanning complete"
        assert progress_calls[-1][0] == "Indexing complete"


class TestIndexFile:
    """Tests for index_file()."""

    @pytest.mark.asyncio
    async def test_index_single_file(
        self,
        temp_repo: Path,
        mock_rag: MagicMock,
        mock_embedding_client: MagicMock,
        mock_parse_file: MagicMock,
    ) -> None:
        """Should index a single file."""
        file_path = temp_repo / "src" / "main.py"

        result = await index_file(
            file_path,
            mock_rag,
            mock_embedding_client,
            mock_parse_file,
        )

        assert result.files == 1
        assert result.entities == 1
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_index_file_with_error(
        self,
        temp_repo: Path,
        mock_rag: MagicMock,
        mock_embedding_client: MagicMock,
    ) -> None:
        """Should handle file parse error."""
        file_path = temp_repo / "src" / "main.py"

        def parse_error(path: Path) -> ParseResult:
            return ParseResult(path=path, error="Parse failed")

        result = await index_file(
            file_path,
            mock_rag,
            mock_embedding_client,
            parse_error,
        )

        assert result.files == 0
        assert len(result.skipped_files) == 1
        assert "Parse error" in result.errors[0]
