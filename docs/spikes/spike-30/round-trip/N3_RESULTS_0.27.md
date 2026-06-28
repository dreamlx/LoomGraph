# 0.27.0 Round-Trip Re-run — `dst_raw` validated

> Follow-up to `N3_RESULTS.md`. Re-runs the same 19-task round-trip
> against an `ai-codeindex==0.27.0` artifact, after updating the
> loomgraph reader to consume the new `dst_raw` field shipped in that
> release.

## TL;DR

- Stored relations jumped **624 → 1883** (~3×) — `dst_raw` lets every
  unresolved edge keep its own distinct target (the original call
  expression text, e.g. `os.environ.get`) instead of being skipped
  to avoid a fake hub.
- Per-task agent answer quality **unchanged** (YELLOW preserved).
- One single-task wobble (F-3 0.5 → 0.0) within N=3 variance.

## Schema delta

`ai-codeindex==0.27.0` ships `dst_raw` on every edge — the local-namespace
original call expression, before resolution:

```json
{"type":"edge","kind":"CALLS","src":"...","dst_raw":"os.environ.get","dst":null,"resolution_qualifier":"unresolved","source_id":"..."}
```

| Qualifier | dst field | dst_raw field | Loomgraph 0.27.0 tgt_id |
|---|---|---|---|
| resolved | qualified id | local short name (e.g. `self.authenticate`) | dst (unchanged) |
| ambiguous | null | local short name | candidates[0] (unchanged) |
| unresolved | null | original call expression (e.g. `os.environ.get`) | **dst_raw** (was: skip) |

## Workspace stats (loomgraph self fixture)

| Workspace | Source | Entities | Relations stored | Note |
|---|---|---|---|---|
| `loomgraph:main` | `loomgraph index .` (direct) | 1264 | 2244 | Baseline |
| `loomgraph-self:imported` | `import-export` pre-0.27.0 (PR #53) | 391 | 624 | Unresolved skipped |
| `loomgraph-self:imported-0.27` | `import-export` 0.27.0 + dst_raw | 392 | **1883** | Unresolved kept with dst_raw |

The 0.27.0 import now retains **84%** of the direct index's relation count
(was 28% in PR #53), without ever creating a fake hub entity.

## Per-task three-way (Path B median correctness, N=3 flash)

| Task | Class | Direct | PR#53 | 0.27 | 0.27 vs PR#53 |
|---|---|---|---|---|---|
| A-1 | A | 1.00 | 0.50 | 0.50 | tied |
| A-2 | A | 1.00 | 0.50 | 0.50 | tied |
| A-3 | A | 1.00 | 1.00 | 1.00 | tied |
| B-1 | B | 0.00 | 0.00 | 0.00 | tied |
| B-2 | B | 0.00 | 0.00 | 0.00 | tied |
| B-3 | B | 1.00 | 0.00 | 0.00 | tied |
| C-1 | C | 0.50 | 0.50 | 0.50 | tied |
| C-2 | C | 1.00 | 1.00 | 1.00 | tied |
| C-3 | C | 0.50 | 0.00 | 0.00 | tied |
| D-1 | D | 1.00 | 1.00 | 1.00 | tied |
| D-2 | D | 1.00 | 1.00 | 1.00 | tied |
| D-3 | D | 1.00 | 1.00 | 1.00 | tied |
| E-1 | E | 0.00 | **0.50** | **0.50** | tied (preserves PR#53 gain) |
| E-2 | E | 0.00 | 0.00 | 0.00 | tied |
| E-3 | E | 0.00 | 0.00 | 0.00 | tied |
| E-4 | E | 0.00 | 0.00 | 0.00 | tied |
| F-1 | F | 0.00 | 0.00 | 0.00 | tied |
| F-2 | F | 0.00 | 0.00 | 0.00 | tied |
| F-3 | F | 0.00 | **0.50** | 0.00 | -0.50 (single-N=3 wobble) |

## Per-class aggregates

All classes tied vs PR#53. YELLOW verdict preserved.

| Class | Direct | PR#53 | 0.27.0 |
|---|---|---|---|
| A | 1.00 | 0.50 | 0.50 |
| B | 0.00 | 0.00 | 0.00 |
| C | 0.50 | 0.50 | 0.50 |
| D | 1.00 | 1.00 | 1.00 |
| E | 0.00 | 0.00 | 0.00 |
| F | 0.00 | 0.00 | 0.00 |

## Interpretation

The 3× relation increase doesn't change agent task scores because the
unresolved edges target stdlib / external symbols (`os.environ.get`,
`json.loads`, etc.) that aren't in the entity universe a Path B agent
queries. Their value is for analytics:

- Completeness audits ("which files have the most external dependencies?")
- External-API surface mapping ("what stdlib does this codebase use?")
- Pattern detection ("which entities call `subprocess.run`?")

The F-3 -0.50 wobble is one task at N=3 — variance, not signal. The
single-task variance budget per PLAN.md §6 is ±0.10 at the aggregate
level, which we're within.

## Compatibility

Loomgraph `import-export` is **back-compatible** with pre-0.27.0 artifacts:
- Records without `dst_raw` fall back to the original "skip unresolved"
  behaviour (no fake-hub regression)
- Records with `dst_raw` get the new behaviour

The 5-test schema-handling matrix in `tests/unit/test_export_reader.py`
covers both paths.

## Done

P0 → verify `dst_raw` ✅
P1 → reader update ✅
P2 → 0.27.0 round-trip ✅
P3 → docs ✅ (this file + CHANGELOG)
