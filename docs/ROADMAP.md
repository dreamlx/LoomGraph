# LoomGraph 开发路线图

**版本**: 0.1.0
**更新日期**: 2025-02-03

---

## 📍 当前状态: Phase 0 - 项目初始化

---

## Phase 1: 基建层 (Core Engine) - M1

> **目标**: 建立存储基础设施和 Embedding 管道

### Epic 1.1: 存储层初始化

| Story | 描述 | 状态 |
|-------|------|------|
| S1.1.1 | 设计 PostgreSQL schema（代码块、向量、实体、关系） | 🔲 TODO |
| S1.1.2 | 实现 pgvector 扩展配置和索引策略 | 🔲 TODO |
| S1.1.3 | 封装数据库连接池和 Repository 层 | 🔲 TODO |
| S1.1.4 | 编写存储层集成测试 | 🔲 TODO |

### Epic 1.2: Embedding 服务封装

| Story | 描述 | 状态 |
|-------|------|------|
| S1.2.1 | 实现 Jina Code V2 Embedding 客户端 | 🔲 TODO |
| S1.2.2 | 支持批量向量化（优化 H200 吞吐量） | 🔲 TODO |
| S1.2.3 | 实现 EmbeddingFunc 适配器（兼容 LightRAG） | 🔲 TODO |
| S1.2.4 | 编写 Embedding 单元测试和基准测试 | 🔲 TODO |

### Epic 1.3: LLM 服务封装

| Story | 描述 | 状态 |
|-------|------|------|
| S1.3.1 | 实现 vLLM 客户端（DeepSeek-Coder） | 🔲 TODO |
| S1.3.2 | 封装 llm_model_func 适配器（兼容 LightRAG） | 🔲 TODO |
| S1.3.3 | 实现请求重试和错误处理 | 🔲 TODO |

**交付物**:
- `loomgraph.storage` 模块
- `loomgraph.core.embedding` 模块
- `loomgraph.core.llm` 模块
- Docker Compose 开发环境

---

## Phase 2: 图谱层 (Graph Brain) - M2

> **目标**: 实现代码解析和图谱构建

### Epic 2.1: AST 代码切片器

| Story | 描述 | 状态 |
|-------|------|------|
| S2.1.1 | 集成 tree-sitter Python binding | 🔲 TODO |
| S2.1.2 | 实现 Python 代码切片器（函数/类粒度） | 🔲 TODO |
| S2.1.3 | 实现 JavaScript/TypeScript 切片器 | 🔲 TODO |
| S2.1.4 | 保留 Docstring 和注释上下文 | 🔲 TODO |
| S2.1.5 | 编写切片器测试用例（边界情况） | 🔲 TODO |

### Epic 2.2: LightRAG 集成

| Story | 描述 | 状态 |
|-------|------|------|
| S2.2.1 | 初始化 LightRAG 实例（注入自定义函数） | 🔲 TODO |
| S2.2.2 | 实现代码块批量插入管道 | 🔲 TODO |
| S2.2.3 | 配置 PostgreSQL 作为 LightRAG 存储后端 | 🔲 TODO |
| S2.2.4 | 实现混合检索接口（naive/local/global/hybrid） | 🔲 TODO |

### Epic 2.3: 图谱查询

| Story | 描述 | 状态 |
|-------|------|------|
| S2.3.1 | 实现调用链查询（谁调用了 X？） | 🔲 TODO |
| S2.3.2 | 实现依赖分析（X 依赖什么？） | 🔲 TODO |
| S2.3.3 | 实现影响范围分析（修改 X 影响谁？） | 🔲 TODO |

**交付物**:
- `loomgraph.chunking` 模块
- `loomgraph.graph` 模块
- 图谱查询 API

---

## Phase 3: 应用层 (Interface) - M3

> **目标**: 提供 CLI 和 MCP 服务接口

### Epic 3.1: CLI 工具

| Story | 描述 | 状态 |
|-------|------|------|
| S3.1.1 | 实现 `loomgraph init` 命令 | 🔲 TODO |
| S3.1.2 | 实现 `loomgraph index` 命令 | 🔲 TODO |
| S3.1.3 | 实现 `loomgraph search` 命令 | 🔲 TODO |
| S3.1.4 | 实现 `loomgraph serve` 命令 | 🔲 TODO |

### Epic 3.2: MCP Server

