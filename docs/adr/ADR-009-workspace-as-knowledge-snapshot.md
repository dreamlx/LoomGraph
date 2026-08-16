# ADR-009: Workspace 重定义 — 从隔离机制到知识快照

**状态**: ✅ 已批准
**日期**: 2026-02-18
**决策者**: DreamLinx
**关联**: ADR-008 (双向调度器), 研发熵减解决方案

---

## 上下文

### 客户实际场景

客户有多个代码仓库（gateway、backend、common），同一项目有多个客户分支。面临三个问题：

1. **可见性缺失**：客户不知道 LightRAG 里有哪些 workspace，不知道哪些项目已索引
2. **分支无感知**：同一目录切分支后 re-index 会覆盖，无法保留或对比不同分支的知识图谱
3. **跨项目隔离**：上下游项目（gateway → backend）各自独立 workspace，无法做跨项目依赖分析

### 业务驱动：研发熵减解决方案

企业客户需要基于代码知识图谱的版本和分支管理洞察：

| Skill | 场景 | 对 workspace 的需求 |
|-------|------|---------------------|
| **A 债务雷达** | 单项目技术债务审计 | 单 workspace 查询 |
| **B 智能同步** | 上游补丁 → 分析下游哪些分支受影响 | 跨 workspace 实体对比 |
| **C 演化观察** | 追踪代码分叉轨迹和维护代价 | 跨 workspace 相似检测 + 历史快照 |

当前 workspace 只是一个隔离 header，无法支撑 Skill B/C。

### 当前实现

```python
def get_auto_workspace(workspace):
    if workspace:
        return workspace       # 显式 --workspace 参数
    return Path.cwd().name     # 自动取当前目录名
```

LightRAG 通过 `LIGHTRAG-WORKSPACE` HTTP header 实现 workspace 隔离，workspace 之间完全不可见。

## 决策

**将 workspace 从"数据隔离机制"重定义为"知识快照"——某个代码仓库在某个分支/版本的知识图谱切片。**

### 命名约定

```
{project}                    # 默认：目录名，当前分支
{project}:{branch}           # 分支快照
{project}:{tag}              # 版本快照
{project}-all                # 多仓库联合 workspace
```

示例：

| workspace 名 | 含义 |
|--------------|------|
| `[customer]-backend` | [customer]-backend 项目，当前工作状态 |
| `[customer]-backend:main` | [customer]-backend 的 main 分支快照 |
| `[customer]-backend:feature-auth` | feature 分支快照 |
| `[customer]-backend:v2.0` | v2.0 版本快照 |
| `[customer]-all` | gateway + backend + common 联合索引 |

### 行为规则

1. **默认行为不变**：不指定 `-w` 时，workspace = 当前目录名，覆盖更新
2. **显式快照**：`-w project:branch` 创建命名快照，不影响默认 workspace
3. **联合索引**：多个项目 `index --no-clear -w name` 追加到同一 workspace
4. **对比查询**：新命令支持跨 workspace 结构化对比

## LoomGraph 在研发熵减方案中的定位

### 三层架构

```
Skill 层 (Claude Code Skills)
    ├── Skill A: 债务雷达    → 编排 codeindex + LoomGraph 单 workspace 查询
    ├── Skill B: 智能同步    → 编排 LoomGraph 跨 workspace 对比 + git + LLM
    └── Skill C: 演化观察    → 编排 LoomGraph 相似检测 + LLM 趋势分析

LoomGraph 能力层 (本项目)
    ├── 单 workspace: deps, overview, search, impact
    ├── workspace 管理: list, info, delete
    └── 跨 workspace: compare, similar

基础设施层
    ├── codeindex (AST 解析, tech-debt, symbols)
    ├── LightRAG (图谱存储, 向量检索, workspace 隔离)
    └── LLM (Claude/GLM, 语义推理)
```

### 边界划分

