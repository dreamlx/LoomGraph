# Capability run matrix v1 — approved executable protocol

> **Status: protocol and raw-observation runner approved.** This document does
> not publish a result artifact, a performance claim, or an agent-use result.
> It turns the eight reviewed A--C contracts into executable observations.

## Primary question

> 面对一个已声明的结构/时间/比较问题，LoomGraph 能否给出正确、且附带可信度
> 限定的回答；而 `rg` 是否存在等价的单查询答案？

`rg` is a calibration only. It is run only for the two A rows and never timed
against LoomGraph. B and C report `unsupported` rather than inventing an
equivalent text search.

## Proposed fixture package and record

The runner materializes six tiny versioned repositories:

| Fixture repository | Used by | Required history |
| --- | --- | --- |
| `python-core` | A1, A2 | one immutable commit |
| `python-deps` | B2 | one immutable commit; one resolved cross-module call |
| `python-history` | B1, B4 | `base` and `head` tags; fixed author/committer dates |
| `topology-debt-git` | B3 | one hub with eight consumers and thirteen fixed-date commits |
| `factory-receiver` | C1 | `base`/`head` tags: annotated factory positive plus sparse no-caller change |
| `ts-barrel-alias` | C2 | one immutable commit; barrel and `tsconfig` path-alias cases are separate files |

The materializer calculates a content SHA after writing each fixture, and the
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
    "cold_setup": {"kind": "workspace_index | branch_diff_snapshot",
                   "command": ["..."], "wall_ms": 0, "exit_code": 0,
                   "raw_stdout": "...", "raw_stderr": "..."},
    "query_command": ["..."], "query_wall_ms": 0, "reindexed": true,
    "exit_code": 0, "raw_stdout": "...", "raw_stderr": "..."
  },
  "answer": {"status": "complete | partial | ambiguous | unavailable | error"},
  "trust": {
    "workspace": "...", "source_id": "...", "partial": false,
    "resolved_ratio": 0.0, "internal_unresolved_ratio": 0.0,
    "external_unresolved_ratio": 0.0, "limitations": []
  },
  "oracle": {"passed": true, "failures": []},
  "comparison": {"backend": "codegraph", "availability": "available | infrastructure_unavailable", "backend_version": "...", "oracle": {"passed": true}},
  "supplemental": {"command": ["..."], "oracle": {"passed": true}},
  "rg": {"equivalence": "equivalent | unsupported", "command": null,
         "raw_stdout": null, "oracle_passed": null}
}
```

The timing fields distinguish index setup from query execution. They are
diagnostic metadata, never a cross-tool speed score.

`cold` records the actual setup that makes the following answer meaningful:
ordinary tasks run a `workspace_index`; B4 records its primary
`branch_diff_snapshot` operation, which both provisions snapshots and answers
the comparison question. Its setup command is intentionally not an unrelated
pre-index. `warm` uses the same fixture SHA and workspace or snapshots without
new setup and omits `cold_setup`. A changed SHA, Git ref, backend, parser or
codeindex version makes the record incomparable rather than silently reused.
B4 additionally stores the codegraph comparison operation in the same phase
record; B3 stores its caller-topology check and C2 its second (barrel) query as
`supplemental`.

Run the eight tasks into an adapter-owned directory with:

```bash
python evals/run_capability_observations.py \
  --work-root /tmp/loomgraph-capability-v1-work \
  --output /tmp/loomgraph-capability-v1-observations.jsonl
