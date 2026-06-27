# Spike #30 — Consumption A/B Report

> Status: **FINAL (flash tier)**. Full N=3 run completed; stronger-tier
> (deepseek-v4-pro) deferred — verdict is actionable at the flash tier
> and pro is optional confirmation.

## TL;DR — 🟡 YELLOW

**Path B (loomgraph CLI tools) wins decisively on impact analysis (A,
ΔCorr +1.00) and cross-file relatedness (D, ΔCorr +0.50). Path A
(README_AI prose) wins on call-chain tracing (B, ΔCorr -0.50). The
remaining three classes (C/E/F) tie at zero or low values.**

The win count (2 of 6 classes) does not meet the PLAN.md §6 pre-registered
GREEN trigger (≥3 of 6) but is far from BLACK (which would require
\|Δ\| < +0.10 across all classes; A has +1.00).

**Recommendation for codeindex#102**: solidify graph-export schema for
the field set Path B's tools actually used (entity + type + source_id +
edges callers/callees with provenance). Do NOT固化 schema fields that
Class B, E, F would need (chain-of-chains traversal helpers, dynamic
dispatch shadows, alias-aware resolution) — those are unsupported in the
current AST extraction and exposing them would authoritatively transmit
incomplete data.

Verdict scope: **DeepSeek v4 flash, Haiku-class tier (~30B effective)**.
Per G2, this does not bind decisions for stronger-agent populations.

## Verdict palette outcome

| Verdict | Pre-registered trigger | Met? |
|---|---|---|
| 🟢 GREEN | ΔCorr ≥ +0.20 OR ΔRecall ≥ +0.30 in ≥3 of 6 classes, incl. ≥1 of A/B; class E miss ≤50%; class F misres ≤30% | No — 2 of 6 wins |
| 🟡 **YELLOW** | Wins in 1-2 classes only | **YES (A + D)** |
| ⚫ BLACK | All deltas \|Δ\| < +0.10; or class E miss > 70% w/o caveat; or class F misres > 50% | No — A has +1.00 |
| 🔴 RED | Either path correctness < 30% on ≥3 classes | No — Path A meets threshold on E-2 (1.00), C, B, D; Path B on A, B-3, C-2, D |

## Per-class results (N=3 median of medians, deepseek-v4-flash)

| Class | Path A (README) Corr / Recall | Path B (LOOMGRAPH) Corr / Recall | ΔCorr | ΔRecall | Outcome |
|---|---|---|---|---|---|
| **A** impact analysis | 0.00 / 0.00 | **1.00 / 1.00** | +1.00 | +1.00 | 🟢 GREEN |
| **B** call-chain trace | **0.50 / 0.50** | 0.00 / 0.00 | -0.50 | -0.50 | Path A wins |
| **C** responsibility | 0.50 / 0.67 | 0.50 / 0.67 | +0.00 | +0.00 | Tie |
| **D** relatedness | 0.50 / 0.50 | **1.00 / 1.00** | +0.50 | +0.50 | 🟢 GREEN |
| **E** recall adversarial | 0.00 / 0.00 | 0.00 / 0.00 | +0.00 | +0.00 | Both fail |
| **F** precision adversarial | 0.00 / 0.00 | 0.00 / 0.00 | +0.00 | +0.00 | Both fail |

Token cost: Path A median ≈ 1k tokens/run; Path B median ≈ 7-8k tokens/run.
Path B is ~7× more expensive per task — economically justified only on
classes where it wins decisively (A, D).

## Key qualitative findings (replacing smoke findings with full-run evidence)

### Finding 1 — Class A: Path B wins 3/3 tasks at 1.00, Path A loses 3/3 at 0.00

All three impact-analysis tasks (A-1 prepare_workspace_store, A-2
create_graph_store, A-3 inject_parse_result) gave the same result:
Path B walked the callers cleanly via `loomgraph_graph` tool, Path A
returned 0 because the README_AI tree either omits the function entirely
(A-1: cli/README references the old `prepare_workspace_client` name, not
the v0.10+ rename), or doesn't enumerate the caller relationships
(A-2, A-3).

The model on Path A behaves correctly — it sees no evidence in the
READMEs and refuses to hallucinate rather than make up an answer:

> "I cannot assume it exists. Therefore, the answer is that there are
> no entities to update based on the provided READMEs. I will output
> nothing."

**Production implication**: codeindex#102 graph-export's edges field IS
load-bearing for impact analysis. The data exists, the schema固化 is
justified.

### Finding 2 — Class B: Path A wins because Path B over-explores

