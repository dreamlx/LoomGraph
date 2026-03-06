"""
Integration tests for debt CLI command
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main


@pytest.fixture
def runner() -> CliRunner:
    """Create Click CLI runner."""
    return CliRunner()


@pytest.fixture
def minimal_fixture_path() -> Path:
    """Path to minimal codeindex fixture."""
    return Path(__file__).parent.parent / "fixtures" / "codeindex-minimal.json"


class TestDebtCommand:
    """Test debt CLI command."""

    def test_debt_help(self, runner: CliRunner):
        """Test debt --help."""
        result = runner.invoke(main, ["debt", "--help"])

        assert result.exit_code == 0
        assert "Analyze technical debt" in result.output
        assert "--codeindex-data" in result.output
        assert "--format" in result.output

    def test_debt_without_data(self, runner: CliRunner):
        """Test debt command without codeindex data."""
        result = runner.invoke(main, ["debt"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["data"]["overall_health"]["total_score"] == 100
        assert len(output["data"]["issues"]) == 0

    def test_debt_with_minimal_data_json_format(
        self, runner: CliRunner, minimal_fixture_path: Path
    ):
        """Test debt command with minimal data (JSON format)."""
        result = runner.invoke(
            main, ["debt", "--codeindex-data", str(minimal_fixture_path)]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True

        report = output["data"]
        assert report["schema_version"] == "1.0"
        assert report["generator"]["tool"] == "loomgraph"
        assert report["overall_health"]["grade"] == "C"
        assert len(report["issues"]) == 6

    def test_debt_with_minimal_data_console_format(
        self, runner: CliRunner, minimal_fixture_path: Path
    ):
        """Test debt command with console format."""
        result = runner.invoke(
            main,
            [
                "debt",
                "--codeindex-data",
                str(minimal_fixture_path),
                "--format",
                "console",
            ],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True

        data = output["data"]
        assert "message" in data
        assert "=== Technical Debt Analysis ===" in data["message"]
        assert "Overall Score: 77/100" in data["message"]
        assert "Grade: C" in data["message"]
        assert "report" in data

    def test_debt_with_minimal_data_markdown_format(
        self, runner: CliRunner, minimal_fixture_path: Path
    ):
        """Test debt command with markdown format."""
        result = runner.invoke(
            main,
            [
                "debt",
                "--codeindex-data",
                str(minimal_fixture_path),
                "--format",
                "markdown",
            ],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True

        data = output["data"]
        assert "content" in data
        content = data["content"]
        assert "# Technical Debt Analysis Report" in content
        assert "## Overall Health" in content
        assert "**Score**: 77/100 (Grade: C)" in content
        assert "## Critical Priority Issues" in content

    def test_debt_with_nonexistent_file(self, runner: CliRunner):
        """Test debt command with non-existent codeindex file."""
        result = runner.invoke(
            main, ["debt", "--codeindex-data", "/nonexistent/file.json"]
        )

        # Click validates path before our code runs
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_debt_with_invalid_json(self, runner: CliRunner, tmp_path: Path):
        """Test debt command with invalid JSON."""
        invalid_json = tmp_path / "invalid.json"
        invalid_json.write_text("{ invalid json }")

        result = runner.invoke(main, ["debt", "--codeindex-data", str(invalid_json)])

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
        assert output["error"]["code"] == "INVALID_INPUT"
        assert "Invalid JSON" in output["error"]["message"]

    def test_debt_issue_categories(
        self, runner: CliRunner, minimal_fixture_path: Path
    ):
        """Test that all expected issue categories are detected."""
        result = runner.invoke(
            main, ["debt", "--codeindex-data", str(minimal_fixture_path)]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        issues = output["data"]["issues"]

        categories = {issue["category"] for issue in issues}
        assert "god_class" in categories
        assert "god_function" in categories
        assert "test_smell" in categories

    def test_debt_severity_levels(self, runner: CliRunner, minimal_fixture_path: Path):
        """Test that all severity levels are assigned correctly."""
        result = runner.invoke(
            main, ["debt", "--codeindex-data", str(minimal_fixture_path)]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        issues = output["data"]["issues"]

        severities = {issue["severity"] for issue in issues}
        assert "P0" in severities
        assert "P1" in severities
        assert "P2" in severities

        # Verify god_class is P0
        god_class_issues = [i for i in issues if i["category"] == "god_class"]
        assert all(i["severity"] == "P0" for i in god_class_issues)

        # Verify god_function is P1
        god_function_issues = [i for i in issues if i["category"] == "god_function"]
        assert all(i["severity"] == "P1" for i in god_function_issues)

        # Verify test_smell is P2
        test_smell_issues = [i for i in issues if i["category"] == "test_smell"]
        assert all(i["severity"] == "P2" for i in test_smell_issues)

    def test_debt_complexity_estimation(
        self, runner: CliRunner, minimal_fixture_path: Path
    ):
        """Test that complexity is estimated from lines."""
        result = runner.invoke(
            main, ["debt", "--codeindex-data", str(minimal_fixture_path)]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        issues = output["data"]["issues"]

        # Find god_function issues with complexity
        god_functions = [i for i in issues if i["category"] == "god_function"]
        assert len(god_functions) == 2

        for func in god_functions:
            lines = func["metrics"]["lines"]
            complexity = func["metrics"]["complexity"]
            # Verify formula: complexity ≈ lines // 10
            assert complexity == lines // 10
