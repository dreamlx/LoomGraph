# Migration Guide — LoomGraph v0.9.x → v0.10.0

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
| Deployment | H200 needs LightRAG service (port 3001) | H200 only needs embedding service (port 3002) |

## Upgrade steps

```bash
# 1. Upgrade tooling
pipx install --upgrade ai-codeindex
pipx install --upgrade loomgraph

# 2. (Optional) configure LLM provider — defaults to H200 GLM-4.7
cat >> .loomgraph.yaml <<EOF
llm:
  provider: glm           # glm | openrouter | vllm
  api_url: http://internal.example.invalid:3000
  model: glm-4-flash
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

The LightRAG API (port 3001) and PostgreSQL container can be shut down.
Keep the embedding service (port 3002, Jina Code V2) running:

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
  provider: glm
  api_url: http://internal.example.invalid:3000
  model: glm-4-flash
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
