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
import sys
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


class GraphExportEmptyError(RuntimeError):
    """graph-export returned 0 entities; a gate hard-stops before any write (#120/#141).

    Raised by callers after :func:`assess_export` reports an unsafe 0-entity
    result, so the CLI surfaces it via ``output_error`` (exit 1) and MCP via
    ``safe_call`` (error envelope) — never a silent ``success:true``.
    """


def assess_export(
    summary: ImportSummary, warnings: list[str]
) -> tuple[bool, str | None]:
    """Gate a graph-export result before any write path touches the store (#120).

    Returns ``(is_safe_to_write, warning)``:

    - ``entity_count > 0`` → ``(True, None)``. A healthy export. Callers may
      still echo ``warnings`` (partial-graph, #108) but the write proceeds.
    - ``entity_count == 0`` → ``(False, <warning>)``. **Unsafe** for any write
      path that clears or GCs (``clear=True``, ``ingest_incremental``'s symbol
      GC): a 0-entity export on a non-empty repo is almost always a
      languages/grammar mismatch (#93/#96/#108/#118), and writing through it
      would silently wipe real data. The warning folds codeindex's own stderr
      diagnostic (missing grammar / languages mismatch) into its leading line
      when present — so the agent gets the real root cause, not a bare count.

    Callers decide policy on top of this: ``index`` warns + still writes
    (empty-repo is a legitimate 0); ``refresh force_full`` and ``update`` must
    treat ``is_safe_to_write=False`` as a hard stop before ``clear``/``GC``.
    """
    if summary.entity_count > 0:
        return True, None

    if warnings:
        first_lines = [w.split("\n")[0].rstrip() for w in warnings]
        joined = "; ".join(first_lines)
        return False, (
            f"graph-export returned 0 entities; codeindex reports: {joined}. "
            "Install the matching `loomgraph[<lang>]` extra and ensure that "
            "language is listed under `languages` in .codeindex.yaml"
        )
    return False, (
        "graph-export returned 0 entities; check that .codeindex.yaml "
        "languages matches this repository's code"
    )


