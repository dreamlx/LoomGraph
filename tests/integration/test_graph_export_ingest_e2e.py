"""End-to-end collision-regression test (#66 win criterion).

Real `codeindex graph-export` → real `loomgraph index` → real SqliteGraphStore.
Pins the fix: cross-module same-name functions land as DISTINCT entities
(qualified ids), so topology no longer reports a phantom god_function. If
anyone re-introduces simple-name keying, this fails loudly.

Skipped when `codeindex` is not on PATH (CI without the parser installed).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli.main import main
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


def test_index_then_no_phantom_handle(tmp_path: Path, monkeypatch) -> None:
    if not shutil.which("codeindex"):
        pytest.skip("codeindex not on PATH — e2e needs the real parser")

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
