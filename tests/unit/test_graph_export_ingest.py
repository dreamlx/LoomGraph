"""graph_export_ingest — the shared graph-export ingestion pipeline (#66).

`run_graph_export` shells out to `codeindex graph-export` and reads the NDJSON
via `GraphExportReader`; `ingest` does the embed + insert (mirroring
`import-export`). Used by both `loomgraph index` and `loomgraph update`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from loomgraph.core.config import reset_settings
from loomgraph.core.graph_export_ingest import (
    GraphExportError,
    assess_export,
    ingest,
    ingest_incremental,
    run_graph_export,
)
from loomgraph.core.models import EntityData, RelationData
from loomgraph.io.export_reader import ImportSummary

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

    def __init__(
        self, *, stdout: str = "", stderr: str = "", returncode: int = 0, timeout: bool = False
    ) -> None:
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
    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc)
    entities, relations, summary, _ = run_graph_export(tmp_path)
    assert len(entities) == 2
    assert [e.entity_name for e in entities] == ["pkg.a.handle", "pkg.b.handle"]
    assert len(relations) == 1
    assert relations[0].src_id == "pkg.a.handle"
    assert relations[0].tgt_id == "pkg.b.handle"
    assert summary.entity_count == 2
    assert summary.relation_count == 1


def test_run_graph_export_returns_stderr_warnings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#108: codeindex's partial-graph WARNING (few-entity false-positive, #131)
    must reach the caller so `loomgraph index` isn't a silent success on a
    misconfigured non-Python repo. returncode is 0; stderr holds the warning."""
    proc = _FakeProc(
        stdout=_ndjson([META, E1]),
        stderr=(
            "WARNING: partial graph — graph-export captured 1 entities but "
            "configured languages ['python'] leave code files uncaptured "
            "(.tsx (1), .ts (1)). Add typescript to .codeindex.yaml "
            "`languages:` to capture them\n"
        ),
    )
    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc)
    entities, relations, summary, warnings = run_graph_export(tmp_path)
    assert len(entities) == 1
    assert len(warnings) == 1
    assert "partial graph" in warnings[0]
    assert "typescript" in warnings[0]


def test_run_graph_export_no_warnings_when_stderr_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A clean export returns an empty warnings list (not None)."""
    proc = _FakeProc(stdout=_ndjson([META, E1]), stderr="")
    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc)
    _, _, _, warnings = run_graph_export(tmp_path)
    assert warnings == []


def test_run_graph_export_surfaces_parser_library_not_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#118: codeindex emits per-file ``Parser library not installed for <lang>``
    lines (no ``WARNING:`` prefix) when a tree-sitter grammar is missing. These
    carry the actual root cause + fix (``pip install tree-sitter-<lang>``) and
    must reach the caller — otherwise a missing-grammar repo indexes to 0 as a
    silent success. codeindex repeats the line per file; dedupe to one.
    """
    proc = _FakeProc(
        stdout=_ndjson([META]),
        stderr=(
            "Parser library not installed for swift: tree-sitter-swift is not "
            "installed. Install it with: pip install tree-sitter-swift "
            "(Sources/App/AppState.swift)\n"
            "Parser library not installed for swift: tree-sitter-swift is not "
            "installed. Install it with: pip install tree-sitter-swift "
            "(Sources/App/ContentView.swift)\n"
            "WARNING: no indexable directories found.\n"
        ),
    )
    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc)
    _, _, _, warnings = run_graph_export(tmp_path)
    # The parser-missing diagnostic is surfaced exactly once (deduped)…
    parser_lines = [w for w in warnings if "Parser library not installed" in w]
    assert len(parser_lines) == 1
    assert "tree-sitter-swift" in parser_lines[0]
    # …alongside the regular WARNING line.
    assert any("no indexable directories" in w for w in warnings)


