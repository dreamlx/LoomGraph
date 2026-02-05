# LoomGraph 文档索引

**更新日期**: 2025-02-04
**项目版本**: 0.1.0 (MVP 开发中)

---

## 文档状态说明

| 状态 | 说明 |
|------|------|
| ✅ 确认 | 已审核，反映当前设计 |
| 📝 草稿 | 初稿，可能需要更新 |
| 🔄 讨论中 | 设计讨论，未最终确定 |
| ⚠️ 过时 | 需要更新以匹配当前实现 |

---

## 核心文档

### 产品与规划

| 文档 | 状态 | 说明 |
|------|------|------|
| [PRD.md](PRD.md) | 📝 草稿 | 产品需求文档，定义目标用户和功能需求 |
| [ROADMAP.md](ROADMAP.md) | ✅ 确认 | 开发路线图 (Phase 1 CLI 完成) |
| [WORKSTREAM_ASSIGNMENT.md](WORKSTREAM_ASSIGNMENT.md) | ✅ 确认 | 三仓库工作流分配 |

### 架构设计

| 文档 | 状态 | 说明 |
|------|------|------|
| [architecture/SYSTEM_DESIGN.md](architecture/SYSTEM_DESIGN.md) | ✅ 确认 | **核心文档** - 系统架构、Pipeline、模块设计 |
| [architecture/TOOLBOX_OVERVIEW.md](architecture/TOOLBOX_OVERVIEW.md) | ✅ 确认 | 三仓库工具箱整体架构 |
| [architecture/FEATURE_BOUNDARY.md](architecture/FEATURE_BOUNDARY.md) | ✅ 确认 | LightRAG Fork vs LoomGraph 功能边界 |
| [architecture/GRAPH_OPTIMIZATION_DISCUSSION.md](architecture/GRAPH_OPTIMIZATION_DISCUSSION.md) | ✅ 已决策 | AST vs LLM 提取策略 (采用 AST，见 ADR-005) |
| [architecture/UPDATE_STRATEGY.md](architecture/UPDATE_STRATEGY.md) | ✅ 确认 | Hot/Warm/Cold 更新策略 |

### API 文档

| 文档 | 状态 | 说明 |
|------|------|------|
| [api/DATA_CONTRACT.md](api/DATA_CONTRACT.md) | ✅ 确认 | **关键文档** - codeindex ↔ LightRAG 数据映射 |
| [api/CLI_DESIGN.md](api/CLI_DESIGN.md) | ✅ 确认 | CLI 命令设计 (AI Agent 友好) |

### 架构决策记录 (ADR)

| 文档 | 状态 | 说明 |
|------|------|------|
| [adr/ADR-001-postgresql-unified-storage.md](adr/ADR-001-postgresql-unified-storage.md) | ✅ 确认 | PostgreSQL 统一存储决策 |
| [adr/ADR-002-lightrag-framework.md](adr/ADR-002-lightrag-framework.md) | ✅ 确认 | 选择 LightRAG 框架 |
| [adr/ADR-003-code-parser-strategy.md](adr/ADR-003-code-parser-strategy.md) | ✅ 确认 | 代码解析策略 (tree-sitter) |
| [adr/ADR-004-lightrag-fork-strategy.md](adr/ADR-004-lightrag-fork-strategy.md) | ✅ 确认 | LightRAG Fork 策略 |
| [adr/ADR-005-extraction-strategy.md](adr/ADR-005-extraction-strategy.md) | ✅ 确认 | AST 优先提取策略 |
| [adr/ADR-006-mvp-simplification.md](adr/ADR-006-mvp-simplification.md) | ✅ 确认 | MVP 简化决策 (全量重建) |

### 集成文档

| 文档 | 状态 | 说明 |
|------|------|------|
| [integration/LIGHTRAG_REQUIREMENTS.md](integration/LIGHTRAG_REQUIREMENTS.md) | ✅ 已确认 | LightRAG API 需求文档 (已与 LightRAG 团队确认) |

---

## 文档依赖关系

```
PRD.md (产品需求)
    │
    ├── WORKSTREAM_ASSIGNMENT.md (工作分配)
    │       │
    │       └── TOOLBOX_OVERVIEW.md (工具箱架构)
    │
    └── SYSTEM_DESIGN.md (系统设计) ◄── 核心入口
            │
            ├── DATA_CONTRACT.md (数据契约)
            │
            ├── CLI_DESIGN.md (CLI 设计)
            │
            └── ADR-00X (架构决策)
```

---

## 快速导航

### 我想了解...

| 问题 | 阅读顺序 |
|------|----------|
| **项目是什么？** | PRD.md → TOOLBOX_OVERVIEW.md |
| **整体架构？** | SYSTEM_DESIGN.md |
| **三仓库如何协作？** | WORKSTREAM_ASSIGNMENT.md → DATA_CONTRACT.md |
| **CLI 如何使用？** | CLI_DESIGN.md |
| **为什么这样设计？** | ADR-001 ~ ADR-006 |
| **MVP 范围是什么？** | ADR-006-mvp-simplification.md |

### 开发参考

| 任务 | 参考文档 |
|------|----------|
| 实现 Mapper | DATA_CONTRACT.md Section 3 |
| 实现 Injector | DATA_CONTRACT.md Section 4 |
| 实现 CLI | CLI_DESIGN.md |
| 集成 codeindex | SYSTEM_DESIGN.md Section 3.3 |
| 集成 LightRAG | integration/LIGHTRAG_REQUIREMENTS.md |

---

## 待完成文档

| 文档 | 优先级 | 说明 |
|------|--------|------|
| `deployment/DOCKER.md` | 中 | Docker 部署指南 |
| `deployment/H200.md` | 低 | H200 生产环境配置 |
| `api/MCP_DESIGN.md` | 低 | MCP 服务设计 (v0.2.0) |
| `tutorials/QUICKSTART.md` | 中 | 快速开始教程 |

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.3.0 | 2025-02-04 | 添加 integration/LIGHTRAG_REQUIREMENTS.md, CLI 实现完成 |
| 0.2.0 | 2025-02-03 | 添加 CLI_DESIGN.md, 更新 SYSTEM_DESIGN.md Pipeline 章节 |
| 0.1.0 | 2025-02-03 | 初始文档结构，DATA_CONTRACT.md, ADR-001~006 |
