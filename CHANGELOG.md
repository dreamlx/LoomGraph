# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add `loomgraph orient`, a read-only Claude Code first-step navigation plan
  that reports native, conditional light, or temporal-review guidance without
  creating an index or snapshot (#284).

### Changed

- Close the v1 structural capability benchmark protocol and define the separate
  branch-diff agent-use entry boundary in ADR-016.
- Add the proposed, independently scoped branch-diff agent-use v2 task design.

## [0.22.0] - 2026-08-23

### Added — resolved_ratio split into internal/external unresolved (#208)
- `compute_resolution_breakdown()` decomposes edges into three ratios over
  the same denominator: `resolved_ratio` (join-based, unchanged) +
  `internal_unresolved_ratio` (codeindex `ambiguous` qualifier — actionable
  DI / dynamic-dispatch defect where the parser saw in-repo candidates but
  couldn't disambiguate) + `external_unresolved_ratio` (codeindex
  `unresolved` qualifier — expected external / stdlib calls, plus
  codeindex-blind internal edges that are indistinguishable from external at
  this layer). All three are persisted as workspace meta on every ingest
  path (cold `index`, incremental `update`, `import-export`). `topology`
  and `impact` surface the two new keys alongside `resolved_ratio`.
- **Additive only — no risk-band migration.** The #231 factory / DI blind
  spot (receiver type statically unknowable, GH #127) lives in the
  `unresolved` qualifier bucket; codeindex's qualifier cannot separate it
  from genuine external calls, so migrating the `impact` risk band from
  `resolved_ratio` to `internal_unresolved_ratio` (ambiguous-only) would
  reopen the false-`isolated` label #231 just closed. The split is a
  read-side diagnostic; the band still reads `resolved_ratio`. A clean
  band migration would need codeindex to flag unresolved edges with an
  in-repo target hint — upstream, not loomgraph's layer.

### Changed — bump codeindex pin to `>=0.40.0` (codeindex #187, #230 engine-side fix)
- `ai-codeindex>=0.35.0` → `>=0.40.0`. codeindex #187 extends the GH #185
  factory-return-type binding to descend to a subclass impl when the factory
  names an abstract base (`create_graph_store() -> GraphStore(ABC)`) whose
  `@abstractmethod` has no entity (parser skips abstract methods). Exactly
  one in-workspace subclass carrying the method resolves to its impl; two or
  more stays unresolved (ambiguous dynamic dispatch). This is the engine-side
  fix for #230: self-dogfood now resolves 8/33 `store.*` CALLS edges that
  were previously orphans, and `loomgraph graph insert_custom_kg` returns
  `1` caller (`_async_import_export`) instead of `0`. The L0 dishonest-label
  fix below stays — it guards the 25/33 edges still unresolved (function-
  parameter receivers / tuple-unpacking, a deeper cross-scope gap codeindex
  does not yet cover).

### Fixed — impact `low`/`isolated` risk label is dishonest on a sparse graph (#225, #230)
- `RiskAssessor` now refuses the `"low: isolated change"` label when the
  graph is sparse: a `resolved_ratio` in the 0.1–0.5 band with zero
  discovered callers moves to `medium`, not `low`. At that ratio most CALLS
  edges are unresolved and an empty traversal often reflects a factory / DI
  resolution blind spot (the receiver type is statically unknowable to the
  AST — codeindex GH #127), not true isolation. Self-dogfood on this repo:
  `impact --file src/loomgraph/storage/sqlite_store.py` reported
  `low / "no callers found, isolated change"` at `resolved_ratio 0.1989`,
  though `SqliteGraphStore` has ~20 factory-routed call sites. The reason
  string now names the blind spot and points to grep for verification.
  Below 0.1 (extreme-blind) stays `unknown`; above 0.5 (dense) keeps the
  trustworthy `low / isolated` label. Engine-side fix (codeindex return-type
  binding) tracked separately.

### Fixed — import-export stops spamming unknown-kind warnings for REFERENCES edges (#227)
- `export_reader.VALID_EDGE_KINDS` now includes `REFERENCES` (codeindex GH
  #128, Pass 4 import-ref + Pass 5 type-ref). REFERENCES edges were already
  stored and already queryable via `graph --relation-type REFERENCES`, but
  the import gate lagged, emitting one `unknown kind 'REFERENCES'` schema
  warning per edge (638 lines on the codeindex repo's own artifact). The
  kind runs for every language with type annotations — not TS-only — 627/637
  REFERENCES edges on codeindex's own repo come from `.py` type annotations.

## [0.21.1] - 2026-08-19

### Changed — distinguish guided retrieval from setup-only evaluation use (#209)
- DeepSWE orientation runs are labelled `voluntary` or `assisted`; assisted
  treatment requires and reports one structural retrieval separately from
  availability, setup indexing, or target quality. Backend-aware guidance now
  tells codegraph treatment to query its setup-ready graph instead of indexing
  again, while codeindex may index once before retrieval.

### Fixed — copyable missing-grammar remediation (#210)
- Parser-missing warnings now retain codeindex's original diagnostic and add
  one deduplicated LoomGraph install command plus the required `languages:`
  configuration step. Zero-entity failures use the same exact known-language
  command; unknown languages remain explicit rather than guessing a package.

### Added — Evaluation v1 orientation pilot harness (#206)
- Added a reproducible DeepSWE/Pier orientation protocol, frozen target
  manifest, raw-packet schema, and separate codeindex/codegraph setup gates.
  It records pre-edit candidate positioning, source-clean compliance, and
  observed LoomGraph invocation/retrieval. Results are deliberately reported
  per task/stratum; this is capability-and-use evidence, not a task solve-rate
  claim.

## [0.21.0] - 2026-08-18

### Changed — explicit L2 content-comparison contract (#201)
- `branch-diff` now returns one versioned `content_comparison` object instead
  of a top-level `content_changed` list and `summary` counters. Its
  `status` is `available`, `partial`, or `unavailable`; only available/partial
  comparisons expose a `changed` list. `unavailable` returns `changed: null`,
  so an empty list can never masquerade as proof that bodies did not change.
- Comparison is same-backend-only. codeindex graph-export schema v1 uses its
  per-symbol hash; legacy/missing hashes yield `partial`. codegraph and
  mixed-backend snapshots report why content comparison is unavailable while
  retaining the L0/L1 structural diff.
- `compare` remains structural-only and makes no L2 source-content claim.

### Added — MCP `loomgraph_branch_diff` composite (#191)
- Exposes the branch-diff provisioning + directional analyzer as one MCP
  call with the same nested `data` shape as the CLI.
- First calls are transparently long-running cold snapshots; unchanged refs
  reuse their workspaces and moved refs rebuild them. The optional backend
  matches the CLI (`codeindex` by default, or `codegraph`) and returns
  structured `BRANCH_DIFF_FAILED` envelopes.

### Added — `loomgraph index --at-ref <ref>` historical snapshot command (#190)
- Reuses branch-diff's detached-worktree + cold-index provisioning kernel to
  materialize a tag/branch/commit as an isolated, queryable workspace.
- `REPO_PATH` now defaults to the current directory for this form; `-w` still
  explicitly selects the destination workspace. The mode is intentionally
  codeindex-only and always cold (`--no-clear` is rejected); use
  `branch-diff --backend codegraph` for historical codegraph snapshots.

### Added — `loomgraph branch-diff --backend codegraph` (#189)
- The branch-diff provisioning kernel now supports the installed npm
  `codegraph` CLI in addition to the default `codeindex` backend. Each
  detached ref worktree is initialized (or synced when it already contains a
  codegraph database) before loomgraph snapshots `.codegraph/codegraph.db`.
- Provisioned caches record their extraction backend, so a codeindex snapshot
  is never reused as codegraph (or vice versa). See #201 for the explicit L2
  result contract used when codegraph content cannot be compared.
- The explicit backend has a 10,000 tracked-file default cap and 30-minute
  per-worktree timeout. `LOOMGRAPH_CODEGRAPH_MAX_FILES` overrides the file cap;
  missing/failed CLI and cost-gate failures return `CODEGRAPH_FAILED`.

## [0.20.0] - 2026-08-18

### Fixed — MCP `debt_audit` / `sync_advice` debt dimensions silently dead since v0.15
- All three `_async_debt` call sites in `mcp/tools/debt_audit.py` /
  `sync_advice.py` omitted the `scope` positional argument (#61 added it in
  v0.15.0) — every call raised `TypeError` *before* `_safe` could even wrap
  it, so both composites returned their debt dimension as an error envelope
  and the advice summary silently degraded to compare-only. Invisible to
  tests because every composite test mocks `_async_debt` wholesale. Surfaced
  by the mypy `call-arg` backlog cleanup (117 → 0); regression test now
  invokes the real binding (no mock).
- `cli/_analysis.py` git-metrics error handler referenced the nonexistent
  `ErrorCode.OPERATION_FAILED` (renamed away in 0.9.0-era cleanup, this call
  site missed) and passed `output_error` args positionally in the wrong
  order — any git-metrics failure raised `AttributeError` inside the except
  branch, masking the original error. Now `STORAGE_ERROR` + keyword args,
  regression-tested.

### Changed — mypy backlog cleared (117 → 0) and gated in CI
- `core/git_parser.py` (68 errors): the heterogeneous per-file aggregation
  dict is now two `TypedDict`s (`_CommitData` / `_FileAcc`) — runtime shape
  unchanged.
- Mechanical: bare `dict`/`Counter` parameterized (18), cross-module
  re-export imports redirected to defining modules (10), `Any`-returning
  expressions wrapped (7), optional `[embed]` imports `type: ignore` (3),
  annotation-only mismatches (4). `types-PyYAML` restored to the venv via
  `uv sync --extra dev` (6).
- `mypy src/` now runs in test.yml + release.yml (floors bumped to the
  verified 1.19) — the backlog accumulated precisely because the gate was
  local-only, and it hid the two real bugs above.

### Added — `loomgraph branch-diff <A>..<B>`: structural diff between two refs (EPIC-016 #185)
- One command answers "what structurally changed between two git refs":
  auto-provisions snapshot workspaces for missing refs (`git worktree add
  --detach` temp dir + cold index — the workspace mechanism addressed by ref,
  no new storage; ADR-015's event-sourcing rejection stands), then runs the
  new directional `BranchDiffAnalyzer`.
- **Diff output**: entity + edge added/removed (edges keyed `(src, tgt, kind)`
  on the resolvable-graph口径 — #149/#154, unresolved edges counted only),
  **broken_chains** (base edge gone while its src entity survives — "caller
  still there, callee gone"), **new_chains** (head edge whose src existed in
  base — surviving function started calling something new), **content_changed**
  (L2: shared entities whose codeindex `content_hash` differs — graph shape
  same, body changed; `content_hash_missing` counts non-comparable sides),
  **module_delta** (added/removed edges aggregated by src module,
  `extract_module` depth 2). Lists capped at 50 / modules at 20 (module
  constants, zero config knobs); summary always carries uncapped `*_total`.
- **Provisioning semantics** (#185 decision table): provisioned workspaces
  are meta-tagged (`provisioned_by/ref/sha`) disposable caches — same ref +
  same sha → `reused` (skip indexing; reruns are cheap), branch moved →
  `rebuilt` in place (a stale-ref diff is silently-wrong output), non-tagged
  workspaces (the user's own, or `feature/x`-vs-`feature-x` sanitization
  collisions) are never clobbered → sha-suffixed fallback name. Both refs are
  always provisioned — the current checkout's workspace (which may contain
  uncommitted `refresh` edits) never leaks into a ref diff.
- `CompareAnalyzer` and its consumers (`evolution_track` / `sync_advice`) are
  untouched — directionality lives in the new analyzer.
- New git primitives in `core/git.py`: `resolve_ref` (`^{commit}` peels
  annotated tags), `worktree_add --detach` (detach is load-bearing: the base
  ref is often the checked-out branch), `worktree_remove --force`. Zero new
  ErrorCodes. Follow-ups tracked in #185: `index --at-ref` and MCP composite
  (both now landed; codegraph provisioning is #189).

### Fixed — CI workflow's last bare `codeindex` PATH lookup (#183)
- `.github/workflows/incremental-update.yml` invoked `codeindex affected` via
  PATH — the #76 PATH-bypass class, the one remaining bare invocation after
  the product code was pinned (`graph_export_ingest` / impact extractor /
  `check_codeindex` / the `loomgraph codeindex` passthrough all use
  `sys.executable -m codeindex.cli`). A runner image shipping a codeindex
  ahead of the venv install would compute the changed-file set under a
  different version's semantics than the one loomgraph tests against. Now
  `python -m codeindex.cli affected --json --since ...` (flags contract
  verified against the installed version).
- New guard test `tests/unit/test_ci_workflows.py` scans workflow `run:`
  command lines (literal blocks tracked by indent + single-line forms; step
  names/comments exempt) and fails on any bare `codeindex` — same
  regression-guard pattern as the #65 stale-package-name test.

### Added — machine-readable `partial` flag on write-path success payloads (#184)
- Decision (option 2, revised): exit code stays 0 — a graph missing 1 of 5
  languages is still better than no graph, and the #93/#142 fail-loud boundary
  deliberately sits at `entity_count == 0`. But `index` / `update` / MCP
  `refresh` success payloads now carry `partial: true|false` — true iff a
  partial-graph-class warning fired (parser grammar missing, or the #161
  language fingerprint), distinguishing "graph is missing symbols" from the
  advisory warnings (resolved_ratio hint, test pollution) that also populate
  `warning`. Agents check one boolean instead of substring-matching `warning`;
  a `warnings.silence` pattern also clears `partial` (silencing = the user
  said "I know").
- **Fixed en route — MCP `refresh` silently dropped partial-graph warnings.**
  `_async_refresh` fed warnings to the 0-entity gate and discarded them on any
  export with `entity_count > 0` — on the primary agent surface (ADR-014's
  whole purpose) a partial export returned `success: true` with zero signal,
  not even a `warning` field. The refresh result now carries `warning`
  (joined string, same shape as the CLI payloads) + `partial`. The issue's
  premise ("agents discard stderr, so CLI exit 0 is operationally silent")
  was in fact backwards: the CLI payloads already carried `warning` in stdout
  JSON since #108; the MCP path was the real silent one.
- Documented in `docs/guides/index-output.md` (field table). codegraph
  refresh keeps no flag — `run_codegraph_export` structurally cannot emit
  partial-class warnings (resolved-edges-only, no `.codeindex.yaml` gate).

### Tests
- Updated `update` command fixtures to cover the #165 diff short-circuit helper
  separately from the incremental changed-files helper.

## [0.19.2] - 2026-08-17

### Fixed — `update` silently skipped unstaged source edits (#175)
- The skip gate diffed `HEAD~1..working-tree` but the ingest path diffed
  `HEAD~1..HEAD` — a post-commit-hook run with unstaged edits in the
  working tree passed the "no code changes" short-circuit while the ingest
  leg never saw those files. `get_changed_files` now diffs to the working
  tree by default on both legs; an explicit `until` ref still selects the
  committed-range semantics. Verified live on lh-enterprise:develop.

### Fixed — `workspace=None` no longer creates a literal `{workspace}.db` (#176)
- `create_graph_store(workspace=None)` left the `{workspace}` placeholder
  un-interpolated and opened a real file at
  `~/.loomgraph/{workspace}.db` (a junk file on disk that also failed on
  case-sensitive filesystems). `None` is now an in-memory discovery handle
  (`db_path=":memory:"`) used by `workspace list` / `similar`; the returned
  object is still a `SqliteGraphStore`, interface-compatible. No caller
  depended on the old literal-file behavior (verified call-chain).

### Fixed — parser-missing warnings dedup per language, not globally (#178)
- The "Parser library not installed for <lang>" dedup kept only the FIRST
  missing language ever seen — a repo missing 3 tree-sitter grammars
  reported one, hiding the rest. Now dedups per language (3 missing → 3
  lines); a line that can't be parsed for its language falls back to the
  whole line as key (at worst loses dedup, never the diagnostic — #118's
  fix-hint semantics preserved).

### Added — contract tests pinning the codeindex CLI output shapes (#179)
- `tests/contract/` invokes the pinned venv codeindex (never PATH) and pins
  the two shapes loomgraph's correctness depends on: `parse` returns bare
  symbol names (the #173 fix's qualification logic prepends module paths
  itself) and `graph-export` emits module-qualified entity ids + the
  known edge-kind set. This is the drift guard for the #173 bug class —
  RED on any breaking change forces a coordinated update instead of a
  silent field drift. Collected by CI in both the PR gate (test.yml) and
  the release gate (release.yml) — a path-filtered `pytest tests/unit/`
  would otherwise never run them (codex review finding, fixed in 5bd6357).

## [0.19.1] - 2026-08-17

### Fixed — `loomgraph impact` direct/indirect callers always empty (#173)
- `_find_callers` now qualifies the changed symbol's bare parse name with its
  file's module path before the exact-equality match against the graph's
  module-qualified ids. `codeindex parse` returns `func` / `Class.method`
  (no module prefix); the graph stores `pkg.mod.func` /
  `pkg.mod.Class.method` — the bare name never matched, so
  `direct_callers`/`indirect_callers` were always `[]` even for symbols
  with provable callers. The fix uses the existing `_file_to_module`
  helper (`file` → `pkg.mod`) + `"." + name`, which matches graph-export's
  id construction exactly (verified on top-level funcs and class methods).
  Option 1 from the issue — preserves #66's same-name collision fix (no
  loosened `endswith` match). The indirect path is unaffected: it feeds
  back graph-sourced (already-qualified) names; `_qualify_symbol_name`
  guards against double-prefixing. Dogfood (loomgraph:main): `impact
  ecc0e81` went from 0/0 callers to 21 direct / 12 indirect.

### Fixed — `loomgraph status` reports the codeindex loomgraph actually invokes
- `check_codeindex` now probes via `sys.executable -m codeindex.cli --version`
  — the SAME pinned-env path `index` / `update` / `loomgraph codeindex` run
  through. The old `shutil.which("codeindex")` PATH lookup could report a
  different or stale install (e.g. pipx `0.37.0`) than the one `index` runs
  (the venv-pinned dep), so `status` would lie about the version/path
  loomgraph depends on — the reverse-direction sibling of the #76
  PATH-bypass class. Surfaced by self-dogfood on the loomgraph repo itself.

### Fixed — `debt --with-git` git dimension: serialize `source` field + graduate the score (#174)
- **`_issue_to_dict` now serializes `source`** (static | topology | git).
  `DebtIssue.source` is a first-class model field — the #59 double-count
  guard keys off it — but it was dropped at serialization, making the
  entire git/topology issue set invisible downstream (MCP `debt_audit`,
  agents). On loomgraph's own repo, 333 git-sourced issues existed in
  memory but read as 0 in the JSON.
- **`_analyze_git_issues` penalty is now graduated, not a cliff.** The old
  unbounded `+15 per critical hotspot, +8 per single-owner file`
  saturated at 7 hotspots → score 0, so every repo with a handful of
  hotspots scored indistinguishably from a catastrophically fragile one.
  Per-category penalties are now capped (hotspot cap 40, silo cap 40,
  matching the `topology._compute_score` precedent), so more signal =
  strictly lower score, but the dimension never collapses to 0 on first
  touch. Issues are still emitted for every signal — only the score is
  capped. On loomgraph's own repo: git score 0 → 20, total F → D.
- Surfaced by self-dogfood (same session as the status fix).

## [0.19.0] - 2026-08-17

### Added — pluggable extraction backend: codegraph (#152)
- **`loomgraph index --backend codegraph`** — a second extraction backend
  alongside codeindex. codegraph (`@colbymchenry/codegraph`, TS+Rust, 33
  languages) keeps its own SQLite graph at `.codegraph/codegraph.db`; the
  adapter snapshots it (SQLite `backup()` API, `query_only=ON` — never mutates
  the user's db, honors WAL) and maps it to the SAME `(entities, relations)`
  4-tuple the codeindex path produces, so the shared `embed → inject` pipeline
  is reused unchanged. Per-workspace single source (parallel, not serial —
  codeindex navigation is a side path that never enters the graph). cbm stays
  a candidate-#3 stub.
- **Why**: #168 spike measured codegraph at 100% edge joinability on 3
  fixtures where codeindex hit 5.3% / 3.2% / 20.9% (Java DI / TS `@` alias /
  Python cross-file). The #167 pnpm-mono cross-package CALLS gap (1.76% on
  codeindex) resolves to ~263 edges on the codegraph backend.
- **Schema fingerprint (fail-loud, #142)**: required tables/columns are a
  subset check (codegraph migrations v1–v9 are append-only); a
  semantics-bump without a schema change is caught by
  `indexed_with_extraction_version <= 24`. Mismatch → `CodegraphSchemaError`
  → exit 1, never a silent mis-map.
- **Name disambiguation (BLOCKER)**: codegraph `qualified_name` is not
  unique (354 shared names on the BlueHawkLock fixture, `styles`×33) and
  `entity_name` is the store PK, so unqualified names would silently merge
  into phantom hubs. Non-unique names get `file_path::qualified_name`; the
  93% unique majority keeps clean `::` names. Edges use the same map.
- **file nodes as first-class entities**: 64% of codegraph calls edges
  originate at a file node (measured), so dropping them guts the graph.
  topology now excludes `entity_type ∈ {module, file}` from orphan + god
  detection (4 spots: server-side orphan/gods + client fallback) — a file's
  ~19 avg out-degree would flag every file as a god function otherwise.
- **`::` name resolution**: `graph <simple-name>` and the #105 class-fold
  now try both `.` (codeindex) and `::` (codegraph) separators, so the #98
  feature isn't dead for the whole backend. The orphan whitelist split
  matches. Backend-neutral (existing codeindex workspaces unaffected).
- **New edge kind `REFERENCES`**: codegraph `references`/`decorates` edges
  map to it (codeindex had no equivalent). `VALID_EDGE_KINDS` and
  `graph --relation-type` extended.
- **`update --backend codegraph`**: codegraph has no per-symbol content_hash
  → no incremental. Instead a content fingerprint (node/edge counts + max
  `updated_at`) is recorded in workspace meta; an unchanged snapshot returns
  `mode: codegraph_noop` (loomgraph never runs `codegraph sync` itself — a
  noop carries a `run codegraph sync` hint rather than silently re-ingesting
  identical data). Changed → `clear=True` rebuild. A bare `update` (no
  `--backend`) reads the workspace's `extraction_backend` meta and routes to
  the same backend — a bare update must not swap a codegraph graph for a
  codeindex one.
- **MCP `refresh` routing**: a codegraph workspace's `force_full` re-snapshots
  + clear-rebuilds; incremental refresh fails loud (no content_hash →
  `ingest_incremental` would GC codegraph symbols).
- **Adaptive MCP surface**: on a codegraph-backed workspace `loomgraph_find`
  + `loomgraph_graph` are unlisted (they overlap `codegraph_explore`).
  Detection reads the workspace's `extraction_backend` meta — NOT cwd/`which
  codegraph` (unreliable: serve cwd ≠ queried workspace; installed-for-
  another-project would hide tools on every codeindex workspace). Unlisted ≠
  removed (still callable); `LOOMGRAPH_MCP_TOOLS=all` forces the full list.
  Tool descriptions carry the division-of-labor wording.
- **`status` backend recommendation** (non-enforcing): reuses the #161
  language fingerprint — TS/Java/multi-language/mobile repos get a
  `codegraph` recommendation; Python/PHP stay codeindex.
- **Provenance**: codegraph's db carries no git sha, so loomgraph records
  `codegraph_head` = `git rev-parse HEAD` at snapshot time + the fingerprint
  + codegraph versions into workspace meta.
- **Documented residuals (accept, not fix)**: constant/interface entities
  enter hub candidates (calls file→constant measured 892); `find` short
  queries match file-path names; cross-backend `compare` matches ~0; a
  disambiguated name can flip across commits when a duplicate appears/
  disappears (`clear=True` makes this moot for correctness).

### Added — index output: language-fingerprint warning + reading guide (#161, #162)
- **Language fingerprint warning** (#161): a non-Python repo (TS/Java/Swift…)
  indexed without `.codeindex.yaml` defaults codeindex to
  `languages=["python"]` and silently captures only stray `.py files (from
  Pods/node_modules) — entity_count > 0 evades the 0-entity gate and the
  output reads as success with 0% coverage of the repo's actual language
  (HEXFORCE-RN: 7 entities on an all-TS repo; correct config → 667). `index`
  and `update` now fingerprint the repo's source files (excluding vendored
  dirs) and warn when the dominant language isn't in the effective
  `languages` set: `language fingerprint: detected N typescript source files,
  none indexed — add 'typescript' to languages in .codeindex.yaml`. A
  presentation-layer hint only — exit code unchanged, filterable via
  `warnings.silence` like codeindex's own warnings.
- **resolved_ratio reading guide** (#162): `index` now appends a warning at
  `resolved_ratio < 0.1` (the known-blind-spot tier: PetClinic Java DI 4.9%,
  HEXFORCE-RN TS aliases 6.1%) explaining that topology orphan counts are
  not dead-code evidence at that level. No hint at ~0.2 — that's a normal
  Python repo (loomgraph self: 0.19; third-party calls never resolve).
- **New doc `docs/guides/index-output.md`** (#162): field-by-field reading
  guide answering the recurring "why don't these numbers add up" questions —
  `relations_created` (edge events) vs `store_stats.relation_count`
  (deduped by `(src_id, tgt_id, keywords)`), `cross+intra ≠ relation_count`
  (module stats only count edges whose both endpoints resolve to entities),
  and the resolved_ratio tier table.
- **click 8.3 compatibility** (found via `uv sync` against the lockfile):
  the 0.18.1 `-q` usage hint matched the quoted option format `'-q'` that
  click 8.4 prints; 8.3.1 prints `No such option: -q` (bare, colon), so on
  the lockfile-pinned 8.3.1 the hint silently never fired. CI installs from
  the dependency spec (resolves 8.4) which masked it. The match now covers
  both formats.
- dev extras: `types-PyYAML` added so local `mypy src/` doesn't report
  missing stubs for the three existing `import yaml` sites (CI runs ruff
  only; mypy is a local-dev gate).

## [0.18.1] - 2026-08-17

### Fixed — first external-project dogfood batch (HEXFORCE-RN / BlueHawkLock)
- `hooks install -w <name>` bakes the workspace into the post-commit hook so
  it updates the db the user actually indexed; previously the hook's bare
  `loomgraph update` auto-detected `<repo>:<branch>` — a different workspace
  than a fixed-name `index -w` db (#160).
- `hooks install` on a husky v9 repo (core.hooksPath=`.husky/_`) writes
  `.husky/post-commit` instead of a shim inside the regenerable `_` dir,
  where npm prepare silently deleted it and overwriting broke husky's chain
  (#164). The hook's sync path now also reports the real `update` exit code
  (`${PIPESTATUS[0]}` — `$?` was tee's).
- `update` short-circuits before the whole-tree export when the git diff
  touches no parsable source file — docs/config/shell-only commits no longer
  pay the multi-second export via the post-commit hook (#165). A diff that
  touches a graph-affecting config (`.codeindex.yaml` / `.loomgraph.yaml`,
  modified OR deleted — the gate reads `--diff-filter=ACMRD`) instead routes
  to a clear rebuild (`mode: config_rebuild`): a `languages:` change reshapes
  the whole graph, and the incremental path would have ingested nothing
  (a config file is no entity's source_id).
- `-q` placed after the subcommand (`loomgraph find x -q`) now gets a usage
  hint pointing at the global-flag form instead of a bare
  `No such option '-q'` (#163, #166).
- Recurring export warnings (e.g. the partial-graph language hint) can be
  silenced per substring via `warnings.silence` in `.loomgraph.yaml` (#166).

## [0.18.0] - 2026-08-16

### Added — built-in zero-config embedding: CodeRankEmbed-137M int8 ONNX (#158)
- New `loomgraph[embed]` extra (onnxruntime + tokenizers, no torch) powers a
  `builtin` embedding provider: local CPU inference, 768-d (existing vec0
  dimension — no migration), MIT model, ~139 MB downloaded on first use.
- New default provider `auto` resolves once per workspace and persists the
  choice (explicit config > ollama probe > builtin); embedding spaces are
  provider-specific and never silently mix. `LOOMGRAPH_EMBED_MODEL_URL`
  overrides the model source (default chain: GitHub release asset →
  ModelScope → HuggingFace, sha256-pinned).
- Model selection note: HF `nomic-embed-code` is a 7B Qwen2.5-Coder model —
  unusable on CPU; CodeRankEmbed-137M is the small sibling (CoRNStack).
- Fixes found during real-model bring-up: the community ONNX export is NOT
  pre-normalized (measured norm ~24.7) — client L2-normalizes; semantic
  search score now reports cosine similarity (vec0 L2 distance converted),
  which stops lower-cos models from flooring every score at 0.000.

### Fixed — codex release review (NO-SHIP → SHIP): 4 blockers + C2 batch
- auto-provider coverage: import-export / embed-backfill now resolve
  sticky like index/search; workspaces with vectors but no recorded
  provider (pre-v0.18) refuse auto-resolution instead of guessing the
  space (EmbeddingSpaceUnknownError with re-index remedy)
- resolved_ratio recomputed on incremental update and import-export
  (was cold-index only — the daily `update` path served stale trust data)
- deterministic builtin errors (missing [embed] extra, download failures,
  sha mismatch, unknown space) fail the index instead of being swallowed
  into a green zero-vector result
- debt-report-v1 schema: maintainability nullable (matches #154); fixed
  pre-existing drift found by validating a real report (metrics/location
  optionality, open entity_type/category sets)
- scoped topology: client fallback now joins edges against the whole
  graph like the server SQL (in-scope entities reachable only via
  out-of-scope callers are connected, not orphaned)
- model cache: tokenizer sha256-pinned; cached ONNX re-verified on load;
  per-pid tmp files (concurrent-download safe)
- test-pollution markers cover Python conventions (tests/, test_*.py);
  index output carries the test-pollution warning

### Added — usage frictions from #153 audit (proposals 3/4/5, #156)
- `import-export` / `index` summaries carry `test_entity_ratio` /
  `test_relation_ratio`; above 50% test-file entities a warning explains
  that mock-call edges rarely resolve and skew topology/debt readings
  (a customer NestJS monorepo measured 77% of edges from test files).
- `git-metrics` accepts `--repo/-r` as a named alternative to the PATH
  positional (flag-style mutual recognition with the other commands).
- Single-author repositories (author strings case-folded) downgrade every
  bus-factor entry to `informational` and emit a summary note instead of
  counting hundreds of trivial `critical` files. Known limitation: distinct
  name strings for one human (e.g. `dreamlx` vs `DreamLinx`) need
  email-level unification, out of scope.

### Added — trust-calculus propagation: resolution quality surfaces in analytics (#154, from #153 audit)
- Ingest persists a join-based `resolved_ratio` (share of stored edges whose
  both endpoints join entities) into workspace metadata; `index` /
  `import-export` outputs carry it.
- `topology` emits a `resolution` block (`resolved_ratio` + human-readable
  `caveat` when below 50%) so orphan counts and `topology_score` are not read
  as dead-code evidence on low-resolution graphs (Java DI / TS path-alias
  blind spots: Spring PetClinic resolves 4.9%).
- Orphans are now classified `truly_isolated` (no relation rows — real
  dead-code signal, P1) vs `neighbors_unresolved` (edges exist but none
  resolved — resolution blind spot, P2 with low confidence).
- `debt`: `maintainability` is `null` when no codeindex data flowed in, and
  its weight redistributes over the present dimensions — vacuous
  perfect-100 scores removed (#153 提案 2). Total scores shift accordingly
  (e.g. quality 100 / topology 75: 92 → 89).

### Fixed — topology orphan/hub/god metrics now computed on the resolvable graph (#149)
- `get_orphan_entities` / `get_degree_distribution` (storage layer) and the
  client-side degree build in `TopologyAnalyzer` previously counted any stored
  relation row as connectivity, even when the far endpoint never joined an
  entity (dangling edge). An entity could be reported non-orphan while
  `loomgraph graph` returned empty callers/callees for it.
- Now only fully-resolvable edges (both endpoints in the entity set) count —
  same semantics as `graph` traversal. On Spring PetClinic the reported orphan
  rate moves 40.6%→79.9%, matching the effective-orphan rate measured in the
  #147 horizontal eval; hub/god counts drop as dangling edges no longer
  inflate degrees (loomgraph self: hubs 15→7, god functions 44→3).

## [0.17.1] - 2026-08-12

### Changed — codeindex lower bound 0.34.0 → 0.35.0
- `ai-codeindex>=0.35.0` to pick up codeindex#154 (de-double Java entity ids
  + edge srcs): Java graph CALLS orphan rate 60%→41% (Spring PetClinic).
  loomgraph needs no code change — #154 is in codeindex's graph-export output
  layer, which loomgraph consumes as NDJSON.

## [0.17.0] - 2026-08-03

### Fixed — MCP server adapted to mcp 2.0 API; `mcp<2` pin lifted (#144)
- mcp 2.0.0 dropped with breaking API changes; `mcp>=1.0` (no upper bound)
  resolved to 2.0 in CI and broke the server (PR #143 pinned `<2` as a
  stopgap). Adapted the low-level `Server` to the 2.0 API and lifted the pin
  to `mcp>=2.0`. v1.x is in maintenance mode (security fixes only).
- `build_server()`: `@server.list_tools()`/`@server.call_tool()` decorators →
  `Server(..., on_list_tools=, on_call_tool=)` constructor params.
- `list_tools` returns `ListToolsResult` (not `list[Tool]`); `call_tool` takes
  `(ctx, params)` reading `params.name`/`params.arguments` and returns
  `CallToolResult(content=...)` (not bare `list[TextContent]`).
- `Tool.input_schema` is the v2 field name (alias `inputSchema=` still accepted
  as a constructor kwarg via pydantic's `populate_by_name`); tests now access
  `spec.input_schema`.
- Side benefit: 4 pre-existing mypy errors on `server.py` (untyped-decorator /
  no-any-return) are gone — the typed constructor params replaced the untyped
  decorators.

### Fixed — 0-entity graph-export now fails loud instead of silent success (#141)
- `loomgraph update` and MCP `refresh` returned `success:true` + exit 0 when
  graph-export produced 0 entities (parser grammar missing / languages
  mismatch) — the gate (`assess_export`) correctly blocked the empty-graph
  write (no data-loss), but the signal layer lied, so agents/hooks saw
  success while the graph stayed empty (dogfood 2026-08-03).
- CLI `update`: `output_success` → `output_error(GRAPH_EXPORT_EMPTY)` → exit 1.
- MCP `_async_refresh`: `return dict` → `raise GraphExportEmptyError` →
  `safe_call` wraps it as an error envelope (`success:false`).
- The post-commit hook needs no change — it checks `$EXIT_CODE`, so update
  exiting 1 now auto-prints the warning (commit still completes).
- New `ErrorCode.GRAPH_EXPORT_EMPTY` + `GraphExportEmptyError`.
- The `index` command's sister case is now fixed in #142 (same fail-loud treatment).

### Fixed — `index` command also fails loud on 0-entity export (#142)
- Sister case to #141: `index` (cold build) took a different path — on 0
  entities it warned + **still wrote** an empty graph + `success:true`. Now
  consistent with `update`/`refresh`: `output_error(GRAPH_EXPORT_EMPTY)` +
  exit 1, never writes the empty graph. An empty repo also exits 1 (safe —
  the user checks why there's nothing to index).

### Docs — removed `docs/archive/` (15 v0.1–0.5 LightRAG-era dead files)
- Deleted the entire `docs/archive/` directory (PRD, TOOLBOX_OVERVIEW,
  WORKSTREAM_ASSIGNMENT, LIGHTRAG_*×4, FEATURE_BOUNDARY, GRAPH_OPTIMIZATION,
  DISCUSSION-001, DOGFOODING_EPIC010, debt-analysis-2026-03-06, CLAUDE_INTEGRATION,
  issues/×2, INDEX). All v0.1–v0.5 LightRAG/three-repo-era content, fully
  recoverable via `git log` (git is the better archive). No inbound links
  anywhere in the repo; the directory was already excluded from the sdist.
  Its INDEX.md was a v0.1.0 (2025-02-04) dead index with broken relative paths
  (pointing at `architecture/`/`adr/` as if inside archive/) — actively
  misleading. Removed the now-dead `/docs/archive` line from the sdist exclude
  list. Continues the "docs/ 不留完成态" cleanup started with ROADMAP (#137).

### Docs — README documents the multi-language extras; ROADMAP removed
- README's Install section now documents the opt-in grammar extras
  (`[typescript]`/`[javascript]`/`[swift]`/`[java]`/`[objc]`). A pure TS/JS/Swift/
  Java/ObjC repo indexes to 0 (or stray) entities without the matching grammar,
  and the README — the primary entry point — never mentioned this. Added the
  install commands (quotes required — `[extra]` is a zsh/bash glob) + a pointer
  to `/loomgraph-setup` for `.codeindex.yaml` `languages:` setup.
- Removed `docs/ROADMAP.md`. It was a v0.9.0-era (2026-03-07) Phase 1–4 sprint
  log still narrating the retired LightRAG/Jina/H200 architecture — untouched
  for ~4.5 months (last commit `f60e06d` at v0.9.0; now 0.16.3), and never
  updated after ADR-013 (2026-06-24) retired that stack. Exactly the
  "docs/ 不留完成态" anti-pattern. Direction/planning is covered by GitHub
  issues + CHANGELOG. Cleaned its 4 inbound links (CLAUDE.md, AGILE_GUIDE,
  SYSTEM_DESIGN, epics/README). AGILE_GUIDE's §6 three-repo coordination
  section also de-LightRAG'd (three-repo → two-repo: codeindex graph-export →
  loomgraph SQLite).

## [0.16.3] - 2026-07-19

### Added — `loomgraph[javascript]` / `loomgraph[objc]` extras for first-class JS/ObjC support (#134)
- loomgraph already had `[java]` / `[typescript]` / `[swift]` opt-in grammar
  extras, but JS/JSX and Objective-C were missing — even though codeindex's
  parser supports them (`FILE_EXTENSIONS`: `.js`/`.jsx` → javascript, `.h`/`.m`
  → objc). Without the grammar, JS/ObjC files skip with a warning during
  indexing. The only workaround was an undiscoverable
  `pipx runpip loomgraph install tree-sitter-javascript`.
- Added `javascript = ["tree-sitter-javascript>=0.23"]` and
  `objc = ["tree-sitter-objc>=3.0.0"]` to `pyproject.toml`. Parity with the
  existing extras: `pipx install "loomgraph[javascript]"` (quotes required —
  `[extra]` is a glob in zsh/bash). The ObjC lower bound mirrors codeindex's
  own `[objc]` extra; pre-3.0.0 `tree-sitter-objc` predates the `language()`
  binding API codeindex's parser dispatches against.
- `loomgraph-setup` skill's grammar-install table updated: JS/JSX and ObjC now
  use the proper extras (was: the `pipx runpip` workaround). The "known gap"
  note removed.
- **Note**: `.mm` (Objective-C++) is not supported — codeindex matches only
  `.h` + `.m`.

## [0.16.2] - 2026-07-18

### Refactored — `loomgraph-setup` skill delegates `.codeindex.yaml` to codeindex's wizard; new `loomgraph codeindex` passthrough (#132)
- The setup skill generated `.codeindex.yaml` from **static hand-written templates
  with invented schema keys** (`codeindex: 1` instead of `version: 1`; fake
  `symbols.project_symbols`). On real layouts it silently indexed 0 entities:
  multi-module Maven (hardcoded `src/main/java/`), plain Composer PHP (assumed
  `app/`/`src/`), mixed JS/TS (no template), non-standard source roots. Root
  cause: the skill **reinvented codeindex's own wizard, worse**.
- Rewritten to **pure delegation**: the skill runs codeindex's own automation-ready
  wizard (`init_wizard.py` — `detect_languages`/`infer_include_patterns`/
  `infer_exclude_patterns`). All four static templates + the flat-layout bash
  hack + the broken `scan --dry-run` validation deleted. codeindex is the
  authority on its own schema; loomgraph stops hand-writing it.
- **New `loomgraph codeindex <args>` passthrough CLI command**: runs codeindex in
  loomgraph's pinned venv (`sys.executable -m codeindex.cli`), exposing the same
  pinned-env guarantee the internals already use (`graph_export_ingest.py`). The
  skill calls `loomgraph codeindex init` instead of a PATH-resolved `python` /
  `codeindex` that could hit a non-pinned install (#76 class). Unit-tested
  (`test_codeindex_passthrough.py`).
- Codex review hardening (6 findings, all accepted): removed false claims that
  go/rust are supported (codeindex parser only does python/php/java/ts/js/swift/
  objc); warned that `codeindex init` has side effects (injects CLAUDE.md, adds
  README_AI.md to .gitignore) and that `--force` overwrites; tightened the smoke
  test to check coverage completeness, not just `entities_created > 0`
  (monorepo could index a wrong subset and still pass); documented the wizard's
  limits (1000-file detection cap, fixed include-dir list); JS/ObjC grammar
  install via `pipx runpip loomgraph install tree-sitter-<lang>` (no first-class
  extra yet — #134).
- Spike-gated: `codeindex init --yes` → `loomgraph index .` produces >0 entities
  on 5 layouts (multi-module Java, plain PHP, mixed JS/TS, Python flat, Python
  src); old skill produced 0 on the first two.

### Fixed — `hooks install` wrote a dead hook when `core.hooksPath` is set (#130)
- `loomgraph hooks install` reported `success: true` but the hook never fired
  on repos with a custom `core.hooksPath` (husky, shared-hook setups, this
  repo's own `.githooks/`). git with a `core.hooksPath` reads ONLY that dir and
  ignores `.git/hooks/` entirely — but `get_hooks_dir()` hardcoded `.git/hooks`,
  so the installed hook landed where git never looks. Fix: resolve the hooks dir
  via `git rev-parse --git-path hooks`, which respects `core.hooksPath` (and
  falls back to `.git/hooks` when unset). Distinct from #128 (couldn't install
  at all); here it installed to a dead location.
- Added `core.hooksPath`-aware tests. Ship-gated on a repo with a custom
  hooksPath — the default-path-only trap that masked #128 applies here too.
- This repo now dogfoods its own post-commit hook in `.githooks/` (shared; the
  script skips silently when `loomgraph` isn't on PATH, harmless to contributors).

### Fixed — `loomgraph hooks install` failed on every wheel/pipx install (#128)
- `loomgraph hooks install` returned `installed_count: 0` with the template
  "not found" on every wheel/pipx install — the core "commit → index this
  round's changes" feature was broken for all normal install paths. Double
  defect: (A) the post-commit template was never packaged into the wheel;
  (B) the path logic assumed a source-tree layout (`Path(__file__).parent×4 /
  "scripts/hooks"`) that only coincidentally resolved under editable install —
  which is why it was never caught (developers dogfood editable, users install
  wheel). Moved the template into the package (`src/loomgraph/_hooks_templates/`)
  and resolved it via `importlib.resources`, so editable/wheel/pipx all behave
  identically.
- Silent-success masking: `loomgraph hooks install` returned `success: true`
  even when every hook was skipped. A total failure now reports
  `HOOK_INSTALL_FAILED` so future packaging regressions aren't swallowed.
- Added `tests/unit/test_hooks.py` (zero coverage before). Ship-gated on a real
  pipx install — the bug only reproduces outside editable mode.

### Fixed — incremental-update.yml called removed `--lightrag-url` (#125)
- The reusable workflow `.github/workflows/incremental-update.yml` invoked
  `loomgraph update --lightrag-url ...`, but `update` dropped that option when
  LightRAG was removed (v0.10-0.11, ADR-013). Any project referencing the
  workflow hit a click "no such option" error on every push. Removed the
  `--lightrag-url` line and the `lightrag_endpoint` input; `embedding_endpoint`
  is now optional (default empty → vectors-free structural index, since
  GitHub-hosted runners can't reach local Ollama anyway).
- `src/loomgraph/cli/_setup.py`: `status` docstring still said "Jina Code V2
  embedding service" (Jina retired v0.11). Corrected to "OpenAI-compatible
  embedding provider (optional, default local Ollama)". `loomgraph status --help`
  no longer misleads.
- `docs/guides/github-action-integration.md`: removed the #124 "broken until
  #125" warning (workflow now works); `LIGHTRAG_URL` secret dropped from the
  quick-start; `EMBEDDING_URL` marked optional with the vectors-vs-structural
  trade-off explained.

### Changed — CLI_DESIGN.md full detail realignment + EPIC-003 archived (#124)
- `docs/api/CLI_DESIGN.md` rewritten end-to-end. The command overview table was
  fixed in #122 but the detail sections (`### N.x`, 646 lines) still contradicted
  the real CLI: `update` was described as whole-tree re-export (it's per-file
  warm-diff + content_hash since #85/#91); `status` example showed
  PostgreSQL/Jina/LightRAG/docker (all retired v0.10-0.11, ADR-013); error-code
  table listed `LIGHTRAG_ERROR` (doesn't exist in `ErrorCode`); env-var table
  used `LOOMGRAPH_DB_URL` (PostgreSQL-era). Missing detail sections added for
  `deps`/`debt`/`impact`/`overview`/`git-metrics`/`trends`/`workspace`/
  `compare`/`similar`/`hooks`/`mcp` (only existed in the overview). Every
  parameter table re-verified against `loomgraph <cmd> --help`; top-of-file
  snapshot-authority notice added (option A from #124: detail is a writing-time
  snapshot, `--help` is the only authority — a CI command-name diff would not
  have caught the `update` semantic-inversion since the command name was right).
- `docs/epics/active/EPIC-003-update-strategy.md` → `completed/`. Its core goal
  (incremental update strategy) shipped: warm-diff (#85), content_hash (#91),
  `loomgraph hooks install` (post-commit auto-trigger), `loomgraph_refresh`
  (ADR-014). File gains an archive banner pointing to current implementation and
  flagging the LightRAG-era internals as superseded by ADR-013. `epics/active/`
  is now empty.
- `docs/guides/github-action-integration.md`: top-of-file warning added — the
  reusable `incremental-update.yml` still calls `loomgraph update --lightrag-url`
  (removed arg), so the documented integration is broken until #125 fixes the
  workflow. LightRAG-era API names in the flow diagram replaced; Feature-005/006
  status corrected to shipped.

### Added — README now defines the `workspace` concept (heir-lens follow-up)
- `workspace` is a load-bearing concept (storage path, query target, branch
  isolation, auto-fallback) but README used it throughout without ever
  defining it. New "Workspaces" section between Quick start and Configuration:
  what a workspace is (one indexed snapshot, `~/.loomgraph/<ws>.db`), how the
  name auto-derives (`<repo-dir>:<branch>`, lowercase), branch isolation
  semantics, `--workspace` override, `workspace list/info/delete`, and the
  empty-workspace `main → develop → master` auto-fallback. Every claim
  verified against `_common.py` (get_auto_workspace / resolve_workspace_with_fallback)
  and `workspace --help` — no new drift introduced.

### Changed — docs truth-realignment (heir-lens review)
- Removed stale `inject`/`embed` command references (v0.13 legacy removal, #84):
  `CLAUDE.md` project-structure tree + `CLI_DESIGN.md` command overview now
  describe the real command surface (`index` internal pipeline, `embed-backfill`,
  + `topology`/`deps`/`impact`/`debt`/`overview`/`check`/`git-metrics`/`trends`
  that were missing from the overview). Command authority redirected to
  `loomgraph --help`.
- Branch strategy doc: `CLAUDE.md` GitFlow (`main ← develop ← feature`) replaced
  with the real trunk-based `main ← feature/fix` (no develop branch ever existed;
  made explicit by `ec2477a`). The runtime workspace fallback chain
  (`main → develop → master`) in `_common.py:97` is unchanged — it's real code,
  not a doc fiction.
- README tests badge: dropped the stale hardcoded count (`460` badge vs `495`
  body, both wrong vs actual 623) → static `passing`; body now says `600+`.
- Moved dated completion-state docs out of `docs/` (violates the "no
  completion-state in docs/" rule): `debt-analysis-2026-03-06.md`,
  `DOGFOODING_EPIC010.md` → `docs/archive/`. `LIGHTRAG_INTEGRATION.md` (LightRAG
  + PostgreSQL era, retired v0.10-0.11 / ADR-013) moved `docs/api/` →
  `docs/archive/` alongside its already-archived source fragments; 2 dead links
  fixed.
- NOT changed (verified false alarms): AGILE_GUIDE Task row ("建 Issue" was a
  misread of the "可关闭" column — CLAUDE.md and AGILE_GUIDE already agree Task
  doesn't get an Issue); the workspace fallback chain (real runtime behavior).

### Fixed — 0-entity / silent-success paths hardened across update/refresh/impact (#120)
- The #118 fix hardened **`index`** against silent 0-entity exports, but the
  same `run_graph_export` callers — **`update`** and **`refresh`** (incl.
  MCP `loomgraph_refresh`) — were not aligned. A misconfigured repo (missing
  grammar / languages mismatch) yielding 0 entities could:
  - **`refresh --force-full`**: call `ingest(clear=True)` on an empty export,
    silently **wiping the whole workspace** before inserting nothing.
  - **`update`**: reach `ingest_incremental`, whose symbol GC would treat the
    empty export as "all changed-file symbols removed" and **delete real
    symbols**.
- New shared `assess_export(summary, warnings)` gate: 0-entity exports return
  `is_safe_to_write=False` + a diagnosis (folding codeindex's stderr root cause).
  `refresh` (both `force_full` and incremental) and `update` now hard-stop at
  the gate with `mode: zero_entity_skipped` + `warning` instead of touching the
  store. `index` keeps its richer suffix-hint warning but the gate logic is
  shared.
- **`impact` PATH bypass** (`core/impact/extractor.py:_run_codeindex`) — same
  class of bug as #76: a bare `codeindex parse` subprocess went through PATH
  and could pick up a stale pipx codeindex, ignoring the pinned
  `ai-codeindex` dep. Now invokes `sys.executable -m codeindex.cli parse`.

## [0.16.1] - 2026-07-14

### Fixed — non-Python repos no longer silently index to 0 entities (#118)
- A pure-Swift repo indexed to **0 entities** with only a vague warning on a
  fresh `pipx install loomgraph`: loomgraph declared no `[swift]` extra
  (codeindex doesn't hard-depend on `tree-sitter-swift`), the new-user venv
  shipped no Swift grammar, and the diagnostic chain dropped codeindex's
  `Parser library not installed` stderr lines (only `WARNING:`-prefixed lines
  were kept). The result: `success: true` + a hint blaming `.codeindex.yaml`
  when the config was actually correct.
- **`[swift]` extra** now declared in `pyproject.toml`
  (`swift = ["tree-sitter-swift>=0.0.1"]`), parity with `[java]` (#93) /
  `[typescript]` (#96). `pipx install loomgraph[swift]` surfaces the grammar.
- **`run_graph_export`** now surfaces `Parser library not installed for <lang>`
  lines (deduped to one) alongside `WARNING:` lines — covers Java/TS/Swift/
  objc/JS grammar-missing cases, which all share codeindex's exit-0 + per-file
  stderr behavior.
- **`_zero_entities_warning`** now prefers codeindex's stderr diagnostic when
  present (names the exact missing language + the config-vs-extensions gap,
  even for PHP/objc/JS that have no extra branch), adds a `.swift` suffix-hint
  branch (parity with java/typescript), and folds multi-line hints to their
  leading line. A PHP repo with `languages: [python]` now reports the mismatch
  instead of the generic config hint.
- No runtime behavior change for Python repos (double safety net: `tree-sitter-
  python` is a hard dep + codeindex defaults to `languages: ["python"]`).

## [0.16.0] - 2026-07-13

### Changed — remove private customer-distribution scaffolding
- LoomGraph is now public-PyPI-only (since v0.16); the enterprise private-
  distribution framework (GitHub PAT management, per-customer INSTALL.md,
  offline tarball packaging, delivery-summary generation) is dead code. This
  release deletes it and aligns docs to the actual `release.yml` CI flow.
- **Deleted scripts**: `scripts/manage_tokens.py` (PAT management),
  `scripts/generate_delivery_summary.py` (customer delivery docs),
  `scripts/quickstart.sh` + `scripts/upgrade.sh` (venv+TOKEN install/upgrade,
  superseded by `pipx`), `scripts/package.py` (offline tarball packaging +
  README.template rendering). `scripts/bump_version.py` / `check_version.py`
  / `install-hooks.sh` kept (still serve the release flow).
- **Deleted docs**: `docs/guides/CUSTOMER_PACKAGING.md`,
  `CUSTOMER_QUICKSTART.md`, `TOKEN_MANAGEMENT.md`, `TOKEN_QUICKSTART.md`
  (all private-distribution-era). `customers/DELIVERY_GUIDE.md`,
  `customers/README.template.md`, `customers/customers.yaml.example` removed.
- **`docs/PACKAGING.md`** rewritten from 399 lines (full private-distribution
  playbook) to a focused guide: `release.yml` CI flow + three-file version
  consistency + the two-CHANGELOG strategy (which is the still-relevant part).
- **`Makefile`**: dropped 11 dead targets (`delivery-summary`, `token-*` ×4,
  `package-*` ×4, `run-query`, `docker-*` ×3) + `docker-compose.yml` (HF TEI
  embedding container, LightRAG-era, embedding now defaults to local Ollama).
- **`CLAUDE.md`** MUST-READ table + change-log triggers updated: release now
  keyed on `git tag vX.Y.Z` (was `scripts/package.py`); CLI command-table
  authority is root `README.md` + `loomgraph --help` (was `README.template.md`).
- **No runtime code change** (`src/` untouched). `pyproject.toml` sdist
  exclude list trimmed (`/customers`, `/scripts/package.py` gone with the
  files).

## [0.15.5] - 2026-07-12

### Fixed — pin `ai-codeindex>=0.33.3` (codeindex #144, downstream of #139)
- TS `tsconfig.json` `paths` aliases now resolve for the common `./`-prefixed
  target form. codeindex #139 (v0.33.2) fixed `paths: {"@/*": ["src/*"]}` but
  left `{"@/*": ["./src/*"]}` — the form Vite, Next.js, and the TS handbook
  example all emit — **100% unresolved**, because `_load_tsconfig_paths`'s
  `_dot` closure mangled `./src/*` into `..src.*` (leading `.` → dot) which
  never matched `module_set`'s `src.*` entries. codeindex #144 (v0.33.3)
  normalizes `_dot` to drop empty + `.` segments, matching the adjacent
  `baseUrl` handling. Downstream effect, verified on an internal TS monorepo (630 entities):
  `@/`-alias IMPORTS edges **0/381 (0%) → 840/868 (96%)** resolved; the
  residual 4% target modules outside `include: [src/]` (correct `unresolved`).
  `loomgraph topology` orphan count **235 → 208** (27 false-positive orphans
  eliminated, 0 new orphans introduced) — symbols like `Button`, `appRoutes`,
  `zhCN`, `TenantProvider` that were imported only via `@/` now have inbound
  edges and are no longer flagged as orphans.
- **Upgrade guidance**: after `pipx install --upgrade loomgraph`, run
  `loomgraph index --clear .` once on TS repos using `@/` path aliases so
  `topology` drops the stale false-positive orphans.

### Changed — deprecate LightRAG-era onboarding artifacts (#114)
- `loomgraph setup-config` is deprecated. It dated from the LightRAG era and
  still generated `lightrag.api_url` config, contradicting the v0.11+ SQLite
  default. It now emits a stderr warning and writes a SQLite-era config stub
  (`storage.backend: sqlite`, embedding opt-in) instead of LightRAG config.
  The command stays registered so existing scripts don't break.
- `customers/README.template.md` rewritten for the public-PyPI era: `pipx
  install loomgraph` replaces the `~/.loomgraph-venv` + GitHub TOKEN + remote
  LightRAG-URL flow. CLI command table aligned with `loomgraph --help` (drops
  removed `query`, marks `search` as semantic, adds `graph --include-unresolved`,
  `debt`, `git-metrics`, `embed-backfill`, `trends`).
- `skills/loomgraph-setup/SKILL.md` updated: `loomgraph version` (no hardcoded
  venv path), `pipx install loomgraph[<lang>]` extras, dropped `setup-config
  --lightrag-url`, added flat-layout detection (`include: ["."]` when `*.py`
  at repo root with no `src/`) — fixes the 0-entity silent-clear dogfood bug.
- `scripts/package.py`: `get_cli_commands` now scans all `cli/_*.py`
  submodules (was main.py-only, false-positive-flagging real commands);
  deprecated-command set corrected to `query`/`scan` (`search` is a
  first-class semantic-search command since EPIC-015).
- `CLAUDE.md` rewritten to the SQLite/codeindex/MCP-native architecture,
  dropping the stale three-repo / LightRAG / Postgres / H200 / Jina / remote-
  endpoint / `/mo:*`-skill / `loomgraph query` legacy content.
- `customers/customers.yaml.example` simplified (drops `lightrag_url` /
  `github_token_*` / `language_parser` / `exclude_dirs` — public PyPI needs
  none of them).
- `customers/DELIVERY_GUIDE.md` redacted: 6 plaintext GitHub PATs ([customer] /
  [customer] / demo) replaced with placeholders. **git history still contains
  the plaintext tokens — revoke them at github.com/settings/tokens.**

## [0.15.4] - 2026-07-11

### Fixed — self-dogfood QA pass (#105, #106, #108)
- `graph <Class>` now aggregates callees from the class's methods (#105).
  Class entities don't own outgoing edges — calls live on their methods
  (`Class.method`), so `graph SomeClass` showed 0 callees even when every
  method called something. Method callees are now folded in, deduped
  against any direct edges (e.g. REFERENCES). Callers are unaffected
  (constructor edges land on the class via codeindex #132). Verified on
  loomgraph itself: 0 → 80 callees for a class that calls extensively.
- `deps` auto-drills module depth for single-package repos (#106). A repo
  whose source sits one dir deep (e.g. all under `src/pkg/`) collapsed to a
  single module at depth 1, hiding real internal coupling. `DepsAnalyzer`
  now expands depth until ≥2 real modules appear, stopping at the first
  multi-module depth (no over-splitting). `--depth` is now the *starting*
  depth. Verified: 1 module/0 deps → 7 modules/11 deps on loomgraph.
- `loomgraph index`/`update` surface codeindex's partial-graph WARNING
  instead of a silent success (#108). A non-Python repo indexed with the
  default `languages:[python]` yields a few stray entities + a stderr
  WARNING; loomgraph discarded stderr on exit 0, so it reported `success:1`
  with near-zero entities. The WARNING is now captured and echoed to stderr
  and into the JSON result's `warning` field.

### Changed — pin `ai-codeindex>=0.33.1` (#107, #111)
- graph-export now honors `.codeindex.yaml` `include:` (codeindex #137), so
  `loomgraph index .` no longer ingests `docs/`/`tests/`/`spikes/` when a
  project scopes its index to `src/` — removing the phantom god/hub/orphan
  nodes they created in `topology` (#107).
- MCP server + debt-report versions are sourced from `loomgraph.__version__`
  via `importlib.metadata`, not hardcoded constants that lagged the
  installed package (#111).

## [0.15.3] - 2026-07-08

### Fixed — `graph --depth` now does a real BFS, was a no-op (#103)
- `graph()` received `--depth` but dropped it before calling
  `_async_graph_query`, so depth 1/2/3/5 returned identical results (direct
  neighbours only). `_async_graph_query` now builds relation_type-filtered
  adjacency and BFS-expands callers/callees to `depth` layers (reuses
  `_bfs_collect`, the helper `find --with-relations` already uses).
  depth=1 unchanged; depth>1 expands transitively, deduped.
- Verified an internal TS monorepo: `graph src.__tests__.db-seed.test. --callees --depth 1`
  → 22, `--depth 2` → 23 (reaches `JSON.stringify` via a callee hop).

## [0.15.2] - 2026-07-08

### Fixed — ambiguous CALLS edges no longer create phantom module deps (#101)
- codeindex tags dynamic-dispatch calls (`db.exec`, `x.json()`) as
  `resolution_qualifier=ambiguous` and stuffs every same-name method into
  `candidates` (e.g. all four `test.exec` helpers). `map_edge` took
  `candidates[0]`, so every `db.exec` in `src/lib/api/queries.ts` resolved
  to `server.test.customers.test.exec` — a systematic phantom cross-module
  dep that made `deps` and `topology` untrustworthy on TS projects.
- `map_edge` now uses `dst_raw` (the call expression) as the ambiguous
  edge's `tgt_id`, mirroring `unresolved`, so `deps`/`topology` skip it
  (no entity matches a call-expression id) while the candidate list stays
  in `edge_data` for graph callers that want it.
- Verified on an internal TS monorepo: 544 ambiguous edges were 100% phantom before (all
  hit a real entity), 0 after; `deps` `→ server/test` edges went from ~20
  to 0. Note: the issue's original root cause ("inject resolves dst_raw
  against the entity table") was wrong — loomgraph has no such logic; the
  real cause was `candidates[0]`.

## [0.15.1] - 2026-07-08

### Fixed — slash in git branch name no longer breaks indexing (#99)
- A branch like `codex/ui-grammar-filter-parity-us023` made the workspace
  name contain `/`, which the filesystem parsed as a path — the DB landed
  in a subdirectory with 0 rows injected and was undiscoverable by
  `workspace list` (which globs top-level `*.db`). `_resolve_db_path` now
  sanitizes `/` and `\` to `-`, so the DB stays at the top level and
  round-trips (index → query). Affects every `feature/*` / `bugfix/*` /
  `codex/*` branch (mainstream git convention); the silent-fail nature
  had previously masqueraded as a "TS CALLS-edge quality bug".

### Fixed — `graph <simple-name>` resolves to the stored FQN (#98)
- `loomgraph graph downstreamBlockers` returned `callers: [], source_id: ""`
  because the traversal compared the raw name with `==` against
  module-qualified stored names and never resolved it. `_async_graph_query`
  now resolves a simple name to its FQN (exact match wins; else a unique
  dotted-suffix match). `graph downstreamBlockers` now returns the 2
  callers (handler + test) that `find --with-relations` and Serena LSP
  already saw. Root cause was in the query, not ingest.

## [0.15.0] - 2026-07-07

### Added — `--scope` path-prefix filter for debt/topology (#61)
- `loomgraph debt --scope src/` and `loomgraph topology --scope src/` limit
  both the codeindex static layer (giant_files/functions/smells/file_reports)
  and the topology layer (orphans/hubs/gods) to an absolute path prefix, so
  docs/scripts/tests stop inflating audits. `--module` kept as a deprecated
  alias; scope wins. Server-side coupling still uses the global prefix
  (scoping it needs a store API change; noted inline).
- `loomgraph_topology` + `loomgraph_debt` MCP tools gain `scope`.

### Added — MCP debt/check/git_metrics primitives (#62)
- `loomgraph_debt`, `loomgraph_check`, `loomgraph_git_metrics` exposed as
  standalone read primitives (previously only reachable via the
  `loomgraph_debt_audit` composite). `git_metrics.gather()` shared with the
  composite (dedupes the inline `_git_metrics_dim`).

### Fixed — `summary.total_entities` wired to topology run (#60)
- `overall_health.summary.total_entities` was hardcoded 0 with a TODO; now
  reflects the topology run's real entity count.

### Removed — deprecated workflow skills (#64, breaking)
- `loomgraph-debt-radar` / `-evolution` / `-sync-advisor` skills deleted
  (deprecated v0.12.1; replaced by the `loomgraph_debt_audit` /
  `loomgraph_evolution_track` / `loomgraph_sync_advice` MCP composites).
  `install-skills` now ships only `init` + `setup`; ship-surface guard pins
  the surviving set.

### Fixed
- `SERVER_VERSION` was stale (0.13.0); tracks the release version again.

## [0.14.2] - 2026-07-06

### Fixed — `workspace delete` now removes the .db file (#95)
- `_async_workspace_delete` called `store.delete_all()` (drops in-db tables)
  but left the `<name>.db` file on disk, so the deleted workspace kept
  reappearing in `workspace list` (which globs `*.db`). It also created an
  empty shell when deleting a non-existent name. Now unlinks `<name>.db`
  plus its sqlite `-wal`/`-shm` sidecars without opening a store; idempotent
  on missing workspaces (no shell created).

### Added — `[typescript]` extra + `.ts`/`.tsx` zero-entities hint (#96)
- TS out-of-box parity with `[java]` (#93): `pipx install loomgraph[typescript]`
  now pulls `tree-sitter-typescript>=0.23`. A pure-TS repo previously indexed
  to 0 entities with only a generic "check languages config" warning.
- `loomgraph index` now detects `.ts`/`.tsx` on a 0-entity export and hints
  `pipx install loomgraph[typescript]` + add `typescript` to `.codeindex.yaml`
  languages.
- Note: a `.codeindex.yaml` with `languages: [typescript]` is still required
  — codeindex `graph-export` has no auto-detect / `--languages` flag; the
  extra + hint make the path discoverable rather than zero-config (same
  contract as Java).

## [0.14.1] - 2026-07-06

### Fixed — `loomgraph index` now actually uses the pinned codeindex (#76)
- `run_graph_export` shelled out to bare `codeindex` (PATH lookup), so a
  stale codeindex elsewhere on PATH (e.g. a pipx-managed 0.29.0) silently
  shadowed the venv-pinned `ai-codeindex>=0.32.0`. The 0.14.0 dep bump was
  correct but ineffective: `loomgraph index` kept running the old parser,
  so Java call graphs stayed broken (0% of edge `src_id`s resolved) even
  though the fixed codeindex was installed in the venv.
- Now invokes `[sys.executable, "-m", "codeindex.cli", ...]`, running
  codeindex under loomgraph's own interpreter — same venv as the pinned dep,
  no PATH dependence. `codeindex.cli:main` is the console-scripts entry
  point; `python -m codeindex.cli` is verified working.
- Verified end-to-end on spring-petclinic: store `src_id ∈ entity_id`
  0%→65%, topology orphan 81%→50%, coupling density 0.0→0.62.
- **Upgrade + `loomgraph index --clear .`** to rebuild existing Java
  workspaces — their edges were indexed under the stale PATH codeindex.

## [0.14.0] - 2026-07-06

### Changed — `ai-codeindex>=0.32.0` (Java call-graph connectivity, #76)
- Dep floor bumped 0.29.0 → 0.32.0. codeindex 0.32.0 fixes the Java parser
  `call.caller`/`sym.name` qualification mismatch that left every Java edge
  dangling at the source — `graph` / `topology` / `coupling` all reported
  empty on Java repos while Python worked. Verified on spring-petclinic
  via `loomgraph index`: processFindForm 0→9 callees, orphan rate
  81%→49%, coupling density 0.0→0.62. Python repos unaffected. **Existing
  Java workspaces need a `loomgraph index --clear .` rebuild** — their
  edges were dangling under the old codeindex.

### Added — Java out-of-box + index safety (#93)
- `loomgraph[java]` optional extra declares `tree-sitter-java>=0.23.0`.
  Pure-Python installs stay light; Java repos install with
  `pipx install loomgraph[java]`. Mirrors the existing python/php
  direct-grammar-pin pattern (java is opt-in, not a core dep) so the
  grammar ships only where needed.
- `loomgraph index` no longer silent-successes on 0 entities: when
  `codeindex graph-export` returns nothing, it emits a stderr warning and
  a `data.warning` field (agent-visible). `.java` files present → hints
  `pipx install loomgraph[java]` + add `java` to `.codeindex.yaml`
  languages; else → generic languages-config hint. Kept as exit-0 warning
  (an empty repo legitimately indexes to 0).

### Fixed — reader false-positive warnings on codeindex entity types (#76)
- `VALID_ENTITY_TYPES` synced to codeindex's full 12-kind output
  (class, constructor, enum, field, function, interface, method,
  namespace, property, record, type_alias, variable). The reader always
  stored these entities; it now stops logging a per-record "unknown
  entity_type 'field'/'constructor'/..." warning that flooded every
  Java/TS index summary. Verified on a Java DI bean export (6 entities,
  0 warnings post-fix vs 2 pre-fix).

## [0.13.0] - 2026-07-06

### Added — symbol-level incremental + local-Ollama default (#90)
- `ingest_incremental` upgraded file-level → symbol-level via codeindex
  >=0.31.0 per-symbol `content_hash` (sv1). A one-function edit in a
  50-entity file re-embeds 1 symbol, not 50. `map_entity` carries
  `content_hash`; reader `SUPPORTED_SCHEMA_VERSION` 0→1. New
  `GraphStore.delete_entities` (cascade relations + vec0) and
  `get_entities_by_source`. Spike corrected two issue mis-estimates: no
  storage migration needed (content_hash round-trips via properties_json);
  the issue's change-list omitted the two new store methods.
- LLM default switched H200 GLM → **local Ollama** (`gemma3:12b-it-qat`,
  non-reasoning; `glm-4.7-flash:q8_0` rejected — reasoning model, content
  goes empty under moderate max_tokens). Embedding default was already
  Ollama. H200 (`internal.example.invalid`) retired 2026-07. Third-party
  OpenAI-compatible endpoints remain configurable.
- `maybe_embed_entities` skips degenerate zero vectors — a provider
  200-OK-but-empty under load would poison KNN (every query at distance
  ~1.0, score 0).
- Docs: 7 live docs retired H200/LightRAG/Jina references; SYSTEM_DESIGN
  rewritten v0.5.0 → v0.7.0.

### Changed — graph-export contract migration (#66, breaking)
- `index` / `update` now consume `codeindex graph-export` NDJSON:
  module-qualified entity ids, edges carry `resolution_qualifier` +
  cross-file callee resolution. Fixes cross-module same-name collisions
  (9 `handle` funcs merged into 1 phantom god_function, out_degree 34).
  **Requires `index --clear` rebuild** of existing workspaces. Depends
  `ai-codeindex >= 0.28.0` (signature field).

### Removed — legacy programmatic API + embed/inject CLI (#77, breaking)
- CLI `loomgraph embed` / `loomgraph inject` removed (old split pipeline;
  `embed` broken since EPIC-012 Jina→Direct migration). Use `index`
  (one-step) or `embed-backfill` (vector top-up for an indexed workspace).
- Python API `loomgraph.index_file` / `index_repository` / `scan_code_files`
  / `inject_parse_result` and `core.mapper` / `indexer` / `injector` /
  `adapter` modules removed (zero internal callers, all served the deleted
  scan path). `loomgraph.__init__` public surface converged to `Settings`
  / `get_settings` / `__version__`.
- Models `Symbol` / `Call` / `Inheritance` / `Import` / `ParseResult`
  removed (legacy codeindex input types); `EntityData` / `RelationData`
  + analysis metrics retained.

### Added — `update` per-file warm-diff restored (路 B, #66 follow-up)
- `loomgraph update` back to per-file incremental (was temporarily
  whole-tree during #66): git-diff filters changed files → re-embed /
  re-inject only those + GC deleted symbols (`delete_by_source`).
  Non-git / `--files` falls back to whole-tree upsert (`clear=False`).

### Added — MCP reactive refresh + storage write-safety (#86)
- `loomgraph_refresh` MCP tool — first write-capable tool exposed via MCP.
  Reactive working-tree re-index (pull-mode): an agent that just edited a
  file (uncommitted, incl. untracked) can re-index it on demand instead of
  waiting for a commit. Complementary to the commit-driven git-hook
  `update`. `path` scopes to a file/dir; `force_full` cold-rebuilds. See
  ADR-014.
- Storage opens SQLite in WAL mode with a 5s busy_timeout, so the MCP
  server (long-lived) and a git-hook `update` subprocess can write the
  same `.db` without `database is locked`. `close()` runs
  `wal_checkpoint(TRUNCATE)` so a bundled `.db` stays self-contained.
  Hardens all write paths, not just refresh.
- `core/git.py`: `get_working_tree_files` — working-tree change detector
  (staged + unstaged + untracked) via `git status --porcelain`, the
  pull-mode source for `refresh`.

### Added — EPIC-015 Phase 1: end-to-end semantic search (#70)
- `loomgraph search` — semantic retrieval over entity-description
  vectors. Reclaims the `search` name (the hidden deprecated alias to
  `find` is removed); `find` (by name) / `search` (by meaning) / `graph`
  (by relation) are now peers. Returns `EMBEDDING_NOT_INDEXED` on a
  workspace with no vectors (or no workspace at all) instead of a
  generic error. Phase 0 (#70) measured intent-query wins where `find`
  returned empty.
- `loomgraph_search` MCP tool — same surface over the MCP server.
  Requires restart to surface in a running client (see MCP_DESIGN.md
  "Upgrading").
- `GraphStore.vector_count()` — reliable empty-state detection for the
  semantic-search pre-check (counts the vec0 `_rowids` shadow table).
- `import-export` now auto-embeds entity descriptions when embedding is
  enabled (mirrors `index`), so an imported graph-export artifact is
  semantically searchable in one step.
- `export_reader.map_entity` projects codeindex#115's `signature` field
  and folds it into `description` (`signature | docstring`). Closes the
  docstring-coverage hole (Phase 0: ~15% of symbols had no docstring →
  no vector → invisible to search; signature is present for ~all).

### Added — EPIC-015 Phase 3: embed-backfill (#70, closes #68)
- `loomgraph embed-backfill [-w <ws>]` — populate `vec_node_descriptions`
  for an already-indexed workspace without triggering a full reindex.
  Embeds existing entity descriptions only (no re-parse, no re-inject).
  Critical for import-export workspaces, which carry no vector data on
  import; backfill is the only path that makes them semantically
  searchable. Idempotent: if vectors already exist, exits cleanly.
- `GraphStore.write_embeddings()` — bulk vector write to vec0 with
  validation and dedup-by-name semantics.

### Fixed
- `DirectEmbeddingClient` double-appended `/v1`: it composed
  `{base_url}/v1/embeddings` while every `EmbeddingConfig` default
  `api_url` already carries `/v1` (OpenAI convention), yielding
  `/v1/v1/embeddings` → 404. `maybe_embed_entities` swallows embedding
  errors, so `loomgraph index` reported success while writing **zero**
  vectors — the vec0 tables silently stayed empty in every workspace.
  Client now appends only `/embeddings`; regression test locks the
  composed URL (#71). Prerequisite unblock for EPIC-015 (#70) semantic
  search.
- `loomgraph index` (and the batch inject path) suggested `pip install
  matrix-codeindex` on the codeindex-not-found error — wrong package
  name; the PyPI package is `ai-codeindex`. Two suggestions in
  `cli/_indexing.py` (:43, :626) + a stale comment in `core/models.py`
  corrected. Regression-guarded by a test asserting no live source
  references the old name (#65). Historical ADR/archive references left
  as point-in-time records.

### Docs
- `docs/api/MCP_DESIGN.md`: new "Upgrading loomgraph — new tools need a
  restart" section (#62). Documents that the stdio MCP server is pinned
  to the version it launched with, so `pipx upgrade` alone doesn't
  surface newly-shipped tools until Claude Code is restarted. Surfaced
  during the v0.12.1 composite-tool dogfood.

## [0.12.2] - 2026-07-01

Patch release. Fixes a debt-scoring bug found during the v0.12.1 MCP
debt-audit dogfood.

### Fixed
- **`loomgraph debt` gave false grade F on healthy codebases** (#59).
  `quality_score` was computed over ALL issues, but topology- and
  git-derived issues already have their own graduated dimensions
  (`topology_score` / `git_score`). They were double-counted — once as
  a soft 0-100 signal, once as an uncapped cliff in `quality_score`
  (40% weight). 58 topology issues drove quality to 0 → total 49 → F
  on a codebase whose only real signal was topology 65.

  Fix: `DebtIssue` now carries a `source` field (`static` | `topology`
  | `git`); `quality_score` penalizes only static-source issues.
  Topology/git issues flow into their own dimensions. Result on
  loomgraph self: **grade F/49 → B/89**. All issues are still listed
  in the report — they're just not double-penalized.
- Removed the hardcoded `test_coverage: 0` from the health breakdown
  (#60) — it read as "0% coverage" but wasn't part of the score
  formula. Will return when coverage is actually wired.

## [0.12.1] - 2026-06-30

Patch release. Two themes: release-process hardening (post-v0.12.0
retro), and composite MCP tools that fold the legacy workflow skills
into native MCP calls.

### Added — composite MCP tools
- `loomgraph_debt_audit` — full 10-dimension debt audit in one MCP
  call. Parallel-fans-out across `debt`, `deps`, `overview`, `topology`,
  `workspace_info`, `check`, git-metrics, and (optional) trends.
  Replaces the multi-step `/loomgraph-debt-radar` skill with ~10× the
  speed.
- `loomgraph_evolution_track` — cross-workspace entity evolution
  (similar + pairwise compare + per-workspace graph). Replaces
  `/loomgraph-evolution`.
- `loomgraph_sync_advice` — upstream/downstream sync analysis
  (compare + 3-dim debt × 2 workspaces + per-entity impact).
  Replaces `/loomgraph-sync-advisor`.

Each composite returns `{data, error}` per dimension so the response
gracefully degrades when a dim can't compute (no git, no historical
snapshots, missing workspace), rather than failing the whole call.

### Deprecated
- Skills `loomgraph-debt-radar`, `loomgraph-evolution`,
  `loomgraph-sync-advisor` deprecated in favor of the composite MCP
  tools above. Skills remain functional in v0.12.x for backward
  compat; **scheduled for removal in v0.13.0**. `loomgraph-init` and
  `loomgraph-setup` are unaffected (they handle setup side-effects
  that don't belong in MCP).

### Fixed — release process hardening (post-v0.12.0)
- `.github/workflows/release.yml`: new `version-check` job (runs before
  test/build) that fails fast in <10s when the pushed tag doesn't match
  pyproject.toml's version. Catches the v0.12.0 release scenario where
  a tag got pushed pointing at a commit that still had the old version.
- `.githooks/pre-push` + `scripts/install-hooks.sh`: optional local
  pre-push hook that validates tag-vs-pyproject mismatch BEFORE the
  push reaches GitHub. CI is the source of truth; the hook just
  fails faster and shows fix steps inline.
- `docs/PACKAGING.md`: documents the hook install as a one-time
  post-clone step.

### Changed — measured MCP performance
- `docs/api/MCP_DESIGN.md` replaces the hand-waved 50× speedup
  estimate with measured numbers: tools/list 0.8ms, find cold 61ms,
  graph warm 14.8ms vs CLI subprocess ~240ms = 4× cold / 13-16× warm.

## [0.12.0] - 2026-06-29 — MCP server + codeindex 0.27.0 round-trip

Major release. Two big additions: native MCP (Model Context Protocol)
server for AI-agent tool use, and a fully validated `import-export`
consumer for codeindex's `graph-export` artifacts (codeindex#102
contract). Plus a 3× boost in unresolved-edge coverage when consuming
`ai-codeindex>=0.27.0` artifacts via the new `dst_raw` schema field.

Spike-30 round-trip verdict (🟡 YELLOW) preserved at the stronger
DeepSeek v4 pro tier; loomgraph + codeindex now form a working
end-to-end pipeline for real Python codebases up to ~22k LoC
(documented in `docs/benchmarks/dogfood.md`).

### Added — MCP server (EPIC-013, v0.12.0)
- `loomgraph mcp serve` — native Model Context Protocol stdio server
  exposing 8 read-side tools (`find`, `graph`, `topology`, `impact`,
  `deps`, `overview`, `workspace_list`, `workspace_info`) for AI agents
  (Claude Code / Codex / Cursor) to call as first-class tools.
- `loomgraph mcp install-config [--path]` — print or merge the
  Claude Code MCP config snippet for loomgraph; default location
  `~/.claude/mcp.json`.
- `--default-workspace` flag on `mcp serve` plus
  `LOOMGRAPH_MCP_DEFAULT_WORKSPACE` env var — pin a workspace when
  the stdio launch dir doesn't carry useful auto-detect signal.
- `loomgraph.mcp` package — public surface for harnesses that want to
  embed the MCP server in their own process (e.g. multi-tool
  aggregators).
- `docs/api/MCP_DESIGN.md` — full tool reference + setup walkthrough.

### Notes — what MCP is NOT
- Write tools (`index`, `update`, `import-export`) are intentionally
  CLI-only. They're slow, mutating, and require `ai-codeindex` on the
  runtime path. Keeping them out of MCP lets query-only users skip
  the codeindex install entirely (`pipx install loomgraph` is enough
  to query an existing workspace via the MCP server).

### Added
- `loomgraph import-export <artifact>` — consumes a codeindex
  `graph-export` NDJSON file (codeindex#102 contract) and lands the
  entities + edges in a workspace. Default workspace name is
  `<basename>:imported`, isolated from `loomgraph index .` output.
- `--dry-run` flag on `import-export` — reads + validates + maps
  without touching storage. Returns the same summary structure the
  real run would, plus a `would_write` count of intended writes.
- `loomgraph.io` package — public reader API (`GraphExportReader`,
  `map_entity`, `map_edge`, `ImportSummary`) for callers that want
  to consume the format directly without going through the CLI.

### Changed
- `loomgraph.io.export_reader`: consume the new `dst_raw` field shipped
  in `ai-codeindex>=0.27.0`. For unresolved edges the reader now uses
  `dst_raw` (the original call expression, e.g. `os.environ.get`) as
  the relation's `tgt_id`. Each unresolved edge gets its own distinct
  target — no more fake hub problem. Round-trip on loomgraph self
  jumped from 624 → 1883 stored relations (~3×) with verdict-quality
  unchanged (YELLOW preserved per-class). Older artifacts without
  `dst_raw` still degrade gracefully: unresolved edges are skipped
  rather than collapsed onto a sentinel.

### Notes
- `import-export --clear` defaults to **False** (non-destructive).
  Workspace contents are preserved unless the flag is passed
  explicitly. This protects AI agents that may invoke the command
  without flags.
- Compatibility: validated against `ai-codeindex>=0.27.0` graph-export
  artifacts. Pre-0.27.0 artifacts continue to load but lose the
  unresolved-edge coverage above.

## [0.11.3] - 2026-06-26 — `check_embedding` honors `embedding.enabled`

Patch release. `loomgraph status` no longer probes the embedding URL or
emits a "service not reachable" warning when the user has explicitly
set `embedding.enabled: false` (the v0.11.0 default).

### Changed
- `cli/_deps_check.check_embedding`: short-circuits to `{"enabled": false,
  "connected": false}` when `settings.embedding.enabled` is false. No HTTP
  call, no error message. When enabled, response shape gains an `enabled`
  field so downstream code can distinguish "off by choice" from "off by
  failure".
- `cli/_setup.status`: suppresses the "Embedding service not reachable"
  suggestion when `embedding.enabled` is false. Matches the runtime
  semantics of `maybe_embed_entities` which has always honored the flag.

### Added
- 5 regression tests in `test_embedding_disabled.py`: disabled-skips-probe /
  enabled-still-probes / enabled-but-unreachable-still-warns / status
  command warning on/off based on enabled flag.

## [0.11.2] - 2026-06-26 — Graceful stale-config handling

Patch release. Old `.loomgraph.yaml` / `~/.config/loomgraph/config.yaml`
files written for v0.9.x or v0.10.x no longer crash the CLI with a
pydantic stack trace on upgrade.

### Added
- `ConfigSchemaError` — wraps pydantic `ValidationError` with a single
  human-readable message and a pointer to the migration guide
- `cli_entry()` — new user-facing entrypoint that intercepts
  `ConfigSchemaError` and writes one stderr line + exits 2 (no traceback);
  `[project.scripts]` now points here
- 6 regression tests covering legacy `lightrag:` block / renamed
  `embedding.base_url` / invalid `Literal` values / wrong types / CLI
  formatter

### Changed
- Every sub-config (`ASTExtractionConfig`, `SemanticEnhancementConfig`,
  `IndexingConfig`, `EmbeddingConfig`, `StorageConfig`, `LLMConfig`,
  `RetrievalConfig`) now sets `model_config = SettingsConfigDict(extra="ignore")`
  so removed YAML fields (e.g. `embedding.base_url`) are silently dropped
  rather than raising `extra_forbidden`. Typos in known fields still
  surface via `ConfigSchemaError`.

## [0.11.1] - 2026-06-26 — First PyPI publication

First release published to PyPI. Code is identical to v0.11.0; only release
infrastructure was added.

### Added
- `LICENSE` (MIT) file
- `pyproject.toml` — `Project-URL` block (Homepage / Repository / Documentation
  / Changelog / Issues), Topic classifiers, `license-files = ["LICENSE"]` (PEP 639)
- `.github/workflows/release.yml` — Trusted Publisher OIDC (`pypa/gh-action-pypi-publish@release/v1`),
  test matrix on Python 3.11/3.12, environment `pypi`

### Changed
- `pyproject.toml` keywords cleaned: removed `lightrag` / `jina` / `h200`,
  added `code-intelligence` / `knowledge-graph` / `sqlite-vec` / `ast` /
  `embeddings` / `vector-search` / `claude-code`
- Development Status: `3 - Alpha` → `4 - Beta`
- `description` neutralized for PyPI (was "Enterprise … H200 Optimized GraphRAG")
- `README.md` rewritten for v0.11.0+ reality (was stuck at v0.9.0 / LightRAG / H200)
- Wheel/sdist exclude lists: drop `README_AI.md`, `PROJECT_SYMBOLS.md`,
  `customers/`, `scripts/package.py`, `docs/epics`, `docs/archive`,
  `tests/integration` (391 KB wheel, 58 entries vs 65 before)

### Removed
- `asyncio>=3.4` from runtime dependencies (stdlib — listing it as a PyPI
  package is an anti-pattern that installs a placeholder package of the same
  name)
- mypy override for `asyncpg.*` / `pgvector.*` (LightRAG-era leftover);
  replaced with `sqlite_vec.*`

## [0.11.0] - 2026-06-25 — EPIC-012 Embedding provider 解耦 (Breaking)

### Added
- `DirectEmbeddingClient` — OpenAI-compatible `POST /v1/embeddings`, single
  client covers Ollama / OpenAI / Voyage / GLM / vLLM / custom
- `EmbeddingConfig` 重塑：
  - `enabled: bool` (default `false`) — embedding 不再自动尝试连接
  - `provider: ollama | openai | voyage | glm | custom` (default `ollama`)
  - `api_url`, `api_key`, `model`, `dimension` 可配
- `SqliteGraphStore(dimension=...)` 参数化 + 启动时 detect mismatch →
  `SqliteDimensionMismatch` 引导 cold rebuild
- `storage.factory.create_embedding_client()` 工厂
- `.loomgraph.yaml` 默认配置示例（embedding 段）

### Removed (Breaking)
- `JinaEmbeddingClient` / `loomgraph.embedding.jina` 整模块删除
- `EmbeddingConfig.base_url` 字段 → 重命名为 `api_url`
- `EmbeddingConfig.provider` 旧值（`jina`/`local`）废弃，新值
  `ollama`/`openai`/`voyage`/`glm`/`custom`
- `SqliteGraphStore.VECTOR_DIM` 常量改为 `DEFAULT_VECTOR_DIM`（仍 768）

### Changed
- `maybe_embed_entities` 改读 `embedding.enabled` 门控
  （默认 `False` → pipx install 不连任何远端 embedding 服务）
- 默认 embedding 指向本地 Ollama（`http://localhost:11434/v1`）

## [0.10.0] - 2026-06-25 — EPIC-011 SQLite + sqlite-vec (Breaking)

### Added — EPIC-011 SQLite + sqlite-vec backend (Phase 1-5)
- `GraphStore` ABC + `LightRAGGraphStore` adapter + `SqliteGraphStore` with vec0 KNN (Phase 1-2)
- `storage.factory.create_graph_store(workspace)` per `settings.storage.backend`
- `LLMClient` ABC + `DirectLLMClient` (OpenAI-compatible chat completions) supporting GLM / OpenRouter / vLLM (Phase 4)
- `storage.backend` config (`lightrag` | `sqlite`, default `lightrag` through Phase 4)
- `llm.provider` config (`lightrag` | `glm` | `openrouter` | `vllm`)
- `scripts/bench_backends.py` cross-backend latency benchmarks
- `scripts/diff_backends.py` cross-backend analytics consistency diff
- ADR-013: SQLite + sqlite-vec replace LightRAG (supersedes ADR-001, ADR-002; partial ADR-010, ADR-011)

### Changed
- `ImpactAnalyzer._query_callers` now uses deterministic graph traversal (CALLS edges) instead of LLM inference — faster and exact

### Removed (Breaking) — v0.10.0
- **`loomgraph query` command removed**. Natural-language code Q&A is now handled by general-purpose agents (Claude Code / Codex / Cursor). LoomGraph focuses on deterministic `find` / `graph` / `topology`.
- **LightRAG client / adapter / config removed** (`core/lightrag_client.py`, `storage/lightrag_store.py`, `llm/lightrag_llm.py`, `LightRAGConfig`, `storage.backend=lightrag`, `llm.provider=lightrag`)
- **PostgreSQL + pgvector dropped from runtime deps** (`asyncpg`, `pgvector`); `docker-compose.yml` postgres service removed; `scripts/init-db.sql` removed
- `cli/_common.create_client` / `prepare_workspace_client` (legacy LightRAG helpers)
- `cli/_indexing.py --lightrag-url` override flag
- `cli/_deps_check.check_lightrag_api` (replaced with `check_storage` — SQLite + sqlite-vec smoke)
- `ErrorCode.LIGHTRAG_ERROR` renamed to `STORAGE_ERROR`
- `ImpactAnalyzer.lightrag_client` / `llm_client` fields → single `store: GraphStore` (deterministic graph traversal, no LLM needed)
- ADR-001 (PostgreSQL storage) and ADR-002 (LightRAG framework) marked Superseded by ADR-013

## [0.9.3] - 2026-03-22

### Fixed
- **Indexing timeout on large codebases**: Dynamic timeout calculation based on entity count (minimum 60s, scales with payload size)
- **Timeout error message**: Now suggests increasing `api_timeout` or using smaller batch size

### Changed
- **Batch injection for large codebases**: Payloads exceeding 5000 entities are automatically split into multiple HTTP calls
- **Indexing progress feedback**: Shows file collection progress (every 100 files), entity/relation counts, and per-batch upload status
- **CLI boilerplate extraction**: `prepare_workspace_client()` helper replaces 8-line repeated pattern across 8 async functions (-141 lines)

### Removed
- Dead code: `Settings.ensure_working_dir()`, `GitDiffParser.get_file_diff()`, `GitDiffParser.has_changes()`

### Improved
- **Customer README template**: Updated CLI command reference, added feature prerequisite matrix, added post-install diagnostic checklist
- **quickstart.sh**: Fixed codeindex wheel filename pattern, added post-install self-check with feature availability summary
- **Packaging validation**: `package.py` now checks for stale version references and deprecated CLI commands before packaging

## [0.9.2] - 2026-03-08

### Fixed
- **Technical Debt Scoring Formula**: Fixed data inconsistency where Quality 97/100 (A+) + Maintainability 97/100 (A+) resulted in Technical Debt 50/100 (F)
  - Root cause: `technical_debt_score` only considered `god_penalty`, ignoring quality and maintainability dimensions
  - Solution: Multi-dimensional weighted formula - `quality*0.4 + maintainability*0.3 + topology*0.3`
  - Impact: codeindex evaluation improved from 50/100 (F) to 87/100 (B+), eliminating scoring contradiction
  - Reference: codeindex Issue feedback (2026-03-08)

### Changed
- **God Function Detection**: Added domain complexity whitelist to reduce false positives
  - Whitelisted patterns: Parser domain (`*.visit_*`, `*.parse_*`), Code generators (`*.generate_*`, `*.render_*`), CLI commands (`*.execute`, `*.main`)
  - Behavior: Matching functions downgraded from P0 (critical) to P1 (warning) with explicit "Domain complexity" label
  - Impact: 26 god functions in codeindex → 4 P0 (real debt) + 22 P1 (domain complexity)
  - Design pattern: Similar to ADR-012 orphan whitelist (99 → 0 false positives)

## [0.9.1] - 2026-03-07

### Fixed

#### Critical Bug Fixes
- **Issue #26**: Fixed `find`/`query`/`graph` commands crash due to incorrect `workspace` parameter in `get_graph_stats()` calls
  - Root cause: `client.get_graph_stats(workspace=ws)` but method doesn't accept workspace parameter (passed via HTTP header)
  - Impact: All query commands were completely broken (blocking core functionality)
  - Solution: Removed invalid `workspace=` parameter from 2 calls in `_common.py`
  - Testing: All 10 resolve_workspace tests + 125 core CLI tests pass
  - Commit: aa9b9ac

#### Accuracy Improvements (Issue #28)
- **Orphan Entity Detection**: Reduced false positive rate from ~70% to ~10%
  - Root cause: Classes and `__init__` methods stored as separate entities (e.g., `MyClass` flagged as orphan but `MyClass.__init__` has 18 callers)
  - Solution: Aggregate class + constructor relations before orphan detection
  - Enhancement: Added regex whitelist for common data classes (`*Config`, `*Result`, `*Info`, `*Error`, `*Data`, `*DTO`, `*Model`, `*Schema`)
  - Impact: codeindex dogfooding improved from 81 orphans (57 false positives) to ~24 orphans (~8 false positives)

- **Hotspot Detection**: Reduced false positive rate from ~32% to ~10%
  - Root cause: Auto-generated files flagged as hotspots (README_AI.md, CHANGELOG.md, *.lock)
  - Solution: Added `AUTOGEN_FILE_PATTERNS` to filter auto-generated files
  - Patterns: `README_AI.md`, `**/README_AI.md`, `CHANGELOG.md`, `poetry.lock`, `package-lock.json`, `**/__pycache__/**`, `**/*.pyc`
  - Impact: codeindex dogfooding improved from 63 hotspots (20 false positives) to ~43 hotspots (~4 false positives)

### Added

#### Skill Enhancements
- **Skill B v2** (Issue #27): Upgraded `sync-advisor` with Git history integration
  - New Step 2.5: Git history quality analysis (hotspots, knowledge silos, bug magnets)
  - Enhanced Step 4: Git-dimension-weighted conflict prediction algorithm
    - Risk scoring: `base_risk + (hotspot +20) + (silo +30) + (bug_magnet +25) + (quality_decline +15) + (dual_modify +25)`
    - Risk tiers: 🟢 0-30 (auto-merge), 🟡 31-60 (manual review), 🔴 61-100 (staged merge)
  - New Step 5: Quality trend comparison (optional, requires ≥3 snapshots)
  - Report enhancements:
    - Added "Upstream Health Score" and "Downstream Health Score" fields
    - Added "Upstream Change Quality Analysis" section with risk-tiered file tables
    - Added "Quality Trend Comparison" section (monthly change rates + predictions)
  - Graceful degradation: Non-Git projects auto-skip Git analysis steps
  - Documentation: Expanded from 213 → 531 lines
  - Commit: 5249546

### Performance
- Overall technical debt analysis accuracy improved from ~60% to **~90%+**
- No performance regressions (all operations <1 second)

### Testing
- Added 5 new unit tests (orphan aggregation, whitelist patterns, autogen filtering)
- All 441 tests passing
- Test coverage maintained at >90% for core modules

## [0.9.0] - 2026-03-07

### Added - EPIC-010: Git Metrics Integration

#### Feature 1: Git History Metrics Analysis
- **`loomgraph git-metrics` command**: Analyze repository git history for technical debt indicators
  - `GitMetricsAnalyzer` class: Extract file-level metrics from git log (change frequency, churn, authors, bug fixes)
  - `GitLogParser` class: Parse git log --numstat output with bug fix detection (keywords: fix, bug, patch)
  - Hotspot detection: Calculate hotspot score = change_frequency × log10(churn + 1) × 10
  - Bus factor analysis: Identify knowledge silos (1 contributor = critical, 2 contributors + >70% ownership = high risk)
  - CLI options: `--since "3 months"` (time window), `--output metrics.json` (save results)
  - 13 unit tests + 1 integration test (all passing)

#### Feature 2: Three-Dimensional Debt Scoring
- **Enhanced `loomgraph debt` command**: Integrate git metrics into debt analysis (optional `--with-git` flag)
  - Three-dimensional scoring: `(quality + topology + git) // 3` (when `--with-git` enabled)
  - Backward compatible: Two-dimensional scoring `(quality + topology) // 2` (default)
  - New issue categories:
    - `critical_hotspot` (P0): High-frequency change files (hotspot_score ≥ 80) with high coupling (in_degree > 8)
    - `knowledge_silo` (P1): Single-contributor files (bus factor = 1) or 2 contributors with >70% ownership
  - Issue enrichment:
    - `orphan_entity`: Add confidence field (high/medium/low based on last_modified_days > 365/90/0)
    - `god_function`: Add is_hotspot marker + upgrade to P0 if change_frequency > 10
  - Graceful fallback: Non-git projects or git errors → git_score = 100 (no penalty)
  - CLI options: `--with-git` (enable git analysis), `--git-since "3 months"` (time window)
  - 7 unit tests (all passing, including graceful fallback test)

#### Feature 3: Code Rot Trend Analysis
- **`loomgraph trends` command**: Linear regression-based trend analysis for detecting code complexity growth over time
  - `TrendAnalyzer` class: Load historical snapshots, calculate linear regression (least squares), generate ASCII charts
  - Linear regression: slope/intercept/R² calculation with trend direction classification (increasing > 0.1/day, decreasing < -0.1/day, stable otherwise)
  - Forecast: Predict next period value (30 days ahead)
  - Alert generation: Rapid growth warning when slope > 0.15/day (~4.5/month)
  - ASCII chart visualization: 60×16 character grid with data points (●) and trend line (─)
  - Auto-save integration: `loomgraph debt` automatically saves project-level snapshot to `~/.loomgraph/metrics-history/`
  - Snapshot cleanup: Delete snapshots older than 12 months (default)
  - CLI options: `-e <entity>` (entity to analyze), `-m <metric>` (metric name, default: complexity), `--months N` (time window, default: 6), `-w <workspace>` (workspace filter)
  - 13 unit tests (all passing, <1 second performance requirement verified)

#### Documentation
- **ADR-015: Git-Knowledge Graph Integration**: Technical design for three-dimensional debt analysis with git metrics integration strategy (originally mis-numbered ADR-013; renumbered 2026-07-05 to resolve collision with the sqlite-vec ADR-013)
- **EPIC-010-git-metrics-integration.md**: Complete epic specification with 3 features and acceptance criteria
- **EPIC-010-technical-design.md**: Detailed technical design covering data models, algorithms, CLI design, and integration points
- **DEBT_REPORT_FORMAT.md**: Technical debt report format specification with JSON schema and output examples
- **debt-report-v1.schema.json**: JSON Schema for debt report validation
- **DOGFOODING_EPIC010.md**: Dogfooding results documenting 5 bugs found and fixed (timezone mismatch, error handling, UX improvements)

#### Infrastructure
- **Makefile**: Unified command interface for all development, testing, and release workflows. 40+ commands organized into 9 categories (Development, Release Management, Token Management, Packaging, CLI, Docker, Git). Run `make help` to see all available commands.
- **Delivery summary generator**: `scripts/generate_delivery_summary.py` - automated customer delivery document generation with install commands, token info, release highlights, and delivery instructions. Integrated into release workflow.
- **ADR-011: AI Iteration Strategy**: Architectural decision documenting "external iteration" approach - LoomGraph provides high-quality atomic capabilities, Claude controls iteration. Analyzed Manon's "internal iteration" model and concluded external iteration offers better cost (40-60% savings), performance (75% faster), transparency, and flexibility.
- **ADR-012: Technical Debt Analysis Format**: Standardized multi-dimensional scoring system (Maintainability + Testability + Impact + Coupling = 0-40 score) with three output formats (JSON/Markdown/Console). Defines clear responsibility boundaries between codeindex (static analysis) and LoomGraph (graph analysis). Decision rules: ≥35 keep, 25-34 refactor, <25 rewrite.

### Changed
- **Release workflow**: Now recommends `make release VERSION=x.y.z` as the primary method (auto-runs bump → test → lint → commit → tag → push)

### Fixed
- **Trends timezone handling**: Fixed `TypeError` when comparing naive and aware datetimes. All functions now use `datetime.now(UTC)` consistently.
- **Trends slope display**: Clarified slope units by displaying both `/month` and `/day` (e.g., "Slope: +30.00/month (+1.000/day)")
- **Trends X-axis labels**: Same-day snapshots now show time ("HH:MM") instead of duplicate dates
- **Trends error handling**: Changed `ErrorCode.OPERATION_FAILED` (non-existent) to `LIGHTRAG_ERROR` for proper error reporting
- **Test suite UTC consistency**: All trend tests now use UTC-aware datetimes to prevent future timezone bugs

### Performance
- **Git metrics**: 99 hotspots + 159 bus factors analyzed in < 3 seconds (self-analysis on LoomGraph project)
- **Trend analysis**: < 1 second for 6 months of data (10 snapshots, verified in performance test)
- **Three-dimensional debt scoring**: No performance degradation when `--with-git` enabled (~2s for 278 issues on LoomGraph project)

## [0.8.0] - 2026-02-24

### Added
- **GitHub Token management system**: Comprehensive enterprise-grade token lifecycle management for online customer access
  - `docs/guides/TOKEN_MANAGEMENT.md` (26KB): Complete guide covering Fine-grained PAT creation, storage solutions (password managers/GPG), secure delivery methods, lifecycle management, and security best practices
  - `docs/guides/TOKEN_QUICKSTART.md`: 5-minute quick start guide with 4 common scenarios and customer installation templates
  - `scripts/manage_tokens.py`: CLI management tool with 4 core features: `--check-expiry` (30-day advance warning), `--list` (customer token status), `--generate-install` (pip/pipx commands), `--verify` (GitHub API validation)
  - Customer delivery packages: `customers/{[customer],[customer],demo}/` with `INSTALL.md` (installation guide with token) and `config.yaml` (service configuration)
  - Token metadata tracking in `customers.yaml` (github_token_name, created/expires dates, last_4 digits, contact info)
  - `customers/DELIVERY_GUIDE.md`: Complete delivery workflow and security checklist

### Changed
- **Workspace fallback**: Query commands (`find`, `query`, `graph`, `topology`, `check`, `impact`, `deps`, `overview`) now automatically fallback to `main`/`develop`/`master` branches when target workspace is empty. Multi-workspace comparison commands (`workspace compare`, `workspace similar`) require explicit workspace specification. Improves UX for 80% use case (single knowledge graph workflow). See Issue #20 Phase 1.
- **`resolve_workspace_with_fallback()`**: new core function in `cli/_common.py` that transparently resolves workspace with fallback to main branches, controlled by `allow_fallback` parameter. Displays info message when fallback occurs.
- **Token management in PACKAGING.md**: Enhanced section with links to comprehensive token management guides and quick reference for management tools.

### Fixed
- **Token verification proxy compatibility**: Added `trust_env=False` to `httpx.Client` in `manage_tokens.py` to avoid socksio dependency when system has SOCKS proxy configured.

## [0.7.0] - 2026-02-22

### Added - EPIC-003: Incremental Update Strategy
- **GitHub Action integration**: reusable workflow (`.github/workflows/incremental-update.yml`) for CI/CD automatic knowledge graph updates on push. Uses `codeindex affected --json` for smart change detection.
- **Post-commit hook**: `loomgraph hooks install/uninstall/status` commands for git hook management. Hook template in `scripts/hooks/post-commit` with 4 modes (auto/sync/async/disabled) via environment variables.
- **`loomgraph update` enhanced**: new `--files`, `--lightrag-url`, `--embedding-url`, `--use-affected` parameters for GitHub Action and hook integration.
- **Customer quickstart solution**: `quickstart.sh` (one-command installation), `upgrade.sh` (one-command upgrade), comprehensive `CUSTOMER_QUICKSTART.md` guide. Zero-configuration demo packages with pre-configured service URLs.
- **CLAUDE.md documentation**: added "自动更新与 Claude Code 感知" section with data flow diagrams, initialization/upgrade scenarios, and MCP Skills auto-discovery mechanism.
- **Package script enhancements**: `scripts/package.py` now supports `--mode demo/upgrade` for different package types, includes both `codeindex` and `loomgraph` wheels for offline installation, and generates customer-specific demo/upgrade packages.
- **codeindex affected fix** (upstream): added `affected_files` field to JSON output for GitHub Action integration (commits 3bc5fab, 09f74c8 in codeindex repo).

### Fixed
- **Package script**: added proper exception handling to `build_wheel()` function to prevent build failures.

### Changed - EPIC-009: Topology Analysis & Freshness Checks
- **`get_auto_workspace()`**: default workspace format changed from `project` to `project:branch` (e.g. `loomgraph:develop`). Non-git directories fallback to directory name only. Explicit `-w` argument unaffected.
- **`status` command**: now includes `workspace` field with current workspace name and entity/relation counts from LightRAG.
- **Server-side coupling**: `TopologyAnalyzer` now auto-detects `source_prefix` from source_ids and passes it to `/graph/stats` for correct module extraction. `get_graph_stats()` supports `module_depth` parameter.
- **Topology threshold tuning**: default `god_threshold` raised 5→10, `hub_threshold` 5→8. Scoring thresholds raised (god: 15/25, hub: 15) with per-category caps (god -25, hub -20, placeholder -15). Module-type entities excluded from god function detection.
- **Server-side field normalization**: orphans/hubs/gods now have `entity_type` → `type` field mapping for consistent output format. `most_coupled_pairs` computed client-side when server doesn't return pair detail.

### Added - EPIC-009: Topology Analysis & Freshness Checks
- **`topology` command**: graph topology debt analysis detecting orphan entities, hub fragility, god functions, placeholder modules, and cross-module coupling density. Supports `--module` prefix filter and configurable thresholds. Dual-mode: server-side (efficient) with automatic client-side fallback.
- **`check` command**: index freshness verification — validates entity source_ids against disk files, reports stale ratio and suggests rebuild.
- `LightRAGClient`: 4 new methods (`get_orphan_entities`, `get_degree_distribution`, `get_graph_stats`, `get_source_ids`) for server-side graph analytics (degradation-ready).
- **Skill A (debt-radar) enhanced**: added Step 5 (topology) + Step 6 (check), expanded analysis from 3 to 7 dimensions, enriched report template with topology and freshness sections.
- 38+ new unit tests for topology analysis, scoring, and CLI commands.

### Added - EPIC-008: Search Architecture Redesign
- **`find` command**: structured entity discovery with `--type` filter, `--with-relations` for callers/callees in one call, `--depth N` for BFS expansion. Replaces `search`.
- **`query` command**: semantic knowledge Q&A via LightRAG RAG engine. Supports `--mode hybrid|local|global|naive`. Includes error handling for LLM unavailability with `find` fallback suggestion.
- **`graph` source_id enhancement**: graph results now include `source_id` (file path) for the queried entity and all callers/callees.
- `search` retained as hidden alias with deprecation warning (one version transition period).
- 17 new unit tests for find, query, graph enhancements, and BFS helpers.

### Changed - Infrastructure
- **CLI module split**: refactored `cli/main.py` (1722 lines, 42 functions) into 8 focused submodules (`_common`, `_deps_check`, `_indexing`, `_search`, `_analysis`, `_workspace`, `_setup`, `_hooks`). Entry point `main.py` reduced to 46 lines. All 265 tests pass, backward-compatible re-exports preserved.

## [0.6.1] - 2026-02-21

### Changed
- **Injection migration**: replaced N× `batch_create_graph()` (entity/create + relation/create) with single `insert_custom_kg()` call — ~636x faster on typical projects (~350s → <1s).
- `delete_all()` simplified to single `DELETE /graph/clear` (clears all 11 storage layers).
- `loomgraph update` now uses `DELETE /graph/by_source` + `insert_custom_kg` for true incremental update (delete old → re-inject changed files).

### Added
- `LightRAGClient.delete_by_source()`: delete entities/relations/chunks by source_id list.
- `build_chunks()`: generates per-file chunks with module docstring + symbol signatures, enabling semantic search via document layer.
- `create_external_stubs()`: extracted stub entity creation logic for reuse across injection paths.
- 18 new unit tests for `insert_custom_kg`, `delete_by_source`, `build_chunks`, `create_external_stubs`.

## [0.6.0] - 2026-02-20

### Added
- `loomgraph workspace list` command: list all workspaces with entity/relation counts (EPIC-005).
- `loomgraph workspace info [NAME]` command: workspace details with top entities (EPIC-005).
- `loomgraph workspace delete NAME` command: delete a workspace and all its data (EPIC-005).
- `loomgraph compare` command: cross-workspace entity/relation structural diff (EPIC-006).
- `loomgraph similar` command: cross-workspace similar entity search with exact + fuzzy matching (EPIC-006).
- `CompareAnalyzer` and `SimilarAnalyzer` core modules with full unit test coverage (21 tests).
- `/loomgraph-debt-radar` skill: technical debt audit report with dependency analysis (EPIC-007).
- `/loomgraph-sync-advisor` skill: cross-branch merge advice with conflict prediction (EPIC-007).
- `/loomgraph-evolution` skill: code evolution tracking across versions with fork divergence analysis (EPIC-007).

### Changed
- Docs reorganized: archived 11 outdated files, consolidated LightRAG integration docs, migrated issues to GitHub.

## [0.2.5] - 2026-02-19

### Fixed
- **BUG-4**: External dependencies (Spring, Dubbo, etc.) no longer cause relation injection failures. Auto-creates stub entities for missing targets (Pass 1.5 in `batch_create_graph`). Relations increased from 68 to 451 on typical project.
- **BUG-5**: Version display inconsistency between `pipx list` and `loomgraph --version`. Switched to `importlib.metadata.version()` and synced `pyproject.toml`.
- Injection now uses `/graph/*` endpoints instead of `/documents/insert_custom_kg` — data appears in graph query layer (`/graphs`, `/graph/label/list`).

### Added
- `loomgraph deps` command: module-level dependency analysis with `--depth` grouping (EPIC-004).
- `loomgraph overview` command: project module overview with entity stats, top entities, and optional LLM summaries (EPIC-004).
- `DepsAnalyzer` and `OverviewAnalyzer` core modules with full unit test coverage.
- `LightRAGClient.get_all_entities()` and `get_all_relations()` methods for bulk graph retrieval.
- `batch_create_graph()` method: three-pass injection (entities → external stubs → relations) with concurrent HTTP and connection pooling.
- `--verbose/-v` and `--quiet/-q` global CLI flags for controlling log output.
- `external_stubs` count in index/update JSON output.
- ADR-009: Workspace redefined from isolation mechanism to knowledge snapshot.
- EPIC-005: Workspace management commands (list/info/delete) planned.
- EPIC-006: Cross-workspace comparison (compare/similar) planned.

### Changed
- All logging explicitly routed to stderr; JSON output is stdout-only (pipe-safe).
- Removed dead `--verbose` parameter from `index` and `update` subcommands (replaced by global flag).

## [0.2.4] - 2025-02-10

### Added
- Auto-detect workspace from current directory name (`get_auto_workspace`)

### Changed
- `--workspace/-w` is now optional across all CLI commands, defaults to `cwd.name`

## [0.2.3] - 2025-02-10

### Added
- `--workspace/-w` option for multi-project workspace isolation via `LIGHTRAG-WORKSPACE` header
- Knowledge graph update strategy guide in README template (for customer AI Agents)

### Changed
- Template-based packaging system (`README.template.md` + `customers.yaml`)
- `package.py` renders templates with `{{variable}}` placeholders

## [0.2.2] - 2025-02-10

### Added
- Customer packaging system with `scripts/package.py`
- `customers/CHANGELOG.md` and `customers/VERSION` for version tracking
- `/loomgraph-setup` skill with version check step

### Changed
- `.gitignore` updated to exclude customer-sensitive configs

## [0.2.1] - 2025-02-10

### Added
- `loomgraph index --clear` - Cold Rebuild (clear and re-index)
- `loomgraph update [--since REF]` - Warm Update (incremental git diff indexing)
- `loomgraph version` command

### Changed
- Switched to LightRAG `insert_custom_kg` API for batch injection (~5x faster)
- Use `codeindex parse` for single-file parsing in update flow

### Fixed
- Path-to-module conversion in injector (`4f7bdb3`)

## [0.2.0] - 2025-02-09

### Added
- `loomgraph index <path>` - index codebase into LightRAG
- `loomgraph search "<query>"` - semantic code search (local/global/hybrid modes)
- `loomgraph graph "<entity>"` - call graph and dependency queries
- `loomgraph status` - service health check (LightRAG, embedding, codeindex)
- `/loomgraph-setup` skill - configure codeindex and language parsers
- `/loomgraph-init` skill - initialize project CLAUDE.md
- LightRAG HTTP API integration with E2E tests
- YAML config file support (`.loomgraph.yaml`)

### Changed
- Clarified storage ownership: LoomGraph delegates all storage to LightRAG API
- Switched impact analysis from Python API to codeindex CLI for loose coupling

### Fixed
- System proxy bypass in status command and LightRAG client
- CLI entry point path in `pyproject.toml`

## [0.1.0] - 2025-02-08

### Added
- Initial project structure and MVP configuration
- Core module scaffolding (`core/`, `embedding/`, `mcp/`, `cli/`)
- ADR-005: AST-first extraction strategy
- ADR-006: MVP simplification decisions
- Data contract documentation (codeindex ↔ LightRAG mapping)
- System design document
- Project roadmap, epics, and feature definitions

[Unreleased]: https://github.com/dreamlx/LoomGraph/compare/v0.20.0...HEAD
[0.22.0]: https://github.com/dreamlx/LoomGraph/compare/v0.21.1...v0.22.0
[0.21.1]: https://github.com/dreamlx/LoomGraph/compare/v0.21.0...v0.21.1
[0.21.0]: https://github.com/dreamlx/LoomGraph/compare/v0.20.0...v0.21.0
[0.20.0]: https://github.com/dreamlx/LoomGraph/compare/v0.19.2...v0.20.0
[0.19.2]: https://github.com/dreamlx/LoomGraph/compare/v0.19.1...v0.19.2
[0.19.1]: https://github.com/dreamlx/LoomGraph/compare/v0.19.0...v0.19.1
[0.19.0]: https://github.com/dreamlx/LoomGraph/compare/v0.18.1...v0.19.0
[0.8.0]: https://github.com/dreamlx/LoomGraph/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/dreamlx/LoomGraph/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/dreamlx/LoomGraph/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/dreamlx/LoomGraph/compare/v0.2.5...v0.6.0
[0.2.5]: https://github.com/dreamlx/LoomGraph/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/dreamlx/LoomGraph/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/dreamlx/LoomGraph/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/dreamlx/LoomGraph/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/dreamlx/LoomGraph/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/dreamlx/LoomGraph/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dreamlx/LoomGraph/releases/tag/v0.1.0
