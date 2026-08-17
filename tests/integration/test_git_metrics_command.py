"""Integration tests for git-metrics CLI command."""

import json
import subprocess


class TestGitMetricsCommand:
    """Test git-metrics CLI command end-to-end."""

    def test_git_metrics_help(self):
        """Test git-metrics --help."""
        result = subprocess.run(
            ["loomgraph", "git-metrics", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Analyze git history metrics" in result.stdout
        assert "--since" in result.stdout
        assert "--output" in result.stdout

    def test_git_metrics_on_self(self, tmp_path):
        """Test running git-metrics on LoomGraph itself."""
        output_file = tmp_path / "metrics.json"

        result = subprocess.run(
            [
                "loomgraph",
                "git-metrics",
                "./src",  # LoomGraph src directory
                "--since",
                "1 month",
                "--output",
                str(output_file),
            ],
            capture_output=True,
            text=True,
        )

        # Should succeed
        assert result.returncode == 0

        # Parse JSON output
        response = json.loads(result.stdout)
        assert response["success"] is True
        assert "hotspots" in response["data"]
        assert "bus_factor_critical" in response["data"]

        # Check output file exists and is valid JSON
        assert output_file.exists()
        data = json.loads(output_file.read_text())

        assert "repo_path" in data
        assert "since" in data
        assert data["since"] == "1 month"
        assert "summary" in data
        assert "hotspots" in data
        assert "bus_factor" in data
        assert "file_metrics" in data

        # Verify hotspots structure
        if len(data["hotspots"]) > 0:
            hotspot = data["hotspots"][0]
            assert "file" in hotspot
            assert "change_freq" in hotspot
            assert "hotspot_score" in hotspot
            assert "rank" in hotspot
            assert hotspot["rank"] == 1  # Top hotspot

        # Verify bus_factor structure. Single-author suppression (#156):
        # after the public-history rewrite unified commit emails, this repo
        # reads as one author — every risk_level is legitimately
        # "informational" with a bus_factor_note explaining why.
        if len(data["bus_factor"]) > 0:
            bf = data["bus_factor"][0]
            assert "file" in bf
            assert "owner" in bf
            assert "contributors" in bf
            assert "risk_level" in bf
            if data.get("summary", {}).get("bus_factor_note"):
                assert bf["risk_level"] == "informational"
            else:
                assert bf["risk_level"] in ["critical", "high", "medium"]

    def test_git_metrics_console_output(self):
        """Test git-metrics without --output (console output)."""
        result = subprocess.run(
            [
                "loomgraph",
                "git-metrics",
                "./src",
                "--since",
                "1 month",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Parse JSON output
        response = json.loads(result.stdout)
        assert response["success"] is True
        data = response["data"]

        # Should contain all sections
        assert "repo_path" in data
        assert "summary" in data
        assert "hotspots" in data
        assert "bus_factor" in data

    def test_git_metrics_different_time_windows(self, tmp_path):
        """Test git-metrics with different --since values."""
        for since in ["3 months", "6 months", "1 year"]:
            output_file = tmp_path / f"metrics-{since.replace(' ', '-')}.json"

            result = subprocess.run(
                [
                    "loomgraph",
                    "git-metrics",
                    "./src",
                    "--since",
                    since,
                    "--output",
                    str(output_file),
                ],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert output_file.exists()

            data = json.loads(output_file.read_text())
            assert data["since"] == since

    def test_git_metrics_nonexistent_path(self):
        """Test git-metrics with nonexistent path."""
        result = subprocess.run(
            [
                "loomgraph",
                "git-metrics",
                "/nonexistent/path",
                "--since",
                "1 month",
            ],
            capture_output=True,
            text=True,
        )

        # Should fail with error code 2 (Click path validation)
        assert result.returncode == 2
        assert "does not exist" in result.stderr.lower() or "invalid value" in result.stderr.lower()
