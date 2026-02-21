"""Tests for code health scoring module."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from loomgraph.core.health import (
    FileMetrics,
    HealthScore,
    aggregate_metrics,
    compute_graph_dimensions,
    compute_score,
    scan_file,
)


class TestScanFile:
    """Tests for scan_file()."""

    def test_scan_python_file(self, tmp_path: Path) -> None:
        f = tmp_path / "app.py"
        f.write_text("# TODO fix this\nimport os\nprint('hello')\n")
        m = scan_file(f)
        assert m is not None
        assert m.lines == 4
        assert m.todos == 1
        assert m.is_test is False

    def test_scan_test_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test_app.py"
        f.write_text("def test_foo(): pass\n")
        # test detection via /tests/ path
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        tf = tests_dir / "check.py"
        tf.write_text("assert True\n")
        m = scan_file(tf)
        assert m is not None
        assert m.is_test is True
    def test_scan_ts_any_count(self, tmp_path: Path) -> None:
        f = tmp_path / "app.ts"
        f.write_text("const x: any = 1;\nconst y: any = 2;\n")
        m = scan_file(f)
        assert m is not None
        assert m.any_count == 2

    def test_scan_legacy_marks(self, tmp_path: Path) -> None:
        f = tmp_path / "old.py"
        f.write_text("// DEPRECATED\n// LEGACY\ncode()\n")
        m = scan_file(f)
        assert m is not None
        assert m.legacy_marks == 2

    def test_skip_non_code_file(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Hello\n")
        assert scan_file(f) is None

    def test_hardcoded_urls(self, tmp_path: Path) -> None:
        f = tmp_path / "config.py"
        f.write_text('url = "http://example.com"\nurl2 = "http://foo.bar"\n')
        m = scan_file(f)
        assert m is not None
        assert m.hardcoded_urls == 2


class TestAggregateMetrics:
    """Tests for aggregate_metrics()."""

    def test_aggregate(self) -> None:
        metrics = [
            FileMetrics(path="a.py", lines=100, todos=2, is_test=False),
            FileMetrics(path="b.py", lines=500, todos=1, any_count=3, is_test=False),
            FileMetrics(path="test_a.py", lines=50, is_test=True),
        ]
        agg = aggregate_metrics(metrics)
        assert agg["max_lines"] == 500
        assert agg["any_count"] == 3
        assert agg["mt_issues"] == 3  # 2 + 1 todos
        assert agg["prod_files"] == 2
        assert agg["test_files"] == 1

    def test_empty(self) -> None:
        agg = aggregate_metrics([])
        assert agg["max_lines"] == 0
        assert agg["total_files"] == 0


class TestComputeScore:
    """Tests for compute_score()."""

    def test_perfect_score(self) -> None:
        metrics = {"max_lines": 100, "any_count": 0, "mt_issues": 0, "legacy_marks": 0}
        s = compute_score(metrics)
        assert s.score == 100.0
        assert s.cq == 10
        assert s.ts == 10

    def test_degraded_score(self) -> None:
        metrics = {"max_lines": 900, "any_count": 20, "mt_issues": 10, "legacy_marks": 10}
        s = compute_score(metrics)
        assert s.cq == 5
        assert s.ts == 5
        assert s.mt == 7
        assert s.dc == 5
        assert s.score < 80

    def test_custom_graph_dims(self) -> None:
        metrics = {"max_lines": 100, "any_count": 0, "mt_issues": 0, "legacy_marks": 0}
        s = compute_score(metrics, ir=5, mc=5)
        assert s.ir == 5
        assert s.mc == 5
        assert s.score < 100.0


class TestComputeGraphDimensions:
    """Tests for compute_graph_dimensions()."""

    @pytest.mark.asyncio
    async def test_with_relations(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_relations.return_value = [
            {"src_id": "a.foo", "tgt_id": "b.bar", "keywords": "CALLS"},
            {"src_id": "a.foo", "tgt_id": "b.baz", "keywords": "CALLS"},
            {"src_id": "c.qux", "tgt_id": "b.bar", "keywords": "CALLS"},
        ]
        dims = await compute_graph_dimensions(mock_client)
        assert "ir" in dims
        assert "mc" in dims
        # b.bar has fan-in 2 → ir should be 10 (<=3)
        assert dims["ir"] == 10

    @pytest.mark.asyncio
    async def test_empty_graph(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_relations.return_value = []
        dims = await compute_graph_dimensions(mock_client)
        assert dims == {"ir": 10, "mc": 10}

    @pytest.mark.asyncio
    async def test_client_error_fallback(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_all_relations.side_effect = Exception("connection refused")
        dims = await compute_graph_dimensions(mock_client)
        assert dims == {"ir": 10, "mc": 10}

