# Temporal-review V7 re-registration

## Status and separation

V7 is a prospective, independent cohort. It does not rerun, reinterpret,
rescore, or pool v1--v6. The stopped V6 r1 root remains archive-only evidence
for its own contract. V7 uses the same frozen historical comparisons only as a
same-source contrast; it does not change the hidden AST oracle, raw MCP trust
contract, source-clean boundary, tool allowlist, cold/warm provenance, or the
single `review_locus` answer schema.

The immutable contract is
[`evals/temporal-review-v7-fixture-manifest.json`](../../evals/temporal-review-v7-fixture-manifest.json).
Before any model cell, its fresh, no-model raw selection evidence must be
retained at
[`evals/temporal-review-v7-selection-preflight.json`](../../evals/temporal-review-v7-selection-preflight.json).
V5/V6 selection artifacts and hashes are expressly rejected by the V7 fixture
validator.

## Narrow change

V6 r1 stopped after two cells because the retained raw `modelUsage` encounter
order changed from `["glm-4.7", "glm-5.2[1M]"]` in its identity preflight to
`["glm-5.2[1M]", "glm-4.7"]` in a cell. That is an order-only difference,
not evidence that a label changed. V7 changes only the runtime identity
comparison contract; no model call has occurred under V7 at preregistration.

For each surface—`assistant`, `session`, and `usage`—the runner and audit must
retain the exact raw encounter-order sequence of nonempty model-label strings.
Order and duplicates are evidence and must remain inspectable. Compatibility is
instead evaluated per surface with the canonical set:

```text
sorted(unique(exact_nonempty_raw_labels))
```

“Exact” means byte-exact label equality. V7 must not trim, lowercase, case-fold,
normalize Unicode, remove punctuation, rewrite aliases, or otherwise normalize
labels. Thus a reordered duplicate-free `usage` list can be compatible, while
any changed/added/removed exact label is an identity mismatch. Assistant and
session retain the same two-layer rule; their raw order is auditable and their
canonical comparison is order-insensitive. A runtime-specific request label
remains a request label, not attribution to the observed stack.

The retained preflight and each cell must record both fields for each surface:

```json
{
  "usage_models_raw": ["glm-5.2[1M]", "glm-4.7"],
  "usage_models_canonical": ["glm-4.7", "glm-5.2[1M]"]
}
```

The audit must rebuild raw encounter order directly from each retained stream,
recompute canonical labels from those raw values, and reject any mismatch with
the runner/preflight fields. It must also reject a canonical match when the raw
stream is missing, malformed, or fails to produce a final result. No canonical
comparison may replace raw evidence.

## Evidence and fixed pilot gate

After full implementation gates, review, CI, fresh V7 selection preflight, a
fresh runtime identity preflight, and separate explicit approval, run exactly
two tasks × two counterbalanced replicates × baseline/treatment: eight new
voluntary cells. Preserve raw streams, command/environment surface, source
pre/post state, raw/canonical runtime identity evidence, raw MCP certificates,
validity/exclusion reasons, and cold/warm records.

No expansion is automatic. Terra may ask for approval for the frozen 12-task /
72-run cohort only if all of the following hold:

- no hard protocol stop;
- at least three of four counterbalanced replicate pairs are complete valid
  pairs, with at least one complete valid pair per task;
- zero cells are excluded for AST-unresolvable or multiple/extra review-locus
  structure; and
- zero audit integrity mismatches among final structured payload, retained raw
  stream, runner semantic observation, raw/canonical model-identity evidence,
  or selected raw MCP certificate.

Failure leaves the V7 evidence package complete but does not authorize contract
change, expansion, or the 72-run cohort. Tool counts remain reporting-only. The
pilot neither measures nor claims tokens, development time, velocity, solve
rate, or a general model advantage.

## Required runner/audit interface

The V7 identity preflight, orientation summary, pilot runner, and audit must
all expose six lists, with values as raw strings and no label normalization:

- `assistant_models_raw`, `session_models_raw`, `usage_models_raw`;
- `assistant_models_canonical`, `session_models_canonical`,
  `usage_models_canonical`.

For compatibility, requested model label and identity mode must still match;
then compare the three canonical lists exactly. Raw lists need not be ordered
the same, but every retained raw list must be rebuilt from its own stream and
match the recorded raw list exactly. This is a protocol repair for a raw-order
artifact, not permission to accept missing identity evidence or to merge V6.
