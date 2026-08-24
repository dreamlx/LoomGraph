"""Contract tests: the codeindex CLI output shapes loomgraph depends on (#179).

The graph-export NDJSON contract is *the* seam between the two repos, but
nothing in either CI failed when the shapes drifted — #173 shipped because
the impact extractor assumed a property of ``codeindex parse`` output (bare
symbol names) that no test pinned. These tests fail RED when codeindex
changes any pinned property; that is deliberate — it forces a coordinated
update here (and a codeindex CHANGELOG breaking-change entry).

Invokes the pinned in-venv codeindex (``sys.executable -m codeindex.cli``),
same as production callers (#76 PATH bypass, #120).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _run_codeindex(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codeindex.cli", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def contract_repo(tmp_path: Path) -> Path:
    """Minimal cross-module repo: b.run() calls a.greeter() — yields one
    resolvable CALLS edge plus module-level IMPORTS/REFERENCES edges."""
    (tmp_path / "a.py").write_text("def greeter():\n    return 42\n")
    (tmp_path / "b.py").write_text("from a import greeter\n\n\ndef run():\n    return greeter()\n")
    return tmp_path


@pytest.fixture
def factory_receiver_repo(tmp_path: Path) -> Path:
    """#185 fixture: a local receiver is bound from an annotated factory."""
    (tmp_path / "store.py").write_text(
        "class Store:\n"
        "    async def create_entity(self) -> None:\n"
        "        pass\n"
    )
    (tmp_path / "factory.py").write_text(
        "from store import Store\n\n"
        "async def create_store() -> Store:\n"
        "    return Store()\n"
    )
    (tmp_path / "consumer.py").write_text(
        "from factory import create_store\n\n"
        "async def run() -> None:\n"
        "    store = await create_store()\n"
        "    await store.create_entity()\n"
    )
    return tmp_path


@pytest.fixture
def typescript_barrel_repo(tmp_path: Path) -> Path:
    """#140 fixture: a named import reaches its definition through a barrel."""
    src = tmp_path / "src"
    src.mkdir()
    (tmp_path / ".codeindex.yaml").write_text("languages:\n  - typescript\n")
    (src / "models.ts").write_text("export class Session {}\n")
    (src / "index.ts").write_text('export { Session } from "./models";\n')
    (src / "consumer.ts").write_text(
        'import { Session } from "./index";\n\n'
        "export const useSession = (session: Session) => session;\n"
    )
    return tmp_path


def _export_ndjson(repo: Path) -> list[dict]:
    proc = _run_codeindex("graph-export", "--root", str(repo), "-o", "-")
    assert proc.returncode == 0, f"graph-export failed: {proc.stderr[:300]}"
    lines = [json.loads(raw) for raw in proc.stdout.splitlines() if raw.strip()]
    assert lines, "graph-export produced no NDJSON lines"
    return lines


class TestParseOutputShape:
    """``codeindex parse <file>`` — consumed by core/impact/extractor.py."""

    def test_symbols_name_is_bare(self, contract_repo: Path) -> None:
        """symbols[].name is the SHORT name, no module qualification —
        the impact extractor's qualification logic (#173 fix) prepends the
        module path itself; if codeindex ever starts returning qualified
        names, that logic double-qualifies and every caller lookup misses."""
        proc = _run_codeindex("parse", str(contract_repo / "a.py"))
        assert proc.returncode == 0, proc.stderr[:300]
        data = json.loads(proc.stdout)
        assert "symbols" in data, f"top-level keys: {sorted(data)}"
        names = [s["name"] for s in data["symbols"]]
        assert "greeter" in names
        for name in names:
            assert "." not in name, f"expected bare name, got {name!r}"

    def test_symbol_line_fields_present(self, contract_repo: Path) -> None:
        """Line anchors (line_start/line_end) feed ChangedSymbol extraction."""
        proc = _run_codeindex("parse", str(contract_repo / "a.py"))
        assert proc.returncode == 0, (
            f"codeindex parse failed (exit {proc.returncode}): {proc.stderr[:300]}"
        )
        data = json.loads(proc.stdout)
        sym = next(
            (s for s in data["symbols"] if s["name"] == "greeter"),
            None,
        )
        assert sym is not None, f"greeter not in symbols: {[s.get('name') for s in data['symbols']]}"
        assert sym["line_start"] >= 1, f"line_start missing/drifted: {sym}"
        assert sym["line_end"] >= sym["line_start"], f"line_end drifted: {sym}"


