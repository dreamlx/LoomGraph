"""MCP branch-diff composite tests (#191)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from loomgraph.mcp.tools import branch_diff as t_branch_diff


@pytest.mark.asyncio
async def test_branch_diff_provisions_both_refs_and_returns_cli_shape(
    tmp_path: Path,
) -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40
    provisioned = {
        "main": {
            "ref": "main",
            "sha": base_sha,
            "workspace": "repo:main",
            "provisioned": "created",
        },
        "feature": {
            "ref": "feature",
            "sha": head_sha,
            "workspace": "repo:feature",
            "provisioned": "reused",
        },
    }

    def fake_provision(
        _repo: Path, _repo_dir: str, ref: str, sha: str, *, backend: str
    ):
        assert backend == "codeindex"
        assert sha == provisioned[ref]["sha"]
        return provisioned[ref]

    with (
        patch.object(t_branch_diff, "is_git_repository", return_value=True),
        patch.object(
            t_branch_diff,
            "check_codeindex",
            return_value={"installed": True, "version": "0.37.0"},
        ),
        patch.object(
            t_branch_diff,
            "resolve_ref",
            side_effect=[base_sha, head_sha],
        ),
        patch.object(t_branch_diff, "_provision_ref", side_effect=fake_provision),
        patch.object(
            t_branch_diff,
            "_async_branch_diff",
            new=AsyncMock(return_value={"entities_added": [], "entities_removed": []}),
        ),
    ):
        contents = await t_branch_diff.handle(
            {
                "base_ref": "main",
                "head_ref": "feature",
                "repo_path": str(tmp_path),
            }
        )

    payload = json.loads(contents[0].text)
    assert payload["success"] is True
    data = payload["data"]
    assert data["base"] == provisioned["main"]
    assert data["head"] == provisioned["feature"]
    assert data["diff"]["entities_added"] == []


@pytest.mark.asyncio
async def test_branch_diff_invalid_input_is_structured_error() -> None:
    contents = await t_branch_diff.handle({"base_ref": "main"})
    payload = json.loads(contents[0].text)

    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_branch_diff_wraps_provisioning_errors() -> None:
    with patch.object(
        t_branch_diff,
        "_run_branch_diff",
        new=AsyncMock(side_effect=RuntimeError("unknown ref")),
    ):
        contents = await t_branch_diff.handle(
            {"base_ref": "main", "head_ref": "feature"}
        )

    payload = json.loads(contents[0].text)
    assert payload["success"] is False
    assert payload["error"]["code"] == "BRANCH_DIFF_FAILED"
    assert "unknown ref" in payload["error"]["message"]


def test_branch_diff_tool_registered() -> None:
    from loomgraph.mcp.server import _TOOL_SPECS

    assert "loomgraph_branch_diff" in {spec.name for spec in _TOOL_SPECS}
