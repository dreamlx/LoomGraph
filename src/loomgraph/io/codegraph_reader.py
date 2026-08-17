"""#152: codegraph extraction backend reader.

codegraph (``@colbymchenry/codegraph``) maintains its own SQLite graph at
``<repo>/.codegraph/codegraph.db`` (WAL, possibly held open by a daemon).
This module snapshots that db and maps it to the SAME
``(entities, relations, summary, warnings)`` 4-tuple that
:func:`loomgraph.core.graph_export_ingest.run_graph_export` produces, so the
shared ``ingest()`` pipeline is reused unchanged (per-workspace single-source,
parallel-not-serial — codeindex navigation is a side path, never enters the
graph).

Design decisions (see plan + red-team review):

- **Snapshot**: open source db rw + ``PRAGMA query_only=ON`` + python
  ``Connection.backup()`` to a temp copy. Not ``mode=ro`` (WAL recovery state
  → SQLITE_READONLY_RECOVERY), not ``immutable=1`` (loses WAL recent writes),
  not raw ``cp`` (torn read). query_only guarantees the user's repo db is
  never mutated.
- **Schema fingerprint (fail-loud, #142)**: required tables ⊆ actual, required
  column subsets ⊆ actual (codegraph migrations v1–v9 are append-only, so
  column-SET equality would false-alarm on the first additive migration).
  A semantics bump with no schema change is caught by
  ``indexed_with_extraction_version <= 24``.
- **Node whitelist**: class/struct/interface/trait/protocol/function/method/
  property/field/variable/constant/enum/type_alias/route/component/file enter
  the graph (entity_type = codegraph kind verbatim). import/export/module/
  parameter/enum_member/union/namespace are excluded — import nodes are the
  dangling targets of external-dependency edges (codeindex unresolved parity).
  file nodes become first-class entities: 64% of calls edges originate at a
  file node (measured BlueHawkLock), so dropping them guts the graph.
- **Disambiguation (BLOCKER)**: ``qualified_name`` is NOT unique (354 shared
  names on BlueHawkLock — ``styles``×33). ``entity_name`` is the store PK with
  ``ON CONFLICT DO UPDATE``, so unqualified names silently merge into one
  phantom hub/god. Non-unique names get ``file_path::qualified_name``; edges
  use the same map. The 93% unique majority keeps clean ``::`` names.
- **Edge mapping**: calls→CALLS; imports→IMPORTS; extends/implements→INHERITS;
  instantiates→CALLS; references/decorates→REFERENCES (new kind); contains/
  exports/type_of/returns/overrides dropped. Every edge carries
  ``resolution_qualifier``: "resolved" when the target is an ingested node,
  "unresolved" when the target is an excluded kind (e.g. external import) —
  otherwise the 1151 external-import edges become #113 phantom callees.
  ``provenance='heuristic'`` propagates into edge_data.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from loomgraph.core.models import EntityData, RelationData
from loomgraph.io.export_reader import ImportSummary

# codegraph schema.sql (1.5.0, migrations v1–v9 append-only). Fingerprint is a
# SUBSET check: every table/column below must be present, extras are tolerated.
_REQUIRED_TABLES = {
    "nodes", "edges", "files", "unresolved_refs", "project_metadata",
}
_REQUIRED_NODE_COLS = {
    "id", "kind", "qualified_name", "file_path", "start_line", "end_line",
    "docstring", "signature",
}
_REQUIRED_EDGE_COLS = {"source", "target", "kind", "line", "provenance"}

# node kinds that enter the graph (entity_type = codegraph kind verbatim).
# Excluded: import (dangling target of external deps), export, module,
# parameter, enum_member, union, namespace.
_NODE_WHITELIST = {
    "class", "struct", "interface", "trait", "protocol", "function",
    "method", "property", "field", "variable", "constant", "enum",
    "type_alias", "route", "component", "file",
}

# codegraph edge kind → loomgraph relation keywords.
_EDGE_KIND_MAP: dict[str, str] = {
    "calls": "CALLS",
    "imports": "IMPORTS",
    "extends": "INHERITS",
    "implements": "INHERITS",
    "instantiates": "CALLS",
    "references": "REFERENCES",
    "decorates": "REFERENCES",
    # dropped: contains, exports, type_of, returns, overrides
}

# Highest codegraph extraction-version this reader supports. A semantics bump
# with no schema change (column sets unchanged) is caught here, not by the
# column fingerprint. Bump only after re-verifying the mapping.
_MAX_EXTRACTION_VERSION = 24


class CodegraphDbMissingError(RuntimeError):
    """``.codegraph/codegraph.db`` not found — the repo was never `codegraph init`'d."""


class CodegraphSchemaError(RuntimeError):
    """Snapshot schema doesn't match the expected codegraph 1.5.0 layout, or the
    extraction version is newer than this reader supports (#142 fail-loud)."""


# ─── snapshot + fingerprint ───────────────────────────────────────────────