| 能力 | 归属 | 理由 |
|------|------|------|
| 索引到命名 workspace | **LoomGraph** | 基础设施 |
| workspace 增删查 | **LoomGraph** | 基础设施 |
| 单 workspace deps/overview | **LoomGraph** | 结构化图查询 |
| 两个 workspace 的实体/关系 diff | **LoomGraph** | 结构化图对比 |
| 跨 workspace 相似实体匹配 | **LoomGraph** | 基于名称 + 向量 |
| "合并会冲突吗？怎么解决？" | **Skill 层** | 需要 git + LLM 推理 |
| "继续分叉的代价是什么" | **Skill 层** | 需要 LLM 成本估算 |
| 技术债务检测 (God Class 等) | **codeindex** | 文件级静态分析 |

**原则**: LoomGraph 提供结构化数据能力，Skill 层负责编排 + LLM 推理。

## 新增 CLI 命令规划

### EPIC-005: Workspace 管理

```bash
loomgraph workspace list                    # 列出所有 workspace + 统计
loomgraph workspace info [name]             # 详情 (entity数, relation数, 最后更新)
loomgraph workspace delete <name>           # 清理
```

### EPIC-006: 跨 Workspace 对比

```bash
# 实体/关系 diff
loomgraph compare --ws1 [customer]-backend:main --ws2 [customer]-backend:feature-auth

# 跨 workspace 相似实体检测
loomgraph similar --entity "AuthService" --across-workspaces
```

## 实施路线

```
Phase 1 (快速交付 → Skill A)
├── EPIC-004: deps + overview (单 workspace 智能查询)
├── EPIC-005: workspace list/info/delete (可见性)
└── 交付: Skill A 债务雷达 → 《技术债务报告》

Phase 2 (跨分支能力 → Skill B)
├── EPIC-006: compare + similar (跨 workspace 对比)
├── 技术验证: LightRAG 跨 workspace 查询能力
└── 交付: Skill B 智能同步 → 《同步建议报告》+ 自动 PR

Phase 3 (演化洞察 → Skill C)
├── EPIC-006+: 历史快照 + 趋势分析
└── 交付: Skill C 演化观察 → 《演化报告》+ 代价估算
```

### Epic 依赖关系

```
EPIC-004 (deps/overview)  ──→  Skill A (债务雷达)
     │
EPIC-005 (workspace 管理) ──→  Skill A 增强 (知道哪些项目已索引)
     │
EPIC-006 (跨 ws 对比)    ──→  Skill B (智能同步)
     │                    ──→  Skill C (演化观察)
```

## 技术风险与验证

在投入 EPIC-006 之前需验证：

| 风险 | 影响 | 验证方式 | 时机 |
|------|------|----------|------|
| LightRAG 能否列出所有 workspace | EPIC-005 可行性 | 调 LightRAG API | Phase 1 开始前 |
| Entity 是否保存了文件路径 (`source_id`) | 跨 workspace 实体匹配准确度 | 查已注入数据 | Phase 1 期间 |
| LightRAG 能否跨 workspace 查询 | EPIC-006 实现方式 | API 测试 | Phase 1 完成后 |
| 跨 workspace embedding 对比性能 | similar 命令延迟 | 基准测试 | Phase 2 开始前 |

### 如果 LightRAG 不支持跨 workspace 查询

备选方案：LoomGraph 分别查两个 workspace，在本地做 diff/similarity 计算。增加延迟但不阻塞。

## 后果

### 正面

- workspace 从技术概念变为业务概念，客户容易理解（"这是 main 分支的知识图谱"）
- 为研发熵减三个 Skill 提供统一的数据基座
- 增量交付：Phase 1 就能提供 Skill A 价值，不需要等全部完成

### 负面

- workspace 数量可能膨胀（每个分支/版本一个 workspace）
- 跨 workspace 操作的性能取决于 LightRAG
- 需要文档教育客户理解 workspace 命名约定

### 缓解

- `workspace delete` 命令 + 文档引导清理过时快照
- 性能问题通过 `--module` 缩小范围缓解
- SKILL.md 中内置 workspace 使用指南
