"""SqliteGraphStore — SQLite single-file backend.

Phase 1 (EPIC-011 / ADR-013): pure SQLite (stdlib sqlite3) backing for
all GraphStore methods. No vector column yet — sqlite-vec virtual table
is added in Phase 2.

Threading: stdlib sqlite3.Connection isn't safe for concurrent use,
so a single persistent connection is opened with `check_same_thread=False`
and serialized via an asyncio.Lock. Operations are dispatched to the
default thread pool via `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from loomgraph.storage.base import GraphStore

_T = TypeVar("_T")

# Promoted columns are the high-traffic query fields. Everything else is
# round-tripped in properties_json so callers can stash arbitrary attrs
# without schema changes.
_ENTITY_PROMOTED = {"entity_name", "entity_type", "description", "source_id"}
_RELATION_PROMOTED = {
    "src_id",
    "source",
    "tgt_id",
    "target",
    "keywords",
    "description",
    "source_id",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    entity_name     TEXT PRIMARY KEY,
    entity_type     TEXT,
    description     TEXT,
    source_id       TEXT,
    properties_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_entities_source ON entities(source_id);
CREATE INDEX IF NOT EXISTS idx_entities_type   ON entities(entity_type);

CREATE TABLE IF NOT EXISTS relations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id          TEXT NOT NULL,
    tgt_id          TEXT NOT NULL,
    keywords        TEXT NOT NULL DEFAULT '',
    description     TEXT,
    source_id       TEXT,
    properties_json TEXT,
    UNIQUE(src_id, tgt_id, keywords)
);
CREATE INDEX IF NOT EXISTS idx_relations_src    ON relations(src_id);
CREATE INDEX IF NOT EXISTS idx_relations_tgt    ON relations(tgt_id);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '1');
"""


