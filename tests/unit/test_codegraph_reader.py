"""#152: codegraph extraction backend — reader 单元测试。

数据源是 codegraph(``@colbymchenry/codegraph``)在 ``<repo>/.codegraph/
codegraph.db`` 维护的 SQLite 库(WAL,可能被 daemon 持有)。reader 职责:
快照(query_only + backup,不直连)、schema 指纹(fail-loud 子集校验 +
extraction_version gate)、node 白名单映射 + qualified_name 消歧(不唯一名
是 BLOCKER:store entity_name 是主键,直接用会静默合并成幻影 hub)、边映射
(calls 64% 以 file node 为 source → file 实体入图)。

fixture 全部测试内即时合成(tmp_path),不提交二进制 db。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from loomgraph.io.codegraph_reader import (
    CodegraphDbMissingError,
    CodegraphSchemaError,
    run_codegraph_export,
)

# codegraph schema.sql (1.5.0, migrations v1–v9 append-only) 的最小复刻 ——
# 只建 reader 消费的表/列 + 几个"多余列"锻炼子集指纹。
_SCHEMA = """
CREATE TABLE schema_versions (version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL, description TEXT);
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL,
    start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
    start_column INTEGER NOT NULL, end_column INTEGER NOT NULL,
    docstring TEXT, signature TEXT, visibility TEXT,
    is_exported INTEGER DEFAULT 0,
    extra_future_column TEXT,
    updated_at INTEGER NOT NULL
);
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL, target TEXT NOT NULL,
    kind TEXT NOT NULL,
    metadata TEXT,
    line INTEGER, col INTEGER,
    provenance TEXT DEFAULT NULL,
    FOREIGN KEY (source) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target) REFERENCES nodes(id) ON DELETE CASCADE
);
CREATE TABLE files (
    path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, language TEXT NOT NULL,
    size INTEGER NOT NULL, modified_at INTEGER NOT NULL, indexed_at INTEGER NOT NULL,
    node_count INTEGER DEFAULT 0, errors TEXT, generated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE unresolved_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id TEXT NOT NULL, reference_name TEXT NOT NULL,
    reference_kind TEXT NOT NULL, line INTEGER NOT NULL, col INTEGER NOT NULL,
    candidates TEXT, file_path TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'pending', name_tail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE project_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL);
"""


def _node(
    nid: str, kind: str, qname: str, path: str, line: int = 1,
    doc: str | None = None, sig: str | None = None,
) -> tuple:
    return (nid, kind, qname.rsplit("::", 1)[-1], qname, path, "typescript",
            line, line, 0, 0, doc, sig, "public", 1, None, 1000)


def _edge(src: str, tgt: str, kind: str, provenance: str | None = None,
          line: int | None = None) -> tuple:
    return (src, tgt, kind, None, line, 0, provenance)


def build_codegraph_db(
    db_path: Path,
    nodes: list[tuple],
    edges: list[tuple],
    *,
    extraction_version: int = 24,
    indexed_with_version: str = "1.5.0",
    drop_table: str | None = None,
    drop_column: str | None = None,
) -> Path:
    """Build a minimal codegraph db (schema subset-fingerprint compatible)."""
    schema = _SCHEMA
    if drop_table:
        # remove the CREATE TABLE block for drop_table
        lines = schema.splitlines(keepends=True)
        out, skipping = [], False
        for ln in lines:
            if ln.startswith("CREATE TABLE"):
                skipping = drop_table in ln
            if not skipping:
                out.append(ln)
            elif ln.rstrip().endswith(");"):
                skipping = False
        schema = "".join(out)
    if drop_column:
        schema = "\n".join(
            ln for ln in schema.splitlines()
            if not ln.strip().startswith(drop_column)
        ) + "\n"
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    conn.executemany(
        "INSERT INTO nodes (id,kind,name,qualified_name,file_path,language,"
        "start_line,end_line,start_column,end_column,docstring,signature,"
        "visibility,is_exported,extra_future_column,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        nodes,
    )
    conn.executemany(
        "INSERT INTO edges (source,target,kind,metadata,line,col,provenance) "
        "VALUES (?,?,?,?,?,?,?)",
        edges,
    )
    conn.execute(
        "INSERT INTO project_metadata (key,value,updated_at) VALUES (?,?,?)",
        ("indexed_with_version", indexed_with_version, 1),
    )
    if extraction_version is not None:
        conn.execute(
            "INSERT INTO project_metadata (key,value,updated_at) VALUES (?,?,?)",
            ("indexed_with_extraction_version", str(extraction_version), 1),
        )
    conn.commit()
    conn.close()
    return db_path


def _repo_with_codegraph(
    tmp_path: Path, nodes: list[tuple], edges: list[tuple], **kw: Any
) -> Path:
    repo = tmp_path / "repo"
    (repo / ".codegraph").mkdir(parents=True)
    build_codegraph_db(repo / ".codegraph" / "codegraph.db", nodes, edges, **kw)
    return repo


# ─── schema 指纹 ───────────────────────────────────────────────────────────


def test_missing_codegraph_dir_fails_loud(tmp_path: Path) -> None:
    """无 .codegraph/ → 明确异常(不能当空图 success)。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(CodegraphDbMissingError):
        run_codegraph_export(repo)


