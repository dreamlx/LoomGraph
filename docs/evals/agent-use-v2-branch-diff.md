# Agent-use v2：branch-diff 最小任务设计

> **状态：Proposed，尚未实现或运行模型。**
> 本文落实 [ADR-016](../adr/ADR-016-benchmark-v1-close.md) 的 v2 进入条件。

## 目的与边界

v2 检验 Claude Code 的 additive MCP integration 能否在一个明确的时间/比较问题上
使用 `loomgraph_branch_diff`，并把其比较前提如实带回回答。它不是 v1 的第九个
能力题，不与 v1 `find/graph` agent-use traces 合并，也不产生效率、成本或通用
正确率结论。

主问题为：

> 面对已声明的 `base..head` 结构比较，agent 能否给出固定的断链事实，并说明
> L2 content comparison 是否可比较、为何可比较？

`rg_single_query` 是 `false`：两 ref 的方向性结构断链及 L2 可比性没有等价的单个
文本查询答案。

## 冻结任务

| 字段 | v2 值 |
| --- | --- |
| ID | `python-history-branch-diff-contract` |
| task class | `temporal-structural-comparison` |
| repository | adapter-owned、由 `materialize_fixture("python-history", path)` 生成的 Git 仓库 |
| refs | 固定 tag `base` 与 `head`；fixture 内容 SHA 必须记录 |
| MCP tool | 仅 `mcp__loomgraph__loomgraph_branch_diff` |
| server allowlist | 仅 `loomgraph_branch_diff` |
| backend | `codeindex` |
| correct structural fact | `app.handlers.keep_legacy -> app.auth.legacy_token` 是 `CALLS` broken chain |
| correct L2 fact | `content_comparison.status == "available"`，两端 backend 都是 `codeindex` |

任务指令只给出问题、`base`、`head` 和 `codeindex` backend；不得泄露上述 entity
名称、答案字段、fixture manifest 或实现断言。

## 条件与 tool surface

| 条件 | 可用工具 | 可信度回答 |
| --- | --- | --- |
| baseline | `Read,Glob,Grep` | `availability: "unavailable"`；不得构造 LoomGraph comparison 值 |
| treatment / voluntary | baseline 工具加唯一的 branch-diff MCP tool | 可选择不用；若未取得成功 branch-diff，则是无效的 trust-required treatment |
| treatment / assisted | 与 voluntary 相同 | 必须有一次成功、证据承载的 branch-diff 调用 |

`find`、`graph`、`refresh` 和其他 MCP tool 都不在此 surface。这样测量的是时间比较
工具本身，而不是模型先用其他 LoomGraph 导航工具再答题的混合策略。`voluntary` 与
`assisted` 继续单独记录。

## 回答与 trust contract

v2 必须使用新的 task-specific JSON schema，不能复用 v1 的 `candidates` 或 graph
resolution 三元组：

```json
{
  "findings": [
    {
      "kind": "broken_chain",
      "src": "app.handlers.keep_legacy",
      "tgt": "app.auth.legacy_token",
      "relation": "CALLS",
      "evidence": "..."
    }
  ],
  "trust": {
    "availability": "available",
    "comparison": {
      "base_ref": "base",
      "head_ref": "head",
      "base_backend": "codeindex",
      "head_backend": "codeindex",
      "base_provisioned": "created | reused | rebuilt",
      "head_provisioned": "created | reused | rebuilt",
      "content_comparison": {"status": "available", "reason": null}
    }
  }
}
```

baseline 的 `trust` 为 `{ "availability": "unavailable", "comparison": null }`。
treatment 只有在 adapter 从成功的 MCP raw response 中找到同一组 comparison 字段时
才能报告 `available`。模型文字、工具调用名称或独立计算的值都不是证据来源。

适配器还要记录 raw response 的 resolved base/head SHA、workspace 与每端
`provisioned` 状态；模型仅可复述已声明的 `base`/`head`。若 ref、backend、broken
chain 或 L2 status 与 raw response 不一致，packet 状态为
`unverified_treatment_comparison_trust`。

## 正确性与运行记录

fixture oracle 是 `evals.run_capability_observations._branch_diff_oracle` 的同一事实，
但 agent adapter 必须有独立的 answer oracle；不能把 path recall 当作 comparison
正确性。每次运行至少记录：

- fixture SHA、`base`/`head` resolved SHA、backend 与 LoomGraph/codeindex 版本；
- observed assistant model、完整 MCP tool trace、raw branch-diff response；
- source-clean 的 pre/post Git state；
- task-specific finding oracle 与 trust-source match；
- `agent_execution_seconds`，以及 MCP response 的 `duration_seconds`；
- cold/warm snapshot 状态，分别为首次 provision 与两端均 `reused` 的重复调用。

`duration_seconds` 包含 branch-diff 的 provisioning。它必须与 agent execution 和
任何 setup wall time 分开保存；cold/warm 仅描述可比性，不是性能胜负。

branch-diff 会在 adapter-owned LoomGraph storage 和临时 snapshot worktree 写入数据。
这些不是 source mutation；其路径与生命周期必须记录，源 fixture 的 Git state 仍是
model-phase 的唯一 source-clean 判据。

## 实现前测试清单

实现顺序是先写下列失败测试，再修改 runner：

1. fixture materialization 固定 `base`/`head` tags、内容 SHA 和 broken-chain/L2 oracle；
2. `temporal-additive` tool profile 只把 `loomgraph_branch_diff` 写入 client 和 server
   allowlist，其他 MCP tool 一律属于 `unexpected_mcp_tool`；
3. raw-response parser 只接受 `success: true`、正确 ref/backend、可验证的
   `base`/`head` provisioning 和 `diff.content_comparison`；
4. baseline 的 unavailable comparison、treatment 的 available comparison，以及
   raw/model mismatch、缺失调用、错误 ref、错误 L2 status 的正反例；
5. task-specific finding oracle 独立于 v1 path oracle；
6. cold first provision 与 warm reused snapshot 的记录，以及 storage/snapshot 不影响
   source-clean 的边界。

只有这些测试和 schema 审阅通过，才可运行任一模型。首轮原始证据写入新的 v2 本地
archive，不覆盖 v1 archive；即使得到一对有效 baseline/treatment，也只报告逐 run
事实，不报告 agent delta。

## 非目标

- 不扩展为通用 agent benchmark，不加入 DeepSWE solve-rate；
- 不把 codegraph L2 `unavailable` 当作本切片的 treatment 成功；该变体可在后续单独
  作为不确定性 adversary；
- 不开放任意 MCP write tool；
- 不在 task/spec 审阅前运行模型、发布结果或声称效果。