def run_graph_export(
    repo: Any,
    *,
    timeout: int = 600,
) -> tuple[list[EntityData], list[RelationData], ImportSummary, list[str]]:
    """Invoke ``codeindex graph-export --root <repo> -o -`` and read the NDJSON.

    The export streams to stdout; we capture it via ``communicate`` and hand the
    bytes to :class:`GraphExportReader` (file-path based, hence the temp file).

    Returns ``(entities, relations, summary, warnings)``. ``warnings`` holds
    codeindex's stderr WARNING lines (e.g. the few-entity partial-graph hint,
    #131) so a misconfigured non-Python repo doesn't index as a silent success
    (#108) — callers surface them to the user/agent. Raises
    :class:`GraphExportError` on non-zero exit or timeout.
    """
    # Invoke via the venv python (`sys.executable -m codeindex.cli`), never a
    # bare `codeindex` PATH lookup — otherwise a stale codeindex elsewhere on
    # PATH (e.g. pipx) shadows the pinned `ai-codeindex` dep (#76 PATH bypass).
    proc = Popen(
        [sys.executable, "-m", "codeindex.cli", "graph-export", "--root", str(repo), "-o", "-"],
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

    # codeindex writes partial-graph diagnostics to stderr on a 0-exit (#131);
    # surface those lines so callers don't see a silent success on a
    # misconfigured repo (#108). Non-WARNING stderr (progress noise) is ignored.
    warnings = [
        line for line in stderr.splitlines() if line.strip().startswith("WARNING:")
    ]
    # #118: codeindex also emits per-file ``Parser library not installed for
    # <lang>`` lines (no ``WARNING:`` prefix) when a tree-sitter grammar is
    # missing. These carry the real root cause + fix (``pip install
    # tree-sitter-<lang>``) for a 0-entity export; without them a missing-grammar
    # repo looks like a config problem. Dedupe (one line per file → first only).
    seen_parser = False
    for line in stderr.splitlines():
        if "Parser library not installed" in line and not seen_parser:
            warnings.append(line.strip())
            seen_parser = True

    fd, tmp_path = tempfile.mkstemp(suffix=".ndjson")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(stdout)
        entities, relations, summary = GraphExportReader(tmp_path).read()
    finally:
        os.unlink(tmp_path)
    return entities, relations, summary, warnings


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
    embedded = await maybe_embed_entities(entity_dicts, store)

    _emit(on_progress, "insert", len(entity_dicts), len(relation_dicts))
    await store.insert_custom_kg(entity_dicts, relation_dicts, [])

    # #154: persist join-based edge resolution quality so analytics outputs
    # can caveat their readings (Java DI / TS alias blind spots).
    resolved_ratio = await persist_resolved_ratio(store, entity_dicts, relation_dicts)

    stats = await store.get_graph_stats()
    return {
        "cleared": clear,
        "entities_created": len(entity_dicts),
        "relations_created": len(relation_dicts),
        "resolved_ratio": resolved_ratio,
        "embedded": embedded,
        "store_stats": stats,
    }


def compute_resolved_ratio(
    entity_dicts: list[dict[str, Any]],
    relation_dicts: list[dict[str, Any]],
) -> float | None:
    """Join-based resolvable-edge share (#154/#158 review C1-2).

    Shared by cold ingest, incremental update and import-export so the
    persisted ``resolved_ratio`` never goes stale on the default path.
    None when there are no relations (ratio undefined — topology omits
    the resolution block)."""
    if not relation_dicts:
        return None
    names = {d["entity_name"] for d in entity_dicts}
    resolved = sum(
        1
        for r in relation_dicts
        if r.get("src_id") in names and r.get("tgt_id") in names
    )
    return round(resolved / len(relation_dicts), 4)


async def persist_resolved_ratio(
    store: Any,
    entity_dicts: list[dict[str, Any]],
    relation_dicts: list[dict[str, Any]],
) -> float | None:
    """Compute + persist the ratio; empty '' clears it (empty graph)."""
    ratio = compute_resolved_ratio(entity_dicts, relation_dicts)
    set_meta = getattr(store, "set_meta", None)
    if set_meta is not None:
        await set_meta("resolved_ratio", "" if ratio is None else str(ratio))
    return ratio


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
    """Per-symbol incremental ingest for ``update`` (路 B + #90 symbol-level).

    For each changed file, diffs the new export against the store's current
    entities by per-symbol ``content_hash`` (codeindex>=0.31.0 sv1):

      - hash unchanged (both sides carry the same non-None hash) → SKIP
        (no re-embed, no re-insert). The ~50× embedding savings on a fat file.
      - hash changed, or new symbol, or hash is None → re-embed + upsert.
      - symbol in store but absent from the new export → ``delete_entities``
        (symbol-level GC; relations + vectors cascade in the store).
      - ``content_hash`` is None (no-span entity / sv0 artifact) → always
        re-embed (file-level fallback; skip only when BOTH sides carry a hash).

    Unchanged files cost zero embed calls and zero store reads.

    Relations of removed symbols are dropped via the ``delete_entities``
    cascade; changed-file relations are upserted. Relations between two
    *kept* symbols that disappeared from the export are not GC'd here —
    #90 targets the embedding-cost win, not relation-level diff.
    """
    to_embed: list[EntityData] = []  # new + hash-mismatch symbols
    to_skip = 0
    to_delete: list[str] = []  # entity_names removed since last index

    for f in sorted(changed_files):
        sids = await store.get_source_ids(f)
        old_entities = await store.get_entities_by_source(sids) if sids else []
        old_hash: dict[str, str | None] = {
            e["entity_name"]: e.get("content_hash") for e in old_entities
        }

        new_in_file = [
            e
            for e in entities
            if _file_of(str(e.entity_data.get("source_id", ""))) == f
        ]
        new_names: set[str] = set()
        for e in new_in_file:
            name = e.entity_name
            new_names.add(name)
            h_new = e.entity_data.get("content_hash")
            h_old = old_hash.get(name)
            if h_new is not None and h_old is not None and h_new == h_old:
                to_skip += 1  # symbol unchanged → skip embed/insert
            else:
                to_embed.append(e)  # new symbol or hash mismatch
        # symbols gone from the export → GC (symbol-level, not file-level)
        for name in old_hash:
            if name not in new_names:
                to_delete.append(name)

    changed_relations = [
        r
        for r in relations
        if _file_of(str(r.edge_data.get("source_id", ""))) in changed_files
    ]

    # GC removed symbols first (relations + vectors cascade in store).
    if to_delete:
        _emit(on_progress, "clear", len(to_delete), 0)
        await store.delete_entities(to_delete)

    # Embed + upsert the new/changed subset (mirrors `ingest`).
    entity_dicts = [
        {"entity_name": e.entity_name, **e.entity_data} for e in to_embed
    ]
    relation_dicts = [
        {"src_id": r.src_id, "tgt_id": r.tgt_id, **r.edge_data}
        for r in changed_relations
    ]

    _emit(on_progress, "embed", len(entity_dicts), len(relation_dicts))
    embedded = await maybe_embed_entities(entity_dicts, store)

    _emit(on_progress, "insert", len(entity_dicts), len(relation_dicts))
    await store.insert_custom_kg(entity_dicts, relation_dicts, [])

    # #154/#158 review C1-2: recompute the ratio over the new full export so
    # `update` (the default daily path) never serves a stale trust signal.
    resolved_ratio = await persist_resolved_ratio(store, entity_dicts, relation_dicts)

    stats = await store.get_graph_stats()
    return {
        "incremental": True,
        "changed_files": sorted(changed_files),
        "symbols_skipped": to_skip,
        "symbols_deleted": len(to_delete),
        "gc_source_ids": len(to_delete),  # legacy alias (= symbols GC'd)
        "entities_created": len(entity_dicts),
        "relations_created": len(relation_dicts),
        "resolved_ratio": resolved_ratio,
        "embedded": embedded,
        "store_stats": stats,
    }
