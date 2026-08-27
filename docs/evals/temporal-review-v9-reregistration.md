# Temporal-review V9 re-registration

## Status and separation

V9 is a prospective, independent cohort for the explicitly requested
`glm-5.3-flash` runtime. It does not rerun, reinterpret, rescore, audit, or
pool v1--v8. In particular, the stopped V8 r1 root remains archive-only
evidence for its own contract. V9 has new task identifiers, `v9-base` /
`v9-head` aliases, and fresh no-model raw selection artifacts. It uses the same
frozen historical comparisons only as a same-source contrast; it does not
alter the hidden AST oracle, raw-MCP trust boundary, source-clean requirement,
tool allowlist, cold/warm provenance, or singular `review_locus` schema.

The immutable contract is
[`evals/temporal-review-v9-fixture-manifest.json`](../../evals/temporal-review-v9-fixture-manifest.json).
Before any model cell, fresh selection evidence is retained in
[`evals/temporal-review-v9-selection-preflight.json`](../../evals/temporal-review-v9-selection-preflight.json).
The V9 validator rejects every retained v4--v8 selection artifact hash; v1--v3
predate retained selection artifacts and cannot be reused.

## Runtime and identity contract

V9's sole external runtime change is the exact requested model literal
`glm-5.3-flash`; every identity preflight and pilot cell must freeze that exact
literal. This is not a new interpretation of the `sonnet` alias. The local
probe retained before V9 registration showed that `--model sonnet` resolved to
assistant label `glm-5.3`, while explicit `--model glm-5.3-flash` reported
assistant label `glm-5.3-flash`. The literal is therefore an explicit runtime
choice, not alias semantics or an equivalence claim.

V9 retains V8's strict seven-field identity closure: raw encounter-order and
canonical arrays for each separate `assistant`, `session`, and `usage`
category, plus `model_categories_valid: true`. Each raw category must be an
array of exact, nonempty strings; duplicates and order are retained. Its
canonical category is exactly `sorted(unique(raw))`. No trimming, case folding,
Unicode or punctuation normalization, alias rewriting, inferred equivalence,
or category merging is permitted. The raw retained stream must reconstruct all
three raw and canonical category arrays exactly. Added, removed, replaced,
missing, malformed, or cross-category labels are hard failures.

V9 is runtime-specific only: `model-specific` mode is forbidden. Every raw
category is nonempty, and the canonical assistant category must equal exactly
`["glm-5.3-flash"]`; that is direct attribution for the explicit literal, not
an inference from a `sonnet` alias.

## No-target calibration gate

After the runtime identity preflight and before the scored pilot, run the frozen four-cell
no-target calibration matrix: baseline then treatment in replicate 1, treatment
then baseline in replicate 2. It is voluntary, separately retained, and never
scored or pooled with the pilot. The prompt is calibration-only and must not
receive a target task identifier, fixture/target manifest, oracle, solution, or
gold patch.

Each calibration cell uses the same Claude-orientation command surface as its
corresponding pilot arm, except for that no-target prompt. Baseline exposes no
MCP tool; treatment exposes only `loomgraph_branch_diff`. All three canonical
identity categories must agree across the four calibration streams and later
registered pilot identity evidence. Raw encounter occurrences remain retained
and rebuilt from each individual stream, but their cross-run order is never a
comparison criterion.

The normalized outer/inner Claude command fingerprint is SHA-256 over canonical
JSON. It retains all semantic flags and requires exact equality per condition
across both calibration replicates and all pilot cells. Only run-local
`--source-dir`, `--instruction-file`, `--output-dir`, and `--task-id` values,
the calibration/pilot marker spelling, the terminal instruction, and the MCP
storage-path value are normalized. The maximum budget is frozen at `$0.50` for
both calibration and pilot; a differing budget or surface is a protocol fault.

The fixed calibration source and instruction are hash-bound in the manifest.
The runner must retain those hashes and a case-folded forbidden-token scan over
both files, rejecting `manifest`, `oracle`, `target`, `solution`, `gold`,
`v9-resolution`, or `v9-sparse`. Treatment's MCP server environment may contain
only `LOOMGRAPH_MCP_ALLOWED_TOOLS=loomgraph_branch_diff` and optional
`LOOMGRAPH_STORAGE__DB_PATH`; extra keys are invalid.

## Evidence and fixed pilot gate

After full implementation gates, independent review, CI, fresh V9 selection
preflight, fresh V9 runtime-specific identity preflight, and separate explicit
approval, run exactly two tasks × two counterbalanced replicates × baseline /
treatment: eight voluntary cells. Preserve raw streams, command/environment
surface, source pre/post state, all seven identity fields, raw MCP certificates,
validity/exclusion reasons, and cold/warm records.

No expansion is automatic. Terra may request authorization for the frozen
12-task / 72-run cohort only when there is no hard protocol stop, at least three
of four counterbalanced replicate pairs are complete valid pairs with one per
task, no cell is excluded for AST-unresolvable or multiple/extra review-locus
structure, and audit finds zero final-payload/raw-stream/semantic/MCP/identity
integrity mismatch. The pilot does not measure or claim tokens, development
time, velocity, solve rate, or general model advantage.
