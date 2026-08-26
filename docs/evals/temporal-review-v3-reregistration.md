# Temporal-review v3 re-registration

## Status and separation

This is a new, prospective protocol. It does not alter, rerun, pool, or
reinterpret v1, v2, or any partial v2 runtime output. Its distinct manifest
id is `loomgraph-temporal-review-v3-adapter-trust`, its schema version is 3,
and any later report must name that id, its output root, and its runtime.

V3 is registered before any v3 model run. The frozen oracle is derived from
the declared historical source fixtures and their task-specific review
questions, never from prior model answers, traces, patches, or audit outputs.

## Product question

For a historical code change, can a text-only agent or a branch-diff-assisted
agent identify the registered implementation responsibility and decision
boundary? For treatment, can the integration retain a valid raw comparison
record in the adapter while the model makes only a review decision from the
permitted surface?

This remains an evidence-chain and review-decision study. It is not a claim
about token use, elapsed time, development velocity, solve rate, or a general
model advantage.

## Frozen semantic and evidence contracts

The model answer has only an independently resolvable semantic surface:

1. `decision.{outcome,boundary,rationale}`, with a closed verdict enum;
2. `review_loci[].{path,qualname,rationale}`, resolved against the frozen head
   checkout's Python AST.

There is no model trust, comparison, provenance, or evidence-kind field. The
closed boundary enum is condition-specific: baseline must select
`comparison_not_observed`; a treatment response is evaluated after the adapter
selects its raw event and must select `content_comparison_available` or
`content_comparison_unavailable` accordingly. This prevents a presentation
rewrite (for example, `per_entity` to `per-entity`) from becoming a model
semantic failure when the product evidence is an adapter-owned raw MCP event.

The adapter calls the same task-specific raw parser as the audit. It retains
the canonical comparison values verbatim, including the exact `reason`, and
requires frozen refs/SHAs, backend, provisioning shape, comparison status and
reason, plus raw support for the treatment locus. Thus V3 does not weaken raw
trust: it moves comparison custody from the agent response to the observed
tool response.

For treatment, the adapter and audit independently select the last successful
raw branch-diff event that passed every frozen check **before** the final
structured response. They retain its stream position, tool-use id, original
JSON text, SHA-256, and parsed certificate. A late, malformed, or mismatched
event is a protocol stop; evidence may never be assembled across calls.

| Condition | Allowed surface | Model decision boundary | Adapter evidence |
| --- | --- | --- | --- |
| baseline | `Read`, `Glob`, `Grep` on source-only head | `comparison_not_observed` | absent |
| treatment, voluntary | baseline plus only `loomgraph_branch_diff` | raw-selected available or unavailable boundary | valid raw comparison retained and parsed exactly |

Any answer carrying a trust, comparison, provenance, or evidence-kind field is
schema-invalid. A treatment answer without valid raw evidence, with unsupported
frozen identities, with an unexpected tool, or with a boundary that disagrees
with the selected raw event is excluded. The codegraph control still requires
the adapter to retain
`backend_has_no_per_entity_content_hash`; `unavailable` is never equivalent
to unchanged.

## Cohort, source boundary, and gate

The immutable manifest
[`evals/temporal-review-v3-fixture-manifest.json`](../../evals/temporal-review-v3-fixture-manifest.json)
contains three frozen temporal tasks: two `codeindex` comparisons and one
`codegraph` uncertainty control. It uses a source-only checkout and excludes
release history, tests, evaluations, and related artifacts. The instructions
do not expose the hidden decision, target identities, fixture SHA, solution,
or target manifest.

A later runtime pilot, if separately approved after its v3 runner, audit,
full gates, review, and CI are complete, is exactly three tasks × two
counterbalanced replicates × baseline/treatment: 12 new voluntary runs. It
will retain every raw trace, environment/model/tool surface, source-clean
state, raw MCP evidence, validity or exclusion reason, and cold/warm record.
The v3 audit will rebuild results only from that v3 output root and report
valid paired deltas by task and condition, with median/Q1/Q3/IQR only where
the complete valid pairs support them. It will not merge modes, runtimes,
strata, or v1/v2 evidence.

If source mutation, tool/configuration failure, ref/backend/L2 mismatch, or
raw-parser trust mismatch occurs, expansion stops and the protocol problem is
reported before any new sample is started. Neither this document nor the
contract authorizes a model invocation or modifies the frozen cohort after
observing one.
