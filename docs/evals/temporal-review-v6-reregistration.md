# Temporal-review V6 re-registration

## Status and separation

V6 is a prospective, independent cohort. It does not reinterpret, rescore, or
pool v1--v5. V5's complete pilot root remains archive-only evidence for its own
contract. V6 reuses the same frozen historical comparisons solely as a
same-source contrast: the source question and hidden AST oracle are unchanged,
while the model-visible answer shape changes before any V6 model execution.

The immutable contract is
[`evals/temporal-review-v6-fixture-manifest.json`](../../evals/temporal-review-v6-fixture-manifest.json).
Before any model cell, a fresh, no-model V6 selection preflight must be retained
at `evals/temporal-review-v6-selection-preflight.json`, with distinct raw
branch-diff artifacts and hashes bound into the V6 manifest. V5 selection
artifacts cannot satisfy that gate.

## Narrow change and non-change

V5 retained a `review_loci` list of one to three AST identities. Its pilot
excluded four cells for semantic misses, including extra or nonresolving loci.
V6 changes only that model-visible surface to an exactly-one `review_locus`
object. The prompt instructs the agent to choose one main location, omit
alternatives/callers/adjacent implementations, and check that the path and
qualname resolve against the current source.

The change does **not** relax the oracle: each task still has its same hidden,
exact `(path, qualname)` AST identity. It does not expose an oracle, target
manifest, solution patch, SHA, raw comparison fields, or target list to the
model. It does not change raw MCP adapter trust, source-clean rules, tool
allowlist, baseline/treatment separation, runtime identity, ref/backend/L2
matching, selected-event policy, or cold/warm provenance.

The model-visible answer is exactly:

```json
{
  "decision": {"boundary": "...", "rationale": "..."},
  "review_locus": {"path": "...", "qualname": "...", "rationale": "..."}
}
```

Only `decision.boundary` and the canonical `review_locus` `(path, qualname)`
are scored. Rationale remains retained, but is not gold-scored. Tool-call names
and counts remain raw trace metadata only; quantity cannot make a run valid,
invalid, excluded, stopped, or expanded. A reported/raw trace mismatch is an
integrity exclusion, and unexpected MCP remains a hard stop.

## Evidence and fixed pilot gate

After full implementation gates, review, CI, fresh V6 raw selection preflight,
runtime identity preflight, and a separate explicit runtime approval, run
exactly two tasks × two counterbalanced replicates × baseline/treatment: eight
new voluntary cells. Preserve for every cell the raw stream, command and
environment surface, source pre/post state, observed runtime identity, raw MCP
certificate, validity/exclusion reason, and cold/warm snapshot record.

No expansion is automatic. The only condition under which the Terra may ask for
approval to invest in the frozen 12-task/72-run cohort is all of:

- no hard protocol stop;
- at least 3 of the 4 counterbalanced replicate pairs are complete valid pairs
  (so both conditions have at least 3 valid cells);
- each task has at least 1 complete valid pair; and
- zero cells are excluded because a review locus is AST-unresolvable or because
  the answer contains multiple/extra review-locus structure.
- zero audit integrity mismatches between the retained final structured payload,
  its raw stream event, and the runner's semantic observation.

Any failure of this gate leaves the eight-cell V6 evidence package complete but
does not authorize a contract change, larger sample, or 72-run cohort. No
results are pooled across task, condition, mode, runtime, or cohort. The pilot
does not measure or claim tokens, development time, velocity, solve rate, or a
general model advantage.
