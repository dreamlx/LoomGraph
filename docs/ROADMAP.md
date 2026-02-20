# LoomGraph 开发路线图

**版本**: 0.2.5
**更新日期**: 2026-02-19

---

## 📍 当前状态: Phase 3 第一阶段已完成

**已完成**: MVP 核心 + LightRAG 集成 + CLI + 双通道发布 + deps/overview (EPIC-004) + Workspace 管理 (EPIC-005) + 跨 Workspace 对比 (EPIC-006)
**下一个**: 研发熵减 Skills (EPIC-007)

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

> **目标**: 从"写入调度器"演进为"双向调度器"，提供跨模块分析和研发熵减能力
> **三层交付**: 能力层 (CLI) → Skill 层 (Claude Code) → 集成层 (MCP)

### 第一阶段: 单 Workspace 能力 — v0.3.0

> **ADR**: [ADR-008 双向调度器](adr/ADR-008-bidirectional-orchestrator.md)
> **价值**: 任何客户立即可用，单项目架构理解

| EPIC | Feature | 描述 | 状态 |
|------|---------|------|------|
| EPIC-004 | `loomgraph deps` | 模块级依赖图（纯图查询） | ✅ v0.2.5 |
| EPIC-004 | `loomgraph overview` | 项目模块概览（图查询 + LLM 摘要） | ✅ v0.2.5 |

详见 [EPIC-004](epics/EPIC-004-bidirectional-orchestrator.md)

### 第二阶段: 多 Workspace 能力 — v0.4.0 ~ v0.5.0

> **ADR**: [ADR-009 Workspace 即知识快照](adr/ADR-009-workspace-as-knowledge-snapshot.md)
> **价值**: 多分支/多项目客户，解锁跨分支分析

**v0.4.0 — Workspace 管理 (EPIC-005) ✅**

| Feature | 描述 | 状态 |
|---------|------|------|
| `loomgraph workspace list` | 列出所有 workspace | ✅ |
| `loomgraph workspace info` | 指定 workspace 详情 | ✅ |
| `loomgraph workspace delete` | 清理指定 workspace | ✅ |

详见 [EPIC-005](epics/EPIC-005-workspace-management.md)

**v0.5.0 — 跨 Workspace 对比 (EPIC-006) ✅**

| Feature | 描述 | 状态 |
|---------|------|------|
| `loomgraph compare` | 两个 workspace 的实体/关系 diff | ✅ |
| `loomgraph similar` | 跨 workspace 相似实体检测 | ✅ |

详见 [EPIC-006](epics/EPIC-006-cross-workspace-comparison.md)

### 第三阶段: Skill 交付 — v0.6.0

> **交付**: 3 个 Claude Code Skills，随 wheel 分发，`install-skills` 安装
> **原则**: Skill 是编排者，LoomGraph CLI 提供数据，Skill 负责 LLM 推理 + 报告

| Skill | 名称 | 功能 | 最低依赖 | 状态 |
|-------|------|------|----------|------|
| Skill A | `loomgraph-debt-radar` | 技术债务审计报告 | EPIC-004 (deps/overview) | ✅ |
| Skill B | `loomgraph-sync-advisor` | 跨分支同步建议 | EPIC-006 (compare) | 📋 规划中 |
| Skill C | `loomgraph-evolution` | 代码演化趋势分析 | EPIC-006 (compare/similar) | 📋 规划中 |

详见 [EPIC-007](epics/EPIC-007-entropy-reduction-skills.md)

### 第四阶段: IDE 集成 — v0.7.0

> **定位**: 封装所有 CLI 能力为 MCP 工具，服务 Cursor/IDE 用户
> **放最后的原因**: 能封装最多命令；当前客户群体用 Claude Code Skills，MCP 不紧急

| Story | 描述 | 封装的命令 |
|-------|------|-----------|
| MCP 框架搭建 | FastMCP | — |
| search_code 工具 | 语义搜索 | search |
| get_deps 工具 | 模块依赖 | deps |
| get_overview 工具 | 项目概览 | overview |
| workspace 工具 | workspace 管理 | workspace list/info |
| compare 工具 | 跨 workspace 对比 | compare, similar |

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

| 版本 | 阶段 | 层级 | 主要功能 | 状态 |
|------|------|------|----------|------|
| v0.1.0 | Phase 1 | — | MVP: AST + Embedding + CLI | ✅ 已发布 |
| v0.2.x | Phase 2 | — | LightRAG 集成 + Git + 客户交付 | ✅ 已发布 |
| v0.2.5 | Phase 3 | 能力层 | deps + overview (EPIC-004) | ✅ 已发布 |
| **v0.4.0** | **Phase 3** | **能力层** | **workspace 管理 (list/info/delete)** | **✅ 已完成** |
| **v0.5.0** | **Phase 3** | **能力层** | **跨 workspace 对比 (compare/similar)** | **✅ 已完成** |
| v0.6.0 | Phase 3 | Skill 层 | 研发熵减 Skills (debt-radar/sync-advisor/evolution) | 🔄 Skill A 完成 |
| v0.7.0 | Phase 3 | 集成层 | MCP Server (封装全部命令) | 📋 规划中 |
| v1.0.0 | Phase 4 | — | 生产就绪 | 📋 远期 |