def test_schema_subset_passes_with_extra_columns(tmp_path: Path) -> None:
    """加列 migration(append-only)不误报 —— 指纹是子集校验。"""
    repo = _repo_with_codegraph(tmp_path, [_node("n1", "function", "foo", "a.ts")], [])
    entities, relations, summary, warnings = run_codegraph_export(repo)
    assert summary.entity_count == 1
    assert not relations


def test_missing_table_fails_loud(tmp_path: Path) -> None:
    repo = _repo_with_codegraph(
        tmp_path, [_node("n1", "function", "foo", "a.ts")], [],
        drop_table="unresolved_refs",
    )
    with pytest.raises(CodegraphSchemaError):
        run_codegraph_export(repo)


def test_missing_column_fails_loud(tmp_path: Path) -> None:
    """缺列 fail-loud —— 但先建库(用 SELECT 重建含所有列的 nodes)再 drop 列。"""
    repo = _repo_with_codegraph(
        tmp_path, [_node("n1", "function", "foo", "a.ts")], [],
    )
    db = repo / ".codegraph" / "codegraph.db"
    conn = sqlite3.connect(db)
    conn.execute("ALTER TABLE nodes RENAME TO nodes_full")
    conn.execute(
        "CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
        "name TEXT NOT NULL, file_path TEXT NOT NULL, language TEXT NOT NULL, "
        "start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, "
        "start_column INTEGER NOT NULL, end_column INTEGER NOT NULL, "
        "updated_at INTEGER NOT NULL)"
    )
    conn.execute(
        "INSERT INTO nodes (id,kind,name,file_path,language,start_line,end_line,"
        "start_column,end_column,updated_at) "
        "SELECT id,kind,name,file_path,language,start_line,end_line,"
        "start_column,end_column,updated_at FROM nodes_full"
    )
    conn.commit()
    conn.close()
    with pytest.raises(CodegraphSchemaError):
        run_codegraph_export(repo)


def test_future_extraction_version_fails_loud(tmp_path: Path) -> None:
    """语义 bump 无 schema 变更时列集合抓不到 —— extraction_version gate。"""
    repo = _repo_with_codegraph(
        tmp_path, [_node("n1", "function", "foo", "a.ts")], [],
        extraction_version=25,
    )
    with pytest.raises(CodegraphSchemaError, match="extraction"):
        run_codegraph_export(repo)


# ─── node 映射 ─────────────────────────────────────────────────────────────


def test_node_whitelist_and_type_verbatim(tmp_path: Path) -> None:
    """白名单 kind 原文入 entity_type;import/parameter/enum_member 等排除。"""
    nodes = [
        _node("n1", "function", "foo", "a.ts"),
        _node("n2", "class", "Foo", "a.ts"),
        _node("n3", "route", "a.ts::USE:/api", "a.ts"),
        _node("n4", "component", "Button", "b.tsx"),
        _node("n5", "import", "@prisma/client", "a.ts"),
        _node("n6", "parameter", "x", "a.ts"),
        _node("n7", "enum_member", "RED", "a.ts"),
        _node("n8", "namespace", "ns", "a.ts"),
        _node("n9", "export", "foo", "a.ts"),
    ]
    repo = _repo_with_codegraph(tmp_path, nodes, [])
    entities, _, summary, _ = run_codegraph_export(repo)
    types = {e.entity_data["entity_type"] for e in entities}
    assert types == {"function", "class", "route", "component"}
    assert summary.entity_count == 4


def test_file_nodes_become_entities(tmp_path: Path) -> None:
    """file node 入图为一等实体(64% calls 边的 source 是 file,不入图即丢)。"""
    nodes = [
        _node("f1", "file", "src/a.ts", "src/a.ts"),
        _node("n1", "function", "foo", "src/a.ts"),
    ]
    repo = _repo_with_codegraph(tmp_path, nodes, [])
    entities, _, _, _ = run_codegraph_export(repo)
    names = {e.entity_name for e in entities}
    assert "src/a.ts" in names
    (file_e,) = [e for e in entities if e.entity_data["entity_type"] == "file"]
    assert not file_e.entity_data.get("description"), (
        "file 实体 description 留空(0/675 实测无 docstring;有值会无谓 embed)"
    )