def test_run_graph_export_parser_warning_dedups_per_language(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#178: the parser-missing dedup key is the LANGUAGE, not a global flag.
    codeindex emits one line per missing grammar per file; #118's boolean
    dedup collapsed *different* languages too, so a multi-language repo
    surfaced one missing grammar per index round (dogfood: 3 rounds to
    discover typescript→java→javascript). Each language must appear exactly
    once, all languages in one run.
    """
    proc = _FakeProc(
        stdout=_ndjson([META]),
        stderr=(
            "Parser library not installed for typescript: tree-sitter-typescript "
            "is not installed. Install it with: pip install tree-sitter-typescript "
            "(tests/fixtures/typescript/service.ts)\n"
            "Parser library not installed for java: tree-sitter-java is not "
            "installed. Install it with: pip install tree-sitter-java "
            "(tests/fixtures/cli_parse/Service.java)\n"
            "Parser library not installed for javascript: tree-sitter-javascript "
            "is not installed. Install it with: pip install tree-sitter-javascript "
            "(tests/fixtures/typescript/app.js)\n"
            "Parser library not installed for typescript: tree-sitter-typescript "
            "is not installed. Install it with: pip install tree-sitter-typescript "
            "(tests/fixtures/typescript/component.tsx)\n"
        ),
    )
    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc)
    _, _, _, warnings = run_graph_export(tmp_path)
    parser_lines = [w for w in warnings if "Parser library not installed" in w]
    # All three languages surfaced in ONE run…
    assert len(parser_lines) == 3
    langs = {line.split(" for ")[1].split(":")[0] for line in parser_lines}
    assert langs == {"typescript", "java", "javascript"}
    # …and per-language repetition (typescript appears twice in stderr) deduped.
    ts_lines = [ln for ln in parser_lines if "for typescript" in ln]
    assert len(ts_lines) == 1


def test_run_graph_export_invokes_codeindex_graph_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The subprocess must call `codeindex graph-export --root <repo> -o -`.

    Invoke via the venv python (``sys.executable -m codeindex.cli``), NOT a bare
    ``codeindex`` PATH lookup — otherwise a stale codeindex elsewhere on PATH
    (e.g. pipx) shadows the pinned ``ai-codeindex`` dep (#76 PATH bypass).
    """
    captured: dict[str, Any] = {}
    proc = _FakeProc(stdout=_ndjson([META, E1]))

    def _fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return proc

    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", _fake_popen)
    run_graph_export(tmp_path)
    cmd = captured["args"][0]
    # Runs under loomgraph's own interpreter (same venv as the pinned ai-codeindex)
    # and goes through the `codeindex.cli` module entry point — never bare `codeindex`.
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-m", "codeindex.cli", "graph-export"]
    assert "--root" in cmd and str(tmp_path) in cmd
    assert "-o" in cmd and "-" in cmd  # emit to stdout


def test_run_graph_export_does_not_bypass_venv_via_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression guard for the #76 PATH bypass: the command must NOT start with
    a bare ``codeindex`` (which resolves via PATH and can pick up a stale
    pipx/global install, ignoring the ``ai-codeindex`` pin). Must use sys.executable.
    """
    captured: dict[str, Any] = {}
    proc = _FakeProc(stdout=_ndjson([META, E1]))

    def _fake_popen(*args, **kwargs):
        captured["args"] = args
        return proc

    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", _fake_popen)
    run_graph_export(tmp_path)
    cmd = captured["args"][0]
    assert cmd[0] != "codeindex", (
        "must invoke codeindex via sys.executable (venv python), not a bare PATH lookup"
    )
    assert cmd[0] == sys.executable


def test_run_graph_export_nonzero_exit_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proc = _FakeProc(returncode=1, stderr="codeindex blew up")
    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc)
    with pytest.raises(GraphExportError, match="codeindex blew up"):
        run_graph_export(tmp_path)


def test_run_graph_export_timeout_kills_and_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proc = _FakeProc(timeout=True)
    monkeypatch.setattr("loomgraph.core.graph_export_ingest.Popen", lambda *a, **kw: proc)
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

    await ingest(_sample_entities(), _sample_relations(), store, clear=True, on_progress=_cb)
    assert phases == ["clear", "embed", "insert"]


async def test_ingest_progress_callback_fires_no_clear() -> None:
    """clear=False → on_progress skips `clear` (delete_all is not called)."""
    store = _FakeStore()
    phases: list[str] = []

    def _cb(phase: str, n_entities: int, n_relations: int) -> None:
        phases.append(phase)

    await ingest(_sample_entities(), _sample_relations(), store, clear=False, on_progress=_cb)
    assert phases == ["embed", "insert"]


# ----- ingest_incremental (per-file warm-diff, 路 B) -------------------------


class _FakeStoreIncremental:
    """Store stub for ingest_incremental: dict-backed, tracks symbol-level
    diff calls (get_source_ids / get_entities_by_source / delete_entities)."""

    def __init__(self, entities_by_source: dict[str, list[dict]] | None = None) -> None:
        self._entities: dict[str, dict[str, Any]] = {}
        for ents in (entities_by_source or {}).values():
            for e in ents:
                self._entities[e["entity_name"]] = dict(e)
        self.deleted_entity_names: list[str] = []
        self.deleted_source_ids: list[str] = []  # legacy delete_by_source tracker
        self.insert_custom_kg = AsyncMock()
        self.get_graph_stats = AsyncMock(return_value={"entities": 1, "relations": 0})

    async def get_source_ids(self, source_prefix: str | None = None) -> list[str]:
        sids = {e.get("source_id") for e in self._entities.values()}
        sids.discard(None)
        if source_prefix:
            sids = {s for s in sids if s.startswith(source_prefix)}
        return sorted(sids)

    async def get_entities_by_source(self, source_ids: list[str]) -> list[dict]:
        sids = set(source_ids)
        return [e for e in self._entities.values() if e.get("source_id") in sids]

    async def delete_entities(self, entity_names: list[str]) -> None:
        self.deleted_entity_names.extend(entity_names)
        for n in entity_names:
            self._entities.pop(n, None)

    async def delete_by_source(self, source_ids: list[str]) -> None:
        sids = set(source_ids)
        self.deleted_source_ids.extend(source_ids)
        self._entities = {k: v for k, v in self._entities.items() if v.get("source_id") not in sids}


def _ent(name: str, source_id: str, content_hash: str | None = None) -> EntityData:
    return EntityData(
        entity_name=name,
        entity_data={"source_id": source_id, "content_hash": content_hash},
    )


def _store_ent(name: str, source_id: str, content_hash: str | None = None) -> dict[str, Any]:
    """An entity as get_entities_by_source returns it (store-side old state)."""
    return {"entity_name": name, "source_id": source_id, "content_hash": content_hash}


async def test_ingest_incremental_only_touches_changed_files() -> None:
    """Only changed-file entities are processed; unchanged-file entities are
    filtered out. Within a changed file, hash-matched symbols are skipped (#90)."""
    store = _FakeStoreIncremental(
        entities_by_source={"pkg/a.py": [_store_ent("pkg.a.handle", "pkg/a.py:1", "h1-old")]}
    )
    entities = [
        _ent("pkg.a.handle", "pkg/a.py:1", "h1-new"),  # changed file, mismatch → re-embed
        _ent("pkg.b.handle", "pkg/b.py:1", "h2"),  # unchanged file — filtered out
    ]

    result = await ingest_incremental(entities, [], store, changed_files={"pkg/a.py"})

    inserted = store.insert_custom_kg.call_args.args[0]
    assert [e["entity_name"] for e in inserted] == ["pkg.a.handle"]
    assert result["changed_files"] == ["pkg/a.py"]


async def test_ingest_incremental_skips_unchanged_symbol_by_hash() -> None:
    """#90 core: same file, same content_hash → symbol skipped (no re-embed,
    no re-insert). The ~50× embedding savings vs file-level on a fat file."""
    store = _FakeStoreIncremental(
        entities_by_source={
            "pkg/a.py": [
                _store_ent("pkg.a.handle", "pkg/a.py:1", "h1"),
                _store_ent("pkg.b.handle", "pkg/a.py:2", "h2"),
            ]
        }
    )
    entities = [
        _ent("pkg.a.handle", "pkg/a.py:1", "h1"),
        _ent("pkg.b.handle", "pkg/a.py:2", "h2"),
    ]

    result = await ingest_incremental(entities, [], store, changed_files={"pkg/a.py"})

    assert store.insert_custom_kg.call_args.args[0] == []
    assert store.deleted_entity_names == []
    assert result["symbols_skipped"] == 2


async def test_ingest_incremental_reembeds_hash_mismatch() -> None:
    """One symbol's content_hash changed → only that symbol re-embedded."""
    store = _FakeStoreIncremental(
        entities_by_source={
            "pkg/a.py": [
                _store_ent("pkg.a.handle", "pkg/a.py:1", "h1-old"),
                _store_ent("pkg.b.handle", "pkg/a.py:2", "h2"),
            ]
        }
    )
    entities = [
        _ent("pkg.a.handle", "pkg/a.py:1", "h1-new"),  # changed
        _ent("pkg.b.handle", "pkg/a.py:2", "h2"),  # unchanged
    ]

    await ingest_incremental(entities, [], store, changed_files={"pkg/a.py"})

    inserted = store.insert_custom_kg.call_args.args[0]
    assert [e["entity_name"] for e in inserted] == ["pkg.a.handle"]
    assert store.deleted_entity_names == []


async def test_ingest_incremental_inserts_new_symbol() -> None:
    """Symbol in new export but absent from store → inserted."""
    store = _FakeStoreIncremental(
        entities_by_source={"pkg/a.py": [_store_ent("pkg.a.handle", "pkg/a.py:1", "h1")]}
    )
    entities = [
        _ent("pkg.a.handle", "pkg/a.py:1", "h1"),
        _ent("pkg.a.new", "pkg/a.py:30", "h3"),  # new symbol
    ]

    await ingest_incremental(entities, [], store, changed_files={"pkg/a.py"})

    inserted = store.insert_custom_kg.call_args.args[0]
    assert [e["entity_name"] for e in inserted] == ["pkg.a.new"]


async def test_ingest_incremental_deletes_removed_symbol() -> None:
    """Symbol in store but absent from new export → delete_entities([name])."""
    store = _FakeStoreIncremental(
        entities_by_source={
            "pkg/a.py": [
                _store_ent("pkg.a.kept", "pkg/a.py:1", "h1"),
                _store_ent("pkg.a.gone", "pkg/a.py:50", "h2"),
            ]
        }
    )
    entities = [_ent("pkg.a.kept", "pkg/a.py:1", "h1")]

    result = await ingest_incremental(entities, [], store, changed_files={"pkg/a.py"})

    assert store.deleted_entity_names == ["pkg.a.gone"]
    assert result["symbols_deleted"] == 1


async def test_ingest_incremental_null_hash_falls_back_to_reembed() -> None:
    """content_hash=None (no-span entity / sv0 artifact) → always re-embed
    (file-level fallback). Skip only when BOTH old and new carry a hash."""
    store = _FakeStoreIncremental(
        entities_by_source={"pkg/a.py": [_store_ent("pkg.a.handle", "pkg/a.py:1", None)]}
    )
    entities = [_ent("pkg.a.handle", "pkg/a.py:1", None)]

    await ingest_incremental(entities, [], store, changed_files={"pkg/a.py"})

    inserted = store.insert_custom_kg.call_args.args[0]
    assert [e["entity_name"] for e in inserted] == ["pkg.a.handle"]
    assert store.deleted_entity_names == []


async def test_ingest_incremental_garbage_collects_deleted_symbol() -> None:
    """Deleted symbols (in store but absent from export) are pruned via
    delete_entities — symbol-level GC (#90), NOT file-level delete_by_source."""
    store = _FakeStoreIncremental(
        entities_by_source={
            "pkg/a.py": [
                _store_ent("pkg.a.kept", "pkg/a.py:1", "h1"),
                _store_ent("pkg.a.gone", "pkg/a.py:50", "h2"),
            ]
        }
    )
    entities = [_ent("pkg.a.kept", "pkg/a.py:1", "h1")]

    await ingest_incremental(entities, [], store, changed_files={"pkg/a.py"})

    assert store.deleted_entity_names == ["pkg.a.gone"]
    assert store.deleted_source_ids == []  # no file-level delete anymore
    inserted = store.insert_custom_kg.call_args.args[0]
    assert inserted == []  # pkg.a.kept hash matches → skipped


# ----- assess_export (shared 0-entity gate, #120) --------------------------


def _summary(entity_count: int, relation_count: int = 0) -> ImportSummary:
    return ImportSummary(entity_count=entity_count, relation_count=relation_count)


def test_assess_export_non_empty_is_safe_no_warning() -> None:
    """A healthy export: safe to write, no warning."""
    safe, warning = assess_export(_summary(entity_count=5), warnings=[])
    assert safe is True
    assert warning is None


def test_assess_export_zero_entities_no_warnings_unsafe() -> None:
    """#120: 0 entities with no codeindex diagnostic — unsafe to write through
    clear/GC paths. Warning is the generic config-mismatch hint (the caller
    may still surface it but must not clear/delete on top of it)."""
    safe, warning = assess_export(_summary(entity_count=0), warnings=[])
    assert safe is False
    assert warning is not None
    assert "0 entities" in warning


def test_assess_export_zero_entities_surfaces_codeindex_diagnostic() -> None:
    """#120: when codeindex already diagnosed the 0-entity cause on stderr
    (missing grammar / languages mismatch), fold that into the warning so the
    agent gets the real root cause, not just '0 entities'."""
    safe, warning = assess_export(
        _summary(entity_count=0),
        warnings=[
            "Parser library not installed for swift: tree-sitter-swift is not "
            "installed. Install it with: pip install tree-sitter-swift "
            "(Sources/App/AppState.swift)"
        ],
    )
    assert safe is False
    assert warning is not None
    assert "tree-sitter-swift" in warning
    assert "swift" in warning


def test_assess_export_zero_entities_folds_multiline_hint_to_leading_line() -> None:
    """#120: codeindex's language-mismatch hint is one multi-line WARNING;
    the leading line carries the missing-language name + evidence. Fold to it
    (drop per-file path noise) rather than dumping the whole block."""
    safe, warning = assess_export(
        _summary(entity_count=0),
        warnings=[
            "WARNING: no indexable directories found.\n"
            "  Configured languages: ['python']\n"
            "  Detected file types in include roots: .php (2)\n"
            "  Hint: add php to .codeindex.yaml languages"
        ],
    )
    assert safe is False
    assert warning is not None
    assert "no indexable directories" in warning


def test_assess_export_warnings_present_but_entities_nonempty_is_safe() -> None:
    """A partial-graph WARNING (#108) on a repo that DID yield entities is
    informational only — safe to write. Don't treat it as a 0-entity gate."""
    safe, warning = assess_export(
        _summary(entity_count=3),
        warnings=["WARNING: partial graph — ... .tsx (1)"],
    )
    assert safe is True
    assert warning is None  # caller still echoes warnings separately; gate passes


class TestIncrementalRatioOverFullGraph:
    """#158 review C1-2 regression: incremental must persist the FULL-graph
    ratio — a no-change update must not wipe it to ''."""

    @staticmethod
    def _mk(name, source_id, content_hash="h1"):
        from loomgraph.core.models import EntityData

        return EntityData(
            entity_name=name, entity_data={"source_id": source_id, "content_hash": content_hash}
        )

    @staticmethod
    def _rel(s, t):
        from loomgraph.core.models import RelationData

        return RelationData(src_id=s, tgt_id=t, edge_data={})

    async def test_zero_change_update_keeps_ratio(self, tmp_path):
        from loomgraph.storage.sqlite_store import SqliteGraphStore

        store = SqliteGraphStore(db_path=tmp_path / "t.db")
        await store.initialize()
        from loomgraph.core.graph_export_ingest import ingest, ingest_incremental

        ents = [self._mk("A", "a.py"), self._mk("B", "b.py")]
        rels = [self._rel("A", "B")]
        await ingest(ents, rels, store, clear=True)
        assert await store.get_meta("resolved_ratio") == "1.0"

        # same hashes → zero changes; ratio must survive, not become ''
        result = await ingest_incremental(ents, rels, store, changed_files=set())
        assert result["resolved_ratio"] == 1.0
        assert await store.get_meta("resolved_ratio") == "1.0"
        await store.close()

    async def test_ratio_is_full_graph_not_subset(self, tmp_path):
        from loomgraph.storage.sqlite_store import SqliteGraphStore

        store = SqliteGraphStore(db_path=tmp_path / "t2.db")
        await store.initialize()
        from loomgraph.core.graph_export_ingest import ingest, ingest_incremental

        ents = [self._mk("A", "a.py"), self._mk("B", "b.py")]
        rels = [self._rel("A", "B"), self._rel("A", "Ghost")]
        await ingest(ents, rels, store, clear=True)
        assert await store.get_meta("resolved_ratio") == "0.5"

        # change one symbol; subset contains only its edge, full graph is 0.5
        ents2 = [self._mk("A", "a.py", "h2"), self._mk("B", "b.py")]
        result = await ingest_incremental(ents2, rels, store, changed_files={"a.py"})
        assert result["resolved_ratio"] == 0.5
        await store.close()
