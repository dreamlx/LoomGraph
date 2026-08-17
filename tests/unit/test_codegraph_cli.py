"""#152 CLI backend dispatch + `::` resolution + topology file-exclusion.

Covers the wiring layer (the reader's own mapping is in
test_codegraph_reader.py): index --backend dispatch, update meta-routing +
fingerprint noop, refresh codegraph routing, the `::` name resolution in
`graph`, and topology's `file`-type exclusion.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main

# ─── `::` simple-name resolution (#152, backend-neutral) ───────────────────


def test_resolve_simple_name_dotted() -> None:
    """codeindex: `graph downstreamBlockers` → `src.lib.downstreamBlockers` (#98)."""
    from loomgraph.cli._search import _resolve_simple_name

    names = {"src.lib.api.downstreamBlockers", "other.thing"}
    assert _resolve_simple_name("downstreamBlockers", names) == "src.lib.api.downstreamBlockers"


def test_resolve_simple_name_double_colon() -> None:
    """codegraph: `graph MigrationManager` → a `::MigrationManager`-suffixed name."""
    from loomgraph.cli._search import _resolve_simple_name

    names = {"app::MigrationManager", "util::helper"}
    assert _resolve_simple_name("MigrationManager", names) == "app::MigrationManager"


def test_resolve_simple_name_ambiguous_returns_unchanged() -> None:
    from loomgraph.cli._search import _resolve_simple_name

    names = {"a.styles", "b.styles"}
    assert _resolve_simple_name("styles", names) == "styles"


def test_class_methods_collects_both_separators() -> None:
    """#105 class-fold: codeindex `Class.method` AND codegraph `Class::method`."""
    from loomgraph.cli._search import _class_methods

    names = {"Foo.bar", "Foo::baz", "Other.thing", "unrelated"}
    assert set(_class_methods("Foo", names)) == {"Foo.bar", "Foo::baz"}


# ─── index --backend codegraph dispatch ────────────────────────────────────


def _codegraph_repo(tmp_path: Path) -> Path:
    """A repo with a minimal .codegraph/codegraph.db the reader accepts."""
    repo = tmp_path / "repo"
    (repo / ".codegraph").mkdir(parents=True)
    db = repo / ".codegraph" / "codegraph.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE schema_versions (version INTEGER PRIMARY KEY, applied_at INTEGER, description TEXT);"
        "CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT, name TEXT, qualified_name TEXT, "
        "file_path TEXT, language TEXT, start_line INTEGER, end_line INTEGER, "
        "start_column INTEGER, end_column INTEGER, docstring TEXT, signature TEXT, "
        "visibility TEXT, is_exported INTEGER, updated_at INTEGER);"
        "CREATE TABLE edges (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, target TEXT, "
        "kind TEXT, metadata TEXT, line INTEGER, col INTEGER, provenance TEXT);"
        "CREATE TABLE files (path TEXT PRIMARY KEY, content_hash TEXT, language TEXT, "
        "size INTEGER, modified_at INTEGER, indexed_at INTEGER, node_count INTEGER, "
        "errors TEXT, generated INTEGER);"
        "CREATE TABLE unresolved_refs (id INTEGER PRIMARY KEY, from_node_id TEXT, "
        "reference_name TEXT, reference_kind TEXT, line INTEGER, col INTEGER, "
        "candidates TEXT, file_path TEXT, language TEXT, status TEXT, name_tail TEXT);"
        "CREATE TABLE project_metadata (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER);"
    )
    conn.execute("INSERT INTO project_metadata VALUES ('indexed_with_version','1.5.0',1)")
    conn.execute("INSERT INTO project_metadata VALUES ('indexed_with_extraction_version','24',1)")
    conn.execute(
        "INSERT INTO nodes VALUES ('n1','function','foo','foo','a.ts','typescript',"
        "1,1,0,0,NULL,'foo()','public',1,1000)"
    )
    conn.commit()
    conn.close()
    return repo


