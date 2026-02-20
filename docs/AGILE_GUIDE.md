# 敏捷开发流程指南

**适用范围**: LoomGraph / codeindex / LightRAG 三仓库
**更新日期**: 2026-02-20

---

## 1. 概念层级

```
ADR (架构决策记录)              "为什么这样设计"
  └── Epic                     "做什么大目标"
       └── Feature             "交付什么功能"
            └── Story          "用户要什么"（可选）
                 └── Task      "开发者做什么"
```

### 1.1 各层级定义

| 层级 | 定义 | 粒度 | 谁写 | 是否可关闭 | 有代码改动 |
|------|------|------|------|-----------|-----------|
| **ADR** | 记录一个**架构决策**的上下文、选项和理由 | 跨 Epic | 架构师 | 否（永久存档） | 否 |
| **Epic** | 一个完整的**业务目标**，通常对应一个版本 | 1-3 个版本 | PM/架构师 | 是 | 否 |
| **Feature** | Epic 内**一个可独立交付的功能点** | 1-2 周 | PM | 是 | 否 |
| **Story** | 从**用户视角**描述的需求切片（可选） | 2-5 天 | PM + 用户 | 是 | 否 |
| **Task** | 开发者的**具体工作项** | 几小时~1 天 | 开发者 | 是 | 是 |

### 1.2 什么时候可以跳过 Story？

Story 的核心价值是"站在用户角度思考需求"。以下场景可以跳过 Story，直接从 Feature 到 Task：

- **用户是 AI Agent**：不需要 "作为用户，我希望……" 的叙述格式
- **需求已经足够明确**：Feature 描述已包含输入/输出/验收标准
- **纯技术性工作**：重构、性能优化、基础设施搭建

保留 Story 的场景：
- 面向人类终端用户的功能
- 需求模糊，需要通过 Story 来澄清边界

### 1.3 各层级之间的关系

```
ADR-009 (Workspace 即知识快照)
  ↓ 指导
EPIC-006 (跨 Workspace 对比)
  ├── Feature: loomgraph compare
  │     ├── Task: 写 test_compare.py
  │     ├── Task: 实现 CompareAnalyzer
  │     └── Task: CLI 注册 compare 命令
  └── Feature: loomgraph similar
        ├── Task: 写 test_similar.py
        ├── Task: 实现 SimilarAnalyzer
        └── Task: CLI 注册 similar 命令
```

---

## 2. ADR (Architecture Decision Record)

### 2.1 什么时候写 ADR

- 选择了一个技术方案而放弃了另一个
- 确立了一个跨模块/跨仓库的设计约定
- 做了一个不可逆或难以回退的决策

### 2.2 ADR 不是什么

- 不是需求文档（那是 Epic/Feature）
- 不是 Issue（ADR 永远不应该被"关闭"或"完成"）
- 不是设计文档（ADR 只记录决策和理由，不写详细实现）

### 2.3 文件位置

```
docs/adr/ADR-NNN-short-title.md
```

### 2.4 模板

```markdown
# ADR-NNN: 标题

**状态**: 提议 / 已确认 / 已废弃
**日期**: YYYY-MM-DD

## 背景
为什么需要做这个决策？

## 选项
1. 方案 A — 优点 / 缺点
2. 方案 B — 优点 / 缺点

## 决策
选择方案 X。

## 理由
为什么选 X 而不选 Y。

## 影响
这个决策影响了哪些 Epic/模块/仓库。
```

---

## 3. Epic

### 3.1 Epic 文档

每个 Epic 在 `docs/epics/` 下有一个详细文档，包含完整的背景、Feature 分解、验收标准。

```
docs/epics/EPIC-NNN-short-title.md
```

### 3.2 Epic 文档内容

- 背景和业务目标
- Feature 分解（含预估）
- 技术方案概要
- 验收标准（checklist）
- 风险
- 依赖关系

### 3.3 Epic 与 GitHub Issue

每个 Epic 在 GitHub 上建一个 Issue（label: `epic`），用 checklist 跟踪 Feature 完成状态：

```markdown
## Features
- [x] `loomgraph compare` 命令 #11
- [x] `loomgraph similar` 命令 #12

详细设计: docs/epics/EPIC-006-cross-workspace-comparison.md
```

Epic Issue 绑定 Milestone，在版本发布时批量关闭。

---

## 4. Feature / Task

### 4.1 Feature

