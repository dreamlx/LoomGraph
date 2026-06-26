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

Four primary classes spanning the README↔graph utility axis, **plus a
fifth adversarial class** that probes the graph path's known failure
modes. Verdict gets reported per class; aggregate verdict gates schema.

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

**E. Adversarial — recall failures** (graph false-negatives)
- E1. **Dynamic dispatch** — "who calls `<method X>` via duck typing / `getattr` / event handler?" — AST extraction misses these; graph returns 0 callers but ground truth has 2-3.
- E2. **Reflection / metaprogramming** — "find every place that touches `<class Y>` via `__init_subclass__` / decorator / metaclass" — graph misses entirely; README often has prose that mentions it.
- E3. **Test-only callers** — "who tests `<entity Z>`?" — depending on how tests parse, graph may or may not include test files; ground truth pulls from `tests/`.

**F. Adversarial — precision failures** (graph false-positives, per review G1)
> The asymmetric risk: a missing edge makes the agent fall back to
> reading code (recoverable). A wrong edge with `provenance=AST`
> stamped on it makes the agent confidently act on bad data
> (irrecoverable, breaks the trust the schema is meant to confer).
> Fixing schema固化 to authoritatively transmit wrong data is worse
> than not固化 at all — this class directly gates #102.

- F1. **Name collision** — codebase has `Foo.bar` in two different modules; trace "who really calls `module_a.Foo.bar` from `module_b`?" Path B must NOT report `module_c.Foo.bar` as a caller.
- F2. **Alias misresolution** — `import Foo as Bar` patterns + chained re-exports; trace true callee through alias chain.
- F3. **Same-name method on unrelated classes** — `ServiceA.run()` vs `ServiceB.run()`; graph should resolve to the right one given a call site.

Hallucination metric (§5) misses these because the false-positive
entity *exists* in the fixture — it's just the wrong one. F-class
needs its own scorer: "did Path B return an entity that is a real
collision target, not the intended one?"

### Distribution

- **6 classes × 3 tasks per class per fixture = 18 tasks/fixture**
- 2 fixtures → **36 tasks total**
- Class balance: A-D (graph-favored / README-favored / mixed) +
  E (recall-adversarial) + F (precision-adversarial) — same weight per
  class
- N=3 runs per task × 2 paths × 36 tasks = **216 agent runs**, Haiku
  budget ~\$8-15

Distribution is **balanced**, not weighted by "real usage" — codeindex
/ loomgraph decide weighting at use. The verdict per class is the
deliverable.

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
| **Hallucination rate** | Count of answer entities NOT in fixture | Critical for trust on entities |
| **Misresolution rate** (F-class only) | Count of answer entities that are a real collision target (exist in fixture) but NOT the ground-truth target | Catches the failure mode hallucination misses; gates #102 schema固化 directly |
| **Tokens spent** | Agent input + output, summed across turns | Secondary, but per `feedback_benchmark_must_grade_quality` cannot be primary |
| **Wall time** | Seconds from prompt sent to final answer | Secondary |

## 6. Verdict palette (with BLACK exit — the missing one from issue spec)

| Verdict | Definition | Action |
|---|---|---|
**Pre-registered effect-size gates** (per review G3 — no post-hoc
"statistically meaningful" judgments at N=3). All thresholds computed
on per-task **median across 3 runs**, then aggregated per class as the
median of task scores.

| Verdict | Pre-registered trigger | Action |
|---|---|---|
| 🟢 **GREEN** | Path B beats Path A by **`median(B.correctness) − median(A.correctness) ≥ +0.20`** OR **`recall_B − recall_A ≥ +0.30`** in **≥3 of 6 task classes**, **including ≥1 of A/B** (impact / call-chain), AND **class E miss ≤ 50%**, AND **class F misresolution ≤ 30%** | Solidify `graph-export` schema; promote loomgraph CLI to first-class export. codeindex 2a flip justified. Schema **must** ship with E/F caveats discovered. |
| 🟡 **YELLOW** | Path B wins on **1-2 task classes only** (typically A + B), Path A wins on others; class E/F within GREEN limits | Solidify only the schema fields the winning classes use (e.g. edges + entity_type). Don't export anything README already covers. Same provenance caveat requirement as GREEN. |
| ⚫ **BLACK** | **`|median(B) − median(A)| < +0.10` (within noise) on ALL 6 classes** OR **class E miss > 70%** OR **class F misresolution > 50%** | **Scope-limited verdict**: For Haiku-class agent population (≤30B effective params, ≈GPT-4o-mini tier), graph-export does not earn its weight. Stronger agents (Sonnet/Opus tier) on harder real tasks may show different results — this BLACK does not bind decisions for those populations. codeindex schema固化 may proceed for larger-agent target tiers, but NOT for the tier tested here. F-class trigger is the strongest signal: schema would authoritatively transmit wrong data → must not固化 in current form. |
| 🔴 **RED** | Either path has **correctness < 30%** on ≥3 classes → tasks too hard, results uninterpretable | Re-scope task set; spike inconclusive. |

