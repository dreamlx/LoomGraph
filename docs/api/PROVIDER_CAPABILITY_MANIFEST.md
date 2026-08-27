# Provider capability manifest v1

This is a local, read-only declaration used before any provider discovery or
invocation. It does not install, probe, configure, or call CBM, Serena, MCP,
or an LLM.

Each capability has exactly one provider and operation. `structural_candidate`,
`live_semantic`, and `temporal_comparison` are distinct evidence kinds; no
consumer may promote one into another.

| Field | Meaning |
| --- | --- |
| `provider_id` / `provider_version` | Declared provider identity, never inferred from a model or host name. |
| `operation` | `structural_navigation`, `live_semantic`, `live_edit`, or `temporal_comparison`. |
| `availability` / `reason` | `available`, `conditional`, or `unavailable`, with a reason whenever it is not available. |
| `snapshot_scope` / `snapshot_identity` | A temporal comparison alone may use `pinned_comparison`, and must carry both refs and full resolved SHAs. |
| `index_owner` | `loomgraph`, `provider`, or `none`; a provider-owned index must not be rebuilt automatically. |
| `data_scope` | `local` or `unknown`; `unknown` cannot be silently treated as local. |
| `write_authority` | Only `live_edit` may require `user_authorization`; it is never auto-selected. |

The checked-in example fixture is
[`tests/fixtures/provider-capability-manifest-v1.json`](../../tests/fixtures/provider-capability-manifest-v1.json).
It declares codeindex, CBM, and Serena boundaries but no runtime availability.
An undeclared provider or operation returns a native `unavailable` fallback.