| Story | 描述 | 状态 |
|-------|------|------|
| S3.2.1 | 实现 MCP Server 基础框架 | 🔲 TODO |
| S3.2.2 | 实现 `search_code` 工具 | 🔲 TODO |
| S3.2.3 | 实现 `get_dependencies` 工具 | 🔲 TODO |
| S3.2.4 | 实现 `get_call_graph` 工具 | 🔲 TODO |
| S3.2.5 | 编写 MCP 集成测试 | 🔲 TODO |

### Epic 3.3: 增量更新

| Story | 描述 | 状态 |
|-------|------|------|
| S3.3.1 | 实现文件系统 Watcher | 🔲 TODO |
| S3.3.2 | 实现增量索引逻辑（差异检测） | 🔲 TODO |
| S3.3.3 | 实现图谱增量更新（处理旧节点） | 🔲 TODO |

**交付物**:
- `loomgraph.cli` 模块
- `loomgraph.mcp` 模块
- MCP 配置文档

---

## Phase 4: 生产就绪 - M4

> **目标**: 性能优化、稳定性加固

### Epic 4.1: 性能优化

| Story | 描述 | 状态 |
|-------|------|------|
| S4.1.1 | H200 批量推理优化（Embedding） | 🔲 TODO |
| S4.1.2 | 图谱查询索引优化 | 🔲 TODO |
| S4.1.3 | 向量检索 HNSW 调优 | 🔲 TODO |
| S4.1.4 | 性能基准测试套件 | 🔲 TODO |

### Epic 4.2: 稳定性

| Story | 描述 | 状态 |
|-------|------|------|
| S4.2.1 | 错误处理和重试机制 | 🔲 TODO |
| S4.2.2 | 健康检查和监控端点 | 🔲 TODO |
| S4.2.3 | 日志和追踪（OpenTelemetry） | 🔲 TODO |

**交付物**:
- 性能测试报告
- 部署文档
- v1.0.0 发布

---

## 当前 Sprint 任务

### Sprint 0: 项目初始化 (当前)

| Task | 描述 | 负责人 | 状态 |
|------|------|--------|------|
| T0.1 | 创建 GitHub 仓库 | - | 🔲 TODO |
| T0.2 | 初始化项目结构（pyproject.toml） | - | 🔲 TODO |
| T0.3 | 配置 CI/CD（GitHub Actions） | - | 🔲 TODO |
| T0.4 | 创建 Docker Compose 开发环境 | - | 🔲 TODO |
| T0.5 | 完成 PRD 和架构文档评审 | - | 🔲 TODO |

### Sprint 1: 存储层 (下一个)

| Task | 描述 | 负责人 | 状态 |
|------|------|--------|------|
| T1.1 | 设计并实现 PostgreSQL schema | - | 🔲 TODO |
| T1.2 | 实现 pgvector 集成 | - | 🔲 TODO |
| T1.3 | 实现 Repository 模式 | - | 🔲 TODO |
| T1.4 | 编写存储层测试 | - | 🔲 TODO |

---

## 版本计划

| 版本 | 里程碑 | 主要功能 | semantic_enhancement |
|------|--------|----------|---------------------|
| v0.1.0 (MVP) | M1 | AST 关系 + 向量检索 + CLI | `false` |
| v0.2.0 | M2 | LLM 语义增强 + MCP 服务 | `true` (可选) |
| v0.3.0 | M3 | 增量更新 + 性能优化 | `true` (可选) |
| v1.0.0 | M4 | 生产就绪 | 按需配置 |

### MVP v0.1.0 范围

```
✅ 包含                          ❌ 不包含 (v0.2.0+)
├── codeindex AST 提取           ├── LLM 语义增强
├── Call/Inheritance 关系        ├── 架构模式识别
├── Jina Code V2 向量化          ├── MCP 服务接口
├── PostgreSQL 存储              └── File Watcher 增量更新
├── CLI: index / search
└── 向量 + 图谱混合检索
```

---

## 风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LightRAG PostgreSQL 支持不完善 | 高 | 准备 Fork 定制方案 |
| Jina Code V2 在 H200 上性能未知 | 中 | 早期进行基准测试 |
| Tree-sitter 多语言支持复杂 | 中 | 先聚焦 Python/JS |

---

## 更新日志

- **2025-02-03**: 初始化路线图文档
