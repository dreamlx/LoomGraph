"""Benchmark GraphStore backends: SQLite (sqlite-vec) vs LightRAG.

Synthesizes a corpus of N entities + relations (optionally with embeddings)
and measures write + read latency on each backend. The LightRAG backend
requires a reachable LightRAG service; if unreachable the script falls
back to SQLite-only.

Usage:
    python scripts/bench_backends.py --n 1000 --with-embeddings
    python scripts/bench_backends.py --backends sqlite,lightrag --n 5000
    python scripts/bench_backends.py --workspace bench-test

Output is JSON to stdout for AI Agent consumption.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

# Add src to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from loomgraph.storage.base import GraphStore  # noqa: E402
from loomgraph.storage.sqlite_store import VECTOR_DIM, SqliteGraphStore  # noqa: E402


def synth_entity(i: int, with_embedding: bool) -> dict[str, Any]:
    """Generate a synthetic entity dict."""
    e: dict[str, Any] = {
        "entity_name": f"Entity_{i}",
        "entity_type": ["class", "function", "method", "module"][i % 4],
        "description": f"Synthetic entity #{i} for benchmarking purposes.",
        "source_id": f"src/mod{i % 100}/file_{i // 100}.py:{i}",
    }
    if with_embedding:
        rnd = random.Random(i)
        e["embedding"] = [rnd.uniform(-1.0, 1.0) for _ in range(VECTOR_DIM)]
    return e


def synth_relation(i: int, n: int) -> dict[str, Any]:
    src = f"Entity_{i}"
    tgt = f"Entity_{(i * 7 + 13) % n}"
    return {
        "src_id": src,
        "tgt_id": tgt,
        "keywords": ["CALLS", "INHERITS", "IMPORTS"][i % 3],
        "description": f"Relation #{i}",
        "source_id": f"src/mod{i % 100}/file_{i // 100}.py:{i}",
    }


async def bench_store(
    name: str, store: GraphStore, entities: list[dict[str, Any]],
    relations: list[dict[str, Any]], query_embedding: list[float] | None,
) -> dict[str, Any]:
    """Run write + read benchmarks against `store`."""
    results: dict[str, Any] = {"backend": name}

    # --- Bulk write ---
    t0 = time.perf_counter()
    await store.insert_custom_kg(entities, relations)
    results["bulk_insert_seconds"] = round(time.perf_counter() - t0, 3)

    # --- Read all ---
    t0 = time.perf_counter()
    all_entities = await store.get_all_entities()
    results["get_all_entities_seconds"] = round(time.perf_counter() - t0, 4)
    results["entities_count"] = len(all_entities)

    t0 = time.perf_counter()
    all_relations = await store.get_all_relations()
    results["get_all_relations_seconds"] = round(time.perf_counter() - t0, 4)
    results["relations_count"] = len(all_relations)

    # --- Analytics ---
    t0 = time.perf_counter()
    stats = await store.get_graph_stats()
    results["graph_stats_seconds"] = round(time.perf_counter() - t0, 4)
    results["stats"] = stats

    # --- KNN (if supported) ---
    if query_embedding is not None:
        try:
            t0 = time.perf_counter()
            knn = await store.search_similar(query_embedding, k=10)
            results["knn_search_seconds"] = round(time.perf_counter() - t0, 4)
            results["knn_results"] = len(knn)
        except NotImplementedError:
            results["knn_search_seconds"] = None
            results["knn_results"] = "not supported"

    return results


async def run(args: argparse.Namespace) -> dict[str, Any]:
    n = args.n
    entities = [synth_entity(i, args.with_embeddings) for i in range(n)]
    relations = [synth_relation(i, n) for i in range(n)]
    query_emb: list[float] | None = (
        entities[0]["embedding"] if args.with_embeddings else None
    )

    out: dict[str, Any] = {
        "config": {
            "n_entities": n,
            "n_relations": n,
            "with_embeddings": args.with_embeddings,
            "vector_dim": VECTOR_DIM if args.with_embeddings else None,
        },
        "results": [],
    }

    backends = [b.strip() for b in args.backends.split(",")]

    if "sqlite" in backends:
        from loomgraph.storage.sqlite_store import SqliteGraphStore

        db_path = args.sqlite_db
        store = SqliteGraphStore(db_path=db_path)
        await store.initialize()
        try:
            out["results"].append(
                await bench_store("sqlite", store, entities, relations, query_emb)
            )
        finally:
            await store.close()

    if "lightrag" in backends:
        from loomgraph.core.config import get_settings
        from loomgraph.core.lightrag_client import LightRAGClient
        from loomgraph.storage.lightrag_store import LightRAGGraphStore

        settings = get_settings()
        client = LightRAGClient(
            base_url=settings.lightrag.api_url,
            timeout=max(settings.lightrag.api_timeout, 60.0),
            workspace=args.workspace,
        )
        try:
            await client.health_check()
        except Exception as e:
            out["results"].append(
                {"backend": "lightrag", "error": f"unreachable: {e}"}
            )
        else:
            store = LightRAGGraphStore(client)
            await store.delete_all()  # clean slate
            out["results"].append(
                await bench_store(
                    "lightrag", store, entities, relations, query_emb
                )
            )

    # --- Comparison summary ---
    if len(out["results"]) == 2 and all(
        "error" not in r for r in out["results"]
    ):
        sqlite_r = next(r for r in out["results"] if r["backend"] == "sqlite")
        lightrag_r = next(r for r in out["results"] if r["backend"] == "lightrag")
        out["summary"] = {
            "write_ratio_sqlite_over_lightrag": round(
                sqlite_r["bulk_insert_seconds"]
                / max(lightrag_r["bulk_insert_seconds"], 1e-9),
                2,
            ),
            "read_ratio_lightrag_over_sqlite": round(
                lightrag_r["get_all_entities_seconds"]
                / max(sqlite_r["get_all_entities_seconds"], 1e-9),
                2,
            ),
            "gate_write_le_2x": (
                sqlite_r["bulk_insert_seconds"]
                <= 2 * lightrag_r["bulk_insert_seconds"]
            ),
            "gate_read_ge_5x": (
                lightrag_r["get_all_entities_seconds"]
                >= 5 * sqlite_r["get_all_entities_seconds"]
            ),
        }

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n", type=int, default=1000, help="Number of synthetic entities/relations"
    )
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help=f"Generate random {VECTOR_DIM}-dim embeddings (SQLite vec0)",
    )
    parser.add_argument(
        "--backends",
        default="sqlite,lightrag",
        help="Comma-separated backends to benchmark (default: sqlite,lightrag)",
    )
    parser.add_argument(
        "--sqlite-db",
        default=":memory:",
        help="SQLite DB path (default: :memory: for in-process benchmarking)",
    )
    parser.add_argument(
        "--workspace",
        default="bench",
        help="LightRAG workspace name for bench (will be cleared!)",
    )
    args = parser.parse_args()

    result = asyncio.run(run(args))
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
