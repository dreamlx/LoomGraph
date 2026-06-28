"""Unit tests for loomgraph.io.export_reader.

Covers the schema validation, mapping semantics, and resolution-qualifier
handling required by the codeindex#102 consumer contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loomgraph.io.export_reader import (
    UNRESOLVED_SENTINEL,
    ExportReadError,
    GraphExportReader,
    map_edge,
    map_entity,
)

# ----- Fixtures ----------------------------------------------------------

MIN_META = {
    "type": "meta",
    "schema_version": 0,
    "generator": "codeindex",
    "provenance_completeness": "ast-only: dynamic dispatch missing",
}

ENTITY_RECORDS = [
    {
        "type": "entity",
        "id": "app.svc.AuthService",
        "entity_type": "class",
        "source_id": "app/svc.py:8",
        "description": "Authenticates users.",
        "provenance": "ast",
    },
    {
        "type": "entity",
        "id": "app.svc.AuthService.login",
        "entity_type": "method",
        "source_id": "app/svc.py:12",
        "description": "",
        "provenance": "ast",
    },
]

EDGE_RECORDS = [
    {
        "type": "edge",
        "kind": "CALLS",
        "src": "app.svc.AuthService.login",
        "dst": "app.svc.AuthService.authenticate",
        "dst_raw": "self.authenticate",
        "resolution_qualifier": "resolved",
        "source_id": "app/svc.py:15",
    },
    {
        "type": "edge",
        "kind": "CALLS",
        "src": "app.workers.kickoff",
        "dst": None,
        "dst_raw": "Builder.run",
        "candidates": [
            "app.workers.Builder.run",
            "app.workers.Packer.run",
        ],
        "resolution_qualifier": "ambiguous",
        "source_id": "app/workers.py:15",
    },
    {
        "type": "edge",
        "kind": "CALLS",
        "src": "app.svc.AuthService.login",
        "dst": None,
        "dst_raw": "os.environ.get",
        "resolution_qualifier": "unresolved",
        "source_id": "app/svc.py:18",
    },
]


def _write_ndjson(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "export.ndjson"
    p.write_text("\n".join(json.dumps(r) for r in records))
    return p


# ----- map_entity --------------------------------------------------------

def test_map_entity_preserves_qualified_name():
    rec = ENTITY_RECORDS[0]
    ent = map_entity(rec)
    assert ent.entity_name == "app.svc.AuthService"
    assert ent.entity_data["entity_type"] == "class"
    assert ent.entity_data["source_id"] == "app/svc.py:8"
    assert ent.entity_data["file_path"] == "app/svc.py"
    assert ent.entity_data["provenance"] == "ast"
    assert ent.entity_data["description"] == "Authenticates users."


def test_map_entity_handles_empty_description():
    ent = map_entity(ENTITY_RECORDS[1])
    assert ent.entity_data["description"] == ""


# ----- map_edge (the qualifier matrix) -----------------------------------

def test_map_edge_resolved_uses_dst_weight_1():
    rel = map_edge(EDGE_RECORDS[0])
    assert rel is not None
    assert rel.src_id == "app.svc.AuthService.login"
    assert rel.tgt_id == "app.svc.AuthService.authenticate"
    assert rel.edge_data["weight"] == 1.0
    assert rel.edge_data["resolution_qualifier"] == "resolved"
    assert rel.edge_data["keywords"] == "CALLS"


def test_map_edge_ambiguous_uses_first_candidate_keeps_full_list():
    rel = map_edge(EDGE_RECORDS[1])
    assert rel is not None
    assert rel.src_id == "app.workers.kickoff"
    assert rel.tgt_id == "app.workers.Builder.run"
    assert rel.edge_data["weight"] == 0.5
    assert rel.edge_data["resolution_qualifier"] == "ambiguous"
    assert rel.edge_data["candidates"] == [
        "app.workers.Builder.run",
        "app.workers.Packer.run",
    ]


def test_map_edge_unresolved_uses_dst_raw_when_present():
    """ai-codeindex>=0.27.0 ships `dst_raw` (the original call expression)
    on every edge — use it as a distinct tgt for unresolved edges so each
    one targets the actual stdlib/external call name instead of a fake
    shared hub."""
    rel = map_edge(EDGE_RECORDS[2])
    assert rel is not None
    assert rel.tgt_id == "os.environ.get"  # dst_raw preserved
    assert rel.tgt_id != UNRESOLVED_SENTINEL
    assert rel.edge_data["weight"] == 0.5
    assert rel.edge_data["resolution_qualifier"] == "unresolved"
    assert rel.edge_data["dst_raw"] == "os.environ.get"


def test_map_edge_unresolved_falls_back_to_sentinel_pre_0_27_0():
    """Older artifacts without dst_raw: degrade gracefully to the sentinel
    so the reader still loads pre-0.27.0 exports without crashing."""
    rec_pre_0_27 = dict(EDGE_RECORDS[2])
    del rec_pre_0_27["dst_raw"]
    rel = map_edge(rec_pre_0_27)
    assert rel is not None
    assert rel.tgt_id == UNRESOLVED_SENTINEL


def test_map_edge_resolved_preserves_dst_raw_for_display():
    """Resolved edges keep dst_raw in edge_data so consumers showing
    code can render the original short name (e.g. `self.authenticate`)
    even when the resolved id is module-qualified."""
    rel = map_edge(EDGE_RECORDS[0])
    assert rel is not None
    assert rel.tgt_id == "app.svc.AuthService.authenticate"  # resolved
    assert rel.edge_data["dst_raw"] == "self.authenticate"


def test_map_edge_malformed_ambiguous_returns_none():
    rec = dict(EDGE_RECORDS[1])
    rec["candidates"] = []  # ambiguous but no candidates listed
    assert map_edge(rec) is None


def test_map_edge_resolved_without_dst_returns_none():
    rec = dict(EDGE_RECORDS[0])
    rec["dst"] = None
    assert map_edge(rec) is None


# ----- GraphExportReader -------------------------------------------------

def test_reader_round_trips_minimal_artifact(tmp_path: Path):
    """With dst_raw on every edge (ai-codeindex>=0.27.0): all 3 qualifier
    states land in storage with distinct tgt_ids."""
    path = _write_ndjson(tmp_path, [MIN_META, *ENTITY_RECORDS, *EDGE_RECORDS])
    entities, relations, summary = GraphExportReader(path).read()

    assert len(entities) == 2
    assert len(relations) == 3, "all 3 edges stored when dst_raw present"
    qualifiers_stored = {
        r.edge_data["resolution_qualifier"] for r in relations
    }
    assert qualifiers_stored == {"resolved", "ambiguous", "unresolved"}
    # tgt_ids must be distinct — no fake hub
    tgts = {r.tgt_id for r in relations}
    assert len(tgts) == 3
    assert summary.entity_count == 2
    assert summary.relation_count == 3
    assert summary.entity_types == {"class": 1, "method": 1}
    assert summary.edge_qualifiers == {"resolved": 1, "ambiguous": 1, "unresolved": 1}
    assert summary.edge_kinds == {"CALLS": 3}
    assert summary.schema_warnings == []
    assert summary.meta is not None
    assert summary.meta["schema_version"] == 0


def test_reader_pre_0_27_0_artifact_still_skips_unresolved(tmp_path: Path):
    """Backwards compat: artifacts produced before 0.27.0 don't have
    dst_raw — the reader skips unresolved as before so the sentinel
    fake-hub problem doesn't reappear."""
    pre_unresolved = [
        {
            "type": "edge",
            "kind": "CALLS",
            "src": ENTITY_RECORDS[1]["id"],
            "dst": None,
            "resolution_qualifier": "unresolved",
            "source_id": f"app/svc.py:{20 + i}",
        }
        for i in range(5)
    ]
    path = _write_ndjson(tmp_path, [MIN_META, *ENTITY_RECORDS, *pre_unresolved])
    _, relations, summary = GraphExportReader(path).read()
    assert relations == [], "pre-0.27.0 unresolved edges remain skipped"
    assert summary.edge_qualifiers["unresolved"] == 5
    assert summary.relation_count == 0


