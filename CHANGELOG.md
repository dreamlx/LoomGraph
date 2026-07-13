# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- `customers/DELIVERY_GUIDE.md` redacted: 6 plaintext GitHub PATs (customer /
  customer / demo) replaced with placeholders. **git history still contains
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
  - Customer delivery packages: `customers/{customer,customer,demo}/` with `INSTALL.md` (installation guide with token) and `config.yaml` (service configuration)
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

[Unreleased]: https://github.com/dreamlx/LoomGraph/compare/v0.6.0...HEAD
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
