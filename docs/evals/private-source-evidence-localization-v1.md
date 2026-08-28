# Private source-evidence localization contract v1

**Contract version:** `1.0`  
**Status:** methodology contract for authorised private cohorts only

This contract defines an evidence-localization cohort under
[ADR-017](../adr/ADR-017-adaptive-code-understanding-orchestration.md) and the
[private field-validation cohort contract](private-field-validation-contract.md).
It is not a LoomGraph product interface, a public benchmark, or a claim about
correctness, efficiency, token use, cost, or productivity.

No customer source, source-bearing path, commit/ref/SHA, solution, raw trace,
or gold artifact belongs in this repository or a public report.

## 1. Unit of evaluation

One cell contains one declared source question, one source-only materialization,
one runtime/tool condition, and one independent evidence stratum. A cell must
not ask for a code change, product decision, firmware/backend conclusion, or a
claim about runtime behavior that the permitted source cannot establish.

The private registration record must contain the following fields before the
cell starts. It remains outside this repository.

| Field | Requirement |
| --- | --- |
| `contract_version` | Exactly `1.0`. |
| `cohort_id`, `cell_id` | Locally unique identifiers without a customer name. |
| `task_kind` | One of the four kinds in section 2. |
| `question` | One source-answerable question, with no embedded answer or desired implementation. |
| `allowed_source_scope` | The locally retained source-only materialization and permitted history scope. |
| `source_state` | Source and Git pre-state identity plus the check that it is unchanged after the cell. |
| `runtime_envelope` | Host, runtime/model identity, tool surface, provider/backend, policy, parser version, and budget envelope. |
| `raw_provenance` | Private locations for the prompt, raw agent output, tool responses, and reviewer record. |
| `condition` | The declared condition; it is not supplied to a condition-blind decision reviewer. |

Missing, ambiguous, or source-bearing public values make the cell invalid.

## 2. Task taxonomy

| `task_kind` | Permitted question | Required answer shape |
| --- | --- | --- |
| `entry_point` | Where does the permitted source expose or begin the declared behavior? | Cite the entry locus or label it `unavailable`. |
| `direct_handler` | Which directly evidenced handler, method, or component receives the declared input? | Cite direct support, not a likely downstream owner. |
| `direct_edge` | Does a direct source/structural relationship connect two declared loci? | Identify the observed edge and its trust boundary, or state that it is unavailable. |
| `explicit_unavailable` | Can the permitted source establish a stated fact? | State `unavailable` and name the specific evidence class required next. |

A task may state a neutral investigation context, but it must not encode a
solution, expected architecture, product preference, or result claim. A task
whose answer depends on device telemetry, backend state, dynamic dispatch,
runtime configuration, or history outside `allowed_source_scope` is only valid
when it is an `explicit_unavailable` task.

## 3. Required agent response schema

The private runner supplies the task without its condition label. The scored
response contains only the following sections:

1. **Answer boundary** — restate the source question and the permitted source
   scope; do not restate a treatment, provider, or tool result.
2. **Evidence table** — one row per material claim with `claim`, `label`,
   `source_locus`, `support`, and `limit`.
3. **Next evidence** — for every `candidate` or `unavailable` claim, name the
   minimum evidence class needed to resolve it; it must not propose a code or
   product change.
4. **Limits** — name facts excluded by the source/snapshot/runtime boundary.

The only valid evidence labels are:

| Label | Meaning |
| --- | --- |
| `confirmed` | The cited permitted source directly supports the claim, within the stated boundary. |
| `candidate` | The source suggests a locus or relation but does not establish the claim. |
| `unavailable` | The permitted source cannot establish the claim; the response names the needed next evidence class. |

The agent must not turn a `candidate` into `confirmed` by inference, and must
not treat a structural result as proof of semantic, device, backend, temporal,
or runtime behavior.

## 4. Independent reviews

Two reviews are required and are never collapsed into one score.

1. **Condition-blind decision review** scores only evidence relevance and
   uncertainty preservation in the required response schema. It cannot see a
   condition label, tool/provider name, raw tool field, or treatment-only
   artifact.
2. **Deterministic tool-evidence audit** applies only when a condition uses a
   navigation tool. It checks the private raw trace for the declared retrieval,
   workspace/snapshot identity, and trust/comparison fields. It records tool
   behavior; it awards no decision-review credit.

Reject a decision projection if it retains provider, tool, workspace, snapshot,
or trust terms outside a dedicated private tool-evidence appendix.

## 5. Four-quadrant acceptance controls

Every registered task set must contain all four controls. They validate the
evaluation method, not a product benefit.

| Quadrant | Control | Valid result | Invalid result |
| --- | --- | --- | --- |
| Positive | A direct source locus exists for the declared question. | It is cited and labelled `confirmed` with a bounded claim. | A nearby or inferred locus is represented as direct support. |
| Negative | Evidence is missing or ambiguous. | The claim is labelled `candidate` or `unavailable`. | Silence or absence of a result is reported as absence of behavior. |
| Safety | A provider candidate, unresolved edge, stale state, or incomplete parse is present. | The trust limit remains explicit. | Structural evidence is upgraded to a semantic, device, backend, or temporal fact. |
| Boundary | The answer requires evidence beyond the permitted source. | The response names the excluded boundary and next evidence class. | The response makes a runtime, firmware, persistence, ordering, retry, or backend assertion from source alone. |

## 6. Validity, exclusion, and reporting

Exclude a cell rather than score it if its source/Git state changes; the source
or evaluator leaks; runtime, parser, ref, storage, or provider identity drifts;
raw provenance is missing; the response projection is malformed; an unexpected
tool is used; the materialization is unmounted; or declared trust/comparison
fields do not match the condition.

An excluded cell is not rerun under another condition. A new run requires a
newly registered series and remains a separate stratum.

Public reporting may say only that an authorised private cohort applied this
contract and whether its own evidence chain remained valid. It must not report
customer identifiers, source-bearing details, raw artifacts, task solutions,
cell-level results, pooled rates, comparative wins, or token/time/cost/
productivity/correctness claims. It cannot justify a LoomGraph product change.

## 7. Private-runner handoff

A private runner may implement this contract entirely outside this repository:

1. create a source-only materialization and private registration record;
2. register the four task kinds and four-quadrant controls before exposure to
   an agent;
3. retain raw prompts, traces, tool responses, and reviews locally;
4. produce a condition-blind response projection and, when applicable, a
   separate private tool-evidence appendix;
5. run the two independent reviews and apply the exclusion rules; and
6. retain any conclusion as a private evidence ledger until a separately
   approved, anonymised methodology statement is warranted.

Nothing in this handoff authorises a model run, a customer-repository access,
an adapter/MCP invocation, a cross-stratum comparison, or publication.