def _wire_store(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch create_graph_store + ingest + embedding so codegraph index runs."""
    from loomgraph.cli import _indexing

    store = MagicMock()
    store.set_meta = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        AsyncMock(return_value=store),
    )
    monkeypatch.setattr(
        _indexing, "ingest",
        AsyncMock(return_value={
            "cleared": True, "entities_created": 1, "relations_created": 0,
            "resolved_ratio": None, "embedded": 0, "store_stats": {},
        }),
    )
    monkeypatch.setattr(_indexing, "_git_head_safe", lambda: "deadbeef")
    # embedding off
    async def _no_embed(entities, store):  # noqa: ANN001
        return 0
    import loomgraph.core.embedding_pipeline as ep
    monkeypatch.setattr(ep, "maybe_embed_entities", _no_embed)
    return store


def test_index_codegraph_backend_dispatches_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`index --backend codegraph` runs the codegraph reader, not codeindex."""
    from loomgraph.cli import _indexing

    repo = _codegraph_repo(tmp_path)
    _wire_store(monkeypatch)
    # If the codeindex path were taken, check_codeindex would fire — patch it
    # to FAIL so the test is loud if dispatch is wrong.
    def _codeindex_should_not_run() -> dict:
        raise AssertionError("codeindex gate must not run on --backend codegraph")
    monkeypatch.setattr(_indexing, "check_codeindex", _codeindex_should_not_run)

    res = CliRunner().invoke(main, ["index", str(repo), "--backend", "codegraph"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)["data"]
    assert data["backend"] == "codegraph"
    assert data["entities_created"] == 1


def test_index_codegraph_missing_db_fails_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No .codegraph/ → output_error with install hint."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _wire_store(monkeypatch)

    res = CliRunner().invoke(main, ["index", str(repo), "--backend", "codegraph"])
    assert res.exit_code == 1
    payload = json.loads(res.stdout)
    assert payload["success"] is False
    assert "npm i -g" in payload["error"]["suggestion"]


def test_index_codegraph_records_backend_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """codegraph index records extraction_backend + head + fingerprint in meta."""
    repo = _codegraph_repo(tmp_path)
    store = _wire_store(monkeypatch)

    res = CliRunner().invoke(main, ["index", str(repo), "--backend", "codegraph"])
    assert res.exit_code == 0, res.output

    meta_calls = {c.args[0]: c.args[1] for c in store.set_meta.call_args_list}
    assert meta_calls.get("extraction_backend") == "codegraph"
    assert meta_calls.get("codegraph_head") == "deadbeef"
    assert "codegraph_fingerprint" in meta_calls


# ─── update meta-routing + fingerprint noop ────────────────────────────────


def _wire_codegraph_update(
    monkeypatch: pytest.MonkeyPatch, *, fingerprint: str, recorded: str | None
) -> MagicMock:
    from loomgraph.cli import _indexing
    from loomgraph.core.graph_export_ingest import ImportSummary
    from loomgraph.core.models import EntityData

    monkeypatch.setattr(
        _indexing, "run_codegraph_export",
        lambda r: ([EntityData("n1", {})], [], ImportSummary(
            entity_count=1, meta={"codegraph_fingerprint": fingerprint}
        ), []),
    )
    store = MagicMock()
    # get_meta is key-aware: extraction_backend → "codegraph",
    # codegraph_fingerprint → the recorded fingerprint.
    def _get_meta(key: str) -> str | None:
        if key == "extraction_backend":
            return "codegraph"
        if key == "codegraph_fingerprint":
            return recorded
        return None
    store.get_meta = AsyncMock(side_effect=_get_meta)
    store.set_meta = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        AsyncMock(return_value=store),
    )
    monkeypatch.setattr(
        _indexing, "ingest",
        AsyncMock(return_value={
            "cleared": True, "entities_created": 1, "relations_created": 0,
            "resolved_ratio": None, "embedded": 0, "store_stats": {},
        }),
    )
    monkeypatch.setattr(_indexing, "_git_head_safe", lambda: "feedface")
    async def _no_embed(entities, store):  # noqa: ANN001
        return 0
    import loomgraph.core.embedding_pipeline as ep
    monkeypatch.setattr(ep, "maybe_embed_entities", _no_embed)
    return store


def test_update_codegraph_noop_when_snapshot_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same fingerprint → codegraph_noop, no rebuild (post-commit hook scenario)."""
    from loomgraph.cli import _indexing

    repo = _codegraph_repo(tmp_path)
    monkeypatch.chdir(repo)
    _wire_codegraph_update(
        monkeypatch, fingerprint="1/0/1000", recorded="1/0/1000"
    )
    # ingest must NOT be called on noop.
    ingest = AsyncMock()
    monkeypatch.setattr(_indexing, "ingest", ingest)

    res = CliRunner().invoke(main, ["update", "--backend", "codegraph"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)["data"]
    assert data["mode"] == "codegraph_noop"
    assert data["skipped"] is True
    ingest.assert_not_awaited()


def test_update_codegraph_rebuilds_when_snapshot_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different fingerprint → codegraph_rebuild."""
    repo = _codegraph_repo(tmp_path)
    monkeypatch.chdir(repo)
    _wire_codegraph_update(
        monkeypatch, fingerprint="2/0/2000", recorded="1/0/1000"
    )

    res = CliRunner().invoke(main, ["update", "--backend", "codegraph"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.stdout)["data"]["mode"] == "codegraph_rebuild"


def test_update_routes_to_codegraph_by_meta_without_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare `update` (no --backend) on a codegraph workspace stays codegraph."""
    from loomgraph.cli import _indexing

    repo = _codegraph_repo(tmp_path)
    monkeypatch.chdir(repo)
    _wire_codegraph_update(monkeypatch, fingerprint="9/9/9", recorded="9/9/9")
    # codeindex gate must NOT run — meta says codegraph.
    def _no_codeindex() -> dict:
        raise AssertionError("codeindex gate must not run on a codegraph workspace")
    monkeypatch.setattr(_indexing, "check_codeindex", _no_codeindex)

    res = CliRunner().invoke(main, ["update"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.stdout)["data"]["mode"] == "codegraph_noop"


# ─── refresh routing ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_codegraph_incremental_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Incremental refresh on a codegraph workspace must not GC symbols."""
    from loomgraph.cli._indexing import GraphExportEmptyError, _async_refresh

    store = MagicMock()
    store.get_meta = AsyncMock(return_value="codegraph")
    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        AsyncMock(return_value=store),
    )
    with pytest.raises(GraphExportEmptyError, match="incremental refresh"):
        await _async_refresh(
            workspace=None, repo=Path("/tmp"), path=None, force_full=False
        )


@pytest.mark.asyncio
async def test_refresh_codegraph_force_full_rebuilds(monkeypatch: pytest.MonkeyPatch) -> None:
    """force_full on a codegraph workspace re-snapshots + clear-rebuilds."""
    from loomgraph.cli import _indexing
    from loomgraph.cli._indexing import _async_refresh
    from loomgraph.core.graph_export_ingest import ImportSummary
    from loomgraph.core.models import EntityData

    store = MagicMock()
    store.get_meta = AsyncMock(return_value="codegraph")
    store.set_meta = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        AsyncMock(return_value=store),
    )
    monkeypatch.setattr(
        _indexing, "run_codegraph_export",
        lambda r: ([EntityData("n1", {})], [], ImportSummary(
            entity_count=1, meta={"codegraph_fingerprint": "1/0/1"}
        ), []),
    )
    monkeypatch.setattr(
        _indexing, "ingest",
        AsyncMock(return_value={
            "cleared": True, "entities_created": 1, "relations_created": 0,
            "resolved_ratio": None, "embedded": 0, "store_stats": {},
        }),
    )
    monkeypatch.setattr(_indexing, "_git_head_safe", lambda: "h")

    result = await _async_refresh(
        workspace=None, repo=Path("/tmp"), path=None, force_full=True
    )
    assert result["mode"] == "codegraph_rebuild"
    assert result["backend"] == "codegraph"


