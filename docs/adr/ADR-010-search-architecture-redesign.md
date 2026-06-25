# ADR-010: 搜索体系重构 — find / query / graph 三分

**状态**: ⚠️ 部分被 [ADR-013](ADR-013-sqlite-vec-replace-lightrag.md) Supersede (2026-06-25)
**日期**: 2026-02-21
**决策者**: DreamLinx
**关联**: EPIC-008, ADR-008 (双向调度器), Issue #7 (已关闭)

> **v0.10.0 修订**: `loomgraph query` 命令 v0.10.0 移除（EPIC-011 Phase 4）。
> `find` / `graph` 的结构化能力保留。理由：一年实践后 Claude Code / Codex /
> Cursor 已经做好自然语言代码问答，LoomGraph 该聚焦结构精确层。详见 ADR-013。

---

## 上下文

### 当前搜索体系的问题

LoomGraph v0.6.1 有两个搜索命令：

| 命令 | 实现 | 实际能力 |
|------|------|---------|
| `search` | 下载全量实体 → 客户端 SequenceMatcher 模糊匹配 | 名字模糊查找 |
| `graph` | 下载全量关系 → 客户端遍历过滤 | 精确实体关系遍历 |

同时，v0.6.1 的 `insert_custom_kg` 已将数据写入 LightRAG 全部三层：

```
insert_custom_kg → graph 层 (实体/关系)
                 → vdb 层 (向量索引)
                 → chunks 层 (文档内容: docstring + signatures)
```

但 **chunks 层和 vdb 层的查询能力从未暴露给用户**。`LightRAGClient.query()` 方法存在，仅在 `impact` 和 `overview` 内部使用。

### 用户画像分析

LoomGraph 面向企业用户，绑定 H200 算力。用户工作流：

```
工程师 → 启动 Claude Code → 通过 LoomGraph CLI / Skill 进行代码分析
```

**关键认知**：企业用户的 Claude Code 环境不一定有 Serena MCP（需要额外配置 LSP）。

Claude Code 原生工具 vs LoomGraph 能力对比：

| 能力 | Claude Code 原生 | LoomGraph 当前 | 差距 |
|------|-----------------|---------------|------|
| 找文件 | Glob ✅ | — | 无需 |
| 找文本 | Grep ✅ | — | 无需 |
| 找符号（有 Serena） | find_symbol ✅ | `search` (弱化版) | 重叠 |
| 找符号（无 Serena） | Grep（无结构，噪音大）⚠️ | `search` (有类型过滤) | **有价值** |
| 语义问答 | ❌ 不可能 | ❌ 未暴露 | **核心差距** |
| 跨文件关系 | ❌ | `graph` ✅ | 独有 |
| 变更影响 | ❌ | `impact` ✅ | 独有 |

### 两个核心发现

1. **`search` 对有 Serena 的用户是冗余的**（~95% 被 `find_symbol` 覆盖），但**对无 Serena 的企业用户有价值**（唯一的结构化实体发现工具）

2. **语义问答是 LoomGraph 真正的差异化能力**：Claude Code 无法独立完成"错误处理机制是怎样的？"这类跨文件知识综合查询，而 LightRAG 的 RAG 引擎正好能做这件事

## 决策

**将搜索体系拆为三个命令，各有清晰定位：**

```
find  = "我知道名字的一部分，帮我找实体"    → 结构化，无 LLM，快速
query = "我有一个问题，帮我从知识图谱回答"   → 语义化，LLM 驱动，深度
graph = "我知道精确名字，给我它的关系"       → 结构化，无 LLM，精确
```

### find（重命名自 search，增强）

```bash
loomgraph find "auth"                    # 结构化实体匹配
loomgraph find "auth" --type class       # 类型过滤
loomgraph find "auth" --with-relations   # 实体 + callers/callees 一次返回
```

**`--with-relations` 的必要性**：

对 Skill 编排效率有实质影响。无 `--with-relations` 时需要 N+1 次调用：

```
search "pay"          → 找到 3 个实体
graph "PayService"    → 关系
graph "PayController" → 关系
graph "PayRepo"       → 关系
= 4 次 tool call
```

有 `--with-relations` 时 1 次调用：

```
find "pay" --with-relations → 3 个实体 + 各自关系
= 1 次 tool call
```

### query（新增，核心差异化）

```bash
loomgraph query "How does authentication work?"           # 默认 hybrid
loomgraph query "What modules handle payments?" --mode local
loomgraph query "What are the design patterns?" --mode global
```

封装 LightRAG 的 `/query` endpoint，支持四种模式：

| 模式 | 行为 | 场景 |
|------|------|------|
| `hybrid`（默认） | 图谱 + 向量 + LLM | 通用问题 |
| `local` | 以实体为中心展开 | 特定组件深入 |
| `global` | 全局主题提取 | 架构级问题 |
| `naive` | 纯向量搜索 + LLM | 代码内容搜索 |

### graph（保持，微调）

- 接口不变
- 结果添加 `source_id`（文件路径）

## 考虑过的替代方案

### 方案 A: 废弃 search，不保留替代

**否决原因**：企业用户不一定有 Serena MCP。没有 `find`，Claude Code 只能用 Grep 做无结构的文本搜索，丢失实体类型、评分等结构化信息。

### 方案 B: 给 search 加 `--mode structural|semantic`

**否决原因**：`structural` 和 `semantic` 的输出格式完全不同（实体列表 vs 自然语言回答），硬塞到同一命令会让接口混乱。分成 `find` 和 `query` 更清晰。

### 方案 C: 只加 query，search 不动

**否决原因**：`search` 这个名字暗示语义能力，实际只做字符串匹配，对用户有误导。重命名为 `find` 更准确，且可以借机增加 `--with-relations`。

## 后果

### 正面

- **`query` 解锁真正的差异化能力**：Claude Code 原生做不到的跨文件语义问答
- **`find` 对无 Serena 用户有独立价值**：结构化实体发现 + 图谱上下文
- **命令命名精确**：find（发现）、query（问答）、graph（遍历）各司其职
- **Skill 编排更高效**：`find --with-relations` 将 N+1 次调用降为 1 次
- **投资回报兑现**：`build_chunks()` + `insert_custom_kg` 的全层写入能力终于被查询端消费

### 负面

- **`query` 依赖 LLM 服务**：H200 上的 GLM-4.7 不可用时 `query` 失败
- **`search` → `find` 重命名有兼容成本**：现有 Skill、文档、用户习惯需更新
- **RAG 回答质量不确定**：chunks 内容（docstring + signatures）是否足够支撑高质量 RAG 回答需评估

### 缓解

- `query` 失败时给出明确错误信息 + 提示用 `find` 作为 fallback
- `search` 保留一个版本作为 `find` 的隐藏别名 + deprecation warning
- F2-S2 专门评估 RAG 质量，必要时增强 `build_chunks()` 内容
