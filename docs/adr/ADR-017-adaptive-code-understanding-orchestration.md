# ADR-017: 自适应代码理解编排边界

**状态**: Accepted
**日期**: 2026-08-27
**决策者**: User + AI Agent
**相关**: ADR-013（本地结构底座）, ADR-015（Git 时间维度）, ADR-016（agent-use 边界）

---

## 背景

LoomGraph 内置的 `codeindex` 后端提供本地、零服务依赖的 AST 结构索引，适合
轻量代码定位。复杂仓库还可能已有更强的外部能力：

- [codebase-memory-mcp (CBM)](https://github.com/DeusData/codebase-memory-mcp)
  可提供高性能的结构化图查询；
- [Serena](https://github.com/oraios/serena) 可通过 LSP 或 JetBrains 提供符号级
  查找、引用、编辑和重构；
- agent host 也在变化：Claude Code、Codex、Pi 等主要通过 MCP/CLI 集成；
  [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 是 plugin-first
  的预览期 harness。

项目规模、任务类型、已安装 provider、agent host 与模型的工具使用/上下文能力均会
改变合适的探索路径。让每个项目都建立重型图，或让 LoomGraph 重做 CBM/Serena 的
能力，会增加安装、索引、维护和工具选择成本。反过来，直接把所有 provider 暴露给
agent 会扩大工具面，并使不同 provider 的置信度、快照与时间语义混淆。

长上下文也不是免费的代码理解：无关源码会占用上下文预算，并可能降低任务相关
证据的显著性。因此目标不是向模型提供更多代码，而是在需要时提供足以行动的最小、
可追溯证据。

## 选项

1. **LoomGraph 继续作为固定、自包含图谱引擎**：所有仓库均先走 codeindex/
   LoomGraph 索引与查询。
2. **以单一外部 provider 为前提**：例如要求 CBM 或 Serena 成为 LoomGraph 的
   必备后端。
3. **LoomGraph 作为自适应代码理解编排层**：保留 codeindex 轻量路径，按能力与
   策略选择可选 provider，并由 LoomGraph 持有时间证据、信任边界与上下文预算。

## 决策

选择选项 3。

LoomGraph 是 agent 的**代码理解策略层**，而不是所有代码智能能力的唯一实现。
它根据项目与运行时能力选择最小合适路径，并把结果交付为可追溯的 evidence packet。

### 1. 角色边界

| 层 | 责任 | 不承担的责任 |
| --- | --- | --- |
| codeindex | 默认轻量 AST 提取、局部结构定位、LoomGraph 内置 snapshot 输入 | 全局历史解释、agent 策略 |
| CBM（可选） | 高性能结构搜索、调用/架构候选 | LoomGraph 的统一时间/信任语义 |
| Serena（可选） | live symbol 语义、引用、编辑、重构与诊断 | 历史 snapshot 或 ref-to-ref comparison 的默认真相源 |
| LoomGraph | provider 发现与选择、上下文预算、snapshot identity、`base..head` 比较、provenance、availability/trust、审计 | 重做外部 provider 的完整图/LSP/编辑实现，或替 agent 做需求推理 |
| Agent/harness | 意图理解、工具调用、代码编辑与测试 | 把没有证据的导航结果说成已证明的比较结论 |

CBM 存在时，LoomGraph 不得自动重复构建同一重型索引；无 CBM 时，
`codeindex + LoomGraph` 必须保持可用的轻量路径。Serena 存在时，可作为符号确认
与编辑阶段的 provider；它不因具备符号语义而自动获得 temporal comparison 的权威。

### 2. 策略按能力而非品牌或模型名选择

不得按“某模型名必用某 provider”写死路径。策略输入应包括：

- 项目探索复杂度（跨模块、跨服务、历史深度、重复探索风险），而非仅 LOC；
- 任务阶段（局部编辑、探索、符号重构、PR/回归/`base..head` 审查）；
- provider capability 与可用性；
- host 的 MCP/CLI/plugin 能力；
- 用户选择的 `economy`、`balanced` 或 `deep` 策略档；
- 经运行时校验的模型 structured-output、工具调用、预算与上下文画像。

默认路径应逐级升级：

| 条件 | 路径 |
| --- | --- |
| 明确文件/局部改动 | 原生 agent 工具；不强制索引 |
| 跨文件定位不明 | `codeindex` / LoomGraph 轻量结构查询 |
| 大型或高探索成本仓库且 CBM 可用 | 以 CBM 提供结构候选，避免重复索引 |
| 符号引用、重构、精确编辑且 Serena 可用 | Serena 优先用于 live semantic/editing 操作 |
| 历史影响、PR 审查、回归调查 | LoomGraph 负责 snapshot 与 branch-diff evidence；缺少可比较证据时返回 `unavailable` |

### 3. 编排首先是选择、限制、解释、审计

第一阶段的编排不要求 LoomGraph 自动调用所有外部 MCP server。它应先输出一个
最小、可解释的 orientation plan：推荐 provider、响应预算、所需 evidence、降级
路径与不确定性。各 provider 保持自己的原生工具面。

只有在某 host 能安全执行跨 provider 调度时，才增加薄 adapter。MCP/CLI host
先采用 LoomGraph 的 MCP/CLI policy surface；plugin-first host（如 dsh）可在其
API 稳定后实现独立 plugin。不得为了适配单一 preview harness 改写核心。

任何统一 response 至少标注 provider、snapshot/ref、实体 identity、
availability 与 trust。LoomGraph 不得把 provider 的“可能相关”升级为“已证明调用”
或把不可比较结果解释成“没有变化”。

### 4. 采用 Claude Code-first 的渐进交付

第一阶段只以 **Claude Code** 作为支持与评估的 reference runtime。最小产品不是
“跨 agent 自动调度”，而是在 Claude Code 中提供可解释的轻量升级路径：原生工具
→ `codeindex + LoomGraph` →（用户已安装且任务需要时）外部 provider。其余 host
的支持必须在 Claude Code 的 contract、evidence 和策略被实际验证后，以独立 adapter
逐步加入。

这避免把 Pi、Codex、dsh 或某个模型的短期工具行为写进核心。不同 host/model 的
结果是独立 runtime cohort，不能与 Claude Code 样本混算。特别是 dsh 仍处于
developer preview，其 plugin 只可作为后续实验性 adapter。

## 理由

1. 这保留了 LoomGraph 当前零服务、codeindex 可用的低门槛路径，避免把重型依赖
   强加给小项目。
2. 它允许用户采用更强的外部代码智能，而不丢失 LoomGraph 在时间、比较和
   provenance 上的差异化。
3. 它把 context reduction 变成可管理的产品行为：限制工具面与返回大小，而不是
   依赖模型在长上下文中自行筛选。
4. 它适配不同 agent/harness/模型的工具能力，同时不把短期模型名称或某个 host 的
   plugin API 固化进产品语义。

## 后果

### 正面

- 小仓库保持轻；大型或复杂仓库可利用已有 CBM/Serena 投资。
- temporal comparison 与 evidence/trust 是稳定的 LoomGraph 核心，而 provider 可替换。
- agent 的工具面可按任务和预算收缩，降低无目的读文件与上下文膨胀。
- 评估可以按 host、model、provider、policy 分层，而不是伪造一个总体胜率。

### 负面与约束

- capability discovery、fallback 与 provenance contract 需要维护。
- 不同 provider 的语义不可假定等价；适配器必须声明能力缺口。
- 自动跨 provider 调度在部分 MCP host 中不可行，第一阶段只能给出计划而非自动执行。
- 不能把 provider 自报 benchmark 转述为 LoomGraph 的 token/效率结论；必须在固定
  runtime 和任务上独立测量。

## 后续

本 ADR 不引入 adapter、CLI、MCP tool 或新的 agent-use cohort。接受后，最小后续工作是：

1. 在 Claude Code 中定义一个小型、版本化的 provider capability manifest 与
   evidence envelope；
2. 做一个 **CBM capability-discovery / fallback spike**，只验证可发现、可选择、
   不重复索引与缺口声明；
3. 为 Serena 定义 live semantic/editing capability 边界，不把它包装为历史比较后端；
4. 保留两套不可混算的评估：DeepSWE 的公开、可复跑受控 cohort，以及用户授权的
   本地客户仓库 field-validation cohort；
5. 在各自独立预注册 cohort 中分别衡量 `changed_logic_hit`、
   `behavioral_integration_hit`、evidence coverage 与探索预算；不重算或合并既有
   v1--v9 evidence。

### 客户仓库 field validation 约束

客户 PHP、Java 等大型遗留仓库是验证“真实探索成本与技术债务定位”是否值得使用
LoomGraph 的重要补充，但不是 DeepSWE 的替代数据集。每个仓库必须独立登记其语言、
规模/复杂度画像、历史范围、任务类型、host/model/provider/policy，并在本地保留
原始 trace。不得上传源码、solution、gold patch 或客户敏感路径；若需要跨仓汇报，
只导出经人工审查的匿名聚合指标。

field validation 的首轮只评估开发前理解与定位：陌生模块 onboarding、历史技术债务
解释、变更影响/回归调查和重构前符号边界。它应以人工 reviewer 的 evidence-grounded
plan 评价为主，并单独记录 source bytes、tool calls、模型 token/费用（仅在运行时
可可靠取得时）与时间；这些诊断字段不得跨语言、仓库、host 或 model 合成单一胜率。

ADR-008 的 LightRAG 架构图与“LoomGraph 承接全部跨模块能力”的具体实现前提已被
ADR-013 的本地 SQLite 架构取代；本 ADR 进一步将其能力边界更新为
provider-agnostic 的策略与证据边界。