# ─── topology file exclusion ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_topology_excludes_file_type_from_gods(monkeypatch: pytest.MonkeyPatch) -> None:
    """A file entity with huge out-degree must not become a god function (#152)."""
    from loomgraph.core.topology import TopologyAnalyzer

    store = MagicMock()
    store.get_orphan_entities = AsyncMock(return_value=[])
    store.get_degree_distribution = AsyncMock(
        side_effect=[
            # in (hubs) — foo has 20 in-degree, would be a hub but threshold
            # default 8; not the assertion focus.
            [{"entity": "foo", "entity_type": "function", "source_id": "src/a.ts:5",
              "in_degree": 20}],
            # out (gods) — src/a.ts file with 20 out-degree (god_threshold 10)
            # MUST be excluded by the entity_type filter.
            [{"entity": "src/a.ts", "entity_type": "file", "source_id": "src/a.ts:1",
              "out_degree": 20}],
        ]
    )
    store.get_graph_stats = AsyncMock(return_value={
        "entity_count": 2, "relation_count": 20,
        "cross_module_relations": 0, "intra_module_relations": 20,
        "coupling_density": 0.0,
    })
    store.get_all_entities = AsyncMock(return_value=[
        {"entity_name": "src/a.ts", "entity_type": "file", "source_id": "src/a.ts:1"},
        {"entity_name": "foo", "entity_type": "function", "source_id": "src/a.ts:5"},
    ])
    store.get_all_relations = AsyncMock(return_value=[])

    analyzer = TopologyAnalyzer(client=store)
    result = await analyzer.analyze()
    god_names = [g["entity"] for g in result.god_functions]
    assert "src/a.ts" not in god_names, (
        "file entities must be excluded from god detection (out-degree ~19 avg)"
    )