def test_description_signature_then_docstring(tmp_path: Path) -> None:
    nodes = [
        _node("n1", "function", "foo", "a.ts", doc="does x", sig="foo(a: int)"),
        _node("n2", "function", "bar", "a.ts", doc=None, sig="bar()"),
    ]
    repo = _repo_with_codegraph(tmp_path, nodes, [])
    entities, _, _, _ = run_codegraph_export(repo)
    by_name = {e.entity_name: e for e in entities}
    assert by_name["foo"].entity_data["description"] == "foo(a: int) | does x"
    assert by_name["bar"].entity_data["description"] == "bar()"


def test_source_id_is_file_colon_line(tmp_path: Path) -> None:
    """source_id 与 codeindex 契约同构(relpath:line)——deps 模块聚合依赖它。"""
    nodes = [_node("n1", "function", "foo", "src/mod/a.ts", line=42)]
    repo = _repo_with_codegraph(tmp_path, nodes, [])
    entities, _, _, _ = run_codegraph_export(repo)
    assert entities[0].entity_data["source_id"] == "src/mod/a.ts:42"


# ─── 消歧(BLOCKER:qualified_name 不唯一)─────────────────────────────────


def test_duplicate_qualified_names_disambiguated(tmp_path: Path) -> None:
    """styles×33 场景:同名节点静默合并会造幻影 hub/god —— 重名加 file 前缀。"""
    nodes = [
        _node("n1", "function", "styles", "src/a/styles.ts"),
        _node("n2", "function", "styles", "src/b/styles.ts"),
        _node("n3", "function", "styles", "src/c/styles.ts"),
        _node("n4", "function", "unique_fn", "src/a/x.ts"),
    ]
    repo = _repo_with_codegraph(tmp_path, nodes, [])
    entities, _, _, _ = run_codegraph_export(repo)
    names = {e.entity_name for e in entities}
    assert names == {
        "src/a/styles.ts::styles",
        "src/b/styles.ts::styles",
        "src/c/styles.ts::styles",
        "unique_fn",  # 唯一名保持干净(93% 多数不加前缀)
    }


def test_edges_use_disambiguated_names(tmp_path: Path) -> None:
    """边端点必须走同一消歧映射,否则边落到合并前的旧名上变 dangling。"""
    nodes = [
        _node("n1", "function", "styles", "src/a/styles.ts"),
        _node("n2", "function", "styles", "src/b/styles.ts"),
        _node("n3", "function", "caller", "src/x.ts"),
    ]
    edges = [_edge("n3", "n1", "calls"), _edge("n3", "n2", "calls")]
    repo = _repo_with_codegraph(tmp_path, nodes, edges)
    _, relations, _, _ = run_codegraph_export(repo)
    targets = {r.tgt_id for r in relations}
    assert targets == {"src/a/styles.ts::styles", "src/b/styles.ts::styles"}


# ─── 边映射 ────────────────────────────────────────────────────────────────


def test_edge_kind_mapping_table(tmp_path: Path) -> None:
    """calls→CALLS;imports→IMPORTS;extends/implements→INHERITS;
    instantiates→CALLS;references/decorates→REFERENCES;
    contains/exports/type_of/returns/overrides 丢弃。"""
    nodes = [
        _node("a", "function", "fn_a", "a.ts"),
        _node("b", "function", "fn_b", "b.ts"),
        _node("c", "class", "Cls", "c.ts"),
        _node("d", "interface", "Iface", "d.ts"),
    ]
    edges = [
        _edge("a", "b", "calls"),
        _edge("a", "b", "imports"),
        _edge("c", "d", "extends"),
        _edge("c", "d", "implements"),
        _edge("a", "c", "instantiates"),
        _edge("a", "b", "references"),
        _edge("a", "c", "decorates"),
        # dropped:
        _edge("a", "b", "contains"),
        _edge("a", "b", "exports"),
        _edge("a", "b", "type_of"),
        _edge("a", "b", "returns"),
        _edge("a", "b", "overrides"),
    ]
    repo = _repo_with_codegraph(tmp_path, nodes, edges)
    _, relations, summary, _ = run_codegraph_export(repo)
    kinds = sorted(r.edge_data["keywords"] for r in relations)
    assert kinds == ["CALLS", "CALLS", "IMPORTS", "INHERITS", "INHERITS", "REFERENCES", "REFERENCES"]
    assert summary.relation_count == len(relations) == 7


