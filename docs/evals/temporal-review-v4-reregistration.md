# Temporal-review v4 re-registration

## Status and separation

V4 is a prospective cohort, independent of v1, v2, v3, and every previous
runtime output. It has its own manifest id, task ids, frozen source refs,
adapter, runner, audit, and output root. It does not reinterpret, rescore, or
pool v3. Its two tasks were selected by source review plus a deterministic,
no-model raw `branch-diff` preflight before this registration:

- `8e49e067671445c0d6aecb82b3d61c51f78b6069..d6ae4e3bb97efa7c3d8024d2899d24e75308212b`
  returned codeindex `available` comparison and the registered
  `ImpactAnalyzer._find_callers` content identity;
- `a2f7c100f99486848b6db17f3b12e1db0356d4d0..e87b1eb11f8f272d52b306c3931a00b6138d00f8`
  returned codeindex `available` comparison and the registered
  `get_changed_files` content identity.

The immutable contract is
[`evals/temporal-review-v4-fixture-manifest.json`](../../evals/temporal-review-v4-fixture-manifest.json).
The exact no-model raw selection responses and their hashes are retained in
[`evals/temporal-review-v4-selection-preflight.json`](../../evals/temporal-review-v4-selection-preflight.json)
and are hash-bound into that manifest before model execution.

## Product question

For an explicitly declared historical source comparison, can an agent identify
the registered current implementation identity and state the observable
comparison boundary? The treatment asks whether LoomGraph's additive
`branch-diff` surface can supply that temporal evidence while the adapter
retains the raw comparison record.

This is an integration and navigation-evidence study. It does not measure or
claim tokens, time, velocity, solve rate, risk classification quality, or a
general model advantage.

## Model-visible answer and score

The model has exactly this JSON surface:

```json
{
  "decision": {"boundary": "...", "rationale": "..."},
  "review_loci": [
    {"path": "...", "qualname": "...", "rationale": "..."}
  ]
}
```

Only `decision.boundary` and canonical `(path, qualname)` identities are
scored. `rationale` is retained but not gold-scored. There is no `outcome`,
trust, comparison, provenance, or evidence-kind model field; therefore no
hidden risk-decision label can exclude an otherwise valid navigation answer.

Each locus must resolve against the frozen head's Python AST. `path` is
repository-relative; `qualname` is a dot-separated class/function identity.
`::`, module names, variables, prose labels, duplicate entries, and more than
three loci are invalid. The expected identities remain manifest-only so the
agent never sees a target list, solution patch, SHA, or oracle.

The public boundary rule is condition-derived, not task-specific judgement:

| Condition | Required boundary | Raw evidence |
| --- | --- | --- |
| baseline | `comparison_not_observed` | none |
| treatment | raw status `available` → `content_comparison_available`; raw status `unavailable` → `content_comparison_unavailable` | one selected, valid pre-final branch-diff event |

For every treatment event, the adapter and audit independently require exact
base/head aliases and SHAs, backend, provisioning, content-comparison status
and reason, raw bytes hash, and raw support for each registered identity.
`unavailable` is never interpreted as unchanged. The selected raw event is the
last valid branch-diff result before the final structured response; evidence
from different calls is never combined.

## Runtime identity gate

Before any cohort cell, run the no-fixture identity probe and retain its raw
stream. The cohort freezes the requested model token, Claude version, command
hash, and the complete observed identity tuple: `assistant_models`,
`session_models`, and `usage_models`. Every cell must match that tuple exactly;
first drift is a protocol stop. The audit rebuilds the tuple from the retained
preflight stream rather than trusting a summary alone.

`model-specific` mode additionally requires the requested token and sole
observed assistant model to be byte-equal. `runtime-specific` mode may retain
a nonmatching requested token, but reports only the observed runtime identity;
it must never be described as the requested model. This gate exists because
v3 requested `sonnet` but observed a GLM stack.

## Cohort and reporting

After full gates, review, CI, the identity preflight, and a separate explicit
runtime approval, run exactly two tasks × two counterbalanced replicates ×
baseline/treatment: eight new voluntary cells. Source checkouts contain only
`src/` and `.codeindex.yaml`; evaluations, tests, changelogs, and target
artifacts are excluded.

Every cell retains raw stream, command, environment, source pre/post state,
model identity, raw certificate, validity/exclusion, and cold/warm snapshot
record. The audit reports only task-separated complete valid pairs and their
raw records. `target_hit@3` is a navigation guard, not solve rate. No result
is pooled across task, mode, runtime, or historical cohort. Cold/warm is
provenance, not a speed comparison.

Any source mutation, runner/tool failure, model-identity drift, ref/backend/L2
mismatch, late/malformed raw response, or trust mismatch stops expansion before
another cell. A semantic miss is retained as an excluded cell but does not
permit changing this contract or expanding the cohort.
