# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] - 2026-02-22

### Added - EPIC-003: Incremental Update Strategy
- **GitHub Action integration**: reusable workflow (`.github/workflows/incremental-update.yml`) for CI/CD automatic knowledge graph updates on push. Uses `codeindex affected --json` for smart change detection.
- **Post-commit hook**: `loomgraph hooks install/uninstall/status` commands for git hook management. Hook template in `scripts/hooks/post-commit` with 4 modes (auto/sync/async/disabled) via environment variables.
- **`loomgraph update` enhanced**: new `--files`, `--lightrag-url`, `--embedding-url`, `--use-affected` parameters for GitHub Action and hook integration.
- **Customer quickstart solution**: `quickstart.sh` (one-command installation), `upgrade.sh` (one-command upgrade), comprehensive `CUSTOMER_QUICKSTART.md` guide. Zero-configuration demo packages with pre-configured service URLs.
- **CLAUDE.md documentation**: added "自动更新与 Claude Code 感知" section with data flow diagrams, initialization/upgrade scenarios, and MCP Skills auto-discovery mechanism.
- **codeindex affected fix** (upstream): added `affected_files` field to JSON output for GitHub Action integration (commits 3bc5fab, 09f74c8 in codeindex repo).

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
