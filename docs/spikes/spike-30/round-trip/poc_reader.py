"""Stage-A POC reader for codeindex `graph-export` NDJSON artifacts.

Purpose: prove that the codeindex artifact (codeindex#102 feat/102-graph-export
branch) round-trips cleanly into loomgraph's EntityData / RelationData model.
Does NOT write to a workspace .db — pure dry-run inspection.

Reports:
- Record counts (meta / entity / edge by qualifier + kind)
- Schema mismatches between codeindex format and loomgraph expectations
- Mapping decisions for ambiguous + unresolved edges (per Q1=A: import all)
- Sample mapped EntityData + RelationData

Run:
  .venv/bin/python docs/spikes/spike-30/round-trip/poc_reader.py \
    /tmp/codeindex-self-export.ndjson
"""

from __future__ import annotations

import collections
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "src"))

from loomgraph.core.models import EntityData, RelationData


# ============================================
# Codeindex schema constants (from docs/guides/graph-export.md)
# ============================================
META_REQUIRED = {"type", "schema_version", "generator"}
META_RECOMMENDED = {"provenance_completeness"}
ENTITY_REQUIRED = {"type", "id", "entity_type", "source_id", "provenance"}
ENTITY_OPTIONAL = {"description"}
EDGE_REQUIRED = {"type", "kind", "src", "resolution_qualifier", "source_id"}
EDGE_OPTIONAL = {"dst", "candidates"}

VALID_ENTITY_TYPES = {"class", "function", "method"}
VALID_EDGE_KINDS = {"CALLS", "INHERITS"}
VALID_QUALIFIERS = {"resolved", "ambiguous", "unresolved"}


# ============================================
# Mapping (Q1=A: import all edges with qualifier)
# ============================================

def map_entity(rec: dict) -> EntityData:
    """codeindex entity record → loomgraph EntityData.

    Field map (codeindex → loomgraph entity_data):
      id              → entity_name (kept as module-qualified)
      entity_type     → entity_data.entity_type
      source_id       → entity_data.source_id (kept as 'relpath:line';
                        loomgraph idiom is 'relpath:line_start-line_end',
                        but codeindex's single-line form is a strict subset
                        — loomgraph queries / display handle both)
      description     → entity_data.description (may be empty)
      provenance      → entity_data.provenance (preserved verbatim)
    """
    return EntityData(
        entity_name=rec["id"],
        entity_data={
            "entity_type": rec["entity_type"],
            "description": rec.get("description", ""),
            "source_id": rec["source_id"],
            "file_path": rec["source_id"].split(":", 1)[0],
            "provenance": rec.get("provenance", "ast"),
        },
    )


def map_edge(rec: dict) -> RelationData | None:
    """codeindex edge record → loomgraph RelationData.

    Q1=A decision: import ALL edges including ambiguous + unresolved,
    surfacing the resolution_qualifier so downstream consumers (CLI users,
    agents) can apply the trust calculus the spike#30 verdict requires.

    Handling per qualifier:
      resolved   → src→dst as 1 edge with qualifier='resolved'
      ambiguous  → src→candidates[0] as 1 edge with qualifier='ambiguous'
                   and `candidates` preserved in edge_data so consumer can
                   fan out if needed. Does NOT create N parallel edges —
                   that would inflate edge count + bias caller analytics.
      unresolved → src→`<unresolved>` placeholder, qualifier='unresolved'.
                   Preserves edge count for completeness analytics but
                   wired-zero target makes it a dead-end the consumer
                   must filter on qualifier before walking.

    Returns None only if record itself is malformed (defensive).
    """
    kind = rec["kind"]
    src = rec["src"]
    qualifier = rec["resolution_qualifier"]
    candidates = rec.get("candidates", [])
    source_id = rec["source_id"]
    dst = rec.get("dst")

    if qualifier == "resolved":
        tgt_id = dst
    elif qualifier == "ambiguous":
        if not candidates:
            return None  # malformed
        tgt_id = candidates[0]  # first candidate; full list in edge_data
    elif qualifier == "unresolved":
        tgt_id = "<unresolved>"
    else:
        return None

    edge_data = {
        "keywords": kind,  # loomgraph convention
        "description": f"{kind} from {src} at {source_id}",
        "weight": 1.0 if qualifier == "resolved" else 0.5,
        "source_id": source_id,
        "resolution_qualifier": qualifier,
    }
    if candidates:
        edge_data["candidates"] = candidates

    return RelationData(src_id=src, tgt_id=tgt_id, edge_data=edge_data)


