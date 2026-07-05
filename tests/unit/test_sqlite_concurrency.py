"""SQLite WAL + busy_timeout concurrency hardening regression tests.

MCP `refresh` (long-lived server process) and a git-hook `loomgraph update`
(subprocess) can write the same `~/.loomgraph/{ws}.db` from two OS
processes. The asyncio.Lock in SqliteGraphStore only serializes ops within
one process; cross-process safety comes from SQLite itself — which requires
WAL journal mode + a non-zero busy_timeout. These tests pin that contract.

Note: WAL does NOT engage on `:memory:` databases (they are always
`memory` journal mode), so every test here uses a filesystem path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from loomgraph.storage.sqlite_store import SqliteGraphStore


def _entity(name: str) -> dict[str, str]:
    return {"entity_name": name, "source_id": "pkg/a.py:1", "description": name}


async def test_wal_journal_mode_applied_on_open(tmp_path: Path) -> None:
    store = SqliteGraphStore(db_path=tmp_path / "t.db")
    await store.initialize()
    try:
        mode = await store._run(
            lambda c: c.execute("PRAGMA journal_mode").fetchone()[0]
        )
        assert mode == "wal"
    finally:
        await store.close()


async def test_busy_timeout_applied_on_open(tmp_path: Path) -> None:
    store = SqliteGraphStore(db_path=tmp_path / "t.db")
    await store.initialize()
    try:
        ms = await store._run(
            lambda c: c.execute("PRAGMA busy_timeout").fetchone()[0]
        )
        assert ms == 5000
    finally:
        await store.close()


async def test_two_writers_dont_immediately_lock(tmp_path: Path) -> None:
    """Two store instances on the same .db file: interleaved writes within
    the busy_timeout window must NOT raise `database is locked`.

    WAL permits one writer at a time; the second writer waits up to
    busy_timeout (5s) rather than failing immediately. This is the exact
    scenario MCP-refresh + git-hook-update creates.
    """
    db = tmp_path / "shared.db"
    s1 = SqliteGraphStore(db_path=db)
    s2 = SqliteGraphStore(db_path=db)
    await s1.initialize()
    await s2.initialize()
    try:
        await s1.insert_custom_kg([_entity("a")], [], [])
        await s2.insert_custom_kg([_entity("b")], [], [])
        await s1.insert_custom_kg([_entity("c")], [], [])
        # All three writes committed without OperationalError.
        stats = await s1.get_graph_stats()
        assert stats["entity_count"] >= 3
    except sqlite3.OperationalError as exc:
        pytest.fail(f"should serialize via WAL+busy_timeout, not lock: {exc}")
    finally:
        await s1.close()
        await s2.close()


async def test_close_checkpoints_wal(tmp_path: Path) -> None:
    """After graceful close, the -wal sidecar is absent or zero-length.

    `wal_checkpoint(TRUNCATE)` on close makes a bundled .db self-contained
    (no uncommitted writes stranded in -wal). Required for customer bundles
    that ship/copy just the .db.
    """
    db = tmp_path / "ckpt.db"
    store = SqliteGraphStore(db_path=db)
    await store.initialize()
    await store.insert_custom_kg([_entity("a")], [], [])
    await store.close()

    wal = tmp_path / (db.name + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0
