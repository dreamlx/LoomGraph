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
VALID_EDGE_KINDS = {"CALLS", "INHERITS", "IMPORTS"}
VALID_QUALIFIERS = {"resolved", "ambiguous", "unresolved"}

# Historic sentinel for unresolved-edge targets. Pre-0.27.0 (no `dst_raw`
# in the schema) we'd return this as `tgt_id` for unresolved edges, then
# skip them at the reader level to avoid creating a fake hub.
#
# In `ai-codeindex>=0.27.0` every edge carries `dst_raw` (the original
# call expression text, e.g. `os.environ.get` for an unresolved external
# call). The reader uses `dst_raw` as `tgt_id` for unresolved instead —
# each unresolved edge gets its own distinct target, no fake hub.
#
# Kept exported for backwards-compatibility with callers that pre-date
# 0.27.0 or that hit a record where `dst_raw` is missing.
UNRESOLVED_SENTINEL = "<unresolved>"

# Highest schema_version this reader supports.
# sv1 (codeindex>=0.31.0): per-symbol `content_hash` enables symbol-level
# incremental ingest (loomgraph#90). Reader treats it as an opaque string.
SUPPORTED_SCHEMA_VERSION = 1


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
      signature       → entity_data.signature (codeindex>=0.28 / codeindex#115)
      description     → folded into entity_data.description together with
                        signature (see below)
      provenance      → entity_data.provenance
      content_hash    → entity_data.content_hash (codeindex>=0.31.0 sv1;
                        None for older artifacts. Symbol-level ingest
                        treats None as "always re-embed". loomgraph#90.)

    `description` is rebuilt as `signature | docstring` (empty parts dropped)
    so the embedding pipeline — which embeds `description` — gets the
    signature too. This closes the docstring-coverage hole measured in
    EPIC-015 Phase 0: ~15% of symbols have no docstring, and without the
    signature they got an empty description → no vector → invisible to
    semantic search. A signature is present for ~all symbols. Pre-0.28
    records (no `signature` field) keep the old behaviour: description is
    just the docstring. (codeindex intentionally did NOT bump schema_version
    for this additive field — the combine is the consumer's call, ADR-007.)
    """
    source_id = rec["source_id"]
    signature = rec.get("signature", "")
    docstring = rec.get("description", "")
    description = " | ".join(p for p in (signature, docstring) if p)
    return EntityData(
        entity_name=rec["id"],
        entity_data={
            "entity_type": rec["entity_type"],
            "description": description,
            "signature": signature,
            "source_id": source_id,
            "file_path": source_id.split(":", 1)[0],
            "provenance": rec.get("provenance", "ast"),
            "content_hash": rec.get("content_hash"),
        },
    )


def map_edge(rec: dict) -> RelationData | None:
    """codeindex edge record → loomgraph RelationData.

    Q1=A decision (from LoomGraph#30 round-trip planning): surface the
    `resolution_qualifier` for every edge so consumers can apply the
    trust calculus explicitly.

    Per-qualifier handling:
    - resolved   → src→dst, weight=1.0. dst_raw (if present) preserved in
                   edge_data for display/debug.
    - ambiguous  → src→candidates[0], weight=0.5, full candidate list
                   preserved in edge_data["candidates"]. dst_raw kept too.
                   Does NOT fan out to N parallel edges — that would
                   inflate caller analytics.
    - unresolved → src→dst_raw if present (the original call expression,
                   `ai-codeindex>=0.27.0`), else UNRESOLVED_SENTINEL.
                   Each unresolved edge gets its own distinct tgt, so no
                   fake hub forms. Reader stores these (no longer skips).

    Returns None for malformed records (e.g. ambiguous with no candidates,
    resolved with no dst, unresolved with neither dst_raw nor sentinel
    fallback).
    """
    qualifier = rec["resolution_qualifier"]
    kind = rec["kind"]
    src = rec["src"]
    source_id = rec["source_id"]
    candidates = rec.get("candidates") or []
    dst = rec.get("dst")
    dst_raw = rec.get("dst_raw")

    if qualifier == "resolved":
        if not dst:
            return None
        tgt_id = dst
    elif qualifier == "ambiguous":
        if not candidates:
            return None
        tgt_id = candidates[0]
    elif qualifier == "unresolved":
        # 0.27.0+: use raw call expression as distinct tgt per edge.
        # Pre-0.27.0 (no dst_raw): fall back to sentinel.
        tgt_id = dst_raw or UNRESOLVED_SENTINEL
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
    if dst_raw:
        edge_data["dst_raw"] = dst_raw

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
        qualifier = rec["resolution_qualifier"]
        summary.edge_qualifiers[qualifier] += 1

        # Unresolved edges: in `ai-codeindex>=0.27.0` they carry `dst_raw`
        # (the original call expression), so we CAN store them — each
        # gets its own distinct tgt_id. In older artifacts without
        # `dst_raw` we still skip rather than collapse onto a sentinel
        # hub that would distort topology analytics.
        if qualifier == "unresolved" and not rec.get("dst_raw"):
            return

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
