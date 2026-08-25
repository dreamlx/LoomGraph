# ADR-016: 结构能力基准 v1 收口与 agent-use 边界

**状态**: Accepted
**日期**: 2026-08-25
**决策者**: AI Agent + User
**相关**: ADR-013（本地结构底座）, ADR-015（Git 时间维度）, LoomGraph #206 / #208, codeindex #185

---

## 背景

LoomGraph 不应与 `rg` 争夺精确字符串或符号定位的速度，也不应把
DeepSWE 的路径定位结果包装成结构能力。v1 要回答的主问题是：

> 面对一个已声明的结构、时间或比较问题，LoomGraph 能否给出正确、且附带
> 可信度限定的回答；而 `rg` 是否存在等价的单查询答案？

`GraphStore.create_entity` 的历史假空 callers 说明，仅报告全局
`resolved_ratio` 不足以支持“没有调用者”或“变更已隔离”的结论。带注解的
factory receiver、alias/barrel 与动态 receiver 必须把解析盲区作为可观察的
不确定性，而非零结果或失败噪声。

## 决策

### 1. v1 的主证明是八个确定性 A--C fixture

| 轨道 | 数量 | 任务 |
| --- | ---: | --- |
| A：overlap calibration | 2 | 精确定义位置、字面直接静态调用点；仅这两项允许 `rg` 等价单查询。 |
| B：structural answerability | 4 | 多跳影响、跨模块 typed dependency、topology/debt × Git、方向性 branch diff。 |
| C：trust adversary | 2 | annotated-factory receiver，以及 alias/barrel 加动态 receiver。 |

每项 fixture 固定正确 oracle、必要 trust 字段、fixture SHA/Git ref/toolchain，
并独立记录 cold setup 与 warm query。B/C 的 `rg_single_query: unsupported`
是有效答案，不得为了比较而伪造文本等价式。

执行产物首先是每任务的 oracle 与 trust-contract 合规记录，而不是总分。
计时字段仅用于诊断 setup 与 query 边界，不能成为跨工具速度结论。

### 2. Track D 保持 agent-use compatibility dogfood

agent-use 不计入 A--C 成绩，也不作为公开能力主证明。它检验一个特定运行时与
特定 LoomGraph integration surface 的组合是否可用：模型是否可发现/调用允许的
工具、调用是否返回结构证据、回答是否将该证据的可信度如实带回，以及 model
phase 是否保持源码干净。

当前 `find/graph` additive surface 的有效 treatment 必须同时满足：

1. 有 adapter 观察到的成功结构检索；
2. 对 trust-required task，回答中的 resolution 与实际 MCP `graph` 输出逐项一致；
3. 满足 JSON schema、工具预算和 source-clean 约束；
4. 被 fixture 的路径 oracle 单独记录。

文本路径答对而未取得 treatment trust evidence，或模型自报的 ratio 与 MCP 原始
输出不一致，均是无效 treatment observation，不能用来主张 LoomGraph 已被使用。
`voluntary` 与 `assisted` 是不同条件，永不合并。

### 3. v1 的结论和非结论

v1 接受的结论是：LoomGraph 的结构/时间/比较问题可用确定性 oracle 与查询级
trust contract 评估；agent-use 可以作为独立运行时兼容性记录，且能拒绝伪造的
可信度归因。

v1 **不**接受以下结论：

- `rg` 在结构、时间或比较问题上较弱；
- LoomGraph 提升了 agent 的正确率、效率、token 或成本；
- 单个或少量 agent run 可以代表模型、运行时或所有仓库；
- 空 callers 列表等于没有调用者，或 comparison `unavailable` 等于没有变化。

原始 agent traces 保留为本地证据，不进入 Git 历史，也不形成发布材料。

## v2 的进入条件：独立的 branch-diff agent-use 任务

产品 MCP 已提供 `loomgraph_branch_diff`，但 v1 agent-use 的 allowlist 只有
`loomgraph_find` 和 `loomgraph_graph`。因此 v2 不是为 v1 多跑一个样本，而是
新增独立的 **temporal/branch-diff treatment surface**；v1 数据不得与它混算。

在任何 v2 agent run 前，必须先审阅并固定以下设计：

1. 一个最小、版本化、有 `base`/`head` refs 的 repository fixture，以及精确 oracle：
   断链或新链、L2 `available|partial|unavailable`、以及 `unavailable` 绝不解释为
   `unchanged`。
2. baseline 的相同自然语言问题和文本导航权限；treatment 只额外开放声明的
   `loomgraph_branch_diff` surface。`voluntary` 与 `assisted` 继续分层。
3. task 专属 trust contract：`base_ref`、`head_ref`、两端 backend、snapshot
   provisioning 状态、`content_comparison.status`/`reason` 与可比较/不可比较计数。
   不复用 graph resolution 三元组，也不让模型自报字段成为唯一证据。
4. adapter 从原始 MCP response 校验这些字段；首次 snapshot provisioning（cold）与
   已存在 snapshot 的 query（warm）分别记录，且都与 agent execution time 分开。
5. 在形成任何 quality 或 efficiency 表述前，先通过 source-clean、schema、工具
   surface、fixture oracle 与 trust-source 对齐的正反例测试。

## 替代方案

| 方案 | 结论 |
| --- | --- |
| 以 `rg` 速度或泛化 grep 对比为主 | 拒绝；这偏离结构/时间/比较能力问题。 |
| 把 agent-use 路径命中并入 A--C 主分数 | 拒绝；它测量运行时和工具策略，不是确定性产品能力。 |
| 直接把 `branch_diff` 加进现有 find/graph allowlist | 拒绝；其冷/暖 provisioning 与 trust 语义不同，会污染 v1 条件。 |
| 为 branch diff 新建独立 v2 surface 和 contract | 接受；最小且可审计。 |

## 验证与后续

- v1 的可执行规范是 `evals/capability-manifest.json`，运行矩阵是
  `docs/evals/capability-run-matrix-v1.md`。
- v1 runner、fixture 与 agent adapter 的单元/契约测试必须随任何协议变动运行；
  CI 通过仅证明实现门禁，不替代 raw observation 或 agent-use 结论。
- v2 开始时从当时的 `main` 新分支创建，先提交 task/spec 与测试，再运行任何模型
  实验；不回写或覆盖 v1 原始证据。
