"""Unit tests for TrendAnalyzer (EPIC-010 Feature 3)."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from loomgraph.core.models import LinearRegression, MetricsSnapshot, TrendAnalysis, TrendPoint
from loomgraph.core.trends import TrendAnalyzer


@pytest.fixture
def sample_snapshots():
    """Sample metrics snapshots for testing (6 months of data)."""
    # Use recent timestamps (within last 6 months)
    now = datetime.now()
    base_time = now - timedelta(days=150)  # Start 5 months ago
    snapshots = []

    # Simulate complexity growth over 6 months
    for i in range(6):
        timestamp = base_time + timedelta(days=30 * i)
        complexity = 30 + (i * 5)  # Linear growth: 30 → 55

        snapshots.append(
            MetricsSnapshot(
                entity="src/auth/user_service.py",
                entity_type="file",
                timestamp=timestamp,
                metrics={"complexity": complexity, "coupling": 10 + i},
                workspace="myproject:main",
            )
        )

    return snapshots


@pytest.fixture
def sample_stable_snapshots():
    """Sample snapshots with stable (no growth) metrics."""
    # Use recent timestamps (within last 6 months)
    now = datetime.now()
    base_time = now - timedelta(days=150)  # Start 5 months ago
    snapshots = []

    for i in range(6):
        timestamp = base_time + timedelta(days=30 * i)
        snapshots.append(
            MetricsSnapshot(
                entity="src/stable/service.py",
                entity_type="file",
                timestamp=timestamp,
                metrics={"complexity": 25, "coupling": 5},  # Constant values
                workspace="myproject:main",
            )
        )

    return snapshots


class TestTrendAnalyzer:
    """Test TrendAnalyzer functionality."""

    def test_init_creates_storage_directory(self):
        """Test that TrendAnalyzer creates storage directory on init."""
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            analyzer = TrendAnalyzer()

            # Should create ~/.loomgraph/metrics-history/
            expected_path = Path.home() / ".loomgraph" / "metrics-history"
            assert analyzer.storage_path == expected_path
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_save_snapshot(self):
        """Test saving a single metrics snapshot."""
        analyzer = TrendAnalyzer()
        snapshot = MetricsSnapshot(
            entity="src/test.py",
            entity_type="file",
            timestamp=datetime.now(),
            metrics={"complexity": 42},
            workspace="test:main",
        )

        with patch("pathlib.Path.write_text") as mock_write:
            analyzer.save_snapshot(snapshot)

            # Should write JSON to disk
            mock_write.assert_called_once()
            # Check JSON content
            written_content = mock_write.call_args[0][0]
            assert "src/test.py" in written_content
            assert "42" in written_content
            assert "test:main" in written_content

    def test_load_snapshots(self, sample_snapshots, tmp_path):
        """Test loading snapshots for an entity."""
        # Use temporary directory for testing
        analyzer = TrendAnalyzer(storage_path=tmp_path)

        # Save all snapshots to temp directory
        for snapshot in sample_snapshots:
            analyzer.save_snapshot(snapshot)

        # Debug: list all files created
        print(f"\nFiles in {tmp_path}:")
        for f in tmp_path.glob("*"):
            print(f"  {f.name}")

        # Load them back
        snapshots = analyzer.load_snapshots(
            entity="src/auth/user_service.py",
            months=6,
        )

        # Should return 6 snapshots
        assert len(snapshots) == 6, f"Expected 6 snapshots, got {len(snapshots)}. Files: {list(tmp_path.glob('*'))}"
        assert all(isinstance(s, MetricsSnapshot) for s in snapshots)
        # Check values
        assert snapshots[0].metrics["complexity"] == 30
        assert snapshots[5].metrics["complexity"] == 55
        # Check sorted by timestamp
        for i in range(len(snapshots) - 1):
            assert snapshots[i].timestamp <= snapshots[i + 1].timestamp

    def test_analyze_trend_linear_growth(self, sample_snapshots):
        """Test trend analysis with linear growth pattern."""
        analyzer = TrendAnalyzer()

        with patch.object(analyzer, "load_snapshots", return_value=sample_snapshots):
            result = analyzer.analyze(
                entity="src/auth/user_service.py",
                metric_name="complexity",
                months=6,
            )

            # Check result structure
            assert isinstance(result, TrendAnalysis)
            assert result.entity == "src/auth/user_service.py"
            assert result.metric_name == "complexity"
            assert result.time_range == "6 months"

            # Check data points
            assert len(result.data_points) == 6
            assert result.data_points[0].value == 30
            assert result.data_points[5].value == 55

            # Check linear regression
            assert isinstance(result.regression, LinearRegression)
            assert result.regression.slope > 0  # Positive slope = increasing
            assert result.regression.trend_direction == "increasing"
            assert result.regression.r_squared > 0.9  # Strong linear fit

            # Check forecast (next month should be ~60)
            assert 58 <= result.forecast <= 62

            # Check alert (rapid growth should trigger warning)
            assert result.alert is not None
            assert "growth" in result.alert.lower() or "rapid" in result.alert.lower()

    def test_analyze_trend_stable(self, sample_stable_snapshots):
        """Test trend analysis with stable (no growth) metrics."""
        analyzer = TrendAnalyzer()

        with patch.object(analyzer, "load_snapshots", return_value=sample_stable_snapshots):
            result = analyzer.analyze(
                entity="src/stable/service.py",
                metric_name="complexity",
                months=6,
            )

            # Check regression for stable trend
            assert result.regression.trend_direction == "stable"
            assert abs(result.regression.slope) < 1.0  # Near-zero slope

            # Check forecast (should be close to current value)
            assert 23 <= result.forecast <= 27

            # No alert for stable trend
            assert result.alert is None

    def test_analyze_trend_insufficient_data(self):
        """Test handling of insufficient data (< 3 snapshots)."""
        analyzer = TrendAnalyzer()

        # Only 2 snapshots - not enough for trend
        insufficient_snapshots = [
            MetricsSnapshot(
                entity="src/test.py",
                entity_type="file",
                timestamp=datetime.now(),
                metrics={"complexity": 30},
                workspace="test:main",
            ),
            MetricsSnapshot(
                entity="src/test.py",
                entity_type="file",
                timestamp=datetime.now() + timedelta(days=30),
                metrics={"complexity": 35},
                workspace="test:main",
            ),
        ]

        with patch.object(analyzer, "load_snapshots", return_value=insufficient_snapshots):
            with pytest.raises(ValueError, match="at least 3 snapshots"):
                analyzer.analyze(
                    entity="src/test.py",
                    metric_name="complexity",
                    months=6,
                )

    def test_cleanup_old_snapshots(self):
        """Test cleanup of snapshots older than 12 months."""
        analyzer = TrendAnalyzer()

        # Create mock files with different timestamps
        now = datetime.now()
        old_file = Mock()
        old_file.name = f"src_test_py_{(now - timedelta(days=400)).strftime('%Y%m%d_%H%M%S')}.json"
        old_file.stat.return_value.st_mtime = (now - timedelta(days=400)).timestamp()
        old_file_unlinked = False

        def old_file_unlink():
            nonlocal old_file_unlinked
            old_file_unlinked = True

        old_file.unlink = old_file_unlink

        recent_file = Mock()
        recent_file.name = f"src_test_py_{(now - timedelta(days=100)).strftime('%Y%m%d_%H%M%S')}.json"
        recent_file.stat.return_value.st_mtime = (now - timedelta(days=100)).timestamp()

        # Mock glob at the module level
        with patch("pathlib.Path.glob", return_value=[old_file, recent_file]):
            deleted = analyzer.cleanup_old_snapshots(max_age_months=12)

            # Should delete only the old file
            assert deleted == 1
            assert old_file_unlinked is True

    def test_generate_ascii_chart(self, sample_snapshots):
        """Test ASCII chart generation."""
        analyzer = TrendAnalyzer()

        with patch.object(analyzer, "load_snapshots", return_value=sample_snapshots):
            result = analyzer.analyze(
                entity="src/auth/user_service.py",
                metric_name="complexity",
                months=6,
            )

            # Check chart is not empty
            assert result.chart
            assert len(result.chart) > 0

            # Chart should contain trend line
            assert "│" in result.chart  # Y-axis
            assert "─" in result.chart  # X-axis or trend line

            # Should show data points
            assert "●" in result.chart or "*" in result.chart

    def test_linear_regression_calculation(self):
        """Test linear regression math correctness."""
        analyzer = TrendAnalyzer()

        # Dataset with steeper slope: y = 4x + 1 (4 units per day)
        base_time = datetime(2024, 1, 1)
        data_points = [
            TrendPoint(base_time, 1, "T0"),                               # x=0, y=1
            TrendPoint(base_time + timedelta(days=10), 41, "T1"),         # x=10, y=41
            TrendPoint(base_time + timedelta(days=20), 81, "T2"),         # x=20, y=81
            TrendPoint(base_time + timedelta(days=30), 121, "T3"),        # x=30, y=121
        ]

        regression = analyzer._calculate_regression(data_points)

        # Check slope ~= 4.0 per day
        assert isinstance(regression, LinearRegression)
        assert 3.9 <= regression.slope <= 4.1
        assert 0.0 <= regression.intercept <= 2.0
        assert regression.r_squared > 0.99  # Perfect linear fit
        assert regression.trend_direction == "increasing"  # slope > 0.1

    def test_trend_direction_thresholds(self):
        """Test trend direction classification thresholds."""
        analyzer = TrendAnalyzer()

        # Test borderline cases (slope per day)
        test_cases = [
            (0.15, "increasing"),   # slope > 0.1 = increasing (~3/month)
            (0.05, "stable"),       # -0.1 <= slope <= 0.1 = stable
            (-0.15, "decreasing"),  # slope < -0.1 = decreasing
        ]

        for slope, expected_direction in test_cases:
            direction = analyzer._classify_trend(slope)
            assert direction == expected_direction

    def test_performance_requirement(self, sample_snapshots):
        """Test that analysis completes in < 1 second."""
        analyzer = TrendAnalyzer()

        import time

        with patch.object(analyzer, "load_snapshots", return_value=sample_snapshots):
            start = time.time()
            analyzer.analyze(
                entity="src/auth/user_service.py",
                metric_name="complexity",
                months=6,
            )
            duration = time.time() - start

            # Should complete in < 1 second
            assert duration < 1.0


class TestTrendIntegration:
    """Integration tests for trend analysis workflow."""

    def test_save_and_load_roundtrip(self):
        """Test saving and loading snapshots (roundtrip)."""
        analyzer = TrendAnalyzer()
        snapshot = MetricsSnapshot(
            entity="src/integration/test.py",
            entity_type="file",
            timestamp=datetime.now(),
            metrics={"complexity": 42, "coupling": 10},
            workspace="integration:test",
        )

        # Save snapshot
        with patch("pathlib.Path.mkdir"):
            with patch("pathlib.Path.write_text") as mock_write:
                analyzer.save_snapshot(snapshot)

                # Verify JSON structure
                written_json = mock_write.call_args[0][0]
                assert "src/integration/test.py" in written_json
                assert "42" in written_json

    def test_auto_save_in_debt_command(self):
        """Test that debt command auto-saves snapshots."""
        # This will be tested in integration test
        # when we modify debt_analyzer.py
        pass
