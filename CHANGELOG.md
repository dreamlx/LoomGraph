# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `loomgraph compare` command: cross-workspace entity/relation structural diff (EPIC-006).
- `loomgraph similar` command: cross-workspace similar entity search with exact + fuzzy matching (EPIC-006).
- `CompareAnalyzer` and `SimilarAnalyzer` core modules with full unit test coverage (21 tests).
- `/loomgraph-sync-advisor` skill: cross-branch merge advice with conflict prediction (EPIC-007).
- `/loomgraph-evolution` skill: code evolution tracking across versions with fork divergence analysis (EPIC-007).

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

[Unreleased]: https://github.com/user/loomgraph/compare/v0.2.5...HEAD
[0.2.5]: https://github.com/user/loomgraph/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/user/loomgraph/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/user/loomgraph/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/user/loomgraph/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/user/loomgraph/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/user/loomgraph/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/user/loomgraph/releases/tag/v0.1.0