# ============================================
# Driver
# ============================================

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: poc_reader.py <export.ndjson>", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Not found: {path}", file=sys.stderr)
        sys.exit(2)

    print(f"=== Stage A POC — {path.name} ===\n")

    meta = None
    counts = {
        "lines": 0,
        "meta": 0,
        "entity": 0,
        "edge": 0,
        "skipped_malformed": 0,
    }
    entity_types = collections.Counter()
    edge_qualifiers = collections.Counter()
    edge_kinds = collections.Counter()
    schema_warnings = []

    mapped_entities: list[EntityData] = []
    mapped_relations: list[RelationData] = []
    skipped_edges_by_reason = collections.Counter()

    for i, line in enumerate(path.open(), 1):
        counts["lines"] += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            schema_warnings.append(f"line {i}: bad JSON ({e})")
            counts["skipped_malformed"] += 1
            continue

        t = rec.get("type")
        if t == "meta":
            meta = rec
            counts["meta"] += 1
            missing = META_REQUIRED - rec.keys()
            if missing:
                schema_warnings.append(f"line {i} meta: missing required {missing}")
        elif t == "entity":
            counts["entity"] += 1
            missing = ENTITY_REQUIRED - rec.keys()
            if missing:
                schema_warnings.append(f"line {i} entity: missing {missing}")
                continue
            if rec["entity_type"] not in VALID_ENTITY_TYPES:
                schema_warnings.append(
                    f"line {i} entity: unknown entity_type {rec['entity_type']!r}"
                )
            entity_types[rec["entity_type"]] += 1
            mapped_entities.append(map_entity(rec))
        elif t == "edge":
            counts["edge"] += 1
            missing = EDGE_REQUIRED - rec.keys()
            if missing:
                schema_warnings.append(f"line {i} edge: missing {missing}")
                continue
            edge_kinds[rec["kind"]] += 1
            edge_qualifiers[rec["resolution_qualifier"]] += 1
            if rec["kind"] not in VALID_EDGE_KINDS:
                schema_warnings.append(f"line {i} edge: unknown kind {rec['kind']!r}")
            if rec["resolution_qualifier"] not in VALID_QUALIFIERS:
                schema_warnings.append(
                    f"line {i} edge: unknown qualifier {rec['resolution_qualifier']!r}"
                )
            mapped = map_edge(rec)
            if mapped is None:
                skipped_edges_by_reason[rec["resolution_qualifier"]] += 1
                continue
            mapped_relations.append(mapped)
        else:
            schema_warnings.append(f"line {i}: unknown record type {t!r}")

    print("== Counts ==")
    for k, v in counts.items():
        print(f"  {k:24s} {v:>8d}")

    print("\n== Meta record ==")
    if meta:
        for k, v in meta.items():
            if k == "type":
                continue
            preview = str(v)[:140] + ("..." if len(str(v)) > 140 else "")
            print(f"  {k:24s} {preview}")
        missing_rec = META_RECOMMENDED - meta.keys()
        if missing_rec:
            print(f"  ⚠ missing recommended: {missing_rec}")
    else:
        print("  ❌ no meta record found")

    print("\n== Entity types ==")
    for t, n in entity_types.most_common():
        print(f"  {t:12s} {n:>6d}")

    print("\n== Edge kinds × qualifiers ==")
    print(f"  {'kind':12s} {'resolved':>10s} {'ambiguous':>10s} {'unresolved':>10s} {'TOTAL':>8s}")
    for kind in edge_kinds:
        r = a = u = 0
        # second pass — small data, fine
        for line in path.open():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "edge" or rec.get("kind") != kind:
                continue
            q = rec.get("resolution_qualifier")
            if q == "resolved":
                r += 1
            elif q == "ambiguous":
                a += 1
            elif q == "unresolved":
                u += 1
        print(f"  {kind:12s} {r:>10d} {a:>10d} {u:>10d} {r+a+u:>8d}")

    print("\n== Mapping result ==")
    print(f"  entities mapped: {len(mapped_entities)}")
    print(f"  relations mapped: {len(mapped_relations)}")
    print(f"  edges skipped (malformed ambiguous): {dict(skipped_edges_by_reason)}")

    print("\n== Schema warnings ==")
    if not schema_warnings:
        print("  ✅ no warnings — schema mapping clean")
    else:
        print(f"  ⚠ {len(schema_warnings)} warnings; first 5:")
        for w in schema_warnings[:5]:
            print(f"    {w}")

    print("\n== Sample mapped entity (first) ==")
    if mapped_entities:
        print(json.dumps(asdict(mapped_entities[0]), indent=2))

    print("\n== Sample mapped relation (first resolved + first ambiguous + first unresolved) ==")
    seen_q = set()
    for r in mapped_relations:
        q = r.edge_data.get("resolution_qualifier")
        if q in seen_q:
            continue
        seen_q.add(q)
        print(f"  qualifier={q}")
        print(json.dumps(asdict(r), indent=2))
        if len(seen_q) == 3:
            break


if __name__ == "__main__":
    main()
