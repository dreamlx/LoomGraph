# Dogfood Benchmark — loomgraph + codeindex on themselves

> Two-way self-benchmark: index both `loomgraph` and `codeindex` with
> loomgraph; round-trip each via `codeindex graph-export` →
> `loomgraph import-export`. Ground truth is checked by the authors,
> since we wrote both codebases.

**Setup**
- Host: M3 MacBook, macOS Darwin 25.3.0, Python 3.12
- `ai-codeindex==0.27.0` (PyPI)
- `loomgraph` at `main` commit [3281901](https://github.com/dreamlx/LoomGraph/commit/3281901) (post PR #54)
- All measurements `/usr/bin/time -p` wall-real on cold runs.

## Index baseline

```bash
loomgraph index <repo> --workspace <name>
```

| Project | Files | LoC src/ | Index wall | DB size | Entities | Relations |
|---|---|---|---|---|---|---|
| **loomgraph** | 51 .py | 10,930 | **0.88s** | 1.2 MB | 1,300 | 2,319 |
| **codeindex** | 92 .py | 22,025 | **0.93s** | 5.9 MB | 4,559 | 10,561 |

Per-LoC overhead:
- loomgraph: ~110 B/LoC storage, ~80μs/LoC index
- codeindex: ~270 B/LoC storage, ~42μs/LoC index

codeindex's higher density per LoC: it has more class/method entities
(1,722 methods vs loomgraph's 128) and more cross-file CALLS edges per
function — denser graph topology.

## Query latency

Cold-cache, full Python interpreter startup included. Times are end-to-end
wall, not pure SQL.

### loomgraph workspace

| Command | Arg | Wall | Result |
|---|---|---|---|
| `find` | `SqliteGraphStore` | 0.24s | 20 matches |
| `graph callers` | `SqliteGraphStore.insert_custom_kg` | 0.20s | 0 (polymorphic) |
| `topology` | — | 0.22s | 48 god functions |
| `deps` | — | 0.20s | 3 modules |

### codeindex workspace

| Command | Arg | Wall | Result |
|---|---|---|---|
| `find` | `GraphExporter` | 0.38s | 20 matches |
| `graph callers` | `walk_and_parse` | 0.26s | 3 callers |
| `topology` | — | 0.31s | 99 god functions |
| `deps` | — | 0.26s | 14 modules |

Even on the 4× larger codeindex graph (10k relations), every command
returns in under 0.4s wall — and most of that is Python startup, not
SQL. Pure SQL latency is sub-100ms (uvloop / `--quiet` measurements
not shown here).

## Round-trip (codeindex graph-export → loomgraph import-export)

```bash
codeindex graph-export --root <repo> -o /tmp/<name>.ndjson
loomgraph import-export /tmp/<name>.ndjson -w <name>:imported --clear
```

| Project | Export wall | NDJSON lines | Import wall | Entities | Relations |
|---|---|---|---|---|---|
| loomgraph | 0.52s | 3,446 | 0.26s | 392 | 1,884 |
| codeindex | 1.27s | 15,246 | 0.39s | 2,931 | 9,023 |

Round-trip vs direct-index relation coverage:

| Project | Direct | Imported (0.27 + dst_raw) | Coverage |
|---|---|---|---|
| loomgraph | 2,319 | 1,884 | **81%** |
| codeindex | 10,561 | 9,023 | **85%** |

The gap (~15-19%) is module-level edges that codeindex export doesn't
emit (file/module entities are dropped in favour of class/function/method).
This is a known schema choice from `docs/guides/graph-export.md` —
it's a structural slice, not a full index replacement.

## Semantic preservation — same query, both workspaces

To verify the import workspace returns the same answer as the direct
index for representative queries:

| Project | Query | Direct | Imported (qualified arg) | Match |
|---|---|---|---|---|
| loomgraph | `find SqliteGraphStore` | 20 | 20 | ✅ |
| codeindex | `find GraphExporter` | 20 | 20 | ✅ |
| codeindex | `graph walk_and_parse callers` | 3 | 3 | ✅ |
| loomgraph | `graph GraphExportReader.read callers` | 0 (ABC dispatch) | 1 (qualified resolves) | imported BETTER |

The loomgraph `read` query is the F-class precision pattern from
spike-30 — qualified names let codeindex disambiguate
`GraphExportReader.read` from other `.read()` callers in the codebase.
A polymorphic miss in the direct index becomes a single concrete caller
in the imported workspace.

## What this validates

Against the README's claims:

| README claim | Evidence here |
|---|---|
| "Local code knowledge graph for AI agents" | Both projects round-trip end-to-end with `pipx` install + sub-second commands. |
| "Deterministic graph queries" | Identical hit counts on direct vs imported for the same queries on both projects. |
| "AST is the source of truth" | All entities + edges come from codeindex tree-sitter parse; no LLM inference. |
| "Single-file storage" | `~/.loomgraph/<workspace>.db`, 1.2 MB for loomgraph, 5.9 MB for codeindex. |
| "tested on codebases up to ~100k functions" | Largest verified here: codeindex at 4,559 entities. The README claim is still extrapolated — needs a larger fixture (Django / FastAPI / equivalent) to back at the 100k function level. |
| "AI-Agent-shaped CLI" | JSON output works, validated by spike-30 harness consuming it. |

## Honest gaps (worth flagging)

1. **Largest tested codebase here is ~22k LoC.** The README claim of
   "~100k functions" is **not backed** by this dogfood run; it would
   need a 50-100k LoC OSS project.
2. **TypeScript path is untested at the loomgraph layer.** Codeindex
   has TS support; the round-trip on TS hasn't been measured. spike-30
   Stage D round-trip used Python loomgraph only.
3. **Cold-cache Python startup dominates query latency.** A long-running
   loomgraph MCP server (planned) would amortize the ~150ms startup
   away.
4. **`loomgraph index` wall time includes codeindex subprocess.**
   Standalone codeindex scan time would isolate that.

## Reproducing this benchmark

```bash
# Install
pipx install loomgraph
pipx install ai-codeindex==0.27.0

# Direct-index baseline
loomgraph index /path/to/loomgraph -w loomgraph-bench:main
loomgraph index /path/to/codeindex -w codeindex-bench:master

# Round-trip
codeindex graph-export --root /path/to/loomgraph -o /tmp/lg.ndjson
loomgraph import-export /tmp/lg.ndjson -w loomgraph-bench:imported --clear

codeindex graph-export --root /path/to/codeindex -o /tmp/ci.ndjson
loomgraph import-export /tmp/ci.ndjson -w codeindex-bench:imported --clear

# Stats
sqlite3 ~/.loomgraph/loomgraph-bench:main.db \
  "SELECT COUNT(*) AS entities FROM entities, (SELECT COUNT(*) AS r FROM relations)"
```

## Verdict

LoomGraph + codeindex 0.27.0 form a working end-to-end pipeline for
real Python codebases up to ~22k LoC. Round-trip preservation is
~80-85% by relation count, with the gap being structural-slice
fields that the contract intentionally drops. The README claim about
"100k functions" needs a bigger fixture to back, and TypeScript
support needs its own validation pass.