class TestGraphExportShape:
    """``codeindex graph-export --root <repo> -o -`` — consumed by
    core/graph_export_ingest.py (the two-repo NDJSON seam)."""

    def test_meta_schema_version_is_known(self, contract_repo: Path) -> None:
        """schema_version handshake: a NEW unknown version must fail here
        (and in GraphExportReader's warn path) before any silent drift."""
        meta = _export_ndjson(contract_repo)[0]
        assert meta.get("type") == "meta"
        assert meta.get("generator") == "codeindex"
        assert meta.get("schema_version") == 1, (
            "codeindex bumped the NDJSON schema — update GraphExportReader "
            "compat handling + these pins together (#179)"
        )

    def test_entity_ids_are_module_qualified(self, contract_repo: Path) -> None:
        """Entity ids are dotted module paths — module-qualified ids are the
        cross-module same-name collision fix (#66); downstream matching
        (impact callers, graph traversal) relies on the dotted form."""
        rows = _export_ndjson(contract_repo)
        entities = [r for r in rows if r.get("type") == "entity"]
        assert {e["id"] for e in entities} >= {"a.greeter", "b.run"}
        for e in entities:
            assert "." in e["id"], f"expected qualified id, got {e['id']!r}"

    def test_resolved_calls_dst_references_existing_entity(self, contract_repo: Path) -> None:
        """A resolved CALLS edge's dst must be an entity id present in the
        SAME export — the exact invariant the impact caller traversal
        (#173 fix) matches against. Unresolved edges carry dst=None +
        dst_raw instead. Module-level edges (IMPORTS/REFERENCES) may point
        at module paths that are not entities — the invariant is CALLS-only.
        """
        rows = _export_ndjson(contract_repo)
        entities = {r["id"] for r in rows if r.get("type") == "entity"}
        edges = [r for r in rows if r.get("type") == "edge"]
        assert edges, "fixture repo should yield at least one edge"

        calls = [e for e in edges if e.get("kind") == "CALLS"]
        assert any(e.get("src") == "b.run" and e.get("dst") == "a.greeter" for e in calls), (
            f"expected resolved b.run -> a.greeter CALLS, got {calls}"
        )

        for e in edges:
            qualifier = e.get("resolution_qualifier")
            assert qualifier in ("resolved", "unresolved"), e
            if qualifier == "resolved" and e.get("kind") == "CALLS":
                assert e.get("dst") in entities, (
                    f"resolved CALLS dst {e.get('dst')!r} not in entity set"
                )
            elif qualifier == "unresolved":
                assert e.get("dst") is None and e.get("dst_raw"), e

    def test_annotated_factory_receiver_resolves_method_call(
        self, factory_receiver_repo: Path
    ) -> None:
        """#185: ``store = await create_store()`` resolves ``store.method``.

        This is a producer-boundary contract: LoomGraph may rely on the
        resolved edge, but must not recreate this inference itself.
        """
        rows = _export_ndjson(factory_receiver_repo)
        calls = [row for row in rows if row.get("type") == "edge" and row.get("kind") == "CALLS"]

        assert any(
            edge.get("src") == "consumer.run"
            and edge.get("dst") == "store.Store.create_entity"
            and edge.get("resolution_qualifier") == "resolved"
            for edge in calls
        ), calls

    def test_typescript_barrel_reference_reaches_definition(
        self, typescript_barrel_repo: Path
    ) -> None:
        """#140: a barrel re-export resolves to the defining entity, not a ghost."""
        rows = _export_ndjson(typescript_barrel_repo)
        references = [
            row for row in rows
            if row.get("type") == "edge" and row.get("kind") == "REFERENCES"
        ]

        assert any(
            edge.get("src") == "src.consumer"
            and edge.get("dst") == "src.models.Session"
            and edge.get("resolution_qualifier") == "resolved"
            for edge in references
        ), references
        assert not any(edge.get("dst") == "src.index.Session" for edge in references)

    def test_edge_kinds_are_the_known_set(self, contract_repo: Path) -> None:
        """Edge kinds are exactly CALLS/INHERITS/IMPORTS/REFERENCES — the
        store's keywords column and every relation-type filter in query
        commands enumerate this set; a new kind from codeindex must be a
        coordinated addition, not a silent passthrough."""
        rows = _export_ndjson(contract_repo)
        kinds = {e.get("kind") for r in rows if (e := r).get("type") == "edge"}
        assert kinds <= {"CALLS", "INHERITS", "IMPORTS", "REFERENCES"}, kinds