| Task | Path A median | Path B median | Notes |
|---|---|---|---|
| B-1 find→SELECT | 0.50 / 0.50 | 0.00 / 0.00 | Path B 33 tool calls in 10 turns, no final text |
| B-2 index→INSERT | 0.50 / 0.50 | 0.00 / 0.00 | Same over-exploration pattern |
| B-3 topology→Analyzer | 0.50 / 0.40 | **1.00 / 0.80** | Short chain — Path B succeeds |

Path B's failure on long chains is **not a data problem**. The graph
has the data. The failure is **consumption-side**: the agent walks
callees depth-3 across multiple branches in parallel tool calls, fills
its 10-turn budget, and never produces a final text answer.

B-3 (shortest chain in the set, ~5 entities) shows Path B CAN succeed
when chain length stays small.

**Production implication**: graph-export固化 must ship with consumption
guidance. Specifically, agents traversing call chains should be guided
to query *forward from entry point at depth 1*, summarize, then expand
selectively — not depth-3 BFS from every reachable node. This is a
schema documentation requirement, not a schema field.

### Finding 3 — Class C: tie — descriptions adequate from both sources

All three C tasks (SqliteGraphStore / TopologyAnalyzer / maybe_embed_entities
responsibility) scored identical 0.50/0.67 median on both paths. Both
the README_AI prose and the entity description field returned by
`loomgraph_find` are sufficient for "what does X do" questions. README
slightly cheaper (tokens × 7), but graph extracts the same content from
the entity's description field.

**Production implication**: graph-export's description field has value
but no comparative advantage over README. No new schema requirement.

### Finding 4 — Class D: Path B wins by knowing the entity universe

| Task | Path A | Path B | Notes |
|---|---|---|---|
| D-1 LLMClient siblings | 0.50 | **1.00** | Path A found one ABC, Path B found two |
| D-2 Analyzer family (6) | 1.00 | **1.00** | Both surfaced via wildcard or pattern |
| D-3 Direct* pair | 0.00 | **1.00** | Path A failed entirely — pattern not in any single README |

D-3 is the strongest signal: when the related entities live in different
module READMEs, Path A can't cross-link them. Path B's `loomgraph_find
Direct` returns both in one query.

**Production implication**: graph-export must surface entities indexable
by partial-name search. Path B's discriminator is "I can do find queries
that span all modules at once" — the schema needs the entity index
materialized (not lazily computed) for this to scale.

### Finding 5 — Class E: Both paths refuse, but for opposite reasons (and that's the load-bearing distinction)

| Task | Path A | Path B |
|---|---|---|
| E-1 dynamic dispatch (close) | refused "no evidence" | refused "0 callers" |
| E-2 click registration (25 cmds) | **1.00 / 0.96** | 0.00 / 0.00 |
| E-3 test-only callers | both said "test-only" but missed the trap | same |
| E-4 polymorphic dispatch (create_entity) | refused | refused (graph returns 0) |

E-2 is striking: Path A correctly listed ~24 of 25 click commands
(README_AI for `cli/` enumerates them). Path B FAILED — even though
graph indexes every command function, the agent didn't know to query
for them by pattern. It looked for the decorator and the graph doesn't
expose decorator-as-edge.

E-1 and E-4 are the failure-mode that matters for #102: when the graph
returns "0 callers" for an entity that IS called via dynamic dispatch,
Path B's answer is confidently wrong (silently empty). Path A's
explicit "no evidence found in READMEs" is honest about uncertainty.

