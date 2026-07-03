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

import inspect
import os
import subprocess
import tempfile
from collections.abc import Callable
from subprocess import Popen, TimeoutExpired  # noqa: F401 — Popen is a patch target
from typing import Any

from loomgraph.core.embedding_pipeline import maybe_embed_entities
from loomgraph.core.models import EntityData, RelationData
from loomgraph.io.export_reader import GraphExportReader, ImportSummary

# Progress callback: (phase, n_entities, n_relations) -> Optional[Awaitable].
# Sync or async both accepted (awaited if the result is awaitable).
ProgressFn = Callable[[str, int, int], Any]


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


async def _emit(
    on_progress: ProgressFn | None,
    phase: str,
    n_entities: int,
    n_relations: int,
) -> None:
    if on_progress is None:
        return
    res = on_progress(phase, n_entities, n_relations)
    if inspect.isawaitable(res):
        await res


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
        await _emit(on_progress, "clear", len(entities), len(relations))
        await store.delete_all()

    entity_dicts = [
        {"entity_name": e.entity_name, **e.entity_data} for e in entities
    ]
    relation_dicts = [
        {"src_id": r.src_id, "tgt_id": r.tgt_id, **r.edge_data} for r in relations
    ]

    await _emit(on_progress, "embed", len(entity_dicts), len(relation_dicts))
    embedded = await maybe_embed_entities(entity_dicts)

    await _emit(on_progress, "insert", len(entity_dicts), len(relation_dicts))
    await store.insert_custom_kg(entity_dicts, relation_dicts, [])

    stats = await store.get_graph_stats()
    return {
        "cleared": clear,
        "entities_created": len(entity_dicts),
        "relations_created": len(relation_dicts),
        "embedded": embedded,
        "store_stats": stats,
    }
