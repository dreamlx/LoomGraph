"""Shared graph-export ingestion pipeline (#66).

Retires the legacy `codeindex scan --output json` path: both `loomgraph index`
and `loomgraph update` consume the `codeindex graph-export` NDJSON contract
through this module, which gives module-qualified entity ids + qualified edge
endpoints (fixing the cross-module same-name collision that produced phantom
god_functions).

Two pieces:
- ``run_graph_export`` — shell out to ``codeindex graph-export`` and read the
  NDJSON stream via :class:`GraphExportReader` (reused from ``import-export``).
- ``ingest`` — the embed + insert step (mirrors ``_async_import_export``).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from subprocess import Popen, TimeoutExpired  # noqa: F401 — Popen is a patch target
from typing import Any

from loomgraph.core.embedding_pipeline import maybe_embed_entities
from loomgraph.core.models import EntityData, RelationData
from loomgraph.io.export_reader import GraphExportReader, ImportSummary

# Progress callback: (phase, n_entities, n_relations) -> None. Sync-only —
# the sole caller (cli/_indexing._progress) just click.echo's to stderr.
ProgressFn = Callable[[str, int, int], None]


class GraphExportError(RuntimeError):
    """`codeindex graph-export` failed, timed out, or produced no readable output."""


def run_graph_export(
    repo: Any,
    *,
    timeout: int = 600,
) -> tuple[list[EntityData], list[RelationData], ImportSummary]:
    """Invoke ``codeindex graph-export --root <repo> -o -`` and read the NDJSON.

    The export streams to stdout; we capture it via ``communicate`` and hand the
    bytes to :class:`GraphExportReader` (file-path based, hence the temp file).

    Returns the mapped ``(entities, relations, summary)``. Raises
    :class:`GraphExportError` on non-zero exit or timeout.
    """
    proc = Popen(
        ["codeindex", "graph-export", "--root", str(repo), "-o", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except TimeoutExpired:
        proc.kill()
        proc.communicate()  # drain to avoid resource warnings
        raise GraphExportError(
            f"codeindex graph-export timed out after {timeout}s"
        ) from None

    if proc.returncode != 0:
        raise GraphExportError(
            f"codeindex graph-export exited {proc.returncode}: {stderr.strip()}"
        )

    fd, tmp_path = tempfile.mkstemp(suffix=".ndjson")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(stdout)
        return GraphExportReader(tmp_path).read()
    finally:
        os.unlink(tmp_path)


def _emit(
    on_progress: ProgressFn | None,
    phase: str,
    n_entities: int,
    n_relations: int,
) -> None:
    if on_progress is None:
        return
    on_progress(phase, n_entities, n_relations)


async def ingest(
    entities: list[EntityData],
    relations: list[RelationData],
    store: Any,
    *,
    clear: bool,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Embed + insert mapped entities/relations into ``store``.

    Mirrors ``_async_import_export``: optional ``delete_all`` (when ``clear``),
    build plain dicts, ``maybe_embed_entities`` (settings-gated, in-place),
    ``insert_custom_kg(entities, relations, [])`` (empty chunks — graph-export
    carries no vector data; embedding is loomgraph's concern).
    """
    if clear:
        _emit(on_progress, "clear", len(entities), len(relations))
        await store.delete_all()

    entity_dicts = [
        {"entity_name": e.entity_name, **e.entity_data} for e in entities
    ]
    relation_dicts = [
        {"src_id": r.src_id, "tgt_id": r.tgt_id, **r.edge_data} for r in relations
    ]

    _emit(on_progress, "embed", len(entity_dicts), len(relation_dicts))
    embedded = await maybe_embed_entities(entity_dicts)

    _emit(on_progress, "insert", len(entity_dicts), len(relation_dicts))
    await store.insert_custom_kg(entity_dicts, relation_dicts, [])

    stats = await store.get_graph_stats()
    return {
        "cleared": clear,
        "entities_created": len(entity_dicts),
        "relations_created": len(relation_dicts),
        "embedded": embedded,
        "store_stats": stats,
    }


def _file_of(source_id: str) -> str:
    """Extract the file path from a ``pkg/a.py:line`` source_id."""
    return source_id.split(":", 1)[0]


async def ingest_incremental(
    entities: list[EntityData],
    relations: list[RelationData],
    store: Any,
    *,
    changed_files: set[str],
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Per-file incremental ingest for ``update`` (路 B, no codeindex content_hash).

    vs :func:`ingest` with ``clear=False`` (whole-tree upsert): only
    re-embeds/re-inserts entities whose source file is in ``changed_files``,
    and garbage-collects symbols deleted since the last index by first
    deleting every entity under each changed file's source-id prefix.

    Flow:
    1. GC — for each changed file: ``delete_by_source(get_source_ids(file))``
       removes stale entities, **including symbols deleted since the last
       index** (upsert alone never removes them).
    2. Filter — keep only entities/relations whose ``source_id`` file ∈
       ``changed_files``.
    3. ``maybe_embed_entities`` + ``insert_custom_kg`` the filtered subset
       only — so unchanged files cost zero embed calls.

    Granularity is file-level (a one-line edit re-embeds that file's
    entities); symbol-span granularity via codeindex content_hash is the
    follow-up (codeindex#110).
    """
    # Step 1: GC changed files' old entities (source-id prefix delete).
    stale: list[str] = []
    for f in sorted(changed_files):
        stale.extend(await store.get_source_ids(f))
    if stale:
        _emit(on_progress, "clear", len(stale), 0)
        await store.delete_by_source(stale)

    # Step 2: filter to changed files.
    changed_entities = [
        e
        for e in entities
        if _file_of(str(e.entity_data.get("source_id", ""))) in changed_files
    ]
    changed_relations = [
        r
        for r in relations
        if _file_of(str(r.edge_data.get("source_id", ""))) in changed_files
    ]

    # Step 3: embed + insert the subset (mirrors `ingest`).
    entity_dicts = [
        {"entity_name": e.entity_name, **e.entity_data} for e in changed_entities
    ]
    relation_dicts = [
        {"src_id": r.src_id, "tgt_id": r.tgt_id, **r.edge_data} for r in changed_relations
    ]

    _emit(on_progress, "embed", len(entity_dicts), len(relation_dicts))
    embedded = await maybe_embed_entities(entity_dicts)

    _emit(on_progress, "insert", len(entity_dicts), len(relation_dicts))
    await store.insert_custom_kg(entity_dicts, relation_dicts, [])

    stats = await store.get_graph_stats()
    return {
        "incremental": True,
        "changed_files": sorted(changed_files),
        "gc_source_ids": len(stale),
        "entities_created": len(entity_dicts),
        "relations_created": len(relation_dicts),
        "embedded": embedded,
        "store_stats": stats,
    }