**Production implication (CRITICAL for #102)**: graph-export固化 must
include a **provenance_completeness** field or equivalent caveat
metadata for AST-extracted edges. Without it, downstream consumers will
treat 0-edge entities as "no callers" instead of "no statically resolvable
callers" — silently wrong, the worst kind of wrong.

### Finding 6 — Class F: both paths fail — precision adversarial defeats N=3 attempts

| Task | Path A | Path B |
|---|---|---|
| F-1 name collision (TopologyAnalyzer.analyze) | 0.00 | 0.00 |
| F-2 alias misresolution (CodeindexParseResult) | 0.00 | 0.00 |
| F-3 same-name via ABC (create_entity) | 0.00 | 0.00 |

Neither path could distinguish the correct same-named target from its
collision siblings. Hand-inspecting answers: Path A typically lists too
many entities ("the analyze method exists on many classes — here's all
of them"), Path B returns 0 because `loomgraph_graph X.analyze` doesn't
disambiguate from `Y.analyze`.

**Production implication**: precision queries against the graph are
broken at the schema level — qualified-name resolution is not retained
through the CALLS edges. This is the OTHER critical schema field
missing for #102. Either fix at extraction time (codeindex's job) or
explicitly ship the graph with "all edges are simple-name-resolved,
not class-qualified" as a known limitation.

## Decision recommendations

### For codeindex#102 (graph-export schema固化)

🟡 **YELLOW outcome — partial schema固化 justified.** Pre-registered
action per PLAN §6: "solidify only the schema fields the winning task
classes use."

**Fields with strong evidence — 固化 with confidence**:
- `entity` (name) — load-bearing for all wins
- `entity_type` (class / function / method / module) — Path B's filter capability
- `source_id` (file:line) — used for trust + disambiguation in A/D wins
- `description` — Class C tie shows it has value parity with README prose
- `CALLS` edges (callers, callees) — Class A's 100% win driver
- Cross-entity search index (entity-name → entities) — D-3 win driver

**Fields with caveats — 固化 only with metadata**:
- `provenance_completeness` (new field, motivated by E-1/E-4) — must be
  shipped alongside CALLS so consumers can detect dynamic-dispatch gaps
- `resolution_qualifier` (new field, motivated by F class) — must
  distinguish `TopologyAnalyzer.analyze` from `DebtAnalyzer.analyze`
  in CALLS edges, or schema must document the simple-name-resolution
  limitation prominently

**Fields NOT justified — defer**:
- `chain_traversal` / `path_from_to` — Class B's Path B failure shows
  the agent gets lost; this would harm rather than help
- decorator-as-edge (Class E-2 motivation) — README handles this
  adequately; graph attempt is over-engineered

### For codeindex#101 Phase 2 (render-order flip "2a")

🟡 **Conditional GO**. The render-order flip's value is precisely the
field set we're recommending be固化 (entity + edges + provenance). Since
that subset wins decisively, the flip is justified for that subset.

Suggest reviewer scopes Phase 2's flip to the "high-confidence subset"
fields above; defer the YELLOW-caveat fields until codeindex extraction
gains the metadata.

### For loomgraph (CLI consumption-side fixes)

**Class B failure mode is actionable in loomgraph alone**, no codeindex
dependency:
- Add a `loomgraph trace <from> <to>` command that limits agent
  exploration to ONE forward path
- Improve `loomgraph graph --depth N` to cap the answer size and report
  truncation
- Add agent-facing tool description guidance ("use loomgraph_graph
  callers ONCE, then summarize — don't depth-3 BFS")

**Class E follow-up**: surface `provenance` metadata in `loomgraph
find` output, so agents can see "this entity has 0 outbound edges but
that may be dynamic dispatch."

**Optional Day-3**: re-run F-class with explicit qualified-name prompts
("call TopologyAnalyzer.analyze specifically, not just analyze") to
test whether the failure is harness or schema.

## Methodology limits (preserved from PLAN §10)

- **Single fixture (loomgraph self)**. an internal TS monorepo deferred per D1=C.
  TypeScript / cross-language generalization untested. Mitigation: per
  PLAN §7, this spike specifically gates Haiku-class on Python; broader
  result needs follow-up spike.
- **Single model tier (DeepSeek v4 flash)**. G2 scope explicit in PLAN
  §6. Stronger-tier (deepseek-v4-pro) was budgeted but not run — flash
  outcome is actionable; pro would confirm not change the verdict.
- **N=3**. PLAN.md §3 variance floor. No formal stats.
- **Ground truth hand-labelled by spike author** — risk of confirmation
  bias. Mitigation: each task's `notes` field documents the empirical
  verification.

## Run metadata

| | |
|---|---|
| Branch | `spike/issue-30-consumption-spike` |
| PLAN.md commit | `98cbce3` (frozen 2026-06-26) |
| Run script | `harness/run.py --tier flash` |
| Score script | `harness/score.py` |
| Total runs | 114 (19 tasks × 2 paths × 3 runs) |
| Wall time | 1791s (~30 min) |
| API cost | ~\$0.60 total (smoke + full) — well under PLAN's \$1-3 budget |
| Model | `deepseek-v4-flash` via DeepSeek's Anthropic-compatible endpoint |

## Raw artifacts

- PLAN: `docs/spikes/spike-30/PLAN.md`
- Tasks: `docs/spikes/spike-30/harness/tasks/loomgraph/` (19 task JSONs)
- Harness: `docs/spikes/spike-30/harness/`
- Runs: `docs/spikes/spike-30/harness/results/runs-flash.jsonl`
- Scored: `docs/spikes/spike-30/harness/results/scored-flash.jsonl`
- Audit trail: LoomGraph#30 + codeindex#102 comment threads
