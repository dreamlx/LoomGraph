# CBM discovery replay spike

This is the ADR-017 follow-up spike for the fixed stratum:

`Claude Code-first / local CBM 0.10.8 / synthetic fixture / read-only structural candidate / no model`.

It is not a CBM integration, MCP tool, automatic provider router, semantic
adapter, temporal comparison backend, performance result, or production claim.

`tests/fixtures/cbm-discovery-replay-v1.json` retains a reviewed, synthetic
response plus its canonical JSON SHA-256. The adjacent synthetic source fixture
has its own input SHA-256. `load_cbm_replay()` and `replay_cbm_capability()`
only read and validate these values. They never execute CBM, create an index,
open LoomGraph storage, or modify the replay/source files.

On a valid replay, the envelope records:

- `cbm` and the pinned `0.10.8` provider version;
- `structural_navigation` and `structural_candidate` only;
- a local `provider_index` whose owner remains `provider`;
- the synthetic input and raw-response hashes; and
- `provider_routing: not_enabled` plus `provider_owned_index: not_created_or_rebuilt`.

The adapter returns a native `unavailable` fallback for an absent provider,
version mismatch, timeout, empty or unknown capability, missing source
fingerprint, unknown schema, or replay-hash drift. It never changes an invalid
result into a semantic or temporal assertion.
