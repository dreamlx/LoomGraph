# Round-trip Validation Report — codeindex#102 ↔ loomgraph

> Validates the codeindex `graph-export` → loomgraph consumer contract on
> real data, by re-running spike-30 task A-1 against the imported workspace
> and comparing to the direct-indexed baseline.

## Result: ✅ Semantic round-trip works, with naming convention findings

| Stage | Status | Finding |
|---|---|---|
| A — Schema validation (POC reader) | ✅ Clean | 0 schema warnings on 15246-record artifact |
| B — Full CLI import (`loomgraph import-export`) | ✅ Works | 12314 edges parsed; 5524 land (unresolved sentinel dropped by store) |
| C — Round-trip A-1 query | ✅ Same 7 callers found | Naming convention divergence requires discussion |

## Round-trip evidence

**Setup**:
```bash
codeindex graph-export --root /path/to/loomgraph -o /tmp/loomgraph-export.ndjson
loomgraph import-export /tmp/loomgraph-export.ndjson --workspace loomgraph-self:imported
```

**Spike-30 task A-1**: callers of `prepare_workspace_store` (depth 2).

**Baseline (direct `loomgraph index .`)** — `loomgraph:main` workspace:
- 7 callers: `_async_check`, `_async_deps`, `_async_find`, `_async_graph_query`, `_async_impact`, `_async_overview`, `_async_topology`

**Imported (codeindex graph-export → loomgraph import-export)** — `loomgraph-self:imported` workspace:
- 7 callers: `src.loomgraph.cli._analysis._async_check`, `src.loomgraph.cli._analysis._async_deps`, `src.loomgraph.cli._analysis._async_impact`, `src.loomgraph.cli._analysis._async_overview`, `src.loomgraph.cli._analysis._async_topology`, `src.loomgraph.cli._search._async_find`, `src.loomgraph.cli._search._async_graph_query`

**Identical set** (modulo naming convention). The graph-export preserves the impact analysis answer.

## Findings worth surfacing

### Finding 1 — Entity naming convention divergence

Codeindex export uses module-qualified names with `src.` prefix:
- `src.loomgraph.cli._common.prepare_workspace_store`

Loomgraph's `codeindex` scan+mapper (the in-process Python lib path it
used pre-graph-export) uses simple names:
- `prepare_workspace_store`

Both code paths come from codeindex internally, but the artifact format
preserves the full module derivation while the legacy lib path used
unqualified names.

**Decision needed for #102 schema固化**: which form does the contract
mandate? Options:
- **(a)** Schema mandates fully-qualified names (current export behaviour).
  Consumers must accept long names in graph CALLS edges and in entity
  IDs. Cleaner, no collision risk.
- **(b)** Schema mandates simple names (legacy form). Smaller payload,
  but reintroduces the F-class collision problems the spike documented.
- **(c)** Schema preserves BOTH (`id` qualified, `display_name` simple).
  Most flexible, slightly larger.

Recommendation: **(a)**. Fully-qualified is the right contract — it
resolves the F-class precision concern (different `Foo.bar` across
modules are now distinct entities) AND lets consumers strip prefix
themselves when displaying. Loomgraph's query layer should accept
fully-qualified names as the canonical form.

### Finding 2 — Unresolved edges dropped by SqliteGraphStore

12314 edges parsed; **5524 actually landed** in the store. The 6790
dropped edges are mostly `unresolved` (7257 total): they mapped to a
`<unresolved>` sentinel tgt_id, but `SqliteGraphStore.insert_custom_kg`
appears to require both endpoints exist as entities.

Two ways to fix this if we want the count to match:
- Insert a `<unresolved>` sentinel entity at import time so the edges
  have a valid endpoint
- Update the import to skip unresolved edges (lose count fidelity but
  consistent with what the store does anyway)

This is a stage-D follow-up. The dropped edges aren't useful for graph
walks anyway — they have no real target — but the completeness
statistic (how many unresolved calls exist in the codebase) is lost
without the sentinel entity.

### Finding 3 — Codeindex entity count is smaller than direct loomgraph index

- Codeindex graph-export of loomgraph: **394 entities, 3129 edges**
- Direct `loomgraph index .`: **1286 entities, 3435 relations**

The codeindex export emits class/function/method only (per schema).
Loomgraph's direct index also creates entities for modules, files, and
unresolved external callees (the 755-843 "external_stubs" count in its
output). The two are NOT designed to produce identical entity sets —
the export is an L1 structural slice.

Whether this is a contract bug depends on intent:
- If `#102` aims to fully replace `loomgraph index` (consumer scenario:
  CI just runs codeindex once and ships the artifact), the schema
  should include module + file entities
- If `#102` is meant for "callers/callees graph only" and loomgraph's
  index keeps its own embedding/module-tier work, the current
  3-entity-type set is correct

Recommendation: clarify the scope statement in `docs/guides/graph-export.md`.
Currently the doc says "entity_type: class | function | method", but
the implication that this REPLACES loomgraph's full indexing isn't
spelled out either way.

## Recommended actions

For **codeindex#102**:
1. Document the naming convention — `src.<module>.<entity>` is the form
2. Update doc to clarify whether export is a SUPERSET or SUBSET of what
   loomgraph index produces (Finding 3)
3. The `provenance_completeness` meta field landed perfectly — no action

For **loomgraph**:
1. Land the `import-export` command (this PR)
2. Add fully-qualified name handling in `find` / `graph` queries (allow
   query like `prepare_workspace_store` to match `*.prepare_workspace_store`)
3. Add `<unresolved>` sentinel entity insertion at import (Finding 2)

## Stage D (deferred follow-ups)

Not done in this round:
- TypeScript fixture spot-check (codeindex agent's promised caveat from
  the experimental v0 schema)
- Sentinel entity insertion to make unresolved-edge count match parsed
- Cross-check entity types per Finding 3 above
- Unit tests for the reader (sample artifacts in tests/fixtures)
- N=3 round-trip on the full spike-30 task set (not just A-1)

These are real but small follow-ups; the core contract is validated.
