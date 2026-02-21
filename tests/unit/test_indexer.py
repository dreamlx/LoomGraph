"""Unit tests for the indexer module."""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from loomgraph.core.indexer import (
    compute_file_hashes,
    filter_changed_files,
    index_file,
    index_repository,
    load_meta,
    save_meta,
    scan_code_files,
)
from loomgraph.core.models import IncrementalMeta, ParseResult, Symbol


class MockLightRAGClient:
    """Mock LightRAG HTTP client for testing."""

    def __init__(self):
        self.entities: list[dict[str, Any]] = []
        self.relations: list[dict[str, Any]] = []

    async def create_entity(self, entity_name: str, entity_data: dict[str, Any]) -> dict[str, Any]:
        self.entities.append({"name": entity_name, "data": entity_data})
        return {"status": "success", "message": f"Entity '{entity_name}' created"}

    async def create_relation(
        self, source_entity: str, target_entity: str, relation_data: dict[str, Any]
    ) -> dict[str, Any]:
        self.relations.append({
            "src": source_entity,
            "tgt": target_entity,
            "data": relation_data,
        })
        return {"status": "success", "message": "Relation created"}


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
def mock_client() -> MockLightRAGClient:
    """Create mock LightRAG client."""
    return MockLightRAGClient()


@pytest.fixture
def mock_parse_file():
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
        mock_client: MockLightRAGClient,
        mock_parse_file,
    ) -> None:
        """Should index all code files in repository."""
        result = await index_repository(
            temp_repo,
            mock_client,
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
        mock_client: MockLightRAGClient,
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
            mock_client,
            parse_with_error,
            clear_existing=False,
        )

        assert len(result.skipped_files) == 1
        assert result.files == 2  # 3 total - 1 skipped

    @pytest.mark.asyncio
    async def test_index_repository_progress_callback(
        self,
        temp_repo: Path,
        mock_client: MockLightRAGClient,
        mock_parse_file,
    ) -> None:
        """Should call progress callback."""
        progress_calls: list[tuple[str, int, int]] = []

        def on_progress(msg: str, current: int, total: int) -> None:
            progress_calls.append((msg, current, total))

        await index_repository(
            temp_repo,
            mock_client,
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
        mock_client: MockLightRAGClient,
        mock_parse_file,
    ) -> None:
        """Should index a single file."""
        file_path = temp_repo / "src" / "main.py"

        result = await index_file(
            file_path,
            mock_client,
            mock_parse_file,
        )

        assert result.files == 1
        assert result.entities == 1
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_index_file_with_error(
        self,
        temp_repo: Path,
        mock_client: MockLightRAGClient,
    ) -> None:
        """Should handle file parse error."""
        file_path = temp_repo / "src" / "main.py"

        def parse_error(path: Path) -> ParseResult:
            return ParseResult(path=path, error="Parse failed")

        result = await index_file(
            file_path,
            mock_client,
            parse_error,
        )

        assert result.files == 0
        assert len(result.skipped_files) == 1
        assert "Parse error" in result.errors[0]


class TestIncrementalMeta:
    """Tests for incremental indexing meta file operations."""

    def test_load_meta_missing_file(self, temp_repo: Path) -> None:
        """Should return empty meta when file doesn't exist."""
        meta = load_meta(temp_repo)
        assert meta.version == 1
        assert meta.file_hashes == {}

    def test_save_and_load_meta(self, temp_repo: Path) -> None:
        """Should round-trip meta through save/load."""
        meta = IncrementalMeta(
            version=1,
            workspace="test-ws",
            file_hashes={"src/main.py": "abc123", "src/utils.py": "def456"},
            last_indexed="2026-02-21T12:00:00+00:00",
            files_count=2,
            entities_count=5,
            relations_count=3,
        )
        save_meta(temp_repo, meta)

        loaded = load_meta(temp_repo)
        assert loaded.workspace == "test-ws"
        assert loaded.file_hashes == {"src/main.py": "abc123", "src/utils.py": "def456"}
        assert loaded.files_count == 2
        assert loaded.entities_count == 5

    def test_save_meta_creates_directory(self, temp_repo: Path) -> None:
        """Should create .loomgraph directory if missing."""
        meta = IncrementalMeta(file_hashes={"a.py": "hash1"})
        save_meta(temp_repo, meta)
        assert (temp_repo / ".loomgraph" / "meta.json").exists()

    def test_load_meta_corrupt_json(self, temp_repo: Path) -> None:
        """Should return empty meta on corrupt JSON."""
        meta_dir = temp_repo / ".loomgraph"
        meta_dir.mkdir()
        (meta_dir / "meta.json").write_text("not valid json{{{")
        meta = load_meta(temp_repo)
        assert meta.file_hashes == {}


class TestFileHashing:
    """Tests for file hash computation and filtering."""

    def test_compute_file_hashes(self, temp_repo: Path) -> None:
        """Should compute hashes for all files."""
        files = scan_code_files(temp_repo)
        hashes = compute_file_hashes(files, temp_repo)
        assert len(hashes) == 3  # 2 py + 1 js
        assert all(len(h) == 64 for h in hashes.values())  # SHA-256

    def test_compute_hashes_deterministic(self, temp_repo: Path) -> None:
        """Same file content should produce same hash."""
        files = scan_code_files(temp_repo)
        h1 = compute_file_hashes(files, temp_repo)
        h2 = compute_file_hashes(files, temp_repo)
        assert h1 == h2

    def test_compute_hashes_change_on_modification(self, temp_repo: Path) -> None:
        """Modified file should produce different hash."""
        files = scan_code_files(temp_repo)
        h1 = compute_file_hashes(files, temp_repo)

        # Modify a file
        (temp_repo / "src" / "main.py").write_text("def main(): return 42")
        h2 = compute_file_hashes(files, temp_repo)

        main_key = str((temp_repo / "src" / "main.py").relative_to(temp_repo))
        assert h1[main_key] != h2[main_key]

    def test_filter_changed_files_all_new(self, temp_repo: Path) -> None:
        """All files should be indexed when no old hashes exist."""
        files = scan_code_files(temp_repo)
        new_hashes = compute_file_hashes(files, temp_repo)
        changed, skipped = filter_changed_files(files, new_hashes, {}, temp_repo)
        assert len(changed) == 3
        assert skipped == 0

    def test_filter_changed_files_all_unchanged(self, temp_repo: Path) -> None:
        """No files should be indexed when all hashes match."""
        files = scan_code_files(temp_repo)
        hashes = compute_file_hashes(files, temp_repo)
        changed, skipped = filter_changed_files(files, hashes, hashes, temp_repo)
        assert len(changed) == 0
        assert skipped == 3

    def test_filter_changed_files_partial(self, temp_repo: Path) -> None:
        """Only modified files should be indexed."""
        files = scan_code_files(temp_repo)
        old_hashes = compute_file_hashes(files, temp_repo)

        # Modify one file
        (temp_repo / "src" / "main.py").write_text("def main(): return 42")
        new_hashes = compute_file_hashes(files, temp_repo)

        changed, skipped = filter_changed_files(files, new_hashes, old_hashes, temp_repo)
        assert len(changed) == 1
        assert skipped == 2
        assert changed[0].name == "main.py"
