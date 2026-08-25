# Temporal-review product-validation pilot

## Purpose

This pilot tests a narrow product claim: an agent reviewing a real historical
change can receive a branch-diff evidence packet, identify the declared review
locus, and preserve the packet's comparison boundary. It is not a coding-agent
benchmark or an efficiency study.

The intended user decision is: *which implementation responsibility needs
review before accepting a PR or release, and what can the available comparison
evidence actually establish?*

## Cohort boundary

The frozen task manifest is
[`evals/temporal-review-fixture-manifest.json`](../../evals/temporal-review-fixture-manifest.json).
It contains three LoomGraph historical-review tasks:

1. a codeindex comparison of the low-resolution impact-trust change;
2. a codeindex comparison of the later sparse-risk change; and
3. the same sparse-risk change with codegraph, where per-entity L2 content
   comparison is unavailable.

The first two require an evidence-backed, `available` codeindex comparison.
The third is a required uncertainty control: `unavailable` must be carried
through as unavailable, never rewritten as unchanged. These are distinct
tasks, despite two sharing Git refs, because their backend and permitted
conclusion differ.

This is a self-dogfood product slice, not a representative population of
repositories or reviewers. A later external-repository cohort must be frozen
separately and must not be pooled with it.

## Conditions and leakage boundary

Each task is materialized as a clean, source-only historical checkout with its
two fixed aliases. The checkout excludes release notes, evaluation material,
tests, and other oracle-bearing artifacts listed in the manifest. The agent
receives only the natural-language review decision, aliases, backend, and the
structured response schema.

| Condition | Surface | Required trust statement |
| --- | --- | --- |
| baseline | `Read`, `Glob`, `Grep` over the source-only head checkout | `availability: unavailable`, `comparison: null` |
| treatment | baseline plus only `loomgraph_branch_diff` | copy raw comparison fields exactly; report the task's declared `available` or `unavailable` status |

The treatment is evidence-required even in voluntary mode: a task about a
specific temporal comparison cannot be counted as product evidence unless its
raw MCP response is retained and aligns with the structured answer. This does
not alter the already archived v2 voluntary protocol.

## Acceptance and exclusions

A run is valid only when all of the following hold:

- source pre/post Git state is clean;
- the final response satisfies the task-specific schema and independent
  decision/review-locus oracle;
- the only MCP tool in treatment is `loomgraph_branch_diff`;
- the raw response resolves the frozen refs and backend, and its comparison
  fields match the response; and
- the task's L2 rule is respected, including the codegraph uncertainty control.

Missing raw evidence, source mutation, unexpected tools, ref/backend mismatch,
model/raw mismatch, unavailable-as-unchanged, or task-oracle mismatch are
exclusions, never negative product scores.

Cold provisioning and a warm repeat are both recorded for each treatment
task. Their durations are diagnostic metadata only; they are not compared to
baseline, agent execution time, tokens, cost, solve rate, or developer time.

## Pilot and reporting

After contract tests and the repository quality gates pass, run two replicated
baseline/treatment pairs for each task, in opposite condition orders. This is
a runtime and evidence-chain pilot, not an effect-size study. Store raw stream events,
commands, tool environment, resolved image/tool versions, pre/post source
state, raw MCP responses, cold/warm snapshot records, and explicit exclusion
reasons outside Git.

Report each task/backend/condition independently. The only permitted initial
conclusions are whether the evidence chain and task-specific review decision
survived the protocol, and whether an uncertainty boundary was preserved. No
pooled score, token saving, time saving, correctness uplift, or efficiency
claim is permitted.