def _snapshot_codegraph_db(repo: Path) -> tuple[Path, dict[str, str]]:
    """Copy ``<repo>/.codegraph/codegraph.db`` to a temp file and fingerprint it.

    Opens the source rw (WAL recovery needs a writable connection) with
    ``query_only=ON`` so the user's db is never mutated, then uses the SQLite
    backup API to a temp — that honors WAL (unlike ``immutable=1``) and is
    atomic (unlike raw ``cp``). Returns ``(temp_path, project_metadata)``.
    """
    db_path = repo / ".codegraph" / "codegraph.db"
    if not db_path.exists():
        raise CodegraphDbMissingError(
            f"codegraph db not found at {db_path}. Run `codegraph init` "
            "(after `npm i -g @colbymchenry/codegraph`) to build the index."
        )

    src = sqlite3.connect(str(db_path))
    try:
        src.execute("PRAGMA query_only=ON")
        _validate_schema(src)
        meta = dict(
            src.execute(
                "SELECT key, value FROM project_metadata "
                "WHERE key IN ('indexed_with_version','indexed_with_extraction_version')"
            ).fetchall()
        )
        fd, tmp_path = tempfile.mkstemp(suffix=".codegraph-snap.db")
        dst = sqlite3.connect(tmp_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            import os as _os
            _os.close(fd)
    finally:
        src.close()
    return Path(tmp_path), meta


def _validate_schema(conn: sqlite3.Connection) -> None:
    """Fail loud if the db isn't a codegraph 1.5.0-compatible index (#142)."""
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing_tables = _REQUIRED_TABLES - tables
    if missing_tables:
        raise CodegraphSchemaError(
            f"codegraph db missing required tables {sorted(missing_tables)} "
            f"(have {sorted(tables)}) — not a codegraph 1.5.0 index"
        )

    def _cols(table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    node_missing = _REQUIRED_NODE_COLS - _cols("nodes")
    if node_missing:
        raise CodegraphSchemaError(
            f"codegraph nodes missing columns {sorted(node_missing)}"
        )
    edge_missing = _REQUIRED_EDGE_COLS - _cols("edges")
    if edge_missing:
        raise CodegraphSchemaError(
            f"codegraph edges missing columns {sorted(edge_missing)}"
        )

    ext = meta_value(conn, "indexed_with_extraction_version")
    if ext is not None:
        try:
            ext_n = int(ext)
        except ValueError:
            raise CodegraphSchemaError(
                f"codegraph indexed_with_extraction_version is not an integer: {ext!r}"
            ) from None
        if ext_n > _MAX_EXTRACTION_VERSION:
            raise CodegraphSchemaError(
                f"codegraph extraction version {ext_n} > supported "
                f"{_MAX_EXTRACTION_VERSION} — the index was built by a newer "
                "codegraph; upgrade loomgraph or re-index with a compatible version"
            )


def meta_value(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM project_metadata WHERE key = ?", (key,)
    ).fetchone()
    return row[0] if row else None


def _fingerprint(conn: sqlite3.Connection) -> str:
    """Content fingerprint for update's noop short-circuit (#152).

    codegraph has no per-symbol content_hash, so incremental update is out —
    but this fingerprint (node/edge counts + max node updated_at) lets
    ``update`` detect an unchanged snapshot and skip the full clear-rebuild
    instead of re-ingesting identical data every commit. Changed → rebuild;
    unchanged → ``{"mode": "codegraph_noop"}`` + a `run codegraph sync` hint.
    """
    n_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    max_upd = conn.execute(
        "SELECT COALESCE(MAX(updated_at), 0) FROM nodes"
    ).fetchone()[0]
    return f"{n_nodes}/{n_edges}/{max_upd}"


# ─── mapping ──────────────────────────────────────────────────────────────


def _build_entities(
    conn: sqlite3.Connection,
) -> tuple[list[EntityData], dict[str, str], dict[str, str]]:
    """Map whitelisted nodes → EntityData, disambiguating non-unique names.

    Returns ``(entities, node_id_to_name, node_id_to_kind)``. The name map is
    the disambiguated entity_name every edge endpoint must use — using raw
    qualified_name on edges would land them on pre-merge names (dangling).
    """
    rows = conn.execute(
        "SELECT id, kind, qualified_name, file_path, start_line, docstring, "
        "signature FROM nodes WHERE kind IN ({})".format(
            ",".join("?" * len(_NODE_WHITELIST))
        ),
        tuple(_NODE_WHITELIST),
    ).fetchall()

    # First pass: qualified_name uniqueness over whitelisted nodes only.
    seen_count: dict[str, int] = {}
    for row in rows:
        qname = row[2]
        seen_count[qname] = seen_count.get(qname, 0) + 1

    entities: list[EntityData] = []
    id_to_name: dict[str, str] = {}
    id_to_kind: dict[str, str] = {}
    for nid, kind, qname, file_path, line, doc, sig in rows:
        name = qname if seen_count[qname] == 1 else f"{file_path}::{qname}"
        signature = sig or ""
        docstring = doc or ""
        # codeindex contract: "signature | docstring" (empty parts dropped),
        # so the embed pipeline (which embeds description) gets the signature.
        # file nodes have neither — description stays "" → embed skips them
        # (measured 0/675 file nodes carry docstring/signature).
        description = " | ".join(p for p in (signature, docstring) if p)
        entities.append(EntityData(
            entity_name=name,
            entity_data={
                "entity_type": kind,
                "description": description,
                "signature": signature,
                "source_id": f"{file_path}:{line}",
                "file_path": file_path,
                "provenance": "codegraph",
            },
        ))
        id_to_name[nid] = name
        id_to_kind[nid] = kind
    return entities, id_to_name, id_to_kind


def _build_edges(
    conn: sqlite3.Connection,
    id_to_name: dict[str, str],
    id_to_kind: dict[str, str],
) -> list[RelationData]:
    """Map codegraph edges → RelationData (only kinds in _EDGE_KIND_MAP).

    Target resolution: a target node that's in the whitelist → "resolved"
    (tgt = disambiguated name); a target of an excluded kind (import node for
    external deps, parameter, etc.) → "unresolved" (tgt = the raw name, no
    phantom-callee risk). source is always a whitelisted node in practice
    (calls originate at file/function/method; imports at file), but a source
    outside the map is skipped — the edge has no loomgraph endpoint.
    """
    relations: list[RelationData] = []
    placeholders = ",".join("?" * len(_EDGE_KIND_MAP))
    rows = conn.execute(
        f"SELECT source, target, kind, line, provenance FROM edges "
        f"WHERE kind IN ({placeholders})",
        tuple(_EDGE_KIND_MAP),
    ).fetchall()

    for src_id, tgt_id, kind, line, provenance in rows:
        src = id_to_name.get(src_id)
        if src is None:
            continue  # source excluded (e.g. an import-node caller)
        kw = _EDGE_KIND_MAP[kind]
        tgt_node_kind = id_to_kind.get(tgt_id)
        # line is nullable; default to 0 (codeindex contract is relpath:line).
        line_str = str(line) if line is not None else "0"

        if tgt_node_kind is not None and tgt_node_kind in _NODE_WHITELIST:
            tgt = id_to_name[tgt_id]
            qualifier = "resolved"
            dst_raw = None
            weight = 1.0
        else:
            # target excluded (external import / parameter / ...). Use the
            # raw target name as a distinct tgt (no fake hub) and mark
            # unresolved so #113's trust filter excludes it from callees.
            tgt = _raw_target_name(conn, tgt_id)
            qualifier = "unresolved"
            dst_raw = tgt
            weight = 0.5

        edge_data: dict[str, Any] = {
            "keywords": kw,
            "description": f"{kw} from {src} at {src}:{line_str}",
            "weight": weight,
            "source_id": f"{src}:{line_str}",
            "resolution_qualifier": qualifier,
        }
        if dst_raw:
            edge_data["dst_raw"] = dst_raw
        if provenance:
            edge_data["provenance"] = provenance
        relations.append(RelationData(src_id=src, tgt_id=tgt, edge_data=edge_data))
    return relations


def _raw_target_name(conn: sqlite3.Connection, tgt_id: str) -> str:
    """Look up an excluded target node's name (qualified_name) for the distinct
    unresolved tgt — so external deps don't collapse onto one sentinel."""
    row = conn.execute(
        "SELECT qualified_name FROM nodes WHERE id = ?", (tgt_id,)
    ).fetchone()
    return row[0] if row else "<unresolved>"


# ─── public entry ─────────────────────────────────────────────────────────


def run_codegraph_export(
    repo: Path,
) -> tuple[list[EntityData], list[RelationData], ImportSummary, list[str]]:
    """Snapshot + map a codegraph db to the 4-tuple ``ingest()`` consumes.

    Mirrors :func:`run_graph_export`'s signature so the CLI dispatches between
    them with one ``if/else``. ``warnings`` is currently empty (codegraph
    writes no partial-graph stderr — it stores only resolved edges + a
    separate unresolved_refs table); the list is kept for contract symmetry
    and the language-fingerprint hook (applied by the CLI, not here).
    """
    tmp_db, meta = _snapshot_codegraph_db(repo)
    conn = sqlite3.connect(str(tmp_db))
    try:
        conn.row_factory = sqlite3.Row
        entities, id_to_name, id_to_kind = _build_entities(conn)
        relations = _build_edges(conn, id_to_name, id_to_kind)
        # Fingerprint for update's noop short-circuit (#152): codegraph has no
        # per-symbol content_hash, so incremental update is impossible — but a
        # content fingerprint (row counts + max updated_at) lets `update` skip
        # re-ingesting an unchanged snapshot instead of paying a full clear
        # rebuild every commit. Stashed in summary.meta for the CLI to persist.
        meta["codegraph_fingerprint"] = _fingerprint(conn)
    finally:
        conn.close()
        tmp_db.unlink(missing_ok=True)

    from collections import Counter

    summary = ImportSummary(
        meta=meta,
        entity_count=len(entities),
        relation_count=len(relations),
        entity_types=Counter(e.entity_data["entity_type"] for e in entities),
        edge_kinds=Counter(r.edge_data["keywords"] for r in relations),
        edge_qualifiers=Counter(
            r.edge_data["resolution_qualifier"] for r in relations
        ),
    )
    return entities, relations, summary, []
