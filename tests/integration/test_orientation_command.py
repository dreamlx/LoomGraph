"""CLI integration for the read-only orientation command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main

pytestmark = pytest.mark.integration


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _seed_repo(repo: Path) -> tuple[str, str]:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.test")
    _git(repo, "config", "user.name", "t")
    (repo / "example.py").write_text("VALUE = 1\n")
    _git(repo, "add", "example.py")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "example.py").write_text("VALUE = 2\n")
    _git(repo, "commit", "-qam", "head")
    return base_sha, _git(repo, "rev-parse", "HEAD")


def test_orient_resolves_real_git_refs_without_provisioning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_sha, head_sha = _seed_repo(tmp_path)
    monkeypatch.setattr(
        "loomgraph.cli._orientation.check_codeindex", lambda: {"installed": True}
    )
    before = sorted(path.name for path in tmp_path.iterdir())

    with monkeypatch.context() as context:
        context.chdir(tmp_path)
        result = CliRunner().invoke(
            main,
            [
                "orient",
                "--task-kind",
                "temporal-review",
                "--base-ref",
                "HEAD~1",
                "--head-ref",
                "HEAD",
            ],
        )

    assert result.exit_code == 0
    response = json.loads(result.stdout)["data"]
    assert response["availability"] == "conditional"
    assert response["comparison_request"]["base_sha"] == base_sha
    assert response["comparison_request"]["head_sha"] == head_sha
    assert response["execution_boundary"]["orientation"] == "read_only"
    assert sorted(path.name for path in tmp_path.iterdir()) == before