### Why these specific numbers

- `+0.20` correctness delta = roughly "B gets 1 more partial-credit
  answer right out of 6 tasks per class" — small but consistent lift
- `+0.30` recall delta = "B finds 30% more of the ground-truth set" —
  the recall-friendly gate when correctness is tied
- `±0.10` aggregate noise band = N=3 typical run-to-run variance
- Class E `50%/70%` and class F `30%/50%` thresholds are asymmetric on
  purpose: precision failures (F) are more dangerous than recall
  failures (E) per the G1 argument

### Scope discipline (per review G2)

This spike measures Haiku-class consumption. A BLACK verdict scoped to
that tier does NOT close codeindex ADR-007's export path for stronger
agents — only triggers a re-spike requirement before固化 for those
tiers. Future spikes targeting Sonnet/Opus would need their own
pre-registered thresholds; same methodology.

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

- **Day 1** (10 hours max — F-class collision-site hand-finding adds ~1h):
  - Harness scaffold (2h)
  - **36** hand-labelled tasks (6 classes × 3 × 2 fixtures): A-D structural tasks (3h), E-class adversarial recall (1.5h), **F-class collision/alias sites (1.5h — hardest to hand-find)** (6h total)
  - Path A + Path B agent runners (1h)
  - Smoke run on 1 task per class end-to-end (1h)
- **Day 2** (8 hours max):
  - Full run (**36 tasks × 2 paths × N=3 = 216 agent runs**); on Haiku ~$8-15 budget
  - Scoring + per-class verdict against pre-registered thresholds (2h)
  - Report write-up (2h)
  - Comment back on issue #30 + codeindex#102 / #101 threads with verdict tables

### Stop-and-rescope rule

If Day-1 cumulative work > 10h before all 36 tasks are labelled: cut
to **single fixture (loomgraph) only** = 18 tasks. Don't drop class E
or F — they're the highest-signal classes for the gating decision.
Cutting fixture preserves diagnostic power; cutting class doesn't.

If Day 1 overruns (>10h cumulative): **stop and re-scope**. Likely cut to 1 fixture (loomgraph only).

## 10. Definition of done

A reply on LoomGraph#30 containing:
- The verdict (one of 🟢🟡⚫🔴) with per-task-class table
- The raw `results.jsonl` linked
- A pointer to this PLAN.md so the rubric is auditable
- A copy of the verdict + key tables posted to the codeindex render-flip thread, so 2a can be decided

---

## Sign-off check before running

- [x] Fixtures pinned (loomgraph + an internal TS monorepo)
- [x] Task count (36 across 6 classes × 2 fixtures) accepted
- [x] Agent model (Haiku 4.5) accepted, budget acknowledged (~$8-15)
- [x] Verdict palette including BLACK accepted, with G2 scope language
- [x] Time-box 2 days accepted (with Day-1 stop-and-rescope: cut fixture not class)
- [x] All 5 critique guards from §8 noted
- [x] **G1** false-positive class F added with own misresolution metric
- [x] **G2** BLACK scope language explicit (Haiku-tier population, not whole-thesis kill)
- [x] **G3** pre-registered effect sizes (+0.20 correctness, +0.30 recall, ±0.10 noise band)

## Review trail

- 2026-06-26 — initial PLAN frozen
- 2026-06-26 — class E (recall adversarial) added per first review pass
- 2026-06-26 — class F (precision adversarial) + G2 scope + G3 effect sizes added per review G1/G2/G3
