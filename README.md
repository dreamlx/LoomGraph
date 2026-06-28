# LoomGraph

[![PyPI](https://img.shields.io/pypi/v/loomgraph.svg)](https://pypi.org/project/loomgraph/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-460%20passing-brightgreen.svg)](tests/)

**Local code knowledge graph for AI agents.** SQLite + sqlite-vec, AST-driven,
no RAG framework needed. Designed as a [Claude Code](https://claude.com/claude-code)
plugin and a CLI for any agent that needs precise structural code queries.

> v0.11.0 ships fully local by default. `pipx install loomgraph` and go — no
> remote services, no API keys, no Docker. Semantic vector search is opt-in.

---

## Why LoomGraph

LLM agents are good at fuzzy natural-language code Q&A. They are bad at deterministic
structural queries — "every caller of `authenticate()` across this 200k-LoC codebase,
including indirect callers two hops deep." LoomGraph fills exactly that gap.

- **Deterministic graph queries** — `find` / `graph` / `topology` / `impact` walk
  SQLite, not an LLM. Same input, same output, every time.
- **AST is the source of truth** — call/inherit/import edges come from tree-sitter
  via [codeindex](https://github.com/dreamlx/codeindex), not LLM inference.
- **Single-file storage** — `~/.loomgraph/<workspace>.db`. No Postgres, no Docker,
  no fork of someone else's RAG framework.
- **Vector KNN where it matters** — sqlite-vec virtual tables, caller-provided
  embeddings, OpenAI-compatible provider config (Ollama default).
- **AI-Agent-shaped CLI** — every command emits JSON; designed to be called by
  Claude Code or any agent harness.

## Install

```bash
pipx install loomgraph
```

That's it. No additional services required for the structural commands.

## Quick start

```bash
# Index a repo (uses codeindex under the hood for parsing)
loomgraph index .

# Structural search — fuzzy match on entity names
loomgraph find "UserService"

# Walk the call graph
loomgraph graph "UserService.login" --depth 2

# Topology smells (orphans, hubs, god functions)
loomgraph topology

# Change-impact analysis from a git diff
loomgraph impact HEAD --depth 2

# Cross-module dependency map
loomgraph deps
```

Every command outputs JSON to stdout (logs go to stderr) — pipe-friendly for agents.

## Configuration

LoomGraph reads `.loomgraph.yaml` from the current dir, then `~/.config/loomgraph/config.yaml`.
Env vars (`LOOMGRAPH_<SECTION>__<KEY>`) override file values.

### Minimal (fully local, no remote services)

```yaml
storage:
  backend: sqlite
  db_path: "~/.loomgraph/{workspace}.db"
embedding:
  enabled: false   # turn on later for vec0 semantic search
```

### Semantic search with local Ollama

```bash
# Install once: https://ollama.com
ollama pull nomic-embed-text
```

```yaml
embedding:
  enabled: true
  provider: ollama
  api_url: http://localhost:11434/v1
  model: nomic-embed-text
  dimension: 768
```

### With OpenAI / Voyage / GLM (any OpenAI-compatible /v1/embeddings)

```yaml
embedding:
  enabled: true
  provider: openai
  api_url: https://api.openai.com/v1
  api_key: sk-...
  model: text-embedding-3-small
  dimension: 1536
```

### LLM provider (for `overview` summaries)

```yaml
llm:
  provider: glm        # glm | openrouter | vllm
  api_url: http://localhost:8000/v1
  model: glm-4-flash
```

Most commands work without an LLM. Only `loomgraph overview` (module
summary mode) calls the LLM; `--no-summary` skips it entirely.

## What's in the box

| Command | Purpose | Network calls |
|---|---|---|
| `loomgraph index <path>` | Index a repo | codeindex (local) + optional embedding |
| `loomgraph update` | Incremental from git diff | same |
| `loomgraph find "<query>"` | Fuzzy entity search | none |
| `loomgraph graph "<entity>"` | Walk callers/callees | none |
| `loomgraph topology` | Orphans / hubs / god functions | none |
| `loomgraph debt --with-git` | Tech debt scoring | none (reads `git log`) |
| `loomgraph deps` | Module dependency graph | none |
| `loomgraph impact <ref>` | Deterministic change-impact | none |
| `loomgraph trends --entity X` | Code-rot trend prediction | none |
| `loomgraph overview` | Module summaries | LLM (or `--no-summary`) |
| `loomgraph workspace ...` | Multi-workspace management | none |
| `loomgraph compare / similar` | Cross-workspace diff | none |

## Claude Code integration

LoomGraph ships skills for Claude Code (debt audit, sync advisor, evolution).
After `pipx install loomgraph`, install them into your Claude config:

```bash
loomgraph install-skills
```

Then in any project: `/loomgraph-debt-radar`, `/loomgraph-sync-advisor`, ...

## Architecture (v0.11.0+)

```
codeindex (AST parse)
    ↓
loomgraph (map + persist)
    ↓
~/.loomgraph/<workspace>.db (SQLite + sqlite-vec, single file)
    ├── entities       (functions / classes / modules)
    ├── relations      (CALLS / INHERITS / IMPORTS / ...)
    ├── vec_node_descriptions  (vec0, optional)
    └── vec_code_snippets      (vec0, optional)
         ↑
Claude Code / Codex / Cursor — read via CLI (JSON) or upcoming MCP
```

The full architecture rationale is in
[ADR-013](docs/adr/ADR-013-sqlite-vec-replace-lightrag.md).

## Status

- v0.10.0 — LightRAG and PostgreSQL removed; local SQLite backend
- v0.11.0 — Embedding provider decoupled; OpenAI-compatible by default, off by default

495 unit tests passing, ruff clean. Dogfood-benchmarked on `loomgraph`
(10.9k LoC, indexed in 0.88s) and `codeindex` (22.0k LoC, indexed in
0.93s) with sub-0.4s wall on every query — see
[docs/benchmarks/dogfood.md](docs/benchmarks/dogfood.md) for the full
numbers, including round-trip preservation of `codeindex graph-export`
artifacts (81-85% relation coverage vs direct index). Larger fixture
benchmarks (Django/FastAPI-scale) are still pending and are an honest
gap in the README's earlier claims. See [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
