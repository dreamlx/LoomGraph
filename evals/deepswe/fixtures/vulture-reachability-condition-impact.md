Pre-edit structural impact analysis only: do not edit source or propose a patch.

Before changing `vulture.utils.condition_is_always_false` and
`condition_is_always_true`, identify the three existing production source files
that carry condition evaluation through reachability analysis into Vulture's
unreachable-code reporting. Return exactly those three files. For each, give
concise relationship evidence and state whether it is graph-resolved or based
on source text.

The handoff from `Vulture.visit` to `self.reachability.visit` is a dynamic
receiver. A missing or partial graph caller list is not proof that this handoff
or another relationship does not exist.

The structured response must include `edge_trust` and the graph
`resolved_ratio`, `internal_unresolved_ratio`, and `external_unresolved_ratio`.
When graph-resolution evidence is unavailable in the current condition, set
trust availability to `unavailable` and all three ratios to `null`; never
invent graph trust values.
