"""Reader for codeindex `graph-export` NDJSON artifacts.

Contract: codeindex#102 (`docs/guides/graph-export.md` in codeindex repo).
Each line is a JSON record with a `type` field: `meta` | `entity` | `edge`.
Line 1 is the meta; entities follow; edges last.

Loomgraph's role as a #102 consumer (per LoomGraph#30 spike verdict):
honour `resolution_qualifier` on every edge — `unresolved` / `ambiguous`
edges are surfaced through ingestion so downstream queries can filter
them out instead of treating them as authoritative.

Public API:
- `GraphExportReader(path).read() → (entities, relations, summary)`
- `map_entity(rec) → EntityData`
- `map_edge(rec) → RelationData | None`

This module does NOT touch the GraphStore. Persistence belongs to the
CLI command (`loomgraph import-export`).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from loomgraph.core.models import EntityData, RelationData

# Codeindex schema constants (mirror docs/guides/graph-export.md)
META_REQUIRED = {"type", "schema_version", "generator"}
ENTITY_REQUIRED = {"type", "id", "entity_type", "source_id", "provenance"}
EDGE_REQUIRED = {"type", "kind", "src", "resolution_qualifier", "source_id"}

VALID_ENTITY_TYPES = {"class", "function", "method"}
VALID_EDGE_KINDS = {"CALLS", "INHERITS"}
VALID_QUALIFIERS = {"resolved", "ambiguous", "unresolved"}

# Sentinel for unresolved edge targets. Consumers must filter on the
# `resolution_qualifier` field — walking edges by `tgt_id` alone will
# reach this dead-end and rightly fail.
UNRESOLVED_SENTINEL = "<unresolved>"

# Highest schema_version this reader supports
SUPPORTED_SCHEMA_VERSION = 0


class ExportReadError(ValueError):
    """Malformed export — missing required record, unknown type, etc."""


@dataclass
class ImportSummary:
    """Counts + warnings from a single read."""

    meta: dict | None = None
    entity_count: int = 0
    relation_count: int = 0
    entity_types: Counter = field(default_factory=Counter)
    edge_kinds: Counter = field(default_factory=Counter)
    edge_qualifiers: Counter = field(default_factory=Counter)
    schema_warnings: list[str] = field(default_factory=list)
    skipped_records: int = 0

    def to_dict(self) -> dict:
        return {
            "meta": self.meta,
            "entity_count": self.entity_count,
            "relation_count": self.relation_count,
            "entity_types": dict(self.entity_types),
            "edge_kinds": dict(self.edge_kinds),
            "edge_qualifiers": dict(self.edge_qualifiers),
            "skipped_records": self.skipped_records,
            "schema_warnings": self.schema_warnings,
        }


# ============================================
# Mapping (Q1=A: import all edges with qualifier)
# ============================================

def map_entity(rec: dict) -> EntityData:
    """codeindex entity record → loomgraph EntityData.

    Field map:
      id              → entity_name (kept as module-qualified)
      entity_type     → entity_data.entity_type
      source_id       → entity_data.source_id (codeindex format
                        `relpath:line`; loomgraph's idiomatic form is
                        `relpath:line_start-line_end` but the
                        single-line form parses fine in queries)
      description     → entity_data.description (may be empty)
      provenance      → entity_data.provenance
    """
    source_id = rec["source_id"]
    return EntityData(
        entity_name=rec["id"],
        entity_data={
            "entity_type": rec["entity_type"],
            "description": rec.get("description", ""),
            "source_id": source_id,
            "file_path": source_id.split(":", 1)[0],
            "provenance": rec.get("provenance", "ast"),
        },
    )


def map_edge(rec: dict) -> RelationData | None:
    """codeindex edge record → loomgraph RelationData.

    Q1=A decision (from LoomGraph#30 round-trip planning): import ALL
    edges. Surface the qualifier so downstream filtering is explicit.

    - resolved   → src→dst, weight=1.0
    - ambiguous  → src→candidates[0], weight=0.5, full candidate list
                   preserved in edge_data["candidates"]. Does NOT fan
                   out to N parallel edges — that would inflate caller
                   analytics and lie about the underlying ambiguity.
    - unresolved → src→UNRESOLVED_SENTINEL, weight=0.5. Preserves the
                   edge for completeness analytics but the placeholder
                   tgt makes it a dead-end any consumer walking edges
                   by tgt_id will fail at (failing fast is desirable).

    Returns None for malformed records (e.g. ambiguous with no
    candidates) — those are counted under `skipped_records` in the
    summary.
    """
    qualifier = rec["resolution_qualifier"]
    kind = rec["kind"]
    src = rec["src"]
    source_id = rec["source_id"]
    candidates = rec.get("candidates") or []
    dst = rec.get("dst")

    if qualifier == "resolved":
        if not dst:
            return None
        tgt_id = dst
    elif qualifier == "ambiguous":
        if not candidates:
            return None
        tgt_id = candidates[0]
    elif qualifier == "unresolved":
        tgt_id = UNRESOLVED_SENTINEL
    else:
        return None

    edge_data: dict = {
        "keywords": kind,
        "description": f"{kind} from {src} at {source_id}",
        "weight": 1.0 if qualifier == "resolved" else 0.5,
        "source_id": source_id,
        "resolution_qualifier": qualifier,
    }
    if candidates:
        edge_data["candidates"] = candidates

    return RelationData(src_id=src, tgt_id=tgt_id, edge_data=edge_data)


# ============================================
# Reader
# ============================================

class GraphExportReader:
    """Reads + validates + maps a codeindex graph-export NDJSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def read(self) -> tuple[list[EntityData], list[RelationData], ImportSummary]:
        """Eagerly read everything, returning lists + summary.

        Suitable for typical codebases (we tested 15k records / 6 MB
        cleanly). For multi-million-record artifacts a streaming variant
        would be needed.
        """
        if not self.path.exists():
            raise ExportReadError(f"Artifact not found: {self.path}")

        summary = ImportSummary()
        entities: list[EntityData] = []
        relations: list[RelationData] = []

        for i, line in enumerate(self.path.open(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                summary.schema_warnings.append(f"line {i}: bad JSON ({e})")
                summary.skipped_records += 1
                continue

            t = rec.get("type")
            if t == "meta":
                self._handle_meta(i, rec, summary)
            elif t == "entity":
                self._handle_entity(i, rec, summary, entities)
            elif t == "edge":
                self._handle_edge(i, rec, summary, relations)
            else:
                summary.schema_warnings.append(
                    f"line {i}: unknown record type {t!r}"
                )
                summary.skipped_records += 1

        if summary.meta is None:
            summary.schema_warnings.append(
                "no meta record found — schema_version cannot be verified"
            )

        return entities, relations, summary

    def _handle_meta(self, line_no: int, rec: dict, summary: ImportSummary) -> None:
        missing = META_REQUIRED - rec.keys()
        if missing:
            summary.schema_warnings.append(
                f"line {line_no} meta: missing required {sorted(missing)}"
            )
        if rec.get("schema_version") is not None and \
                rec["schema_version"] > SUPPORTED_SCHEMA_VERSION:
            summary.schema_warnings.append(
                f"schema_version {rec['schema_version']} > "
                f"supported {SUPPORTED_SCHEMA_VERSION} — newer codeindex"
            )
        if "provenance_completeness" not in rec:
            summary.schema_warnings.append(
                "meta: missing provenance_completeness — required by "
                "LoomGraph#30 verdict for consumer trust calculus"
            )
        summary.meta = rec

    def _handle_entity(
        self,
        line_no: int,
        rec: dict,
        summary: ImportSummary,
        out: list[EntityData],
    ) -> None:
        missing = ENTITY_REQUIRED - rec.keys()
        if missing:
            summary.schema_warnings.append(
                f"line {line_no} entity: missing {sorted(missing)}"
            )
            summary.skipped_records += 1
            return
        if rec["entity_type"] not in VALID_ENTITY_TYPES:
            summary.schema_warnings.append(
                f"line {line_no} entity: unknown entity_type "
                f"{rec['entity_type']!r}"
            )
        summary.entity_types[rec["entity_type"]] += 1
        summary.entity_count += 1
        out.append(map_entity(rec))

    def _handle_edge(
        self,
        line_no: int,
        rec: dict,
        summary: ImportSummary,
        out: list[RelationData],
    ) -> None:
        missing = EDGE_REQUIRED - rec.keys()
        if missing:
            summary.schema_warnings.append(
                f"line {line_no} edge: missing {sorted(missing)}"
            )
            summary.skipped_records += 1
            return
        if rec["kind"] not in VALID_EDGE_KINDS:
            summary.schema_warnings.append(
                f"line {line_no} edge: unknown kind {rec['kind']!r}"
            )
        if rec["resolution_qualifier"] not in VALID_QUALIFIERS:
            summary.schema_warnings.append(
                f"line {line_no} edge: unknown qualifier "
                f"{rec['resolution_qualifier']!r}"
            )
        summary.edge_kinds[rec["kind"]] += 1
        summary.edge_qualifiers[rec["resolution_qualifier"]] += 1

        mapped = map_edge(rec)
        if mapped is None:
            summary.skipped_records += 1
            return
        summary.relation_count += 1
        out.append(mapped)

    def iter_records(self) -> Iterator[dict]:
        """Memory-friendly iterator over raw JSON records (for tests
        and tooling that don't need the eager-mapped output)."""
        for line in self.path.open():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
