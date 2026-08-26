# Temporal-review V8 re-registration

## Status and separation

V8 is a prospective, independent cohort. It does not rerun, reinterpret,
rescore, audit, or pool v1--v7. Their roots, including stopped V6 r1 and the
completed V7 r1 package, remain archive-only evidence for their own contracts.
V8 uses different fresh selection artifacts and task identifiers. Its historical
comparisons are a same-source contrast only; it does not change the hidden AST
oracle, raw MCP trust contract, source-clean boundary, tool allowlist,
cold/warm provenance, or the single `review_locus` answer schema.

The immutable contract is
[`evals/temporal-review-v8-fixture-manifest.json`](../../evals/temporal-review-v8-fixture-manifest.json).
Before any model cell, fresh no-model raw selection evidence is retained at
[`evals/temporal-review-v8-selection-preflight.json`](../../evals/temporal-review-v8-selection-preflight.json).
The V8 validator rejects every known v1--v7 selection-artifact hash; v1--v3
predate retained selection artifacts and have no hash to reuse.
Each retained selection response uses its task's `v8-base` / `v8-head` aliases
and the manifest-pinned commit SHA together, matching the runtime raw-MCP
surface exactly; either an alias or SHA mismatch is invalid.

## Only new closure

V8 changes exactly one missing integrity closure. The six persisted model-label
arrays remain required: raw encounter-order and canonical arrays for each of
`assistant`, `session`, and `usage`. V8 adds a seventh required persisted
identity field: `model_categories_valid: true`.

The runner may set that field true only after it validates the raw retained
stream has three separate declared categories and each category is an array of
nonempty exact strings. Raw occurrence duplicates are allowed and retained:
repeated normal assistant events are not themselves identity drift. Each
canonical list is exactly `sorted(unique(raw))`. The audit must rebuild all
three raw categories from the raw stream, recompute every canonical list, and
cross-check all seven persisted identity fields. Missing, malformed, replaced,
added, removed, or cross-category model labels are invalid. The audit must not
merge categories.

This is not a label relaxation: no trimming, case-folding, Unicode
normalization, punctuation rewrite, alias rewrite, or inferred equivalence is
allowed. Raw sequence order remains retained and must match the stream exactly;
only the pre-existing per-category canonical comparison is order-insensitive.

## Evidence and fixed pilot gate

After implementation gates, review, CI, fresh V8 selection preflight, fresh
runtime identity preflight, and separate explicit approval, run exactly two
tasks × two counterbalanced replicates × baseline/treatment: eight new voluntary
cells. Preserve raw streams, command/environment surface, source pre/post
state, all seven identity fields, raw MCP certificates, validity/exclusion
reasons, and cold/warm records.

No expansion is automatic. Terra may ask for approval for the frozen 12-task /
72-run cohort only if no hard protocol stop occurs, at least three of four
counterbalanced replicate pairs are complete valid pairs with one per task, no
cell is excluded for AST-unresolvable or multiple/extra review-locus structure,
and the audit finds zero final-payload/raw-stream/semantic/MCP/identity
integrity mismatches. Tool counts are reporting-only. The pilot neither
measures nor claims tokens, development time, velocity, solve rate, or a
general model advantage.
