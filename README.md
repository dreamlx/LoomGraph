# LoomGraph

[![PyPI](https://img.shields.io/pypi/v/loomgraph.svg)](https://pypi.org/project/loomgraph/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

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

That's it. [codeindex](https://github.com/dreamlx/codeindex) is pulled in automatically as the parser engine — no separate install, no direct operation. No additional services required for the structural commands.

### Multi-language repos — install the matching grammar extra

Python and PHP grammars ship by default. A pure **TypeScript / JavaScript / Swift / Java / Objective-C** repo indexes to 0 (or a few stray) entities unless you install the matching `tree-sitter` grammar — the parser skips files with a warning when the grammar is absent.

```bash
pipx install "loomgraph[typescript]"    # TypeScript / TSX
pipx install "loomgraph[javascript]"    # JavaScript / JSX
pipx install "loomgraph[swift]"
pipx install "loomgraph[java]"
pipx install "loomgraph[objc]"          # Objective-C (.h / .m; .mm not supported)
```

> Quotes are required — `[extra]` is a shell glob in zsh/bash (`no matches found`
> without them). Add several at once: `pipx install "loomgraph[typescript,javascript]"`.
> Then ensure the languages are listed under `languages:` in `.codeindex.yaml`
> (the `/loomgraph-setup` skill generates this via codeindex's own wizard).

### LLM code interpretation — codeindex `--ai`, not loomgraph

LoomGraph's index is **pure AST** (entities, relations, call graph) — no LLM, fully reproducible. If you want **LLM-generated natural-language descriptions** of modules/functions (richer `README_AI.md`, AI-completed docstrings), that's codeindex's own `--ai` mode, which is **orthogonal to loomgraph**:

```bash
# Requires ai_command in .codeindex.yaml (e.g. claude -p, deepseek, etc.)
codeindex scan . --ai          # enrich README_AI.md via LLM
codeindex scan-all --ai        # whole tree
```

- **When you need it**: unfamiliar large codebase where you want an LLM to narrate what each module does, or to fill in missing docstrings.
- **When you don't**: structural queries via loomgraph (`find`/`graph`/`topology`/`deps`). The AST is ground truth there; LLM would only add latency and hallucination risk.
- **Relationship**: loomgraph consumes codeindex's `graph-export` (the structural AST output), never the `--ai` enrichment. The two are independent — `--ai` makes codeindex's human-facing docs richer; loomgraph's graph stays structural either way.

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

## Workspaces

A **workspace** is one indexed snapshot of a codebase, stored as a single
SQLite file at `~/.loomgraph/<workspace>.db`. The name auto-derives from your
current directory and git branch:

```
<repo-dir>:<branch>    # git repo, e.g.  loomgraph:main
<repo-dir>             # non-git fallback (lowercase)
```

So indexing the same repo on two branches gives **two independent graphs** —
querying `feature-x` won't see `main`'s entities, and vice versa. You rarely
type a workspace name: `loomgraph index .` auto-detects it, and every query
command auto-targets the current branch's workspace. Override with `--workspace`.

```bash
loomgraph workspace list          # what's indexed
loomgraph workspace info          # current workspace details (auto-detected)
loomgraph workspace delete NAME --yes   # remove a workspace (unlinks the .db)
```

If the current branch's workspace is empty (e.g. you're on a fresh branch that
was never indexed), query commands **auto-fall-back** to `main` → `develop` →
`master` so you still get results — index the current branch explicitly with
`loomgraph index .` when you want branch-specific data.

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

LoomGraph speaks **MCP (Model Context Protocol)** natively as of v0.12.0.
After `pipx install loomgraph` and one-time indexing (`loomgraph index .`):

```bash
loomgraph mcp install-config --path ~/.claude/mcp.json
```

Restart Claude Code. `loomgraph_find` / `loomgraph_graph` /
`loomgraph_topology` / `loomgraph_impact` / `loomgraph_deps` /
`loomgraph_overview` / `loomgraph_workspace_*` appear as native tools —
no subprocess overhead, no `/skill-name` invocation. Full reference:
[docs/api/MCP_DESIGN.md](docs/api/MCP_DESIGN.md).

Legacy skill commands (debt audit, sync advisor, evolution) still ship
via `loomgraph install-skills` for users who prefer the explicit-invoke
model.

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

600+ unit tests passing, ruff clean. Dogfood-benchmarked on `loomgraph`
(10.9k LoC, indexed in 0.88s) and `codeindex` (22.0k LoC, indexed in
0.93s) with sub-0.4s wall on every query — see
[docs/benchmarks/dogfood.md](docs/benchmarks/dogfood.md) for the full
numbers, including round-trip preservation of `codeindex graph-export`
artifacts (81-85% relation coverage vs direct index). Larger fixture
benchmarks (Django/FastAPI-scale) are still pending and are an honest
gap in the README's earlier claims. See [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
