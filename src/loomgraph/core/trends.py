"""Trend analysis for code complexity evolution (EPIC-010 Feature 3).

Analyzes historical metrics snapshots to detect code rot patterns.
Uses linear regression for trend prediction and generates ASCII charts.
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from loomgraph.core.models import (
    LinearRegression,
    MetricsSnapshot,
    TrendAnalysis,
    TrendPoint,
)


class TrendAnalyzer:
    """Analyze historical trends in code complexity metrics.

    Automatically saves snapshots to ~/.loomgraph/metrics-history/
    and provides trend analysis with linear regression forecasting.

    Example:
        >>> analyzer = TrendAnalyzer()
        >>> snapshot = MetricsSnapshot(...)
        >>> analyzer.save_snapshot(snapshot)
        >>> result = analyzer.analyze("src/auth/user_service.py", "complexity", 6)
        >>> print(result.chart)
    """

    def __init__(self, storage_path: Path | None = None):
        """Initialize trend analyzer.

        Args:
            storage_path: Custom storage path (default: ~/.loomgraph/metrics-history/)
        """
        if storage_path is None:
            storage_path = Path.home() / ".loomgraph" / "metrics-history"

        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: MetricsSnapshot) -> None:
        """Save a metrics snapshot to disk.

        Snapshots are stored as JSON files with entity-based naming:
        {entity_hash}_{timestamp}.json

        Args:
            snapshot: Metrics snapshot to save
        """
        # Create filename from entity and timestamp
        entity_slug = self._slugify(snapshot.entity)
        timestamp_str = snapshot.timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{entity_slug}_{timestamp_str}.json"

        file_path = self.storage_path / filename

        # Serialize to JSON
        data = {
            "entity": snapshot.entity,
            "entity_type": snapshot.entity_type,
            "timestamp": snapshot.timestamp.isoformat(),
            "metrics": snapshot.metrics,
            "workspace": snapshot.workspace,
        }

        file_path.write_text(json.dumps(data, indent=2))

    def load_snapshots(
        self,
        entity: str,
        months: int = 6,
        workspace: str | None = None,
    ) -> list[MetricsSnapshot]:
        """Load historical snapshots for an entity.

        Args:
            entity: Entity identifier (e.g., "src/auth/user_service.py")
            months: Number of months to look back
            workspace: Filter by workspace (default: all workspaces)

        Returns:
            List of snapshots sorted by timestamp (oldest first)
        """
        entity_slug = self._slugify(entity)
        pattern = f"{entity_slug}_*.json"

        # Find all matching files
        snapshots = []
        cutoff = datetime.now() - timedelta(days=30 * months)

        for file_path in self.storage_path.glob(pattern):
            try:
                data = json.loads(file_path.read_text())

                # Parse timestamp
                timestamp = datetime.fromisoformat(data["timestamp"])

                # Filter by time window
                if timestamp < cutoff:
                    continue

                # Filter by workspace if specified
                if workspace and data.get("workspace") != workspace:
                    continue

                # Reconstruct snapshot
                snapshot = MetricsSnapshot(
                    entity=data["entity"],
                    entity_type=data["entity_type"],
                    timestamp=timestamp,
                    metrics=data["metrics"],
                    workspace=data["workspace"],
                )
                snapshots.append(snapshot)

            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip corrupted files
                continue

        # Sort by timestamp
        return sorted(snapshots, key=lambda s: s.timestamp)

    def analyze(
        self,
        entity: str,
        metric_name: str,
        months: int = 6,
        workspace: str | None = None,
    ) -> TrendAnalysis:
        """Analyze trend for a specific metric over time.

        Args:
            entity: Entity identifier
            metric_name: Metric to analyze (e.g., "complexity", "coupling")
            months: Number of months to analyze
            workspace: Workspace filter

        Returns:
            Trend analysis with regression and forecast

        Raises:
            ValueError: If insufficient data (< 3 snapshots)
        """
        snapshots = self.load_snapshots(entity, months, workspace)

        if len(snapshots) < 3:
            raise ValueError(
                f"Trend analysis requires at least 3 snapshots, got {len(snapshots)}. "
                f"Run 'loomgraph debt' multiple times over weeks/months to collect data."
            )

        # Extract data points for the metric
        data_points = []
        for snapshot in snapshots:
            if metric_name not in snapshot.metrics:
                continue

            value = snapshot.metrics[metric_name]
            label = snapshot.timestamp.strftime("%Y-%m-%d")

            data_points.append(
                TrendPoint(
                    timestamp=snapshot.timestamp,
                    value=float(value),
                    label=label,
                )
            )

        if len(data_points) < 3:
            raise ValueError(
                f"Metric '{metric_name}' not found in sufficient snapshots. "
                f"Found {len(data_points)} data points, need at least 3."
            )

        # Calculate linear regression
        regression = self._calculate_regression(data_points)

        # Forecast next period (30 days from last snapshot)
        last_timestamp = data_points[-1].timestamp
        next_timestamp = last_timestamp + timedelta(days=30)
        days_from_start = (next_timestamp - data_points[0].timestamp).days
        forecast = regression.slope * days_from_start + regression.intercept

        # Generate alert if needed
        alert = self._generate_alert(regression, data_points)

        # Generate ASCII chart
        chart = self._generate_chart(data_points, regression)

        # Infer entity type from snapshots
        entity_type = snapshots[0].entity_type

        return TrendAnalysis(
            entity=entity,
            entity_type=entity_type,
            metric_name=metric_name,
            time_range=f"{months} months",
            data_points=data_points,
            regression=regression,
            forecast=forecast,
            alert=alert,
            chart=chart,
        )

    def cleanup_old_snapshots(self, max_age_months: int = 12) -> int:
        """Delete snapshots older than specified age.

        Args:
            max_age_months: Maximum age in months (default: 12)

        Returns:
            Number of files deleted
        """
        cutoff = datetime.now() - timedelta(days=30 * max_age_months)
        deleted = 0

        for file_path in self.storage_path.glob("*.json"):
            # Check file modification time
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

            if mtime < cutoff:
                file_path.unlink()
                deleted += 1

        return deleted

    def _calculate_regression(self, data_points: list[TrendPoint]) -> LinearRegression:
        """Calculate linear regression for trend line.

        Uses least squares method: y = mx + b

        Args:
            data_points: Historical data points

        Returns:
            Linear regression result with slope, intercept, and R²
        """
        n = len(data_points)

        # Convert timestamps to days from start
        start = data_points[0].timestamp
        x_values = [(p.timestamp - start).days for p in data_points]
        y_values = [p.value for p in data_points]

        # Calculate means
        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n

        # Calculate slope and intercept
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=True))
        denominator = sum((x - x_mean) ** 2 for x in x_values)

        if denominator == 0:
            slope = 0.0
            intercept = y_mean
        else:
            slope = numerator / denominator
            intercept = y_mean - slope * x_mean

        # Calculate R² (coefficient of determination)
        y_pred = [slope * x + intercept for x in x_values]
        ss_res = sum((y - y_p) ** 2 for y, y_p in zip(y_values, y_pred, strict=True))
        ss_tot = sum((y - y_mean) ** 2 for y in y_values)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Classify trend direction
        trend_direction = self._classify_trend(slope)

        return LinearRegression(
            slope=slope,
            intercept=intercept,
            r_squared=r_squared,
            trend_direction=trend_direction,
        )

    def _classify_trend(self, slope: float) -> str:
        """Classify trend direction based on slope (per day).

        Args:
            slope: Linear regression slope (change per day)

        Returns:
            "increasing" | "decreasing" | "stable"
        """
        # Threshold: 0.1 per day = 3 per month (significant change)
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"

    def _generate_alert(
        self,
        regression: LinearRegression,
        data_points: list[TrendPoint],
    ) -> str | None:
        """Generate alert message for concerning trends.

        Args:
            regression: Linear regression result
            data_points: Historical data points

        Returns:
            Alert message or None if no alert needed
        """
        # Alert on rapid increasing trends (> 0.15 per day = ~4.5 per month)
        if regression.trend_direction == "increasing" and regression.slope > 0.15:
            current = data_points[-1].value
            forecast = current + (regression.slope * 30)  # 30 days ahead
            growth_pct = ((forecast - current) / current) * 100 if current > 0 else 0

            return (
                f"⚠️ Rapid complexity growth detected: "
                f"+{growth_pct:.1f}% projected in next month. "
                f"Current: {current:.0f}, Forecast: {forecast:.0f}. "
                f"Consider refactoring to prevent further deterioration."
            )

        return None

    def _generate_chart(
        self,
        data_points: list[TrendPoint],
        regression: LinearRegression,
    ) -> str:
        """Generate ASCII chart for trend visualization.

        Args:
            data_points: Historical data points
            regression: Linear regression for trend line

        Returns:
            ASCII art chart as string
        """
        if not data_points:
            return ""

        # Chart dimensions
        width = 60
        height = 15

        # Find min/max values
        values = [p.value for p in data_points]
        min_val = min(values)
        max_val = max(values)
        range_val = max_val - min_val if max_val > min_val else 1

        # Build chart lines
        lines = []

        # Title
        lines.append(f"Trend: {regression.trend_direction.upper()}")
        lines.append(f"Slope: {regression.slope:+.2f}/month, R²: {regression.r_squared:.3f}")
        lines.append("")

        # Y-axis scale
        for i in range(height, -1, -1):
            y_val = min_val + (range_val * i / height)
            row = f"{y_val:5.0f} │"

            # Plot data points and trend line
            for j in range(width):
                # Map x position to data point index
                x_idx = int(j * (len(data_points) - 1) / width)
                if x_idx >= len(data_points):
                    x_idx = len(data_points) - 1

                # Get data point and trend line value
                data_val = data_points[x_idx].value

                # Calculate trend line value at this x position
                start = data_points[0].timestamp
                x_timestamp = data_points[x_idx].timestamp
                x_days = (x_timestamp - start).days
                trend_val = regression.slope * x_days + regression.intercept

                # Determine which value is closer to current y_val
                data_dist = abs(data_val - y_val)
                trend_dist = abs(trend_val - y_val)

                # Plot symbol
                threshold = range_val / height / 2
                if data_dist < threshold:
                    row += "●"
                elif trend_dist < threshold:
                    row += "─"
                else:
                    row += " "

            lines.append(row)

        # X-axis
        lines.append("      └" + "─" * width)

        # X-axis labels (first and last date)
        first_label = data_points[0].label
        last_label = data_points[-1].label
        x_labels = f"       {first_label}" + " " * (width - len(first_label) - len(last_label)) + last_label
        lines.append(x_labels)

        return "\n".join(lines)

    def _slugify(self, entity: str) -> str:
        """Convert entity name to filesystem-safe slug.

        Args:
            entity: Entity identifier (e.g., "src/auth/user_service.py")

        Returns:
            Slug (e.g., "src_auth_user_service_py")
        """
        # Replace path separators and special chars
        slug = entity.replace("/", "_").replace("\\", "_").replace(".", "_")

        # Also create a hash to ensure uniqueness
        hash_suffix = hashlib.md5(entity.encode()).hexdigest()[:8]

        return f"{slug}_{hash_suffix}"