```

The output is exactly sixteen raw JSONL rows (eight tasks times `cold`/`warm`).
The runner does not compute a score. If `rg` is absent, the A row records
`rg.available=false` plus an infrastructure error; it never treats that as an
`rg` answer or as a LoomGraph failure.

## Eight proposed observations

`$WS` is the deterministic task workspace. `$ARTIFACT` is an adapter-owned
output directory outside the fixture. The commands below define the runner's
actual query shape, not a performance claim.

| ID / class | Fixture, LoomGraph observation | `rg` status and oracle | Correct answer oracle | Required answer/trust contract |
| --- | --- | --- | --- | --- |
| A1 exact definition location | `python-core`; `loomgraph find AuthService --type class -n 1 -w "$WS"` after `loomgraph index . --clear -w "$WS"` | **equivalent**: `rg -n --glob '*.py' '^class AuthService\\b' .` | one match: `app.auth.AuthService`, `app/auth.py` | entity, source_id, workspace, backend, parser version, `partial` |
| A2 literal direct call-site location | `python-core`; `loomgraph graph app.handlers.handle_login --direction callees --depth 1 --relation-type CALLS -w "$WS"` | **equivalent only under this narrow framing**: `rg -n --glob '*.py' 'validate_token\\(token\\)' app/handlers.py` | one direct call site in `handle_login` to `app.auth.validate_token` | caller/callee entity IDs, source IDs, depth=1, relation type, `partial` |
| B1 multi-hop impact | `python-history`; `loomgraph impact head --base base --depth 2 -w "$WS"` | **unsupported** | modified `app.auth.validate_token` has direct caller `app.handlers.handle_login` and indirect caller `app.api.dispatch`; it also carries the resolution split | changed source IDs, depth, resolution split, `answer.status`; a low-resolution empty result must carry a caveat |
| B2 typed cross-module dependency | `python-deps`; `loomgraph deps -d 2 -w "$WS"` | **unsupported** | exactly one resolved `src/cli → src/core` `CALLS` aggregate | relation type, source scope, `partial`, resolution qualifier |
| B3 topology/debt with Git evidence | `topology-debt-git`; primary `loomgraph debt --with-git --git-since '10 years' -w "$WS"`, supplemental callers graph for `app.hub.HubFunc` | **unsupported** | `app/hub.py` is `critical_hotspot` at P0 (13 changes, score 100) under fixed history, and the supplemental graph returns exactly eight `HubFunc` callers | fixture Git ref, analysis version, source scope, resolution split, Git window |
| B4 directional branch diff / L2 status | `python-history`; codeindex primary plus `codegraph` comparison variant | **unsupported** | codeindex finds fixed broken chains and reports L2 `available`; codegraph reports L2 `unavailable`, never `unchanged` | base/head resolved SHAs, both backends and codegraph version, `content_comparison.status` and reason, comparable/uncomparable shared counts |
| C1 annotated-factory receiver adversary | `factory-receiver`; primary caller graph plus supplemental `loomgraph impact head --base base --depth 2 -w "$WS"` | **unsupported** | positive caller is `consumer.run`; sparse `only_here` change has zero callers but is `medium`/`unknown`, never isolated/low | source ID, resolution split, answer status, uncertainty reason |
| C2 barrel and alias adversary | `ts-barrel-alias`; primary `src.alias_consumer` path-alias query plus supplemental `src.consumer` barrel query, both with `--include-unresolved` | **unsupported** | both references resolve to `src.models.Session`, never a ghost `src.index.Session`; ambiguous references remain non-resolved | workspace, backend, source ID, `edge_trust`, qualifier, `dst_raw`, candidates, answer status, uncertainty reason |

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
4. **B4 environment:** the runner records the local `codegraph --version`. A
   missing executable is an `infrastructure_unavailable` comparison record,
   not a skipped or content-`unavailable` answer. A publishable run must pin
   that executable version; only a successful codegraph query may report the
   valid L2 answer `unavailable`.
5. **No score before raw rows:** per-task `oracle.passed` and trust-contract
   compliance are the first output. Any aggregate, if later wanted, must keep
   task class and backend separate; it cannot collapse B/C into an `rg` race.
6. **B2 scope:** the Python slice exercises the resolved `CALLS` aggregate.
   codeindex also emits module-level `IMPORTS` edges, but `loomgraph deps`
   currently aggregates only edges whose endpoints map to source-bearing
   entities; that import-edge behavior is an explicit follow-up, not a passed
   v1 assertion.

## Explicit non-goals of this draft

- No performance comparison, benchmark timing claim, token/cost estimate, or
  agent delta.
- No DeepSWE task execution. Track D stays an independent compatibility record.
- No merge, release, public result artifact, or aggregate score.
