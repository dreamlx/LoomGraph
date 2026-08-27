"""Integration test: import-export workspace → embed-backfill → search.

EPIC-015 Phase 3 (#70). Validates the end-to-end flow:
1. A workspace with entities but no vectors (simulates import-export)
2. `embed-backfill -w <ws>` populates vec_node_descriptions
3. `search` returns semantic hits afterward
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main
from loomgraph.storage.sqlite_store import DEFAULT_VECTOR_DIM, SqliteGraphStore


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke_success(result):
    payload = json.loads(result.output)
    assert payload["success"], f"CLI reported error: {payload}"
    return payload["data"]


def _parse_output(result) -> dict:
    return json.loads(result.output)


# ----- End-to-end: create un-embedded workspace → backfill → search -----


def test_import_then_backfill_then_search(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    """Full flow: un-embedded workspace → embed-backfill → search hits."""
    ws = "integration-bf-test:imported"

    # Step 1: Create workspace with entities but NO embeddings
    # (simulates the state after `loomgraph import-export` when embedding
    # is disabled at import time)
    async def _seed():
        store = SqliteGraphStore(
            db_path=str(tmp_path / f"{ws}.db"),
            workspace_root=tmp_path,
            dimension=DEFAULT_VECTOR_DIM,
        )
        await store.initialize()
        try:
            # Three entities with descriptions, no embeddings
            await store.create_entity(
                "AuthService",
                {
                    "entity_type": "class",
                    "source_id": "app/auth.py:5",
                    "description": "Handles user authentication and session management",
                },
            )
            await store.create_entity(
                "PaymentGateway",
                {
                    "entity_type": "class",
                    "source_id": "app/payment.py:12",
                    "description": "Processes credit card and PayPal transactions",
                },
            )
            await store.create_entity(
                "ConfigLoader",
                {
                    "entity_type": "class",
                    "source_id": "app/config.py:3",
                    "description": "Loads YAML configuration from disk",
                },
            )
            # One entity without description (should be skipped by backfill)
            await store.create_entity(
                "HelperUtil",
                {
                    "entity_type": "class",
                    "source_id": "app/util.py:1",
                },
            )
            await store.commit() if hasattr(store, "commit") else None
            return store
        finally:
            await store.close()

    asyncio.run(_seed())
    # Verify: no vectors yet
    vc = asyncio.run(_count_vectors(tmp_path, ws))
    assert vc == 0, f"Expected 0 vectors, got {vc}"

    # Step 2: Run embed-backfill
    # Patch prepare_workspace_store to use our temp db

    async def _make_store(workspace=None):
        s = SqliteGraphStore(
            db_path=str(tmp_path / f"{ws}.db"),
            workspace_root=tmp_path,
            dimension=DEFAULT_VECTOR_DIM,
        )
        await s.initialize()
        return s

    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        _make_store,
    )
    monkeypatch.setattr(
        "loomgraph.storage.factory.workspace_exists", lambda _workspace: True
    )

    # Enable embedding
    from loomgraph.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s.embedding, "enabled", True)

    # Stub the embed client
    fake_vec = [0.25] * DEFAULT_VECTOR_DIM

    class FakeEmbedResult:
        def __init__(self, count):
            self.embeddings = [fake_vec] * count
            self.model = "test-model"

    embed_call_count = 0

    class FakeClient:
        async def embed(self, texts):
            nonlocal embed_call_count
            embed_call_count += 1
            return FakeEmbedResult(len(texts))
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

    # Monkeypatch get_auto_workspace to return our workspace
    monkeypatch.setattr(
        "loomgraph.cli._common.get_auto_workspace",
        lambda w: w if w else ws,
    )

    # Run backfill
    result = runner.invoke(main, ["embed-backfill", "-w", ws])
    data = _invoke_success(result)
    assert data["embedded"] == 3, f"Expected 3 embedded, got {data}"
    assert data["total_entities"] == 4

    # Step 3: Verify vectors are now present
    vc = asyncio.run(_count_vectors(tmp_path, ws))
    assert vc == 3, f"Expected 3 vectors after backfill, got {vc}"

    # Step 4: Run search and verify semantic hits
    # Verify directly against the store (search_similar KNN over backfilled vectors)
    async def _search_auth():
        s = await _make_store(ws)
        try:
            vc2 = await s.vector_count()
            assert vc2 == 3, f"vector_count={vc2}"
            hits = await s.search_similar(fake_vec, k=3)
            return hits
        finally:
            await s.close()

    hits = asyncio.run(_search_auth())
    assert len(hits) >= 1, "Expected at least 1 search hit after backfill"


# ----- Idempotency: backfill on already-embedded workspace -----


def test_backfill_idempotent_on_already_embedded(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    """Running backfill twice does not re-embed and does not error."""
    ws = "integration-idem:imported"
    fake_vec = [0.5] * DEFAULT_VECTOR_DIM

    async def _make_store(workspace=None):
        s = SqliteGraphStore(
            db_path=str(tmp_path / f"{ws}.db"),
            workspace_root=tmp_path,
            dimension=DEFAULT_VECTOR_DIM,
        )
        await s.initialize()
        return s

    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        _make_store,
    )
    monkeypatch.setattr(
        "loomgraph.storage.factory.workspace_exists", lambda _workspace: True
    )

    # Pre-seed with entities AND vectors
    async def _seed():
        s = await _make_store()
        try:
            await s.create_entity("Foo", {
                "entity_type": "class",
                "source_id": "f.py",
                "description": "foo desc",
                "embedding": fake_vec,
            })
        finally:
            await s.close()
    asyncio.run(_seed())

    # Enable embedding
    from loomgraph.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s.embedding, "enabled", True)

    monkeypatch.setattr(
        "loomgraph.cli._common.get_auto_workspace",
        lambda w: w if w else ws,
    )

    # First backfill → skipped
    result1 = runner.invoke(main, ["embed-backfill", "-w", ws])
    data1 = _invoke_success(result1)
    assert data1["skipped"] is True

    # Second backfill → still skipped, no error
    result2 = runner.invoke(main, ["embed-backfill", "-w", ws])
    data2 = _invoke_success(result2)
    assert data2["skipped"] is True


# ----- Helper -----


async def _count_vectors(tmp_path: Path, ws: str) -> int:
    store = SqliteGraphStore(
        db_path=str(tmp_path / f"{ws}.db"),
        workspace_root=tmp_path,
        dimension=DEFAULT_VECTOR_DIM,
    )
    await store.initialize()
    try:
        return await store.vector_count()
    finally:
        await store.close()
