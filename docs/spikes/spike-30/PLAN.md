# Spike #30 — README_AI.md vs Knowledge-Graph Queries

> **Status**: Day 0 — scope frozen, awaiting sign-off before execution.
> **Issue**: [LoomGraph#30](https://github.com/dreamlx/LoomGraph/issues/30)
> **Time-box**: 2 days hard. Day 1 = ground-truth labelling + harness; Day 2 = A/B + report.
> **Owner**: dreamlx (assisted by Claude Code)

## 1. Question

For a code-understanding agent operating over an unfamiliar codebase, does
having **structured access to a code knowledge graph** (loomgraph `find` /
`graph` / `topology` / `impact` JSON output) materially out-perform having
only **human-readable architecture docs** (codeindex `README_AI.md` files
at every directory)?

The answer gates two downstream decisions:
- **codeindex**: should `graph-export` be solidified as a stable schema
  contract? Should the proposed render-order flip ("2a") proceed?
- **loomgraph**: should `loomgraph find/graph/topology` be promoted from
  "happens to work" to a first-class exported surface?

## 2. Scope decisions (frozen before running)

| Axis | Decision | Why fixed up-front |
|---|---|---|
| Fixtures | **loomgraph** (this repo) + **an internal TS monorepo** (TS monorepo) | Two languages, two sizes; "self-host first" precedent in codeindex#101 |
| Task classes | Four. See §3. | Cherry-picking one class biases the verdict |
| Tasks per class | 3 per fixture per class = **24 tasks** | N≥3 floor from `reference_agent_middleware_eval_methodology` |
| Ground truth source | **Hand-labelled before running** the A/B path | Otherwise judge becomes the bias vector |
| A/B variants | **A** = agent given `README_AI.md` tree; **B** = agent given loomgraph CLI access | Both are realistic consumption paths |
| Agent model | **Claude Haiku 4.5** | Cheap, fast, representative of "small agent that needs help" — most relevant population |
| Quality judge | **Ground-truth-first**: scored by mechanical match against labelled answers. LLM-as-judge only as secondary signal for partial credit | Avoids `feedback_synthesis_reproduces_sycophancy` |
| Verdict palette | **GREEN / YELLOW / BLACK / RED** (the missing BLACK from issue spec) | See §6 |

## 3. Task classes (frozen)

Four classes that span the README↔graph utility axis:

**A. Impact analysis** (graph-favored a priori)
- "If `<entity X>` changes, which other entities are at risk?"
- Ground truth = transitively-reachable callers up to depth 2

**B. Call-chain tracing** (graph-favored a priori)
- "Trace from `<API entry point>` to `<DB write site>`."
- Ground truth = ordered list of `CALLS`-connected entities

**C. Single-entity responsibility** (README-favored a priori)
- "What does `<class Y>` do?"
- Ground truth = a 1-2 sentence summary judged by overlap with docstring + module description

**D. Cross-file relatedness** (mixed a priori)
- "Which entities are semantically similar to `<entity Z>` but live in a different module?"
- Ground truth = hand-picked list of 3-5 entities sharing purpose

Distribution is **balanced** (6 tasks per class) — not weighted by "real
usage", because we don't have real usage data yet. The verdict per
class is the deliverable; codeindex / loomgraph decide weighting at use.

## 4. Harness

`docs/spikes/spike-30/harness/` — to be implemented Day 1:

```
harness/
├── tasks/              # 24 task JSONs, hand-labelled with ground truth
│   ├── loomgraph/      # 12 tasks (3 per class × 4 classes)
│   └── internal-ts/       # 12 tasks
├── path_a_readme.py    # Agent gets README_AI.md tree, answers tasks
├── path_b_loomgraph.py # Agent gets `loomgraph find/graph/...` CLI, answers tasks
├── judge.py            # Mechanical match + per-task scoring
└── run.py              # Orchestrates A/B for one fixture, writes results.jsonl
```

Each agent run gets:
- **Same task prompt** (no per-path prompt tuning)
- **Same model** (Haiku 4.5)
- **N=3** (run-to-run variance check; report median + range)
- **Same max-turns budget** (10 turns)

## 5. Metrics (per task, per path)

| Metric | How measured | Why |
|---|---|---|
| **Correctness** | Exact match on ground-truth answer set; 1.0 / 0.5 partial / 0.0 | Primary signal |
| **Recall** | `|answer ∩ ground_truth| / |ground_truth|` | Don't reward terse but incomplete answers |
| **Hallucination rate** | Count of answer entities NOT in fixture | Critical for trust |
| **Tokens spent** | Agent input + output, summed across turns | Secondary, but per `feedback_benchmark_must_grade_quality` cannot be primary |
| **Wall time** | Seconds from prompt sent to final answer | Secondary |

## 6. Verdict palette (with BLACK exit — the missing one from issue spec)

| Verdict | Definition | Action |
|---|---|---|
| 🟢 **GREEN** | Path B (graph) ≥ Path A (README) on **correctness + recall** in **≥3 of 4 task classes**, including at least one of A/B (impact / call-chain) | Solidify `graph-export` schema; promote loomgraph CLI to first-class export. codeindex 2a flip justified. |
| 🟡 **YELLOW** | Path B wins on **1-2 task classes only** (typically A + B), Path A wins on others | Solidify only the schema fields that the winning classes use (e.g. edges + entity_type). Don't export anything README already covers. |
| ⚫ **BLACK** | Path B shows **no statistically meaningful lift** on any class; or Path A is within noise on all classes | **codeindex ADR-007 should retract graph-export**. loomgraph CLI remains internal. The whole graph-export thesis is wrong. |
| 🔴 **RED** | Either path has correctness <30% → tasks too hard, results uninterpretable | Re-scope task set; spike inconclusive. |

## 7. Out of scope (explicit)

- **codeindex#102 graph-export schema choice** — this spike gates whether to do it, not which fields to include.
- **vec0 semantic search vs README similarity** — we don't have semantic embeddings live for the spike; structural query only.
- **Larger model evaluation** (Sonnet, Opus) — Haiku is the target audience for "needs help".
- **Real-user workload weighting** — see §3 closing note.

## 8. Failure modes we are actively guarding against

- **`feedback_no_syntactic_proxy_for_test_quality`** — we use ground truth, not "did the JSON have many entities" or similar syntactic proxies.
- **`feedback_synthesis_reproduces_sycophancy`** — Path B looks shiny; we will explicitly mark for the report any class where the verdict surprised us downward.
- **`feedback_benchmark_must_grade_quality`** — token / wall time are reported but never primary.
- **`feedback_read_code_path_before_causal_claim`** — for each task, when scoring, the labeller (human + Claude) reads the fixture to confirm ground truth, not "guess from name".

## 9. Time-box

- **Day 1** (8 hours max):
  - Harness scaffold (2h)
  - 24 hand-labelled tasks with ground truth (4h)
  - Path A + Path B agent runners (1h)
  - Smoke run on 1 task each end-to-end (1h)
- **Day 2** (8 hours max):
  - Full run (24 tasks × 2 paths × N=3 = 144 agent runs); on Haiku ~$5-10 budget
  - Scoring + judge pass (2h)
  - Report write-up (2h)
  - Comment back on issue #30, ping codeindex thread

If Day 1 overruns (>10h cumulative): **stop and re-scope**. Likely cut to 1 fixture (loomgraph only).

## 10. Definition of done

A reply on LoomGraph#30 containing:
- The verdict (one of 🟢🟡⚫🔴) with per-task-class table
- The raw `results.jsonl` linked
- A pointer to this PLAN.md so the rubric is auditable
- A copy of the verdict + key tables posted to the codeindex render-flip thread, so 2a can be decided

---

## Sign-off check before running

- [ ] Fixtures pinned (loomgraph + an internal TS monorepo)
- [ ] Task count (24) accepted
- [ ] Agent model (Haiku 4.5) accepted, budget acknowledged (~$5-10)
- [ ] Verdict palette including BLACK accepted
- [ ] Time-box 2 days accepted (with Day-1 stop-and-rescope rule)
- [ ] All 5 critique guards from §8 noted
