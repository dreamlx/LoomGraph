# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/user/loomgraph/compare/v0.2.4...HEAD
[0.2.4]: https://github.com/user/loomgraph/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/user/loomgraph/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/user/loomgraph/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/user/loomgraph/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/user/loomgraph/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/user/loomgraph/releases/tag/v0.1.0
