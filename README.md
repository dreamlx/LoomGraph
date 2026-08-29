# LoomGraph

[![PyPI](https://img.shields.io/pypi/v/loomgraph.svg)](https://pypi.org/project/loomgraph/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

**Local code knowledge graph for AI agents.** SQLite + sqlite-vec, AST-driven,
no RAG framework needed. Designed as a [Claude Code](https://claude.com/claude-code)
plugin and a CLI for any agent that needs precise structural code queries.

> v0.18.0 ships fully local by default, including optional built-in semantic
> search (`pipx install "loomgraph[embed]"` — local CPU model, zero services).
> `pipx install loomgraph` and go — no remote services, no API keys, no Docker.

---

## Why LoomGraph

LLM agents are good at fuzzy natural-language code Q&A. They are bad at deterministic
structural queries — "every caller of `authenticate()` across this 200k-LoC codebase,
including indirect callers two hops deep." LoomGraph serves that class of queries
from a local graph.

- **Deterministic graph queries** — `find` / `graph` / `topology` / `impact` walk
  SQLite, not an LLM. Same input, same output — and the outputs **tell you how
  much to trust them**: every analysis carries a `resolved_ratio` (share of edges
  that actually resolved) and orphans are classified as truly-isolated vs
  unresolved-neighbor, so a resolution blind spot (dynamic dispatch, DI
  frameworks, path aliases) is visible instead of silently read as dead code.
- **AST is the source of truth** — call/inherit/import edges come from tree-sitter
  via [codeindex](https://github.com/dreamlx/codeindex), not LLM inference.
- **Single-file storage** — `~/.loomgraph/<workspace>.db`. No Postgres, no Docker,
  no fork of someone else's RAG framework.
- **Semantic search, zero or your-way** — built-in local CodeRankEmbed (int8 ONNX,
  MIT, auto-downloaded once) via the `[embed]` extra, or bring Ollama / any
  OpenAI-compatible embeddings endpoint. The provider choice is sticky per
  workspace so embedding spaces never silently mix.
- **AI-Agent-shaped CLI** — every command emits JSON; designed to be called by
  Claude Code or any agent harness.

## Install

```bash
pipx install loomgraph
```

That's it. [codeindex](https://github.com/dreamlx/codeindex) is pulled in automatically as the parser engine — no separate install, no direct operation. No additional services required for the structural commands.

Want zero-config semantic search too? Add the `[embed]` extra — a 137M code-specialized
embedding model (CodeRankEmbed, MIT, int8 ONNX, ~139MB) runs locally on CPU and
auto-downloads on first use:

```bash
pipx install "loomgraph[embed]"
```

The embedding provider is **sticky per workspace**: `auto` (default) probes a local
Ollama first and falls back to the built-in model; whichever wins is recorded in the
workspace, and later commands reuse the recorded choice — different models produce
incompatible vector spaces, and loomgraph refuses to mix them silently.

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
> If `loomgraph` is already installed with pipx, inject the grammar packages into
> that existing venv instead: `pipx inject loomgraph tree-sitter-typescript
> tree-sitter-javascript` (or use `pipx runpip loomgraph install <package>` on
> older pipx installations).
> Then ensure the languages are listed under `languages:` in `.codeindex.yaml`
> (the `/loomgraph-setup` skill generates this via codeindex's own wizard).

### LLM code interpretation — codeindex `--ai`, not loomgraph

LoomGraph's index is **pure AST** (entities, relations, call graph) — no LLM, fully reproducible. If you want **LLM-generated natural-language descriptions** of modules/functions (richer `README_AI.md`, AI-completed docstrings), that's codeindex's own `--ai` mode, which is **orthogonal to loomgraph**:

```bash
# Requires ai_command in .codeindex.yaml (e.g. claude -p, deepseek, etc.)
loomgraph codeindex scan . --ai     # enrich README_AI.md via LLM (passthrough)
loomgraph codeindex scan-all --ai   # whole tree (passthrough)
```

- **When you need it**: unfamiliar large codebase where you want an LLM to narrate what each module does, or to fill in missing docstrings.
- **When you don't**: structural queries via loomgraph (`find`/`graph`/`topology`/`deps`). The AST is ground truth there; LLM would only add latency and hallucination risk.
- **Relationship**: loomgraph consumes codeindex's `graph-export` (the structural AST output), never the `--ai` enrichment. The two are independent — `--ai` makes codeindex's human-facing docs richer; loomgraph's graph stays structural either way.

## Quick start

```bash
# Index a repo (uses codeindex under the hood for parsing)
loomgraph index .

# Ask for a read-only, Claude Code-first navigation plan
loomgraph orient --task-kind cross-file

# Optional but recommended for Claude Code projects: add the project-level
# rule describing when structural navigation is preferable to text lookup.
loomgraph init

# Structural search — fuzzy match on entity names
loomgraph find "UserService"

# Semantic search — by meaning, not name ([embed] extra or an embedding provider)
loomgraph search "where is authentication handled"

# Walk the call graph
loomgraph graph "UserService.login" --depth 2

# Topology smells (orphans, hubs, god functions) + resolution trust signal
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
`loomgraph index .` when you want branch-specific data. A read-only query for a
missing explicit workspace never creates an empty database: it reports the
fallback or missing-workspace hint on stderr. Use `--workspace NAME` when you
need to select a specific existing workspace.

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

`{workspace}` keeps workspace data in separate SQLite files and is required
for multi-snapshot commands such as `loomgraph branch-diff`.

### Semantic search

Default `provider: auto` (v0.18+): a local Ollama is probed first; if absent, the
built-in model is used (and downloaded once). The choice is recorded per workspace
and reused — flipping providers mid-life would mix incompatible vector spaces, so
switching requires `loomgraph index --clear .`.

**Built-in (zero-config, `[embed]` extra)** — no config at all:

```yaml
embedding:
  enabled: true      # provider: auto → builtin when Ollama is absent
```

**Local Ollama**:

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
| `loomgraph index --at-ref <ref> [-w NAME]` | Index a historical git ref into an isolated, queryable snapshot workspace | codeindex (local), on first run per ref |
| `loomgraph update` | Incremental from git diff | same |
| `loomgraph check` | Index freshness vs source files | none |
| `loomgraph find "<query>"` | Fuzzy entity search | none |
| `loomgraph search "<query>"` | Semantic search (by meaning) | embedding provider (or built-in) |
| `loomgraph graph "<entity>"` | Walk callers/callees | none |
| `loomgraph topology` | Orphans / hubs / god functions + `resolved_ratio` trust signal | none |
| `loomgraph debt --with-git` | Multi-dimensional debt scoring | none (reads `git log`) |
| `loomgraph deps` | Module dependency graph | none |
| `loomgraph impact <ref>` | Deterministic change-impact | none |
| `loomgraph orient --task-kind <kind> [--policy <policy>]` | Read-only first-step navigation plan for Claude Code; returns native, conditional light, or temporal-review guidance without creating an index | none (reads codeindex availability and, for temporal review, git refs) |
| `loomgraph git-metrics` | Hotspots / bus-factor / churn | none (reads `git log`) |
| `loomgraph trends --entity X` | Code-rot trend prediction | none |
| `loomgraph overview` | Module summaries | LLM (or `--no-summary`) |
| `loomgraph workspace ...` | Multi-workspace management | none |
| `loomgraph compare / similar` | Cross-workspace diff / near-duplicates | none |
| `loomgraph branch-diff A..B [--backend codeindex|codegraph]` | Structural diff between two git refs — auto-provisions snapshot workspaces (worktree + cold index), reports added/removed entities+edges, broken/new call chains, explicit L2 content-comparison status, module coupling delta | codeindex (local) by default; codegraph uses the local npm CLI on first run per ref |
| `loomgraph embed-backfill` | Vectors for an un-embedded workspace | embedding provider |
| `loomgraph hooks` | Git hooks for auto-update on commit | none |
| `loomgraph codeindex <cmd>` | Run any codeindex command in loomgraph's pinned env | local |
| `loomgraph import-export <file>` | Ingest a codeindex graph-export NDJSON | none |
| `loomgraph mcp / install-skills / status` | Integration & diagnostics | none |

`loomgraph setup-config` is deprecated (v0.16+) — zero-config defaults made it redundant.

## Claude Code integration

LoomGraph speaks **MCP (Model Context Protocol)** natively as of v0.12.0.
After `pipx install loomgraph` and one-time indexing (`loomgraph index .`):

```bash
# private to this project (Claude Code default)
claude mcp add --scope local loomgraph -- loomgraph mcp serve
claude mcp get loomgraph

loomgraph init
```

Use `--scope project` only when the team intends to commit a shared `.mcp.json`
and each member can install `loomgraph`; Claude Code asks members to approve
project-scoped servers. `--scope user` is for a private cross-project setup.
`loomgraph mcp install-config` prints the matching command without writing host
configuration. Its explicit `--path` option is only for MCP hosts that use a
static JSON file.

Restart Claude Code after registering the server. `loomgraph_find` / `loomgraph_graph` /
`loomgraph_topology` / `loomgraph_impact` / `loomgraph_deps` /
`loomgraph_overview` / `loomgraph_workspace_*` appear as native tools —
no subprocess overhead, no `/skill-name` invocation. Full reference:
[docs/api/MCP_DESIGN.md](docs/api/MCP_DESIGN.md).

For users who prefer explicit skill invocation, `loomgraph install-skills`
installs the bundled `/loomgraph-init` and `/loomgraph-setup` skills into
`~/.claude/skills`. The legacy debt audit, sync advisor, and evolution skills
were removed in v0.15.0; use the MCP composite tools described in
[docs/api/MCP_DESIGN.md](docs/api/MCP_DESIGN.md) instead.

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
    └── meta           (workspace facts: embedding_provider, resolved_ratio)
         ↑
Claude Code / Codex / Cursor — read via CLI (JSON) or native MCP server
```

The full architecture rationale is in
[ADR-013](docs/adr/ADR-013-sqlite-vec-replace-lightrag.md). Chinese-language
user-facing release notes live in [customers/CHANGELOG.md](customers/CHANGELOG.md).

## Status

- v0.18.0 — Built-in zero-config embedding (`[embed]` extra); trust-calculus
  propagation (`resolved_ratio`, orphan classification); single-author bus-factor
  suppression; test-pollution warnings
- v0.17.x — MCP on mcp 2.0; graph-export fail-loud; codeindex 0.35 (Java fixes)
- v0.11.0 — Local-first rewrite: LightRAG / PostgreSQL removed, SQLite + sqlite-vec

600+ unit tests passing, ruff clean. Dogfood-benchmarked on `loomgraph`
(10.9k LoC, indexed in 0.88s) and `codeindex` (22.0k LoC, indexed in
0.93s) with sub-0.4s wall on every query — see
[docs/benchmarks/dogfood.md](docs/benchmarks/dogfood.md) for the full
numbers, including round-trip preservation of `codeindex graph-export`
artifacts (81-85% relation coverage vs direct index). Larger fixture
benchmarks (Django/FastAPI-scale) are still pending and are an honest
gap in the README's earlier claims. See [CHANGELOG.md](CHANGELOG.md).

For the separate agent-use evaluation boundary, see
[docs/evals/evaluation-v1.md](docs/evals/evaluation-v1.md). It reports
capability and evidence fields per task; it is not a pooled solve-rate claim.
The separate contract for authorised private field-validation cohorts is
[docs/evals/private-field-validation-contract.md](docs/evals/private-field-validation-contract.md);
it publishes methodology only, never customer source or private run artifacts.
The deterministic Track A assertions live in
[evals/capability-manifest.json](evals/capability-manifest.json) — a live gate,
not inert docs: `python evals/run_capability_manifest.py` resolves and runs
every fixture, failing loud if a referenced test is renamed or regresses. The
frozen 12-task DeepSWE manifest is [evals/deepswe/target-manifest.json](evals/deepswe/target-manifest.json).

## License

[MIT](LICENSE)
