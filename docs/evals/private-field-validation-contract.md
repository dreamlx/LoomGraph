# Private field-validation cohort contract

Private field validation complements public deterministic fixtures and DeepSWE
compatibility records. It does not replace either one, and it never authorizes
publishing a customer repository, raw trace, source path, commit identity,
solution, or result artifact.

The cohort's purpose is to test whether a fixed agent runtime can preserve an
evidence boundary for an authorised private repository. A valid run is not a
claim that LoomGraph improves correctness, efficiency, token use, cost, or
developer productivity.

## Common record and isolation rules

Register the following before a cell starts:

- repository stratum, language/complexity profile, task kind, and allowed
  history scope;
- host, exact runtime/model identity, tool surface, provider/backend, policy,
  parser version, and budget envelope; and
- source-only materialization identity, source/Git pre-state, and the private
  location that retains raw trace and tool responses.

Each repository, language, task kind, host, runtime, model, provider/backend,
policy, condition, and evidence mode is a separate stratum. Do not pool a
private stratum with DeepSWE, another private repository, another runtime, or a
previous cohort.

Raw source and raw traces stay outside Git. A public report may state only an
anonymised, human-reviewed methodological conclusion; it must not reveal a
customer identifier, source-bearing path, ref, SHA, solution, or trace excerpt.

## A. Source-evidence localization cohort

This cohort asks a narrow question: can the agent locate relevant source or
structural evidence for a declared investigation?

The task must ask for a source-supported evidence table with claims labelled
`confirmed`, `candidate`, or `unavailable`. It may ask for the next review
locus, but must not ask the agent to choose a product policy or invent a code
change. The reviewer scores evidence relevance and uncertainty preservation,
not a proposed design.

Treatment-only structural evidence is audited independently from the decision
answer. A successful retrieval must retain its observed workspace/snapshot and
trust fields. The audit cannot award decision-score points merely because a
tool was invoked.

### Four-quadrant controls

| Quadrant | Required control |
| --- | --- |
| Positive | The cited locus directly supports the declared source question. |
| Negative | Missing or ambiguous evidence is reported as `candidate` or `unavailable`, not as absence of behavior. |
| Safety | A provider candidate, unresolved edge, or stale snapshot is never upgraded to a semantic, device, or backend fact. |
| Boundary | The answer names the source/snapshot/provider boundary and what evidence outside the source would be needed. |

## B. Constraint-boundary decision cohort

This cohort asks a different question: given product invariants already stated
in the task, can the agent choose a smallest responsibility boundary while
separating those invariants from facts established by source?

The task must state the required behavior, rejected alternatives, and explicit
device/backend/runtime unknowns. A reviewer must receive those invariants with
the projected decision answer; otherwise it can incorrectly score a requirement
as an unsupported source claim.

The answer must include a four-quadrant test plan. The rubric records
unsupported assertions separately: a source-accurate locus does not excuse a
backend, firmware, dynamic-dispatch, persistence, ordering, or retry claim that
the available evidence cannot establish.

### Condition-blind review and evidence audit

If treatment adds a navigation tool, the final answer must place every
treatment-only field in a dedicated tool-evidence appendix. Before decision
scoring, remove that entire appendix and reject a projection if provider, tool,
workspace, or trust terms remain elsewhere. Keep the following checks separate:

1. **Decision projection review** — sees task invariants, the rubric, and no
   condition label or treatment-only evidence.
2. **Evidence audit** — verifies the raw treatment trace contains the declared
   successful retrieval and required trust/comparison fields.

Neither review may substitute for the other. A ceiling effect, a valid
retrieval, or the absence of an unsupported assertion is not product-benefit
evidence.

## Validity and stop rules

Exclude, rather than score negatively, any cell with source/Git mutation,
source or evaluator leak, runtime/parser/ref/storage drift, missing raw
evidence, malformed projection, unexpected tool, unmounted artifact, or a
trust/comparison field that does not match the declared mode.

Do not rerun an invalid cell under another condition without registering a new
series. A pilot only establishes whether its own evidence chain and review
contract survived; further replication, a new repository, or any wider product
claim requires separate approval.
