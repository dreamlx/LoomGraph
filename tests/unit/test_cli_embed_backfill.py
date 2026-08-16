"""Unit tests for `loomgraph embed-backfill` CLI command.

Validates:
- Idempotent: already-embedded workspace → skipped, no error
- Embedding disabled → actionable error
- Missing workspace → actionable error
- Success path: entities get embedded, vectors written
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke_success(result):
    payload = json.loads(result.output)
    assert payload["success"], f"CLI reported error: {payload}"
    return payload["data"]


def _invoke_error(result):
    payload = json.loads(result.output)
    assert not payload["success"], f"Expected error, got: {payload}"
    return payload["error"]


# ----- Success: idempotent (already embedded) -----

def test_already_embedded_skips(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    """When vector_count > 0, backfill returns skipped without embedding."""
    ws = "test-skip:imported"

    async def fake_prepare(workspace):
        store = MagicMock()
        store.vector_count = AsyncMock(return_value=5)
        store.get_all_entities = AsyncMock(return_value=[
            {"entity_name": "Foo", "description": "desc", "source_id": "a.py"},
        ])
        return ws, store

    monkeypatch.setattr(
        "loomgraph.cli._backfill.prepare_workspace_store",
        fake_prepare,
    )

    result = runner.invoke(main, ["embed-backfill", "-w", ws])
    data = _invoke_success(result)
    assert data["skipped"] is True
    assert data["vector_count"] == 5


# ----- Error: embedding disabled -----

def test_embedding_disabled_errors(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    """When embedding.enabled is False, backfill errors with actionable message."""
    ws = "test-disabled:imported"

    async def fake_prepare(workspace):
        store = MagicMock()
        store.vector_count = AsyncMock(return_value=0)
        store.get_all_entities = AsyncMock(return_value=[
            {"entity_name": "Foo", "description": "desc", "source_id": "a.py"},
        ])
        return ws, store

    monkeypatch.setattr(
        "loomgraph.cli._backfill.prepare_workspace_store",
        fake_prepare,
    )

    # Ensure embedding is disabled
    from loomgraph.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s.embedding, "enabled", False)

    result = runner.invoke(main, ["embed-backfill", "-w", ws])
    assert result.exit_code != 0


# ----- Error: missing workspace -----

def test_missing_workspace_errors(
    runner: CliRunner, monkeypatch
) -> None:
    """When the workspace has no entities, backfill reports error."""
    import click

    async def fake_prepare(workspace):
        raise click.ClickException("Workspace 'nope' has no entities.")

    monkeypatch.setattr(
        "loomgraph.cli._backfill.prepare_workspace_store",
        fake_prepare,
    )

    result = runner.invoke(main, ["embed-backfill", "-w", "nope"])
    error = _invoke_error(result)
    assert error["code"] == "EMBEDDING_NOT_INDEXED"


# ----- Success: normal backfill -----

def test_backfill_embeds_and_writes_vectors(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    """Happy path: entities with descriptions → embed → write → success."""
    # Pin the explicit provider: without this, environments lacking a local
    # .loomgraph.yaml (CI) resolve  → builtin → missing-[embed] error.
    monkeypatch.setenv("LOOMGRAPH_EMBEDDING__PROVIDER", "ollama")
    from loomgraph.storage.sqlite_store import DEFAULT_VECTOR_DIM

    ws = "test-bf:imported"
    fake_vec = [0.1] * DEFAULT_VECTOR_DIM
    write_count = 0

    async def fake_prepare(workspace):
        store = MagicMock()
        store.vector_count = AsyncMock(return_value=0)
        store.get_all_entities = AsyncMock(return_value=[
            {"entity_name": "Foo", "description": "first entity", "source_id": "a.py"},
            {"entity_name": "Bar", "description": "second entity", "source_id": "b.py"},
            {"entity_name": "Baz", "description": "", "source_id": "c.py"},
        ])

        async def _write_embeddings(tuples):
            nonlocal write_count
            write_count = len(tuples)
            return len(tuples)
        store.write_embeddings = _write_embeddings
        return ws, store

    monkeypatch.setattr(
        "loomgraph.cli._backfill.prepare_workspace_store",
        fake_prepare,
    )

    # Enable embedding
    from loomgraph.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s.embedding, "enabled", True)

    # Stub the embed client
    class FakeEmbedResult:
        embeddings = [fake_vec, fake_vec]
        model = "test-model"

    class FakeClient:
        async def embed(self, texts):
            return FakeEmbedResult()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    def fake_create_client():
        return FakeClient()

    monkeypatch.setattr(
        "loomgraph.storage.factory.create_embedding_client",
        fake_create_client,
    )

    result = runner.invoke(main, ["embed-backfill", "-w", ws])
    data = _invoke_success(result)
    assert data["embedded"] == 2
    assert data["total_entities"] == 3
    assert data["model"] == "test-model"
    assert write_count == 2


# ----- Success: no entities with descriptions -----

def test_no_descriptions_returns_zero(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    """When entities exist but none have descriptions, backfill returns 0."""
    ws = "test-nodesc:imported"

    async def fake_prepare(workspace):
        store = MagicMock()
        store.vector_count = AsyncMock(return_value=0)
        store.get_all_entities = AsyncMock(return_value=[
            {"entity_name": "A", "source_id": "a.py"},
            {"entity_name": "B", "source_id": "b.py"},
        ])
        return ws, store

    monkeypatch.setattr(
        "loomgraph.cli._backfill.prepare_workspace_store",
        fake_prepare,
    )

    from loomgraph.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s.embedding, "enabled", True)

    result = runner.invoke(main, ["embed-backfill", "-w", ws])
    data = _invoke_success(result)
    assert data["embedded"] == 0
    assert "skipped_reason" in data
