# LoomGraph 开发路线图

**版本**: 0.2.4
**更新日期**: 2026-02-18

---

## 📍 当前状态: Phase 2 已完成，Phase 3 进行中

**已完成**: MVP 核心 + LightRAG 集成 + CLI 全部命令 + 双通道发布 + 客户交付
**进行中**: 项目级智能查询 (EPIC-004)

---

## Phase 1: MVP 核心层 ✅ 已完成

> **目标**: 实现 AST 提取 + 向量化 + 图谱注入的完整 Pipeline

### Epic 1.1 ~ 1.7: 核心模块 ✅

- 数据模型 (ParseResult, EntityData, RelationData)
- Mapper (symbol → entity, call/inheritance/import → relation)
- Injector (单文件 + 批量注入)
- Embedding (Jina Code V2 客户端)
- Indexer (scan + index pipeline)
- CLI (status/index/embed/inject/search/graph/version)
- 配置管理 (Pydantic Settings, YAML + ENV)

---

## Phase 2: 集成与交付 ✅ 已完成

> **目标**: LightRAG 真实集成、Git 集成、客户交付

### Epic 2.1: LightRAG API 集成 ✅

| Story | 状态 |
|-------|------|
| LightRAGClient (httpx, graph endpoints) | ✅ |
| batch_create_graph() (entity → stubs → relations) | ✅ |
| query API (local/global/hybrid/naive) | ✅ |
| delete_all() (workspace 隔离) | ✅ |
| 集成测试 (H200 真实连接) | ✅ |

### Epic 2.2: Git 集成 + Warm Update ✅

| Story | 状态 |
|-------|------|
| `loomgraph update --since` (增量索引 git 变更) | ✅ |
| git 变更文件检测 + codeindex parse | ✅ |
| Impact 分析 (commit/staged/branch diff) | ✅ |

### Epic 2.3: 客户交付 + 双通道发布 ✅

| Story | 状态 |
|-------|------|
| Skills 打入 wheel (hatch force-include) | ✅ |
| `loomgraph install-skills` 命令 | ✅ |
| `loomgraph setup-config` 命令 | ✅ |
| GitHub Actions CI (test.yml + release.yml) | ✅ |
| package.py 改进 (wheel 入 tarball, 移除 config) | ✅ |
| 客户 README 模板 (双通道安装指南) | ✅ |
| bump_version.py --tag | ✅ |

---

## Phase 3: 项目级智能 🔄 进行中

> **目标**: 从"写入调度器"演进为"双向调度器"，提供跨模块分析能力
> **ADR**: [ADR-008 双向调度器](adr/ADR-008-bidirectional-orchestrator.md)

### Epic 3.1: 双向调度器 — 项目级智能查询 (EPIC-004) 📋

| Feature | 描述 | 优先级 | 预估 |
|---------|------|--------|------|
| `loomgraph deps` | 模块级依赖图（纯图查询） | P1 | 2.5d |
| `loomgraph overview` | 项目模块概览（图查询 + LLM 摘要） | P1 | 3.5d |

详见 [EPIC-004](epics/EPIC-004-bidirectional-orchestrator.md)

### Epic 3.2: MCP Server 📋

| Story | 描述 | 优先级 |
|-------|------|--------|
| MCP 框架搭建 | FastMCP | P2 |
| search_code 工具 | 语义搜索 | P2 |
| get_deps 工具 | 模块依赖 | P2 |
| get_overview 工具 | 项目概览 | P2 |

> MCP Server 依赖 EPIC-004 完成后，封装为 MCP 工具。

---

## Phase 4: 生产就绪 — 未开始

> **目标**: 性能优化、监控、企业级特性

### Epic 4.1: 性能优化

| Story | 描述 |
|-------|------|
| H200 批量 Embedding 优化 | 吞吐量提升 |
| 图谱查询缓存 | overview/deps 结果缓存 |
| 大项目基准测试 | 10万+ 行性能报告 |

### Epic 4.2: 企业级特性

| Story | 描述 |
|-------|------|
| 增量 GC (ADR-006 延后项) | commit_sha 版本追踪 |
| 多仓库管理 | 跨仓库依赖分析 |

---

## 版本计划

| 版本 | 阶段 | 主要功能 | 状态 |
|------|------|----------|------|
| v0.1.0 | Phase 1 | MVP: AST + Embedding + CLI | ✅ 已发布 |
| v0.2.0~v0.2.4 | Phase 2 | LightRAG 集成 + Git + 客户交付 | ✅ 已发布 |
| **v0.3.0** | **Phase 3** | **deps + overview (双向调度器)** | **📋 下一个** |
| v0.4.0 | Phase 3 | MCP Server | 📋 规划中 |
| v1.0.0 | Phase 4 | 生产就绪 | 📋 远期 |

---

## 测试覆盖

| 模块 | 测试数 | 状态 |
|------|--------|------|
| Config | 7 | ✅ |
| Mapper | 26 | ✅ |
| Injector | 9 | ✅ |
| Embedding | 11 | ✅ |
| Indexer | 11 | ✅ |
| CLI | 27 | ✅ |
| LightRAGClient | 34 | ✅ |
| **Total** | **125** | ✅ |

---

## 设计决策摘要

| ADR | 决策 | 影响 |
|-----|------|------|
| ADR-001 | PostgreSQL 统一存储 | 简化运维，使用 LightRAG 内置存储 |
| ADR-002 | 选择 LightRAG | 轻量框架，复用现有 API |
| ADR-003 | tree-sitter 解析 | codeindex 负责，LoomGraph 不自己解析 |
| ADR-005 | AST 优先提取 | MVP 不使用 LLM 提取 |
| ADR-006 | MVP 简化 | 全量重建，无增量 GC |
| ADR-007 | Code Content 提取 | 函数体内容注入策略 |
| **ADR-008** | **双向调度器** | **codeindex/LoomGraph 能力边界** |

---

## 三仓库协作路线

```
          codeindex                    LoomGraph                     LightRAG
          ─────────                    ─────────                     ────────
v0.18+    目录树展开
          AI 模式描述增强

v0.3.0                                deps (模块依赖图)              graph API
                                      overview (模块概览)            query API

v0.4.0                                MCP Server
                                      (封装 deps/overview/search)
```

---

## 更新日志

- **2026-02-18 (v0.2.4)**:
  - 更新实际进度到 Phase 2 完成
  - 新增 Phase 3: 双向调度器 (EPIC-004, ADR-008)
  - 新增三仓库协作路线图
  - 测试覆盖更新到 125 tests
- **2025-02-03 (v0.2.0)**:
  - 更新实际进度 (Phase 1 核心模块完成)
- **2025-02-03 (v0.1.0)**: 初始化路线图文档
