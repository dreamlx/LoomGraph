# ADR-008: LoomGraph 双向调度器 — codeindex/LoomGraph 能力边界

**状态**: ✅ 已批准
**日期**: 2026-02-18
**决策者**: DreamLinx

---

## 上下文

codeindex v0.18.0 benchmark 显示 `architecture_comprehension` 分数从 1-2 提升到 3，但离目标 ≥5 仍有差距。AI 评估反馈的三个改进方向：

1. **目录层级展开** — 多层树形结构展示
2. **模块功能推断** — 如 "gateway 负责路由鉴权"
3. **跨模块依赖** — 如 "gateway → common"

核心问题：这三个能力应该由 codeindex 还是 LoomGraph 实现？

### 现有架构

```
codeindex (AST 解析)  →  LoomGraph (映射调度)  →  LightRAG (存储检索)
   文件级结构               写入调度                 图谱 + 向量
```

LoomGraph 当前定位为**纯写入调度器**：从 codeindex 接收解析结果，映射为 entity/relation，注入 LightRAG。读取能力（search/graph/impact）已有但需要用户主动发起查询。

## 决策

**LoomGraph 从"写入调度器"演进为"双向调度器"（写入 + 查询聚合），承接跨模块语义分析能力。**

边界判断标准：**需要跨文件/跨模块全局视角 → LoomGraph；单目录内可完成 → codeindex。**

## 能力边界划分

| 能力 | 归属 | 理由 |
|------|------|------|
| 目录层级展开（多层树形） | **codeindex** | 纯结构，扫描时即可生成，不需要图谱 |
| 单文件/单目录符号提取 | **codeindex** | 局部信息，AST 解析核心职责 |
| 单目录功能描述 | **codeindex** (AI 模式) | 局部上下文，LLM 在扫描时推断 |
| 模块功能推断（跨文件） | **LoomGraph** | 需要聚合多文件 entity 信息 + LLM 总结 |
| 跨模块依赖图 | **LoomGraph** | 需要完整 relation graph，按目录聚合 |
| 项目级架构概览 | **LoomGraph** | 需要全局知识图谱 |

### 演进后的架构

```
codeindex (解析)  →  LoomGraph (映射 + 注入)  →  LightRAG (存储)
   文件级结构              写入调度

                     LoomGraph (查询 + 聚合)  ←  LightRAG (检索)
                         读取调度
                     ┌─ deps: 模块级依赖图
                     ├─ overview: 项目模块概览
                     └─ search/graph/impact (已有)
```

## 理由

### 1. 数据已在图中

LoomGraph 注入完成后，LightRAG 已有所有 entities + relations。模块功能推断和依赖分析只需要**查询 + 聚合**，不需要新增存储或改 pipeline。

### 2. codeindex 扫描时没有全局视角

codeindex 逐目录扫描，处理 `src/gateway/` 时看不到 `src/common/` 的内容。跨模块依赖必须在全量数据可用后才能分析。

### 3. 符合已有 CLI 架构

LoomGraph CLI 已有读写两类命令：
- 写入：`index`, `update`
- 读取：`search`, `graph`, `impact`

新增 `deps` 和 `overview` 是读取类命令的自然扩展，不改变核心架构。

### 4. 避免 codeindex 职责膨胀

codeindex 的设计哲学是 "提取结构 (What)"。语义推断 (Why) 应由上层处理。在 codeindex 中硬编码启发式规则（如从目录名猜功能）不可靠也不可维护。

## 新增 CLI 命令规划

| 命令 | 功能 | 实现方式 |
|------|------|----------|
| `loomgraph deps [--module <path>]` | 模块级依赖图 | 查询 IMPORTS/CALLS relations，按目录前缀聚合 |
| `loomgraph overview [--depth N]` | 项目模块概览 | 查询各顶级目录的 entities，调用 LLM 生成摘要 |

输出格式保持 JSON，供 AI Agent 消费。

## 后果

### 正面

- 三仓库职责更清晰：解析 / 调度+智能 / 存储
- 充分利用已有图谱数据，无需额外存储
- 为客户提供开箱即用的项目理解能力

### 负面

- LoomGraph 的 `overview` 命令需要调用 LLM（通过 LightRAG query），增加延迟
- 需要 LightRAG 服务在线才能使用查询类命令

### 缓解

- `deps` 命令纯图查询，不需要 LLM，延迟低
- `overview` 可缓存结果，不需每次重新生成

## 与 codeindex benchmark 的关系

benchmark 的 `architecture_comprehension` 指标主要评估 README_AI.md 质量，这是 codeindex 的输出。LoomGraph 的智能查询是**运行时能力**，不直接写入 README_AI.md。

因此改进策略分两路：
1. **codeindex**: 改进目录层级展示 + AI 模式下的单目录描述 → 提升 benchmark 分数
2. **LoomGraph**: 新增 deps/overview → 提供运行时项目理解能力，AI Agent 在需要时按需查询
