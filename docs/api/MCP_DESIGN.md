# LoomGraph MCP Server

> Native Model Context Protocol (MCP) server for loomgraph's read-side
> query surface. Lets Claude Code, Codex, Cursor, and any MCP-aware
> agent harness call `find` / `graph` / `topology` / etc. as
> first-class tools without the ~250ms Python-startup penalty per
> CLI subprocess invocation.

## TL;DR

```bash
# 1. install
pipx install loomgraph

# 2. index a repo (one-time setup; needs codeindex)
pipx install ai-codeindex
loomgraph index .

# 3. tell Claude Code where to find loomgraph (writes ~/.claude/mcp.json)
loomgraph mcp install-config --path ~/.claude/mcp.json

# 4. restart Claude Code — done.
# Tools auto-discovered: loomgraph_find / loomgraph_graph / ...
```

For users who only consume artifacts (no local indexing): skip `ai-codeindex`
install. Use `loomgraph import-export <artifact>.ndjson` to load a
graph artifact someone else produced, then the MCP server serves it.

## Why MCP (vs subprocess CLI)

The CLI already emits JSON. So what's MCP buying?

| | CLI subprocess | MCP server |
|---|---|---|
| Per-call overhead | ~250ms (Python interpreter + Click) | ~5ms (IPC + SQL) |
| Tool discovery | agent must know command names | listed in the protocol |
| Schema | implicit (parse JSON output) | typed `inputSchema` per tool |
| Error envelope | exit code + stderr text | structured `{success, error: {code, message, suggestion}}` |
| Conversation flow | one-shot | long-lived; state stays warm |

For an agent that issues 30+ tool calls in a single conversation (which
spike-30 measured — see `docs/spikes/spike-30/REPORT.md`), the
subprocess overhead alone is ~7.5s. MCP makes that vanish.

## Tool reference

All tools follow the same response envelope — 12 read tools plus the
`loomgraph_refresh` write tool (ADR-014, the first MCP-exposed write
surface):

```jsonc
// success
{"success": true, "data": { /* the same dict the CLI command would emit */ }}

// error
{"success": false, "error": {"code": "FIND_FAILED", "message": "...", "suggestion": "..."}}
```

### `loomgraph_refresh` (write — ADR-014)

First write-capable MCP tool. Reactive working-tree re-index (pull-mode):
an agent that just edited a file (uncommitted, incl. untracked) can
re-index it on demand instead of waiting for a commit. Complementary to
the commit-driven git-hook `update`. Shells `codeindex graph-export`, so
ai-codeindex must be installed (query-only deployments still work without
it — refresh is the only tool that needs codeindex). Returns
`{"mode": "noop"}` on a clean tree with no `path`.

| arg | type | default | desc |
|---|---|---|---|
| `path` | string | — | file/dir prefix to refresh (omit = all working-tree changes) |
| `force_full` | boolean | false | cold whole-tree rebuild (clear + re-ingest) |
| `workspace` | string | server default | per-call workspace override |

### `loomgraph_find`

| arg | type | default | desc |
|---|---|---|---|
| `query` | string | required | name fragment to fuzzy-match |
| `entity_type` | enum | — | class \| function \| method \| module |
| `limit` | integer | 20 | 1..100 |
| `with_relations` | boolean | false | include callers + callees |
| `workspace` | string | server default | per-call workspace override |

### `loomgraph_search`

