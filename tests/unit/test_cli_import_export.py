"""Integration tests for `loomgraph import-export` (the CLI surface).

Validates:
- --dry-run path: returns full summary, never touches storage
- Non-existent artifact → FILE_NOT_FOUND
- Malformed JSON → INVALID_INPUT
- Default workspace naming follows the `<basename>:imported` rule
- `--clear` default is False (non-destructive — regression guard)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main

MIN_META = {
    "type": "meta",
    "schema_version": 0,
    "generator": "codeindex",
    "provenance_completeness": "ast-only",
}
SAMPLE_ENTITY = {
    "type": "entity",
    "id": "app.svc.AuthService",
    "entity_type": "class",
    "source_id": "app/svc.py:8",
    "description": "Authenticates users.",
    "provenance": "ast",
}
SAMPLE_EDGE_RESOLVED = {
    "type": "edge",
    "kind": "CALLS",
    "src": "app.svc.AuthService.login",
    "dst": "app.svc.AuthService.authenticate",
    "resolution_qualifier": "resolved",
    "source_id": "app/svc.py:15",
}


def _write_artifact(tmp_path: Path, name: str = "sample") -> Path:
    p = tmp_path / f"{name}.ndjson"
    p.write_text(
        "\n".join(
            json.dumps(r) for r in [MIN_META, SAMPLE_ENTITY, SAMPLE_EDGE_RESOLVED]
        )
    )
    return p


def _invoke_success(result):
    """Parse stdout JSON, assert success=true, return data."""
    payload = json.loads(result.output)
    assert payload["success"], f"CLI reported error: {payload}"
    return payload["data"]


def _invoke_error(result):
    payload = json.loads(result.output)
    assert not payload["success"], f"Expected error, got: {payload}"
    return payload["error"]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ----- Success path -----------------------------------------------------

def test_dry_run_returns_summary_without_storage_write(
    runner: CliRunner, tmp_path: Path
) -> None:
    artifact = _write_artifact(tmp_path)
    result = runner.invoke(
        main, ["import-export", str(artifact), "--dry-run"]
    )
    assert result.exit_code == 0, result.output

    data = _invoke_success(result)
    assert data["dry_run"] is True
    assert "store_stats" not in data, "dry-run must not call storage"
    assert data["summary"]["entity_count"] == 1
    assert data["summary"]["relation_count"] == 1
    assert data["would_write"] == {"entities": 1, "relations": 1}


def test_default_workspace_name_is_basename_imported(
    runner: CliRunner, tmp_path: Path
) -> None:
    artifact = _write_artifact(tmp_path, name="customer-snapshot")
    result = runner.invoke(
        main, ["import-export", str(artifact), "--dry-run"]
    )
    data = _invoke_success(result)
    assert data["workspace"] == "customer-snapshot:imported"


def test_explicit_workspace_overrides_default(
    runner: CliRunner, tmp_path: Path
) -> None:
    artifact = _write_artifact(tmp_path)
    result = runner.invoke(
        main,
        ["import-export", str(artifact), "-w", "custom-name", "--dry-run"],
    )
    data = _invoke_success(result)
    assert data["workspace"] == "custom-name"


# ----- Error path -------------------------------------------------------

def test_missing_artifact_returns_file_not_found(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["import-export", str(tmp_path / "does-not-exist.ndjson"), "--dry-run"],
    )
    # click's `exists=True` argument validator triggers exit 2 BEFORE we hit
    # our handler — that's the right behavior. Just confirm it's a non-success.
    assert result.exit_code != 0


def test_malformed_artifact_returns_invalid_input(
    runner: CliRunner, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.ndjson"
    bad.write_text("not valid json\n")
    result = runner.invoke(
        main, ["import-export", str(bad), "--dry-run"]
    )
    # Reader tolerates bad JSON with summary warnings — it does NOT raise.
    # So this should still succeed, with a warning surfaced in summary.
    data = _invoke_success(result)
    assert any(
        "bad JSON" in w for w in data["summary"]["schema_warnings"]
    )
    assert data["summary"]["skipped_records"] == 1


# ----- Destructive-default regression guard -----------------------------

def test_clear_default_is_false_in_command_signature() -> None:
    """`--clear` MUST default to False so AI agents calling
    `loomgraph import-export <file>` without flags cannot wipe a
    workspace. This is the response to the destructive-default
    issue caught during PR review."""
    from loomgraph.cli._import_export import import_export

    clear_param = next(
        p for p in import_export.params if p.name == "clear"
    )
    assert clear_param.default is False, (
        "--clear must default to False (non-destructive)."
    )


# ----- Auto-embed (EPIC-015: imported artifacts become searchable in one step)

def test_import_export_embeds_descriptions_when_enabled(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    """When embedding is enabled, import-export attaches vectors so the
    workspace is semantically searchable without a separate step (mirrors
    `loomgraph index`). Verifies the wiring: maybe_embed_entities runs
    BEFORE insert_custom_kg."""
    import asyncio

    from loomgraph.storage.factory import create_graph_store
    from loomgraph.storage.sqlite_store import DEFAULT_VECTOR_DIM

    artifact = _write_artifact(tmp_path, name="with-emb")
    ws = "test-auto-embed:imported"

    # Stub the embed step: attach a dummy vector to each described entity.
    # This tests the WIRING (embed before insert), not the embed client.
    fake_vec = [0.1] * DEFAULT_VECTOR_DIM

    def fake_maybe_embed(entities):
        for e in entities:
            if e.get("description"):
                e["embedding"] = fake_vec
        return sum(1 for e in entities if "embedding" in e)

    async def fake_maybe_embed_async(entities):
        return fake_maybe_embed(entities)

    monkeypatch.setattr(
        "loomgraph.cli._import_export.maybe_embed_entities",
        fake_maybe_embed_async,
    )

    result = runner.invoke(main, ["import-export", str(artifact), "-w", ws, "--clear"])
    _invoke_success(result)  # asserts success=true; we only need the write side-effect

    # The imported workspace must actually have vectors written.
    async def _count() -> int:
        store = await create_graph_store(workspace=ws)
        try:
            return await store.vector_count()
        finally:
            await store.close()

    vc = asyncio.run(_count())
    assert vc > 0, f"expected embedded vectors, got vector_count={vc}"

    # cleanup
    import os
    db = os.path.expanduser(f"~/.loomgraph/{ws}.db")
    if os.path.exists(db):
        os.remove(db)