def test_external_import_edge_marked_unresolved(tmp_path: Path) -> None:
    """imports→import-node(外部依赖)必须标 unresolved,否则 #113 幻影 callees
    (ingest 契约里缺失 qualifier 被当 resolved)。"""
    nodes = [
        _node("f1", "file", "a.ts", "a.ts"),
        _node("imp", "import", "@prisma/client", "a.ts"),
        _node("fn", "function", "main", "a.ts"),
    ]
    edges = [
        _edge("f1", "imp", "imports"),   # external → dangling target
        _edge("f1", "fn", "imports"),    # internal → resolved
        _edge("f1", "fn", "calls"),
    ]
    repo = _repo_with_codegraph(tmp_path, nodes, edges)
    _, relations, _, _ = run_codegraph_export(repo)
    by_kw = {(r.edge_data["keywords"], r.tgt_id): r for r in relations}
    ext = by_kw[("IMPORTS", "@prisma/client")]
    assert ext.edge_data["resolution_qualifier"] == "unresolved"
    assert ext.edge_data["dst_raw"] == "@prisma/client"
    for key in [("IMPORTS", "main"), ("CALLS", "main")]:
        assert by_kw[key].edge_data["resolution_qualifier"] == "resolved"


def test_heuristic_provenance_propagated(tmp_path: Path) -> None:
    nodes = [
        _node("a", "function", "fn_a", "a.ts"),
        _node("b", "function", "fn_b", "b.ts"),
    ]
    edges = [
        _edge("a", "b", "calls", provenance="heuristic"),
        _edge("b", "a", "calls", provenance=None),
    ]
    repo = _repo_with_codegraph(tmp_path, nodes, edges)
    _, relations, _, _ = run_codegraph_export(repo)
    heur = [r for r in relations if r.edge_data.get("provenance") == "heuristic"]
    assert len(heur) == 1 and heur[0].src_id == "fn_a"
    plain = [r for r in relations if r.src_id == "fn_b"]
    assert plain[0].edge_data.get("provenance", "ast") != "heuristic"


def test_edge_to_excluded_node_kept_as_unresolved(tmp_path: Path) -> None:
    """指向被排除 kind(parameter 等)的边也标 unresolved 保留(不静默丢)。"""
    nodes = [
        _node("a", "function", "fn_a", "a.ts"),
        _node("p", "parameter", "x", "a.ts"),
    ]
    edges = [_edge("a", "p", "references")]
    repo = _repo_with_codegraph(tmp_path, nodes, edges)
    _, relations, _, _ = run_codegraph_export(repo)
    assert len(relations) == 1
    assert relations[0].edge_data["resolution_qualifier"] == "unresolved"


# ─── 快照 ──────────────────────────────────────────────────────────────────


def test_snapshot_reads_wal_data(tmp_path: Path) -> None:
    """源 db 带 WAL 未 checkpoint 数据时快照必须读到(rw+backup 路径而非
    immutable=1 —— 后者丢 WAL 近写)。"""
    repo = _repo_with_codegraph(
        tmp_path, [_node("n1", "function", "foo", "a.ts")], [],
    )
    src = repo / ".codegraph" / "codegraph.db"
    conn = sqlite3.connect(src)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "INSERT INTO nodes (id,kind,name,qualified_name,file_path,language,"
        "start_line,end_line,start_column,end_column,docstring,signature,"
        "visibility,is_exported,extra_future_column,updated_at) "
        "VALUES ('n2','function','wal_only','wal_only','w.ts','typescript',"
        "1,1,0,0,NULL,NULL,'public',1,NULL,1001)"
    )
    conn.commit()
    # 不 checkpoint —— n2 只存在于 WAL
    entities, _, _, _ = run_codegraph_export(repo)
    assert "wal_only" in {e.entity_name for e in entities}
    conn.close()


def test_snapshot_does_not_mutate_source(tmp_path: Path) -> None:
    """快照过程对源 db 零写入(query_only)——repo 属于用户/codegraph daemon。"""
    repo = _repo_with_codegraph(
        tmp_path, [_node("n1", "function", "foo", "a.ts")], [],
    )
    src = repo / ".codegraph" / "codegraph.db"
    before = src.read_bytes()
    run_codegraph_export(repo)
    assert src.read_bytes() == before


# ─── summary/meta ──────────────────────────────────────────────────────────


def test_summary_carries_codegraph_meta(tmp_path: Path) -> None:
    """snapshot 诊断信息(extraction_version 等)经 summary.meta 供 CLI 写入
    workspace meta;codegraph db 无 git sha,head 由 CLI 层补记。"""
    nodes = [_node("n1", "function", "foo", "a.ts")]
    repo = _repo_with_codegraph(tmp_path, nodes, [])
    _, _, summary, _ = run_codegraph_export(repo)
    meta = summary.meta or {}
    assert meta.get("indexed_with_version") == "1.5.0"
    assert meta.get("indexed_with_extraction_version") == "24"
