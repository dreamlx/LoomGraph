# Private field-validation protocol

**Status:** active operational protocol

**Authority:** [ADR-017](../adr/ADR-017-adaptive-code-understanding-orchestration.md)

## Purpose

LoomGraph is open source, while some useful validation happens on customer or
otherwise private repositories. This protocol keeps those facts compatible:
the method, decision rules, and synthetic checks are public; private source
and raw evidence stay outside this repository.

Field validation answers whether a narrowly declared LoomGraph capability is
useful and trustworthy in a real development context. It is not a public
benchmark, a customer case study, or evidence of a general model, token, time,
or productivity advantage.

This protocol is separate from both the public deterministic capability
fixtures and the DeepSWE agent-use cohorts. A result from one stratum never
changes the result or denominator of another.

## Evidence boundary

| Location | May contain | Must not contain |
| --- | --- | --- |
| This public repository | Protocol, generic question packs, synthetic fixtures, tool versions, reviewed aggregate claim records | Customer identities, repository names, source, patches, paths, raw graph artifacts, raw model/MCP traces, configuration, credentials, or identifying screenshots |
| Private evidence store | Authorized project registry, immutable run manifests, source snapshot identifiers, reviewer notes, raw commands, tool/model traces, artifacts, and exclusions | Automatic export to Git, issue attachments, release assets, or public dashboards |
| Manually reviewed public claim | Coarse stratum, capability result, limitation, and synthetic corroboration | Any field that can identify a customer, repository, source tree, incident, or contributor |

An opaque project identifier is private evidence-store metadata, not a public
identifier. It must not be derived from a customer or repository name.

## Study registration and execution

Each authorized project starts a distinct private study. Before a run, record
the following in the private evidence store:

- authorization scope and the allowed local operations;
- study, project, and run identifiers;
- language and coarse size/complexity band; history availability; task family;
- LoomGraph, parser/backend, host, model, provider, policy, and operating mode;
- a generic public question-pack identifier, plus the private task wording and
  reviewer acceptance plan; and
- the source snapshot identity, environment identity, and redaction owner.

Retain the raw evidence for every run together with its validity or exclusion
reason. A missing trace, source mutation, version drift, unavailable provider,
or reviewer disagreement is an explicit `inconclusive` or excluded observation;
it is never silently repaired from a later run.

The first field-validation tasks are limited to pre-edit understanding and
navigation: unfamiliar-module onboarding, technical-debt explanation,
change-impact or regression investigation, and pre-refactor symbol boundaries.
Writing source, calling production services, or changing customer configuration
is outside this protocol unless separately authorized by the project owner.

## Repeats, strata, and claims

A repeated run on one private repository is a run sequence, not an independent
project sample. Report `private_repositories` and `runs` separately whenever a
public aggregate is approved.

Do not pool, normalize, or rank results across different repositories,
languages, host runtimes, models, providers, policies, modes, or evidence
strata. In particular, field validation must not be pooled with frozen
DeepSWE/agent-use evidence or used to revive the archived v1--v9 pilot.

Field validation may establish only a bounded statement such as: a declared
capability produced (or did not produce) reviewable evidence for a named task
family under a recorded stratum. It may not establish semantic equivalence,
temporal authority for an external provider, automatic routing safety, or a
productivity claim.

## Public reporting gate

Public reporting is an explicit human decision after redaction review; no
private manifest or artifact is automatically copied into GitHub.

A public result may include:

- protocol and question-pack version;
- coarse language and size/complexity bands;
- task family, LoomGraph/backend version, and declared mode;
- `supported`, `not_supported`, or `inconclusive` capability outcomes;
- aggregate counts, limitations, and the matching public synthetic checks.

A public result must exclude the material listed in the evidence-boundary
table. Use broad bands rather than exact repository size, dates, commit IDs,
module names, or task narratives when those details could enable
re-identification.

Quantitative aggregation requires at least three independently authorized
private repositories in the same coarse stratum. Below that threshold, publish
only a qualitative boundary or no result. Even above it, report each stratum
separately and do not imply a population estimate.

The reviewer must reject publication when redaction is uncertain, the private
evidence is incomplete, the task or environment drifted, a customer owner has
not authorized the intended disclosure, or the proposed wording exceeds what
the evidence establishes. The correct public result in those cases is silence
or an explicit limitation, not a repaired success claim.

## Public templates

Use these templates without inserting private project facts:

- [Generic field-validation question pack](templates/field-validation-question-pack.md)
- [Public field-validation summary](templates/public-field-validation-summary.md)

The private evidence store may use richer operational templates, but they are
not repository artifacts and must not be linked from an issue, pull request,
release, or public result.