Feature 是 Epic 内的一个可独立交付的功能点。在 GitHub 上可以建 Issue（label: `feature`），也可以在 Epic Issue 的 checklist 中直接追踪。

**建 Issue 的标准**：需要多个 PR 才能完成、或者需要跨协作者的 Feature 建独立 Issue。单 PR 可完成的 Feature 用 Epic checklist 即可。

### 4.2 Task

Task 是开发者的具体工作项。**不建 GitHub Issue**，在以下位置追踪：

- PR description 中的 checklist
- Claude Code 会话内的 TaskCreate/TaskUpdate
- commit message 中体现

---

## 5. GitHub 工作流

### 5.1 Labels

| Label | 颜色 | 用途 |
|-------|------|------|
| `epic` | `#7B61FF` 紫色 | 业务目标跟踪 |
| `feature` | `#1D76DB` 蓝色 | 可独立交付的功能点 |
| `bug` | `#D73A4A` 红色 | 缺陷（保留 GitHub 默认） |
| `docs` | `#0075CA` 蓝灰 | 文档（保留 GitHub 默认） |
| `refactor` | `#FBCA04` 黄色 | 重构 / 技术债务 |
| `infra` | `#E4E669` 浅黄 | CI/CD / 打包 / 部署 |

**不建议的 label**: `task`（太碎，不建 Issue）、`adr`（ADR 不建 Issue）、`story`（当前场景跳过）。

### 5.2 Milestones

每个版本对应一个 Milestone：

```
v0.5.0  ← EPIC-005 + EPIC-006
v0.6.0  ← EPIC-007
v0.7.0  ← MCP Server
```

### 5.3 Issue → PR → Close 流程

```
1. Epic Issue 创建，绑定 Milestone
2. Feature 分支开发: feature/epic-006-cross-workspace
3. PR 描述中写: Closes #11 (Feature Issue) 或在 Epic Issue checklist 勾选
4. Merge PR → Feature Issue 自动关闭
5. 版本发布时 → 关闭 Epic Issue + 关闭 Milestone
```

### 5.4 命名约定

| 类型 | Issue 标题格式 | 分支格式 |
|------|---------------|----------|
| Epic | `EPIC-NNN: 简短描述` | `feature/epic-NNN-short-name` |
| Feature | `feat: 功能描述` | 同 Epic 分支（一个分支含多个 Feature） |
| Bug | `bug: 问题描述` | `bugfix/short-name` |

### 5.5 Commit 规范

```
<type>(<scope>): <subject>

type: feat / fix / docs / refactor / test / chore
scope: core / cli / skills / embedding / ...
```

---

## 6. 跨仓库协作

三个仓库各自维护自己的 Epic/Issue 体系，通过以下方式协调：

### 6.1 依赖标注

在 Epic 文档的"依赖"字段标注跨仓库依赖：

```markdown
**依赖**:
- codeindex >= v0.18 (目录树展开)
- LightRAG API: /graph/entities/all 端点
```

### 6.2 数据契约

跨仓库的接口通过 `docs/api/DATA_CONTRACT.md` 约定：

```
codeindex parse JSON → LoomGraph mapper → LightRAG HTTP API
```

接口变更必须同步更新 DATA_CONTRACT.md 并通知下游仓库。

### 6.3 版本对齐

三仓库版本独立，但在 ROADMAP.md 中标注版本对应关系：

```
codeindex v0.18  ←→  LoomGraph v0.5.0  ←→  LightRAG (latest API)
```

---

## 7. 速查表

### 我应该建什么？

| 场景 | 建什么 |
|------|--------|
| 确定用技术方案 A 而非 B | ADR |
| 要做一个跨版本的大功能 | Epic Issue + `docs/epics/` 文档 |
| Epic 内的一个独立功能点 | Epic checklist 条目（或 Feature Issue） |
| 具体的编码工作 | 不建 Issue，在 PR/commit 中体现 |
| 发现了 bug | Bug Issue |
| 需要更新文档 | 直接提 PR（简单）或 Docs Issue（复杂） |

### 我应该在哪里记录？

| 内容 | 位置 |
|------|------|
| 架构决策 | `docs/adr/ADR-NNN.md` |
| Epic 详细设计 | `docs/epics/EPIC-NNN.md` |
| Epic 进度跟踪 | GitHub Issue (label: `epic`) |
| 版本进度 | GitHub Milestone |
| 变更记录 | `CHANGELOG.md` |
| 路线图 | `docs/ROADMAP.md` |
