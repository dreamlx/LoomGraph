# Migration Guide — LoomGraph v0.9.x → v0.10.0 → v0.11.0

> **v0.11.0 update** (EPIC-012): embedding service decoupled. See [§ v0.11.0 changes](#v0110-embedding-provider-decoupling) at the bottom.

**EPIC-011 / ADR-013**: LightRAG backend removed, replaced by local SQLite + sqlite-vec.

This is a **Breaking Change** release. Existing customers must cold-rebuild
their knowledge graph. Data is regenerated from `codeindex` so no source-side
data is lost — only the on-disk format changes.

## What changed

| Layer | v0.9.x (was) | v0.10.0 (now) |
|---|---|---|
| Storage | LightRAG HTTP API + PostgreSQL + pgvector | `~/.loomgraph/<workspace>.db` (SQLite + sqlite-vec) |
| Vector | LightRAG-managed Jina embeddings | Caller-provided, written to vec0 virtual table |
| Analytics | H200 custom endpoints (`/graph/orphans`, `/graph/degree`, `/graph/stats`) | Local SQL (`GROUP BY` / `LEFT JOIN`) |
| LLM | LightRAG `/query` (RAG pipeline) | `DirectLLMClient` → OpenAI-compatible chat completions (GLM / OpenRouter / vLLM) |
| `loomgraph query` | Available | **Removed**. Use Claude Code / Codex / Cursor for NL Q&A |
| Config key `lightrag.*` | Present | **Removed** |
| Config key `storage.*` | n/a | New: `backend` (sqlite-only), `db_path` |
| Config key `llm.*` | n/a | New: `provider`, `api_url`, `api_key`, `model` |
| Deployment | H200 needs LightRAG service (port 3001) | No H200 dependency (local SQLite + local LLM/embedding). H200 was retired 2026-07 |

## Upgrade steps

```bash
# 1. Upgrade tooling
pipx install --upgrade ai-codeindex
pipx install --upgrade loomgraph

# 2. (Optional) configure LLM provider — defaults to local Ollama
#    (H200 GLM-4.7 was the v0.10.0 default; H200 retired 2026-07)
cat >> .loomgraph.yaml <<EOF
llm:
  provider: ollama        # ollama | glm | openrouter | vllm
  api_url: http://localhost:11434
  model: gemma3:12b-it-qat
EOF

# 3. Cold rebuild the knowledge graph (creates ~/.loomgraph/<workspace>.db)
loomgraph index --clear .

# 4. Verify
loomgraph status
loomgraph find "<某类名>"
loomgraph graph "<某方法名>"
```

## Rollback

If you need to stay on the LightRAG path, pin the previous minor:

```bash
pipx install "loomgraph==0.9.3"
```

v0.9.x will not receive backports.

## H200 server-side changes

> **H200 was retired 2026-07.** v0.10.0 originally kept the embedding
> service on H200 (port 3002, Jina Code V2); as of v0.11.0 the default
> embedding provider is local Ollama (`http://localhost:11434/v1`,
> `nomic-embed-text`), disabled by default. The instructions below apply
> only to deployments still running H200 at upgrade time.

The LightRAG API (port 3001) and PostgreSQL container can be shut down.
If you still run the H200 embedding service (port 3002, Jina Code V2),
you may keep it running or migrate to local Ollama (recommended):

```bash
# On H200
docker compose down lightrag
docker compose down postgres
# Keep embedding running
```

## Config diff cheatsheet

```yaml
# v0.9.x
lightrag:
  api_url: http://internal.example.invalid:3001
  api_timeout: 30.0

# v0.10.0 — replace with
storage:
  backend: sqlite
  db_path: ~/.loomgraph/{workspace}.db
llm:
  provider: ollama
  api_url: http://localhost:11434
  model: gemma3:12b-it-qat
```

## What if I was relying on `loomgraph query`?

Use a general-purpose agent for natural-language Q&A — Claude Code / Codex /
Cursor all do this better than the LightRAG-backed `query` ever did. For
structured access, `loomgraph find` / `graph` / `topology` cover the
deterministic side.

## Background

See:
- [ADR-013: SQLite + sqlite-vec replace LightRAG](../adr/ADR-013-sqlite-vec-replace-lightrag.md)
- [EPIC-011 on GitHub](https://github.com/dreamlx/LoomGraph/issues/31)

---

## v0.11.0 — Embedding provider decoupling

### What changed

| Layer | v0.10.0 | v0.11.0 |
|---|---|---|
| Embedding default | Auto-connect H200 Jina TEI (`:3002`) | **Disabled by default** (`embedding.enabled: false`) |
| Protocol | Jina HF TEI (`POST /embed`) | OpenAI-compatible (`POST /v1/embeddings`) |
| Provider | Hardcoded Jina | `ollama` (default) / `openai` / `voyage` / `glm` / `vllm` / `custom` |
| Config key `embedding.base_url` | Present | **Renamed to `api_url`** |
| Config key `embedding.enabled` | n/a | New, default `false` |
| Vector dimension | Hardcoded 768 | Configurable; mismatch with existing `.db` raises `SqliteDimensionMismatch` |
| `JinaEmbeddingClient` | Available | Removed |

### Migration

Existing v0.10.0 deployments default-on to Jina/H200. After upgrading:

```bash
pipx install --upgrade loomgraph
```

Edit your `.loomgraph.yaml`:

```yaml
# Replace this (v0.10.0)
embedding:
  provider: jina
  base_url: http://internal.example.invalid:3002
  model: jinaai/jina-embeddings-v2-base-code

# With this (v0.11.0)
embedding:
  enabled: false      # or: true to keep semantic embedding active
  provider: ollama    # or openai / voyage / glm / custom
  api_url: http://localhost:11434/v1
  model: nomic-embed-text
  dimension: 768
```

### Switching embedding provider

If you change `dimension` (e.g. switching to OpenAI's 1536-dim model),
`SqliteGraphStore` will refuse to open the existing `.db` and tell you
to:

```bash
loomgraph index --clear .
```

This is a safety check — vec0 silently retains the original column type
on `CREATE VIRTUAL TABLE IF NOT EXISTS`, so KNN would return garbage if
we let the schema drift.

### Provider quick examples

**Ollama (local, default)**
```bash
ollama pull nomic-embed-text
# embedding.enabled: true is enough; defaults work
```

**OpenAI**
```yaml
embedding:
  enabled: true
  provider: openai
  api_url: https://api.openai.com/v1
  api_key: sk-...
  model: text-embedding-3-small
  dimension: 1536
```

**Voyage AI** (best-in-class for code per Voyage benchmarks)
```yaml
embedding:
  enabled: true
  provider: voyage
  api_url: https://api.voyageai.com/v1
  api_key: pa-...
  model: voyage-code-2
  dimension: 1536
```

**Self-hosted vLLM / TEI in OpenAI mode**
```yaml
embedding:
  enabled: true
  provider: custom
  api_url: http://internal.example.invalid:8000/v1
  model: jinaai/jina-embeddings-v2-base-code
  dimension: 768
```