def test_reader_unresolved_edges_with_dst_raw_target_distinct_names(tmp_path: Path):
    """0.27.0 regression guard: many unresolved edges to different
    stdlib calls land as distinct relations (no fake hub)."""
    fresh_unresolved = [
        {
            "type": "edge",
            "kind": "CALLS",
            "src": ENTITY_RECORDS[1]["id"],
            "dst": None,
            "dst_raw": raw,
            "resolution_qualifier": "unresolved",
            "source_id": f"app/svc.py:{20 + i}",
        }
        for i, raw in enumerate(
            ["os.environ.get", "json.loads", "json.dumps", "sys.exit", "subprocess.run"]
        )
    ]
    path = _write_ndjson(tmp_path, [MIN_META, *ENTITY_RECORDS, *fresh_unresolved])
    _, relations, summary = GraphExportReader(path).read()
    assert len(relations) == 5
    tgts = {r.tgt_id for r in relations}
    assert tgts == {"os.environ.get", "json.loads", "json.dumps", "sys.exit", "subprocess.run"}
    assert summary.edge_qualifiers["unresolved"] == 5


def test_reader_flags_missing_provenance_completeness(tmp_path: Path):
    meta = dict(MIN_META)
    meta.pop("provenance_completeness")
    path = _write_ndjson(tmp_path, [meta, *ENTITY_RECORDS])
    _, _, summary = GraphExportReader(path).read()
    assert any(
        "provenance_completeness" in w for w in summary.schema_warnings
    ), summary.schema_warnings


def test_reader_flags_missing_meta_record(tmp_path: Path):
    path = _write_ndjson(tmp_path, ENTITY_RECORDS)  # no meta line
    _, _, summary = GraphExportReader(path).read()
    assert summary.meta is None
    assert any("no meta record" in w for w in summary.schema_warnings)


def test_reader_skips_malformed_json_with_warning(tmp_path: Path):
    p = tmp_path / "broken.ndjson"
    p.write_text(json.dumps(MIN_META) + "\n{not-json\n" + json.dumps(ENTITY_RECORDS[0]))
    entities, _, summary = GraphExportReader(p).read()
    assert len(entities) == 1
    assert summary.skipped_records == 1
    assert any("bad JSON" in w for w in summary.schema_warnings)


def test_reader_flags_future_schema_version(tmp_path: Path):
    meta = dict(MIN_META, schema_version=99)
    path = _write_ndjson(tmp_path, [meta])
    _, _, summary = GraphExportReader(path).read()
    assert any(
        "schema_version 99" in w for w in summary.schema_warnings
    ), summary.schema_warnings


def test_reader_missing_path_raises(tmp_path: Path):
    with pytest.raises(ExportReadError):
        GraphExportReader(tmp_path / "does-not-exist.ndjson").read()


def test_summary_to_dict_is_json_serialisable(tmp_path: Path):
    path = _write_ndjson(tmp_path, [MIN_META, *ENTITY_RECORDS, *EDGE_RECORDS])
    _, _, summary = GraphExportReader(path).read()
    # Round-trip through JSON to make sure CLI output won't break
    rebuilt = json.loads(json.dumps(summary.to_dict()))
    assert rebuilt["entity_count"] == 2
    assert rebuilt["edge_qualifiers"] == {
        "resolved": 1,
        "ambiguous": 1,
        "unresolved": 1,
    }
