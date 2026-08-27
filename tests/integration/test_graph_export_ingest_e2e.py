"""End-to-end collision-regression test (#66 win criterion).

Real `codeindex graph-export` → real `loomgraph index` → real SqliteGraphStore.
Pins the fix: cross-module same-name functions land as DISTINCT entities
(qualified ids), so topology no longer reports a phantom god_function. If
anyone re-introduces simple-name keying, this fails loudly.

Skipped when `codeindex` is not importable in the venv (CI without the parser
installed). Note: `run_graph_export` invokes `sys.executable -m codeindex.cli`
(not a bare PATH `codeindex`), so availability is the venv import, not PATH.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main
from loomgraph.core.deps import DepsAnalyzer
from loomgraph.core.graph_export_ingest import ingest, run_graph_export
from loomgraph.storage.sqlite_store import SqliteGraphStore

pytestmark = pytest.mark.integration


def _store_factory(db_path: Path):
    async def _make(workspace=None):  # noqa: ARG001 — workspace irrelevant, tmp db
        s = SqliteGraphStore(db_path=str(db_path))
        await s.initialize()
        return s
    return _make


def _seed_collision_repo(root: Path) -> None:
    """Two modules each defining `handle`; topology.handle calls 3 helpers,
    other.handle calls 10 — under simple-name keying they'd merge into one
    phantom node with out-degree 13."""
    (root / "topology.py").write_text(
        "def _t1():\n    pass\n"
        "def _t2():\n    pass\n"
        "def _t3():\n    pass\n"
        "def handle():\n"
        "    '''topology's handle.'''\n"
        "    _t1(); _t2(); _t3()\n"
    )
    helpers = "\n".join(
        f"def _h{i}():\n    pass\n" for i in range(10)
    )
    calls = "".join(f"    _h{i}()\n" for i in range(10))
    (root / "other.py").write_text(
        helpers
        + "def handle():\n"
        + "    '''other module's handle.'''\n"
        + calls
    )


def _seed_resolved_module_import_repo(root: Path) -> None:
    """A real exporter fixture for #239's module-level import boundary."""
    (root / ".codeindex.yaml").write_text("languages:\n  - python\n")
    (root / "src" / "core").mkdir(parents=True)
    (root / "src" / "cli").mkdir(parents=True)
    (root / "src" / "core" / "service.py").write_text(
        "def authenticate() -> bool:\n"
        "    return True\n"
    )
    (root / "src" / "cli" / "handler.py").write_text(
        "from src.core.service import authenticate\n"
        "from third_party import helper\n"
        "from src.no_source import nothing\n\n"
        "def run() -> bool:\n"
        "    return authenticate()\n"
    )


def test_index_then_no_phantom_handle(tmp_path: Path, monkeypatch) -> None:
    if importlib.util.find_spec("codeindex") is None:
        pytest.skip("codeindex not importable in venv — e2e needs the real parser")

    repo = tmp_path / "repo"
    repo.mkdir()
    _seed_collision_repo(repo)

    # Redirect storage to a tmp db (real SqliteGraphStore, clean location).
    db_path = tmp_path / "e2e.db"
    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store", _store_factory(db_path)
    )
    monkeypatch.setattr(
        "loomgraph.cli._indexing.get_auto_workspace", lambda w: w or "e2e:test"
    )

    # Real index — real codeindex graph-export subprocess + real ingest.
    result = CliRunner().invoke(main, ["index", str(repo), "-w", "e2e:test"])
    assert result.exit_code == 0, result.output

    async def _inspect():
        store = await _store_factory(db_path)()
        try:
            entities = await store.get_all_entities()
            relations = await store.get_all_relations()
            return entities, relations
        finally:
            await store.close()

    entities, relations = asyncio.run(_inspect())

    # #66 pin #1: two DISTINCT `handle` entities (no phantom merge).
    handles = [e for e in entities if e["entity_name"].endswith(".handle")]
    handle_names = {e["entity_name"] for e in handles}
    assert handle_names == {"topology.handle", "other.handle"}, (
        f"same-simple-name `handle` must stay distinct; got {handle_names}"
    )

    # #66 pin #2: topology.handle has exactly 3 callees (not 13 from a merge).
    topo_callees = {
        r["tgt_id"]
        for r in relations
        if r.get("src_id") == "topology.handle"
        and r.get("keywords", r.get("edge_data", {}).get("keywords")) == "CALLS"
    }
    assert topo_callees == {"topology._t1", "topology._t2", "topology._t3"}, (
        f"topology.handle callees must be its 3 local helpers, not a phantom "
        f"merged out-degree; got {topo_callees}"
    )


def test_resolved_internal_module_import_aggregates_without_unresolved_guesses(
    tmp_path: Path,
) -> None:
    """#239: real export → ingest → deps keeps only the proven module import."""
    if importlib.util.find_spec("codeindex") is None:
        pytest.skip("codeindex not importable in venv — e2e needs the real parser")

    repo = tmp_path / "repo"
    repo.mkdir()
    _seed_resolved_module_import_repo(repo)
    entities, relations, _, _ = run_graph_export(repo)

    import_edges = [relation for relation in relations if relation.edge_data["keywords"] == "IMPORTS"]
    assert {
        (relation.tgt_id, relation.edge_data["resolution_qualifier"])
        for relation in import_edges
    } == {
        ("src.core.service", "resolved"),
        ("third_party", "unresolved"),
        ("src.no_source", "unresolved"),
    }

    async def _analyze() -> dict[str, object]:
        store = SqliteGraphStore(db_path=str(tmp_path / "deps.db"))
        await store.initialize()
        try:
            await ingest(entities, relations, store, clear=True)
            return (await DepsAnalyzer(store, depth=2, auto_depth=False).analyze()).to_dict()
        finally:
            await store.close()

    result = asyncio.run(_analyze())
    assert result["dependencies"] == [
        {
            "from": "src/cli",
            "to": "src/core",
            "count": 2,
            "types": {"CALLS": 1, "IMPORTS": 1},
        }
    ]
