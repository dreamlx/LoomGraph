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

All 8 tools follow the same response envelope:

```jsonc
// success
{"success": true, "data": { /* the same dict the CLI command would emit */ }}

// error
{"success": false, "error": {"code": "FIND_FAILED", "message": "...", "suggestion": "..."}}
```

### `loomgraph_find`

| arg | type | default | desc |
|---|---|---|---|
| `query` | string | required | name fragment to fuzzy-match |
| `entity_type` | enum | — | class \| function \| method \| module |
| `limit` | integer | 20 | 1..100 |
| `with_relations` | boolean | false | include callers + callees |
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

## Other agents

The MCP protocol is portable. Anything that speaks stdio MCP works:

- **Cursor**: add to its MCP config (same shape)
- **Cline**: same
- **Custom harness via `mcp` Python SDK**: import + connect to
  `loomgraph mcp serve` as a child process

## Performance budget

Numbers from a smoke run on the dogfood benchmark workspace
(`loomgraph-bench:main`, 1300 entities / 2319 relations):

| Path | Wall (cold) | Notes |
|---|---|---|
| CLI subprocess (`loomgraph find Foo`) | ~240ms | Python startup + Click + SQL |
| In-process call (`await _async_find(...)`) | ~8ms | bare async + SQL |
| MCP stdio call | (TODO: measure end-to-end) | adds IPC; expect ~10-15ms |

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