Semantic peer of `find` (EPIC-015 / #70). Embeds the query and returns
the nearest entities by vector distance over `vec_node_descriptions`
(signature + docstring). Use for intent questions whose words may not
appear in any symbol name. **Requires the workspace indexed with
embedding enabled** (`LOOMGRAPH_EMBEDDING__ENABLED=true`); returns
`EMBEDDING_NOT_INDEXED` otherwise.

| arg | type | default | desc |
|---|---|---|---|
| `query` | string | required | natural-language intent or descriptive phrase |
| `entity_type` | enum | — | class \| function \| method \| module |
| `limit` | integer | 20 | 1..100 |
| `workspace` | string | server default | per-call workspace override |

### `loomgraph_graph`

| arg | type | default | desc |
|---|---|---|---|
| `entity_name` | string | required | qualified name (use `loomgraph_find` first) |
| `direction` | enum | both | callers \| callees \| both |
| `relation_type` | enum | all | CALLS \| INHERITS \| IMPORTS \| all |
| `workspace` | string | server default | — |

### `loomgraph_topology`

| arg | type | default | desc |
|---|---|---|---|
| `hub_threshold` | integer | 10 | min incoming edges to flag |
| `god_threshold` | integer | 10 | min outgoing edges to flag |
| `module` | string | — | source_id prefix filter |
| `workspace` | string | server default | — |

### `loomgraph_impact`

| arg | type | default | desc |
|---|---|---|---|
| `target` | string | HEAD | git ref / commit SHA |
| `staged` | boolean | false | analyze staged diff |
| `base` | string | — | base ref to diff against |
| `depth` | integer | 2 | caller-chain depth |
| `file_path` | string | — | scope to one file |
| `workspace` | string | server default | — |

### `loomgraph_deps`

| arg | type | default | desc |
|---|---|---|---|
| `depth` | integer | 2 | module-traversal depth |
| `workspace` | string | server default | — |

### `loomgraph_overview`

| arg | type | default | desc |
|---|---|---|---|
| `depth` | integer | 1 | module hierarchy depth |
| `no_summary` | boolean | false | skip LLM (return counts only) |
| `workspace` | string | server default | — |

### `loomgraph_workspace_list`

No arguments. Returns every workspace under `~/.loomgraph/`.

### `loomgraph_workspace_info`

| arg | type | default | desc |
|---|---|---|---|
| `name` | string | server default | workspace to inspect |

### `loomgraph_debt` · `loomgraph_check` · `loomgraph_git_metrics` (v0.15.0, #62)

The three debt-audit dimensions, exposed as standalone read primitives
(previously reachable only via the `loomgraph_debt_audit` composite).
Side-effect-free; an agent in a session where the composite isn't loaded
can still reach each dimension individually. `loomgraph_debt` runs the
topology + git layers (the codeindex *static* layer needs a JSON file the
MCP caller rarely has — use `loomgraph debt --codeindex-data` CLI for that).
`loomgraph_debt` and `loomgraph_topology` accept `scope` (#61).

## Composite tools (v0.12.1)

In addition to the 11 primitive read tools above, three **composite
tools** were added in v0.12.1 to subsume the legacy workflow skills
(`/loomgraph-debt-radar`, `/loomgraph-evolution`,
`/loomgraph-sync-advisor` — these skills were **removed in v0.15.0**,
see #64). Each composite fans out across multiple primitives in parallel
and returns one structured response — the agent composes the prose
narrative.

### `loomgraph_debt_audit`

10-dimension debt report in a single MCP call. Replaces
`/loomgraph-debt-radar`. Runs `debt` + `deps` + `overview` +
`topology` + `workspace_info` + `check` + (optional) git-metrics +
(optional) trends-of-top-N-hotspots, all in parallel.

| arg | type | default | desc |
|---|---|---|---|
| `source_path` | string | `.` | path passed to git-metrics + freshness check |
| `with_git` | boolean | true | enable git-history dimensions; auto-disables if not a git repo |
| `git_since` | string | "3 months" | git history window |
| `trends_top_n` | integer | 3 | how many top-hotspot files to forecast; 0 to skip |
| `workspace` | string | server default | — |

Returns:
```jsonc
{
  "workspace": "...",
  "git_enabled": true,
  "dimensions": {
    "debt": {"data": {...}, "error": null},
    "deps": {"data": {...}, "error": null},
    "overview": {"data": {...}, "error": null},
    "topology": {"data": {...}, "error": null},
    "workspace_info": {"data": {...}, "error": null},
    "check": {"data": {...}, "error": null},
    "git_metrics": {"data": {...}, "error": null}    // if git_enabled
  },
  "trends": [/* one entry per hotspot */],
  "summary": {"dimensions_succeeded": 7, "dimensions_attempted": 7, ...}
}
```

### `loomgraph_evolution_track`

Cross-workspace entity tracking. Replaces `/loomgraph-evolution`.

| arg | type | default | desc |
|---|---|---|---|
| `entity` | string | required | entity name to track (e.g. `AuthService`) |
| `workspaces` | array<string> | required (≥2) | workspaces in chronological order; adjacent pairs compared |

### `loomgraph_sync_advice`

Upstream/downstream merge advisor. Replaces `/loomgraph-sync-advisor`.

| arg | type | default | desc |
|---|---|---|---|
| `upstream` | string | required | source-of-changes workspace |
| `downstream` | string | required | merge-target workspace |
| `module` | string | — | optional scope for debt analysis |
| `git_since` | string | "3 months" | window for `debt --with-git` |
| `impact_entities` | array<string> | `[]` | entities to do callers-of in downstream |

### Graceful per-dimension degradation

Each composite uses `{data, error}` envelopes per dimension so a
single failed call doesn't kill the whole report — useful when git
isn't available, historical snapshots don't exist yet, or a
workspace is missing one of the dimensions. Top-level `success=true`
as long as ≥1 dimension produces data.

## What's NOT exposed (and why)

`index`, `update`, `import-export` are **CLI-only by design**:

1. **They're slow.** Index time on the dogfood codeindex fixture is
   ~0.93s — orders of magnitude longer than a query. Conversational
   tool use isn't the right surface for it.
2. **They mutate state.** Write semantics in an MCP tool are easy to
   misuse by agents that don't realize a tool destroys data.
3. **They require codeindex.** `index` / `update` invoke `codeindex
   scan` as a subprocess. Keeping them out of MCP means the MCP
   server runtime tree doesn't need `ai-codeindex` installed.

If you want index-from-Claude, run `loomgraph index .` in the shell
once (or from a CI/CD job, or a `git-hook`). Then queries through MCP
work against the existing workspace.

This split lets us ship **two install profiles**:

| Profile | Install | Use case |
|---|---|---|
| **Query-only** | `pipx install loomgraph` | Consume artifacts from team/CI; query via MCP |
| **Full local** | `pipx install loomgraph ai-codeindex` | Index your own repos + query |

## Workspace resolution precedence

For each tool call, the workspace is resolved as:

1. **Per-call `workspace` argument** (highest priority)
2. **`LOOMGRAPH_MCP_DEFAULT_WORKSPACE` env var** — set this when
   launching `loomgraph mcp serve` to pin a default
3. **`--default-workspace <name>`** flag on `loomgraph mcp serve`
   — convenience for setting #2
4. **None** — the underlying `_async_*` core falls back to CLI's
   auto-detect (cwd / git branch), but in stdio mode that's the MCP
   server's launch directory, which may not be useful

Tip: set a default if your team works in one workspace at a time;
omit for multi-workspace setups and rely on per-call.

## Claude Code config

`loomgraph mcp install-config` writes (or prints) this:

```json
{
  "mcpServers": {
    "loomgraph": {
      "command": "loomgraph",
      "args": ["mcp", "serve"]
    }
  }
}
```

To pin a default workspace at server start:

```json
{
  "mcpServers": {
    "loomgraph": {
      "command": "loomgraph",
      "args": ["mcp", "serve", "--default-workspace", "myproject:main"]
    }
  }
}
```

Restart Claude Code after the config change. Tools appear under
`loomgraph_*` in the agent's tool list.

## Upgrading loomgraph — new tools need a restart

The MCP server runs as a long-lived subprocess that Claude Code (or
Cursor / Cline) spawns once and keeps alive for the whole session. That
process is pinned to the loomgraph version that was installed when it
started. So **`pipx upgrade loomgraph` alone does NOT surface new
tools** in a running session.

To pick up tools added in a newer release (e.g. the composite
`loomgraph_debt_audit` shipped in v0.12.1):

```bash
pipx upgrade loomgraph          # or: pipx install --force loomgraph
# then fully restart Claude Code (quit + reopen, not just a new chat)
```

Symptoms you'll see if you skip the restart:
- A tool you know shipped (`loomgraph_debt_audit`, …) isn't in the tool
  list, or the agent reports it as unknown.
- `loomgraph mcp serve --version`-style checks show the old version.

This is inherent to the stdio MCP lifecycle, not a loomgraph bug — the
server is whatever binary Claude Code launched. When in doubt, restart
the client to force a fresh `loomgraph mcp serve` spawn.

> **Tip for tool authors / dogfooding**: if you're iterating on a new
> MCP tool locally, each change needs a client restart to take effect.
> For fast inner-loop testing, drive the server directly over stdio
> (see the programmatic dogfood in the v0.12.1 notes) instead of going
> through Claude Code.

## Other agents

The MCP protocol is portable. Anything that speaks stdio MCP works:

- **Cursor**: add to its MCP config (same shape)
- **Cline**: same
- **Custom harness via `mcp` Python SDK**: import + connect to
  `loomgraph mcp serve` as a child process

## Performance budget

Numbers measured end-to-end against `loomgraph-bench:main`
(1300 entities / 2319 relations) on M3 Mac:

| Operation | Wall | Notes |
|---|---|---|
| CLI subprocess (`loomgraph find Foo`) | ~240ms | Python startup + Click + SQL each call |
| MCP `tools/list` | **0.8ms** | server in process, just hands the registry |
| MCP `tools/call loomgraph_find` (cold — first SQL touch opens DB) | **61ms** | dominated by sqlite-vec extension load + first connection |
| MCP `tools/call loomgraph_graph` (warm) | **14.8ms** | IPC + SQL only; this is the steady-state cost |
| MCP error path (unknown tool) | 0.7ms | dispatched in the server, never enters a handler |

vs CLI subprocess: ~**4× speedup cold**, ~**13-16× speedup warm**.
For agent chains of 5+ tool calls (common in spike-30 traces), the
amortized win is closer to the upper bound — the DB stays warm across
calls in the same MCP session.

## Limitations / known gaps

1. **No streaming**: large `topology` / `deps` responses come back
   as one blob. Streaming via MCP is possible but deferred.
2. **No write tools**: see "What's NOT exposed" above. By design.
3. **No long-running process management**: if the MCP server crashes
   mid-session, Claude Code restarts it on next tool call (Claude's
   built-in behavior). No state to recover.
4. **Workspace auto-detect doesn't work meaningfully under stdio**:
   set `--default-workspace` or pass per-call.

## See also

- `docs/api/CLI_DESIGN.md` — full CLI surface (write tools live there)
- `docs/spikes/spike-30/REPORT.md` — why MCP matters for agent tool use
- `docs/benchmarks/dogfood.md` — startup-cost measurements
