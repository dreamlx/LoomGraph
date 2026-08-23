# Capability run matrix v1 — approved protocol, runner pending

> **Status: protocol approved; runner pending.** This document does not add a
> result artifact, a performance claim, or an agent-use result. It turns the
> eight reviewed A--C contracts into executable observations; fixture and
> runner implementation remains a separate change.

## Primary question

> 面对一个已声明的结构/时间/比较问题，LoomGraph 能否给出正确、且附带可信度
> 限定的回答；而 `rg` 是否存在等价的单查询答案？

`rg` is a calibration only. It is run only for the two A rows and never timed
against LoomGraph. B and C report `unsupported` rather than inventing an
equivalent text search.

## Proposed fixture package and record

The later fixture package has four tiny versioned repositories:

| Fixture repository | Used by | Required history |
| --- | --- | --- |
| `python-core` | A1, A2, B1, B2 | one immutable commit |
| `python-history` | B3, B4, C1 | `base`, `head`, and `sparse` annotated tags; fixed author/committer dates |
| `factory-receiver` | C1 | `resolved` and `sparse` tags |
| `ts-barrel-alias` | C2 | one immutable commit; barrel and `tsconfig` path-alias cases are separate files |

Each fixture must contain its own `fixture.json` with a content SHA, expected
toolchain versions, source paths, Git refs, and the exact oracle below. The
runner records, but does not aggregate, one JSON record for each `cold` and
`warm` phase:

```json
{
  "fixture": {"id": "...", "sha": "...", "git_ref": "..."},
  "task_id": "...",
  "phase": "cold | warm",
  "toolchain": {
    "loomgraph_version": "...", "codeindex_version": "...",
    "parser_versions": {"python": "..."}, "backend": "codeindex"
  },
  "operation": {
    "index_command": ["..."], "query_command": ["..."],
    "index_clear_wall_ms": 0, "query_wall_ms": 0, "reindexed": false,
    "exit_code": 0, "raw_stdout": "...", "raw_stderr": "..."
  },
  "answer": {"status": "complete | partial | ambiguous | unavailable | error"},
  "trust": {
    "workspace": "...", "source_id": "...", "partial": false,
    "resolved_ratio": 0.0, "internal_unresolved_ratio": 0.0,
    "external_unresolved_ratio": 0.0, "limitations": []
  },
  "oracle": {"passed": true, "failures": []},
  "rg": {"equivalence": "equivalent | unsupported", "command": null,
         "raw_stdout": null, "oracle_passed": null}
}
```

The timing fields distinguish index setup from query execution. They are
diagnostic metadata, never a cross-tool speed score.

`cold` creates a fresh named workspace after clearing its store, then indexes
the fixture. `warm` uses that exact fixture SHA and workspace without a new
index. A changed SHA, Git ref, backend, parser or codeindex version invalidates
the warm record instead of being silently reused.

## Eight proposed observations

`$WS` is a deterministic workspace name derived from fixture SHA and task ID;
`$ARTIFACT` is an adapter-owned output directory outside the fixture. Commands
are specified now but will not be run or reported until the versioned fixture
package and runner exist.

