# Generic field-validation question pack

This public template defines a reusable question shape. Do not add customer
names, source fragments, repository paths, commit IDs, or incident details.
The mapping to a real private task belongs only in that study's private
evidence store.

## Registration

| Field | Public value |
| --- | --- |
| Question-pack ID | `PV-<language>-<number>` |
| Protocol version | Link to the governing protocol revision |
| Task family | Onboarding, debt explanation, impact/regression investigation, or pre-refactor boundary |
| Capability under examination | A precise LoomGraph capability and trust boundary |
| Required evidence | Command/result fields or reviewer-visible evidence categories |
| Explicit non-claim | What this question cannot establish |

## Generic question

State the question without naming a private module, endpoint, customer, or
incident. For example: “For a declared cross-file payment-completion flow,
can the available structural evidence identify the responsible symbols while
preserving unresolved or partial edges?”

## Acceptance and failure rules

- Define what a reviewer must be able to verify from the retained private
  evidence.
- State the expected uncertainty behavior: `unavailable`, `partial`, or
  unresolved evidence remains visible and is never turned into a negative
  assertion.
- List validity exclusions, such as source mutation, missing raw evidence,
  environment drift, or unsupported provider capability.
- Declare the public outcome vocabulary: `supported`, `not_supported`, or
  `inconclusive`.

## Public disclosure check

Before this question pack appears in a public report, confirm it contains no
private identifiers or details that can be combined to identify the project.