class SqliteGraphStore(GraphStore):
    """SQLite-backed GraphStore.

    Use `:memory:` for in-process testing or a filesystem path for
    persistence. Workspace discovery (`list_workspaces`) is filesystem-based
    when `workspace_root` is provided; otherwise returns an empty list.
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        workspace_root: Path | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._workspace_root = workspace_root
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    # ----- Lifecycle -----

    async def initialize(self) -> None:
        def _open() -> sqlite3.Connection:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            return conn

        self._conn = await asyncio.to_thread(_open)

    async def close(self) -> None:
        if self._conn is not None:
            conn = self._conn
            self._conn = None
            await asyncio.to_thread(conn.close)

    async def _run(self, fn: Callable[[sqlite3.Connection], _T]) -> _T:
        if self._conn is None:
            raise RuntimeError(
                "SqliteGraphStore not initialized; call await store.initialize() first."
            )
        async with self._lock:
            return await asyncio.to_thread(fn, self._conn)

    # ----- Encoding helpers -----

    @staticmethod
    def _split_entity(
        entity_data: dict[str, Any],
    ) -> tuple[str | None, str | None, str | None, str]:
        extras = {k: v for k, v in entity_data.items() if k not in _ENTITY_PROMOTED}
        return (
            entity_data.get("entity_type"),
            entity_data.get("description"),
            entity_data.get("source_id"),
            json.dumps(extras) if extras else "{}",
        )

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> dict[str, Any]:
        extras = json.loads(row["properties_json"] or "{}")
        result: dict[str, Any] = {
            "entity_name": row["entity_name"],
            "entity_type": row["entity_type"],
            "description": row["description"],
            "source_id": row["source_id"],
        }
        result.update(extras)
        return result

    @staticmethod
    def _split_relation(
        relation_data: dict[str, Any],
    ) -> tuple[str, str | None, str | None, str]:
        keywords = relation_data.get("keywords") or ""
        extras = {
            k: v for k, v in relation_data.items() if k not in _RELATION_PROMOTED
        }
        return (
            keywords,
            relation_data.get("description"),
            relation_data.get("source_id"),
            json.dumps(extras) if extras else "{}",
        )

    @staticmethod
    def _row_to_relation(row: sqlite3.Row) -> dict[str, Any]:
        extras = json.loads(row["properties_json"] or "{}")
        result: dict[str, Any] = {
            "src_id": row["src_id"],
            "tgt_id": row["tgt_id"],
            "keywords": row["keywords"] or "",
            "description": row["description"],
            "source_id": row["source_id"],
        }
        result.update(extras)
        return result

    # ----- Entity CRUD -----

    async def create_entity(
        self, entity_name: str, entity_data: dict[str, Any]
    ) -> None:
        etype, desc, source_id, extras_json = self._split_entity(entity_data)

        def _exec(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO entities (entity_name, entity_type, description,
                                      source_id, properties_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_name) DO UPDATE SET
                    entity_type     = excluded.entity_type,
                    description     = excluded.description,
                    source_id       = excluded.source_id,
                    properties_json = excluded.properties_json
                """,
                (entity_name, etype, desc, source_id, extras_json),
            )
            conn.commit()

        await self._run(_exec)

    async def entity_exists(self, entity_name: str) -> bool:
        def _query(conn: sqlite3.Connection) -> bool:
            row = conn.execute(
                "SELECT 1 FROM entities WHERE entity_name = ? LIMIT 1",
                (entity_name,),
            ).fetchone()
            return row is not None

        return await self._run(_query)

    async def get_all_entities(self) -> list[dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            rows = conn.execute("SELECT * FROM entities").fetchall()
            return [self._row_to_entity(r) for r in rows]

        return await self._run(_query)

    # ----- Relation CRUD -----

    async def create_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_data: dict[str, Any],
    ) -> None:
        keywords, desc, source_id, extras_json = self._split_relation(
            relation_data
        )

        def _exec(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO relations (src_id, tgt_id, keywords, description,
                                       source_id, properties_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(src_id, tgt_id, keywords) DO UPDATE SET
                    description     = excluded.description,
                    source_id       = excluded.source_id,
                    properties_json = excluded.properties_json
                """,
                (
                    source_entity,
                    target_entity,
                    keywords,
                    desc,
                    source_id,
                    extras_json,
                ),
            )
            conn.commit()

        await self._run(_exec)

    async def get_all_relations(self) -> list[dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            rows = conn.execute(
                "SELECT * FROM relations ORDER BY id"
            ).fetchall()
            return [self._row_to_relation(r) for r in rows]

        return await self._run(_query)

    # ----- Bulk insert -----

    async def insert_custom_kg(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        chunks: list[dict[str, Any]] | None = None,
        *,
        batch_size: int = 5000,
        progress_callback: Any | None = None,
    ) -> None:
        # chunks are accepted for contract symmetry; persistence of code
        # snippet text comes in Phase 2 with the vec0 virtual table.
        # batch_size / progress_callback are honored on the LightRAG path
        # for HTTP timeout protection; SQLite is in-process so a single
        # transaction is fine. Progress is reported once (one logical batch).
        del chunks, batch_size
        if progress_callback is not None:
            progress_callback(1, 1, len(entities))

        entity_rows: list[
            tuple[str, str | None, str | None, str | None, str]
        ] = []
        for e in entities:
            name = e.get("entity_name", "")
            if not name:
                continue
            etype, desc, source_id, extras_json = self._split_entity(e)
            entity_rows.append((name, etype, desc, source_id, extras_json))

        relation_rows: list[
            tuple[str, str, str, str | None, str | None, str]
        ] = []
        for r in relationships:
            src = r.get("src_id", "") or r.get("source", "")
            tgt = r.get("tgt_id", "") or r.get("target", "")
            if not src or not tgt:
                continue
            keywords, desc, source_id, extras_json = self._split_relation(r)
            relation_rows.append(
                (src, tgt, keywords, desc, source_id, extras_json)
            )

        def _exec(conn: sqlite3.Connection) -> None:
            with conn:
                if entity_rows:
                    conn.executemany(
                        """
                        INSERT INTO entities (entity_name, entity_type,
                                              description, source_id,
                                              properties_json)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(entity_name) DO UPDATE SET
                            entity_type     = excluded.entity_type,
                            description     = excluded.description,
                            source_id       = excluded.source_id,
                            properties_json = excluded.properties_json
                        """,
                        entity_rows,
                    )
                if relation_rows:
                    conn.executemany(
                        """
                        INSERT INTO relations (src_id, tgt_id, keywords,
                                               description, source_id,
                                               properties_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(src_id, tgt_id, keywords) DO UPDATE SET
                            description     = excluded.description,
                            source_id       = excluded.source_id,
                            properties_json = excluded.properties_json
                        """,
                        relation_rows,
                    )

        await self._run(_exec)

    # ----- Delete -----

    async def delete_all(self) -> None:
        def _exec(conn: sqlite3.Connection) -> None:
            with conn:
                conn.execute("DELETE FROM entities")
                conn.execute("DELETE FROM relations")

        await self._run(_exec)

    async def delete_by_source(self, source_ids: list[str]) -> None:
        if not source_ids:
            return
        placeholders = ",".join("?" * len(source_ids))

        def _exec(conn: sqlite3.Connection) -> None:
            with conn:
                conn.execute(
                    f"DELETE FROM entities WHERE source_id IN ({placeholders})",
                    source_ids,
                )
                conn.execute(
                    f"DELETE FROM relations WHERE source_id IN ({placeholders})",
                    source_ids,
                )

        await self._run(_exec)

    # ----- Source / workspace queries -----

    async def get_source_ids(
        self, source_prefix: str | None = None
    ) -> list[str]:
        def _query(conn: sqlite3.Connection) -> list[str]:
            if source_prefix:
                rows = conn.execute(
                    """
                    SELECT DISTINCT source_id FROM entities
                    WHERE source_id IS NOT NULL AND source_id LIKE ?
                    ORDER BY source_id
                    """,
                    (f"{source_prefix}%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT source_id FROM entities
                    WHERE source_id IS NOT NULL
                    ORDER BY source_id
                    """
                ).fetchall()
            return [r["source_id"] for r in rows]

        return await self._run(_query)

    async def list_workspaces(self) -> list[str]:
        # Workspace discovery is filesystem-based: each `<name>.db` under
        # workspace_root is a workspace. Without a root configured, return [].
        if self._workspace_root is None:
            return []

        def _scan() -> list[str]:
            root = self._workspace_root
            assert root is not None
            if not root.exists():
                return []
            return sorted(p.stem for p in root.glob("*.db"))

        return await asyncio.to_thread(_scan)

    # ----- Analytics -----

    async def get_orphan_entities(
        self,
        exclude_types: list[str] | None = None,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        def _query(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            sql = """
                SELECT e.* FROM entities e
                WHERE e.entity_name NOT IN (SELECT src_id FROM relations)
                  AND e.entity_name NOT IN (SELECT tgt_id FROM relations)
            """
            params: list[Any] = []
            if exclude_types:
                placeholders = ",".join("?" * len(exclude_types))
                sql += f" AND (e.entity_type IS NULL OR e.entity_type NOT IN ({placeholders}))"
                params.extend(exclude_types)
            if source_prefix:
                sql += " AND e.source_id LIKE ?"
                params.append(f"{source_prefix}%")
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_entity(r) for r in rows]

        return await self._run(_query)

    async def get_degree_distribution(
        self,
        direction: str = "in",
        min_degree: int = 5,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        key_field = "tgt_id" if direction == "in" else "src_id"

        def _query(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            sql = f"""
                SELECT e.*, c.degree FROM (
                    SELECT {key_field} AS name, COUNT(*) AS degree
                    FROM relations
                    GROUP BY {key_field}
                    HAVING degree >= ?
                ) c
                JOIN entities e ON e.entity_name = c.name
            """
            params: list[Any] = [min_degree]
            if source_prefix:
                sql += " WHERE e.source_id LIKE ?"
                params.append(f"{source_prefix}%")
            rows = conn.execute(sql, params).fetchall()
            result = []
            for r in rows:
                entity = self._row_to_entity(r)
                entity["degree"] = r["degree"]
                result.append(entity)
            return result

        return await self._run(_query)

    async def get_graph_stats(
        self,
        source_prefix: str | None = None,
        module_depth: int = 2,
    ) -> dict[str, Any]:
        def _query(conn: sqlite3.Connection) -> dict[str, Any]:
            if source_prefix:
                entities = conn.execute(
                    "SELECT * FROM entities WHERE source_id LIKE ?",
                    (f"{source_prefix}%",),
                ).fetchall()
                names = {r["entity_name"] for r in entities}
                if names:
                    placeholders = ",".join("?" * len(names))
                    relations = conn.execute(
                        f"""
                        SELECT * FROM relations
                        WHERE src_id IN ({placeholders})
                           OR tgt_id IN ({placeholders})
                        """,
                        list(names) + list(names),
                    ).fetchall()
                else:
                    relations = []
            else:
                entities = conn.execute("SELECT * FROM entities").fetchall()
                relations = conn.execute("SELECT * FROM relations").fetchall()

            def strip(s: str) -> str:
                return (
                    s[len(source_prefix) :]
                    if source_prefix and s and s.startswith(source_prefix)
                    else (s or "")
                )

            def module_of(source_id: str) -> str:
                parts = (source_id or "").split("/")
                return "/".join(parts[:module_depth])

            entity_module: dict[str, str] = {
                e["entity_name"]: module_of(strip(e["source_id"] or ""))
                for e in entities
            }
            cross = 0
            intra = 0
            for r in relations:
                src_m = entity_module.get(r["src_id"])
                tgt_m = entity_module.get(r["tgt_id"])
                if src_m and tgt_m:
                    if src_m == tgt_m:
                        intra += 1
                    else:
                        cross += 1
            total = cross + intra
            return {
                "entity_count": len(entities),
                "relation_count": len(relations),
                "cross_module_relations": cross,
                "intra_module_relations": intra,
                "coupling_density": (cross / total) if total else 0.0,
            }

        return await self._run(_query)