---

## 测试覆盖

| 模块 | 测试数 | 状态 |
|------|--------|------|
| Config | 7 | ✅ |
| Mapper | 26 | ✅ |
| Injector | 8 | ✅ |
| Embedding | 11 | ✅ |
| Indexer | 11 | ✅ |
| CLI | 49 | ✅ |
| LightRAGClient | 18 | ✅ |
| Impact | 19 | ✅ |
| Git | 8 | ✅ |
| DepsAnalyzer | 14 | ✅ |
| OverviewAnalyzer | 10 | ✅ |
| CompareAnalyzer | 11 | ✅ |
| SimilarAnalyzer | 10 | ✅ |
| **Total** | **202** | ✅ |

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
| **ADR-009** | **Workspace 即知识快照** | **从隔离机制到可对比的知识切片** |

---

## 三仓库协作路线

```
          codeindex                    LoomGraph                     LightRAG
          ─────────                    ─────────                     ────────
v0.18+    目录树展开
          AI 模式描述增强
          tech-debt 命令

v0.3.0                                deps (模块依赖图)              graph API
                                      overview (模块概览)            query API

v0.4.0                                workspace list/info/delete     workspace header
                                      (知识快照管理)

v0.5.0                                compare (跨 ws diff)           graph API x2
                                      similar (相似实体检测)

v0.6.0                                Skill A: debt-radar
                                      Skill B: sync-advisor
                                      Skill C: evolution

v0.7.0                                MCP Server
                                      (封装全部命令)
```

### 功能依赖关系图

```
                          能力层                    Skill 层           集成层
                     (v0.3.0 ~ v0.5.0)             (v0.6.0)          (v0.7.0)
                    ┌─────────────────┐        ┌──────────────┐   ┌──────────┐
                    │                 │        │              │   │          │
EPIC-004 ──────────┤ deps            ├───────→│ Skill A      │   │          │
(v0.3.0)           │ overview        │   ┌───→│ 债务雷达     │   │          │
  独立 ↕           │                 │   │    │              │   │          │
EPIC-005 ──────────┤ workspace       ├───┘    ├──────────────┤   │ MCP      │
(v0.4.0)           │ list/info/delete│        │              │   │ Server   │
                    │                 │        │ Skill B      │   │          │
  阻塞 ↓           └────────┬────────┘   ┌───→│ 智能同步     │   │ 封装全部 │
                             │            │    │              │   │ CLI 命令 │
EPIC-006 ──────────┐         │            │    ├──────────────┤   │          │
(v0.5.0)           │ compare ├────────────┘    │              │   │          │
 需要 005          │ similar ├────────────────→│ Skill C      │   │          │
                    │         │                 │ 演化观察     │   │          │
                    └─────────┘                 └──────────────┘   └──────────┘

阻塞关系:
  EPIC-004 ←→ EPIC-005   互相独立，可并行（但建议 004 先行）
  EPIC-005  →  EPIC-006   006 需要 workspace 可见性
  EPIC-004  →  Skill A    deps/overview 是数据源
  EPIC-006  →  Skill B/C  compare/similar 是数据源
  全部能力层 →  MCP       MCP 封装所有命令，放最后覆盖面最广
```

详见 [EPIC-007](epics/EPIC-007-entropy-reduction-skills.md)

---

## 更新日志

- **2026-02-19 (v0.2.5)**:
  - EPIC-004 已完成: `loomgraph deps` + `loomgraph overview`
  - 新增 DepsAnalyzer、OverviewAnalyzer、LightRAGClient bulk API
  - 测试覆盖更新到 163 tests
- **2026-02-18 (v0.2.4)**:
  - Phase 3 重构为四阶段: 能力层 → Skill 层 → 集成层
  - 新增 EPIC-007: 研发熵减 Skills (debt-radar/sync-advisor/evolution)
  - 新增 ADR-009: Workspace 即知识快照
  - 新增 EPIC-005/006: Workspace 管理 + 跨 Workspace 对比
  - 新增功能依赖关系图（阻塞关系 + 并行关系）
  - 版本计划加入"层级"列，明确能力层/Skill 层/集成层
  - MCP Server 调整到 v0.7.0（封装全部命令，放最后覆盖面最广）
  - Skills 调整到 v0.6.0（当前客户用 Claude Code，优先级 > MCP）
  - 新增 Phase 3: 双向调度器 (EPIC-004, ADR-008)
  - 测试覆盖更新到 125 tests
- **2025-02-03 (v0.2.0)**:
  - 更新实际进度 (Phase 1 核心模块完成)
- **2025-02-03 (v0.1.0)**: 初始化路线图文档
