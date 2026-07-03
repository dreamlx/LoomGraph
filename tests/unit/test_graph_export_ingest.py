"""graph_export_ingest — the shared graph-export ingestion pipeline (#66).

`run_graph_export` shells out to `codeindex graph-export` and reads the NDJSON
via `GraphExportReader`; `ingest` does the embed + insert (mirroring
`import-export`). Used by both `loomgraph index` and `loomgraph update`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from loomgraph.core.config import reset_settings
from loomgraph.core.graph_export_ingest import (
    GraphExportError,
    ingest,
    run_graph_export,
)
from loomgraph.core.models import EntityData, RelationData

META = {
    "type": "meta",
    "schema_version": 0,
    "generator": "codeindex",
    "provenance_completeness": "ast-only: x",
}
E1 = {
    "type": "entity",
    "id": "pkg.a.handle",
    "entity_type": "function",
    "source_id": "pkg/a.py:1",
    "description": "handles a",
    "signature": "def handle(): ...",
    "provenance": "ast",
}
E2 = {
    "type": "entity",
    "id": "pkg.b.handle",
    "entity_type": "function",
    "source_id": "pkg/b.py:1",
    "description": "handles b",
    "signature": "def handle(): ...",
    "provenance": "ast",
}
EDGE = {
    "type": "edge",
    "kind": "CALLS",
    "src": "pkg.a.handle",
    "dst": "pkg.b.handle",
    "resolution_qualifier": "resolved",
    "source_id": "pkg/a.py:2",
    "dst_raw": "pkg.b.handle",
}


def _ndjson(records: list[dict]) -> str:
    return "\n".join(json.dumps(r) for r in records) + "\n"


@pytest.fixture(autouse=True)
def _embedding_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep embedding disabled so `ingest` tests never hit a real client."""
    monkeypatch.delenv("LOOMGRAPH_EMBEDDING__ENABLED", raising=False)
    reset_settings()
    yield
    reset_settings()


class _FakeProc:
    """Minimal stand-in for a subprocess.Popen result."""

    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0,
                 timeout: bool = False) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._timeout = timeout
        self.killed = False
        self._first = True

    def communicate(self, timeout: float | None = None):
        if self._first:
            self._first = False
            if self._timeout:
                raise subprocess.TimeoutExpired(cmd="codeindex", timeout=timeout or 1)
        return (self._stdout, self._stderr)

    def kill(self) -> None:
        self.killed = True


# ----- run_graph_export ----------------------------------------------------


def test_run_graph_export_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    proc = _FakeProc(stdout=_ndjson([META, E1, E2, EDGE]))
    monkeypatch.setattr(
        "loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc
    )
    entities, relations, summary = run_graph_export(tmp_path)
    assert len(entities) == 2
    assert [e.entity_name for e in entities] == ["pkg.a.handle", "pkg.b.handle"]
    assert len(relations) == 1
    assert relations[0].src_id == "pkg.a.handle"
    assert relations[0].tgt_id == "pkg.b.handle"
    assert summary.entity_count == 2
    assert summary.relation_count == 1


def test_run_graph_export_invokes_codeindex_graph_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The subprocess must call `codeindex graph-export --root <repo> -o -`."""
    captured: dict[str, Any] = {}
    proc = _FakeProc(stdout=_ndjson([META, E1]))

    def _fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return proc

    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", _fake_popen)
    run_graph_export(tmp_path)
    cmd = captured["args"][0]
    assert cmd[:2] == ["codeindex", "graph-export"]
    assert "--root" in cmd and str(tmp_path) in cmd
    assert "-o" in cmd and "-" in cmd  # emit to stdout


def test_run_graph_export_nonzero_exit_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proc = _FakeProc(returncode=1, stderr="codeindex blew up")
    monkeypatch.setattr(
        "loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc
    )
    with pytest.raises(GraphExportError, match="codeindex blew up"):
        run_graph_export(tmp_path)


def test_run_graph_export_timeout_kills_and_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proc = _FakeProc(timeout=True)
    monkeypatch.setattr(
        "loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc
    )
    with pytest.raises(GraphExportError, match="timed out"):
        run_graph_export(tmp_path, timeout=5)
    assert proc.killed is True


# ----- ingest --------------------------------------------------------------


class _FakeStore:
    def __init__(self) -> None:
        self.delete_all = AsyncMock()
        self.insert_custom_kg = AsyncMock()
        self.get_graph_stats = AsyncMock(return_value={"entities": 2, "relations": 1})


def _sample_entities() -> list[EntityData]:
    return [
        EntityData(entity_name="pkg.a.handle", entity_data={"description": "a"}),
        EntityData(entity_name="pkg.b.handle", entity_data={"description": "b"}),
    ]


def _sample_relations() -> list[RelationData]:
    return [
        RelationData(
            src_id="pkg.a.handle",
            tgt_id="pkg.b.handle",
            edge_data={"keywords": "CALLS"},
        )
    ]


async def test_ingest_clear_true_deletes_then_inserts_empty_chunks() -> None:
    store = _FakeStore()
    result = await ingest(_sample_entities(), _sample_relations(), store, clear=True)

    store.delete_all.assert_awaited_once()
    store.insert_custom_kg.assert_awaited_once()
    args = store.insert_custom_kg.call_args.args
    # chunks (3rd positional) must be empty — graph-export carries no vector data
    assert args[2] == []
    assert result["cleared"] is True
    assert result["entities_created"] == 2
    assert result["relations_created"] == 1
    assert result["store_stats"] == {"entities": 2, "relations": 1}


async def test_ingest_clear_false_skips_delete_all() -> None:
    store = _FakeStore()
    await ingest(_sample_entities(), _sample_relations(), store, clear=False)

    store.delete_all.assert_not_awaited()
    store.insert_custom_kg.assert_awaited_once()


async def test_ingest_progress_callback_fires_clear() -> None:
    """clear=True → on_progress fires clear → embed → insert, in that order."""
    store = _FakeStore()
    phases: list[str] = []

    def _cb(phase: str, n_entities: int, n_relations: int) -> None:
        phases.append(phase)

    await ingest(
        _sample_entities(), _sample_relations(), store, clear=True, on_progress=_cb
    )
    assert phases == ["clear", "embed", "insert"]


async def test_ingest_progress_callback_fires_no_clear() -> None:
    """clear=False → on_progress skips `clear` (delete_all is not called)."""
    store = _FakeStore()
    phases: list[str] = []

    def _cb(phase: str, n_entities: int, n_relations: int) -> None:
        phases.append(phase)

    await ingest(
        _sample_entities(), _sample_relations(), store, clear=False, on_progress=_cb
    )
    assert phases == ["embed", "insert"]
