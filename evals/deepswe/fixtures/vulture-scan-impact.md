Pre-edit structural impact analysis only: do not edit source or propose a patch.

Before changing `vulture.core.Vulture.scan` to add persistent cache behavior,
identify its direct caller and the cross-file utility modules reached by that
caller that should be reviewed for cache invalidation. Return at most three
existing production source files. For each candidate, give concise relationship
evidence. State any graph-resolution uncertainty from the available navigation
tools; do not treat an incomplete graph as proof that no other relationship
exists.

The structured response must include `edge_trust` and the graph
`resolved_ratio`, `internal_unresolved_ratio`, and `external_unresolved_ratio`.
When graph-resolution evidence is unavailable in the current condition, set
trust availability to `unavailable` and all three ratios to `null`; never
invent graph trust values.
