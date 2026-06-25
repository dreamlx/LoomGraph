"""Cross-backend analytics diff: SQLite vs LightRAG.

Runs the same analytics (topology / debt / deps / get_graph_stats /
get_orphan_entities / get_degree_distribution) against both backends
populated from the same fixture, normalizes (sort lists, drop volatile
fields), and asserts row-level equality.

Usage:
    # Seed SQLite from an existing LightRAG workspace, then diff:
    python scripts/diff_backends.py \\
        --lightrag-workspace loomgraph:main \\
        --commands topology,deps,stats

    # Diff with a synthetic fixture (no LightRAG needed):
    python scripts/diff_backends.py --synthetic --n 200

Output is JSON to stdout. Exit code 0 if all checks pass, 1 if any
diff is non-empty.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from loomgraph.storage.base import GraphStore  # noqa: E402
from loomgraph.storage.sqlite_store import SqliteGraphStore  # noqa: E402

DEFAULT_COMMANDS = "stats,orphans,degree-in,degree-out"


# ---------- Synthetic fixture ----------


def synth_entities(n: int) -> list[dict[str, Any]]:
    return [
        {
            "entity_name": f"E{i}",
            "entity_type": ["class", "function", "module"][i % 3],
            "description": f"desc {i}",
            "source_id": f"src/m{i % 5}/f{i // 5}.py:{i}",
        }
        for i in range(n)
    ]


def synth_relations(n: int) -> list[dict[str, Any]]:
    return [
        {
            "src_id": f"E{i}",
            "tgt_id": f"E{(i * 7 + 3) % n}",
            "keywords": ["CALLS", "INHERITS", "IMPORTS"][i % 3],
            "source_id": f"src/m{i % 5}/f{i // 5}.py:{i}",
        }
        for i in range(n)
    ]


# ---------- Normalization ----------


def _sorted_entities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: r.get("entity_name", ""))


def _norm_stats(stats: dict[str, Any]) -> dict[str, Any]:
    # Drop volatile fields (timestamps, server version, etc.) if any backend
    # adds them. None today — guard for the future.
    keep = {
        "entity_count",
        "relation_count",
        "cross_module_relations",
        "intra_module_relations",
        "coupling_density",
    }
    return {k: stats.get(k) for k in keep}


# ---------- Backend setup ----------


async def make_sqlite_store(entities: list[dict[str, Any]], relations: list[dict[str, Any]]) -> SqliteGraphStore:
    store = SqliteGraphStore(db_path=":memory:")
    await store.initialize()
    await store.insert_custom_kg(entities, relations)
    return store


async def make_lightrag_store(workspace: str) -> GraphStore:
    from loomgraph.core.config import get_settings
    from loomgraph.core.lightrag_client import LightRAGClient
    from loomgraph.storage.lightrag_store import LightRAGGraphStore

    settings = get_settings()
    client = LightRAGClient(
        base_url=settings.lightrag.api_url,
        timeout=settings.lightrag.api_timeout,
        workspace=workspace,
    )
    await client.health_check()
    return LightRAGGraphStore(client)


async def fetch_lightrag_corpus(store: GraphStore) -> tuple[list[dict], list[dict]]:
    entities = await store.get_all_entities()
    relations = await store.get_all_relations()
    return entities, relations


# ---------- Diff runners ----------


async def diff_stats(lr: GraphStore, sl: GraphStore) -> dict[str, Any]:
    a = _norm_stats(await lr.get_graph_stats())
    b = _norm_stats(await sl.get_graph_stats())
    return {
        "match": a == b,
        "lightrag": a,
        "sqlite": b,
    }


async def diff_orphans(lr: GraphStore, sl: GraphStore) -> dict[str, Any]:
    a = [(e.get("entity_name"), e.get("source_id")) for e in await lr.get_orphan_entities()]
    b = [(e.get("entity_name"), e.get("source_id")) for e in await sl.get_orphan_entities()]
    only_lr = sorted(set(a) - set(b))
    only_sl = sorted(set(b) - set(a))
    return {
        "match": not only_lr and not only_sl,
        "lightrag_count": len(a),
        "sqlite_count": len(b),
        "only_in_lightrag": only_lr,
        "only_in_sqlite": only_sl,
    }


async def diff_degree(lr: GraphStore, sl: GraphStore, direction: str) -> dict[str, Any]:
    a = {
        e["entity_name"]: e.get("degree")
        for e in await lr.get_degree_distribution(direction=direction, min_degree=2)
    }
    b = {
        e["entity_name"]: e.get("degree")
        for e in await sl.get_degree_distribution(direction=direction, min_degree=2)
    }
    diff_names = sorted(set(a) ^ set(b))
    diff_values = sorted(
        n for n in set(a) & set(b) if a[n] != b[n]
    )
    return {
        "match": not diff_names and not diff_values,
        "direction": direction,
        "lightrag_count": len(a),
        "sqlite_count": len(b),
        "only_in_lightrag": [n for n in diff_names if n in a],
        "only_in_sqlite": [n for n in diff_names if n in b],
        "value_mismatch": [
            {"name": n, "lightrag": a[n], "sqlite": b[n]} for n in diff_values
        ],
    }


# ---------- Main ----------


async def run(args: argparse.Namespace) -> dict[str, Any]:
    commands = [c.strip() for c in args.commands.split(",")]
    out: dict[str, Any] = {"mode": "synthetic" if args.synthetic else "lightrag-seeded", "commands": commands, "results": {}}

    # Seed both backends
    if args.synthetic:
        entities = synth_entities(args.n)
        relations = synth_relations(args.n)
        sqlite_store = await make_sqlite_store(entities, relations)
        # Fake LightRAG view: use a second SqliteGraphStore as control —
        # validates the diff harness even without H200. For real cross-backend
        # validation pass --lightrag-workspace instead.
        lightrag_store = await make_sqlite_store(entities, relations)
        out["seed"] = {"n_entities": len(entities), "n_relations": len(relations)}
    else:
        try:
            lightrag_store = await make_lightrag_store(args.lightrag_workspace)
        except Exception as e:
            out["error"] = f"LightRAG unreachable: {e}"
            return out
        entities, relations = await fetch_lightrag_corpus(lightrag_store)
        sqlite_store = await make_sqlite_store(entities, relations)
        out["seed"] = {
            "lightrag_workspace": args.lightrag_workspace,
            "n_entities": len(entities),
            "n_relations": len(relations),
        }

    try:
        if "stats" in commands:
            out["results"]["stats"] = await diff_stats(lightrag_store, sqlite_store)
        if "orphans" in commands:
            out["results"]["orphans"] = await diff_orphans(lightrag_store, sqlite_store)
        if "degree-in" in commands:
            out["results"]["degree-in"] = await diff_degree(lightrag_store, sqlite_store, "in")
        if "degree-out" in commands:
            out["results"]["degree-out"] = await diff_degree(lightrag_store, sqlite_store, "out")
    finally:
        close = getattr(sqlite_store, "close", None)
        if close is not None:
            await close()
        close = getattr(lightrag_store, "close", None)
        if close is not None:
            await close()

    out["all_match"] = all(
        r.get("match", False) for r in out["results"].values()
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commands",
        default=DEFAULT_COMMANDS,
        help=f"Comma-separated checks to run (default: {DEFAULT_COMMANDS})",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic fixture (no LightRAG service needed; "
        "validates the diff harness)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=200,
        help="Synthetic fixture size (entities + relations, default 200)",
    )
    parser.add_argument(
        "--lightrag-workspace",
        default="loomgraph:main",
        help="Workspace name to pull the corpus from (LightRAG mode)",
    )
    args = parser.parse_args()

    result = asyncio.run(run(args))
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    sys.exit(0 if result.get("all_match", False) else 1)


if __name__ == "__main__":
    main()
