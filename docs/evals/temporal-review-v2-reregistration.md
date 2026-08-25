# Temporal-review v2 re-registration

## Status and separation

This is a new, prospective protocol. It was written after the completed
`temporal-review-pilot-20260826-r2` pilot and before any v2 model run. The r2
raw traces, orientations, and audit result remain immutable historical
evidence; they are not evaluated with this contract, pooled with it, or used
as a positive control.

The v2 manifest has a distinct id and versioned instruction files. A v2 report
must name its manifest id, task ids, model/runtime surface, and output root;
it must never merge rows with the v1/r2 evidence package.

## Product question

For a real historical PR/release change, can a text-only agent or a
branch-diff-assisted agent name the primary implementation responsibility that
needs review and preserve the actual temporal comparison boundary?

This is still a narrow evidence-chain and review-decision study. It is not an
efficiency, token, elapsed-time, coding, or solve-rate benchmark.

## Why v2 changes the response contract

The v1 contract required exact fully-qualified symbol strings and literal
Chinese decision phrases. Those are presentation details, not the product
decision. V2 independently scores:

1. a stable AST source identity tuple: repository-relative `path` plus Python
   `qualname`;
2. a task-specific decision verdict chosen from an explicitly presented,
   mutually exclusive question; and
3. raw-MCP comparison trust copied without normalization by the model.

The registered response shape is `decision.{outcome,boundary,rationale}` and
`review_loci[].{path,qualname,evidence_kind,rationale}`. Outcome, boundary,
and evidence kind use closed enums; rationale is required audit context but is
not scored as a literal phrase. Baseline must identify its locus from
`source_text`; treatment must identify it with the registered temporal
evidence kind.

V2 does **not** treat a similar string, a pathless symbol, prose paraphrase,
or an extra speculative locus as a hit. The tuple resolves against the frozen
head source with only `::`/`.` separator normalization in the raw-event
adapter. The resolved identity, verdict, evidence kind, and comparison fields
must each satisfy the frozen contract.

## Frozen cohort and conditions

The new manifest
[`evals/temporal-review-v2-fixture-manifest.json`](../../evals/temporal-review-v2-fixture-manifest.json)
uses the same three historical changes as v1 solely as a new, separately
registered cohort: two `codeindex` comparisons and one required `codegraph`
uncertainty control. Its source-only checkout, aliases, and exclusion list are
identical in purpose but are independently validated.

| Condition | Allowed surface | Trust rule |
| --- | --- | --- |
| baseline | `Read`, `Glob`, `Grep` in the source-only head checkout | no comparison tool; `tool_evidence: absent`, `comparison: null` |
| treatment | baseline plus only `loomgraph_branch_diff` | raw response is mandatory; `tool_evidence: present` and all comparison fields copy it exactly |

The response exposes a decision question and the permitted verdict enum. It
does not expose frozen SHAs, expected identity tuples, raw response fixtures,
the hidden decision verdict, PR/issue data, tests, evaluations, or the v1/r2
audit outcome.

## Validity and exclusions

A v2 row is semantically valid only if all of these hold:

- the source checkout is clean before and after the model phase;
- the response has exactly the registered schema;
- its primary locus matches the registered source-path/anchor tuple and
  evidence-kind rule;
- its verdict matches the task-specific hidden decision rule;
- treatment uses no unexpected MCP tool, keeps within the declared budget, and
  retains a successful raw branch-diff response for the frozen refs/backend;
- treatment trust is byte-for-value aligned with parsed raw comparison fields;
  and
- the codegraph control keeps `unavailable` as an uncertainty boundary rather
  than an unchanged conclusion.

Any failure is an exclusion with a reason, never a negative product score.
Raw tool evidence and semantic scoring are reported separately.

## Planned pilot and decision gate

After implementation, full local gates, review, and PR CI, the planned v2
runtime pilot is three tasks × two counterbalanced replicates × two
conditions: 12 new runs. It will record a cold model-phase comparison and a
separate warm direct repeat for every treatment run that produced valid raw
tool evidence, even if its semantic score fails. Durations remain diagnostic
only.

No v2 runtime run is authorized by this document alone. Starting that 12-run
pilot requires a fresh user confirmation after the v2 manifest, instructions,
oracle tests, runner/audit support, and CI have been inspected. If the pilot
has no valid semantic pair, it is a no-go for further expansion; no metric or
oracle may be changed after observing it.