| ID / class | Fixture, LoomGraph observation | `rg` status and oracle | Correct answer oracle | Required answer/trust contract |
| --- | --- | --- | --- | --- |
| A1 exact definition location | `python-core`; `loomgraph find AuthService --type class -n 1 -w "$WS"` after `loomgraph index . --clear -w "$WS"` | **equivalent**: `rg -n --glob '*.py' '^class AuthService\\b' .` | one match: `app.auth.AuthService`, `app/auth.py` | entity, source_id, workspace, backend, parser version, `partial` |
| A2 literal direct call-site location | `python-core`; `loomgraph graph app.handlers.handle_login --direction callees --depth 1 --relation-type CALLS -w "$WS"` | **equivalent only under this narrow framing**: `rg -n --glob '*.py' 'validate_token\\(token\\)' app/handlers.py` | one direct call site in `handle_login` to `app.auth.validate_token` | caller/callee entity IDs, source IDs, depth=1, relation type, `partial` |
| B1 multi-hop impact | `python-core`; after fixed `base..head`, `loomgraph impact head --base base --depth 2 -w "$WS"` | **unsupported** | changed `app.auth.validate_token` has the expected direct and indirect impacted callers, at depth ≤2 | changed source IDs, depth, resolution split, `answer.status`; a low-resolution empty result must carry a caveat |
| B2 typed module dependencies | `python-core`; `loomgraph deps -d 2 -w "$WS"` | **unsupported** | expected cross-module `CALLS` and `IMPORTS` aggregates | relation types, source scope, unresolved dependency count, `partial`, resolution qualifier |
| B3 topology/debt with Git evidence | `python-history`; produce input with `loomgraph codeindex tech-debt . > "$ARTIFACT/debt.json"`, then `loomgraph debt --codeindex-data "$ARTIFACT/debt.json" --with-git --git-since 2020-01-01 -w "$WS"` | **unsupported** | `HubFunc` is a `critical_hotspot` at P0 under the fixed commit history | fixture Git ref, analysis version, source scope, resolution split, Git window; producer input SHA is recorded |
| B4 directional branch diff / L2 status | `python-history`; `loomgraph branch-diff base..head --backend codeindex`, plus the same command with a pinned `codegraph` image | **unsupported** | codeindex finds the fixed broken/new chains and reports L2 `available`; codegraph reports L2 `unavailable`, never `unchanged` | base/head resolved SHAs, both backends, `content_comparison.status` and reason, comparable/uncomparable shared counts |
| C1 annotated-factory receiver adversary | `factory-receiver`; positive: `loomgraph graph store.Store.create_entity --direction callers --relation-type CALLS -w "$WS"`; sparse variant: `loomgraph impact sparse --base base --depth 2 -w "$WS"` | **unsupported** | positive caller is `consumer.run`; sparse result is not `isolated`/low-risk and carries the #208 resolution split | source ID, resolution split, answer status, uncertainty reason; the positive parse and sparse conclusion are independently asserted |
| C2 barrel and alias adversary | `ts-barrel-alias`; `loomgraph graph src.consumer --direction callees --relation-type REFERENCES --include-unresolved -w "$WS"` for both barrel and path-alias files | **unsupported** | resolved barrel/alias reference targets `src.models.Session`, never a ghost `src.index.Session`; ambiguous references remain non-resolved | workspace, backend, source ID, `edge_trust`, qualifier, `dst_raw`, candidates, answer status, uncertainty reason |

## Approved protocol decisions

1. **A2 wording:** `rg` has a fair single-query answer only for a *literal,
   fixture-constrained call-site location*. It is not generally equivalent to
   "who semantically calls this symbol?" The published task wording should be
   narrowed accordingly; it is not a semantic caller-query claim.
2. **C2 trust carrier:** `loomgraph graph` returns an `edge_trust` omission
   summary for the selected workspace/relation filter. With
   `--include-unresolved`, returned low-trust edges retain their qualifier,
   `dst_raw`, and candidates. C2 is therefore a LoomGraph answerability
   contract as well as a codeindex producer-seam contract.
3. **#208 must be output-checked:** C1/B1/B3 require real command output to
   carry `internal_unresolved_ratio` separately from
   `external_unresolved_ratio`; manifest field names alone are insufficient.
4. **B4 environment:** codegraph must be pinned in the fixture image. A
   missing executable is an infrastructure-invalid record, not a skipped or
   `unavailable` comparison result. `unavailable` is the valid *answer* only
   after codegraph produced its graph.
5. **No score before raw rows:** per-task `oracle.passed` and trust-contract
   compliance are the first output. Any aggregate, if later wanted, must keep
   task class and backend separate; it cannot collapse B/C into an `rg` race.

## Explicit non-goals of this draft

- No performance comparison, benchmark timing claim, token/cost estimate, or
  agent delta.
- No DeepSWE task execution. Track D stays an independent compatibility record.
- No implementation, commit, PR state change, merge, or release.
