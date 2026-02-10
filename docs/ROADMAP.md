# LoomGraph 开发路线图

**版本**: 0.2.0
**更新日期**: 2025-02-03

---

## 📍 当前状态: Phase 1 - MVP 核心开发中

**已完成**: 项目初始化、核心模块实现、CLI 实现、文档设计
**进行中**: LightRAG 集成、集成测试

---

## Phase 0: 项目初始化 ✅ 已完成

> **目标**: 建立项目结构和设计文档

| Task | 描述 | 状态 |
|------|------|------|
| 初始化 pyproject.toml | 项目配置、依赖管理 | ✅ 完成 |
| 创建项目目录结构 | src/loomgraph 模块划分 | ✅ 完成 |
| 设计三仓库架构 | codeindex → LoomGraph → LightRAG | ✅ 完成 |
| 编写 DATA_CONTRACT.md | 数据映射规范 | ✅ 完成 |
| 编写 SYSTEM_DESIGN.md | 系统架构设计 | ✅ 完成 |
| ADR 决策记录 | ADR-001 ~ ADR-006 | ✅ 完成 |

---

## Phase 1: MVP 核心层 🔄 进行中

> **目标**: 实现 AST 提取 + 向量化 + 图谱注入的完整 Pipeline

### Epic 1.1: 核心数据模型 ✅

| Story | 描述 | 状态 |
|-------|------|------|
| 定义 ParseResult 模型 | Symbol, Call, Inheritance, Import | ✅ 完成 |
| 定义 EntityData/RelationData | LightRAG 输入格式 | ✅ 完成 |
| 定义 InjectResult/IndexResult | 操作结果模型 | ✅ 完成 |

### Epic 1.2: Mapper 模块 ✅

| Story | 描述 | 状态 |
|-------|------|------|
| map_symbol_to_entity() | Symbol → LightRAG Entity | ✅ 完成 |
| map_call_to_relation() | Call → CALLS 关系 | ✅ 完成 |
| map_inheritance_to_relation() | Inheritance → INHERITS 关系 | ✅ 完成 |
| map_import_to_relation() | Import → IMPORTS 关系 | ✅ 完成 |
| detect_language() | 语言检测 | ✅ 完成 |
| 单元测试 (26 tests) | 映射函数测试 | ✅ 完成 |

### Epic 1.3: Injector 模块 ✅

| Story | 描述 | 状态 |
|-------|------|------|
| inject_parse_result() | 单文件注入 | ✅ 完成 |
| inject_parse_results_batch() | 批量注入 | ✅ 完成 |
| 错误处理 | 记录错误继续处理 | ✅ 完成 |
| 单元测试 (9 tests) | 注入逻辑测试 | ✅ 完成 |

### Epic 1.4: Embedding 模块 ✅

| Story | 描述 | 状态 |
|-------|------|------|
| JinaEmbeddingClient | TEI/Jina API 客户端 | ✅ 完成 |
| 批量向量化 | batch_size 配置 | ✅ 完成 |
| 重试机制 | embed_with_retry() | ✅ 完成 |
| 单元测试 (11 tests) | Embedding 测试 | ✅ 完成 |

### Epic 1.5: Indexer 模块 ✅

| Story | 描述 | 状态 |
|-------|------|------|
| scan_code_files() | 代码文件扫描 | ✅ 完成 |
| index_repository() | 全量索引 Pipeline | ✅ 完成 |
| index_file() | 单文件索引 | ✅ 完成 |
| 单元测试 (11 tests) | 索引逻辑测试 | ✅ 完成 |

### Epic 1.6: CLI 实现 ✅

| Story | 描述 | 状态 |
|-------|------|------|
| CLI 设计文档 | CLI_DESIGN.md | ✅ 完成 |
| loomgraph status | 检查系统状态 | ✅ 完成 |
| loomgraph index | 一键索引 | ✅ 完成 |
| loomgraph embed | 生成向量 | ✅ 完成 |
| loomgraph inject | 注入图谱 | ✅ 完成 |
| loomgraph search | 语义搜索 | ✅ 完成 (待 LightRAG 集成) |
| loomgraph graph | 图谱查询 | ✅ 完成 (待 LightRAG 集成) |
| 单元测试 (27 tests) | CLI 命令测试 | ✅ 完成 |

### Epic 1.7: 配置管理 ✅

| Story | 描述 | 状态 |
|-------|------|------|
| Settings 类 | Pydantic 配置管理 | ✅ 完成 |
| EmbeddingConfig | Jina 配置 | ✅ 完成 |
| DatabaseConfig | PostgreSQL 配置 | ✅ 完成 |
| 环境变量支持 | LOOMGRAPH_* 前缀 | ✅ 完成 |
| 单元测试 (7 tests) | 配置测试 | ✅ 完成 |

**Phase 1 交付物**:
- ✅ `loomgraph.core.models` - 数据模型
- ✅ `loomgraph.core.mapper` - 映射函数
- ✅ `loomgraph.core.injector` - 注入逻辑
- ✅ `loomgraph.core.indexer` - 索引 Pipeline
- ✅ `loomgraph.core.config` - 配置管理
- ✅ `loomgraph.embedding` - Embedding 客户端
- ✅ `loomgraph.cli` - CLI 工具 (JSON 输出，AI Agent 友好)
- ✅ 91 单元测试通过

---

## Phase 2: 集成与服务 - 待开始

> **目标**: LightRAG 集成、MCP 服务

### Epic 2.1: LightRAG 集成

| Story | 描述 | 状态 |
|-------|------|------|
| LightRAG 初始化 | 配置 PostgreSQL 存储 | 🔲 TODO |
| aquery() 封装 | 混合检索接口 | 🔲 TODO |
| 集成测试 | 端到端测试 | 🔲 TODO |

### Epic 2.2: codeindex CLI 集成

| Story | 描述 | 状态 |
|-------|------|------|
| subprocess 调用 | codeindex scan | 🔲 TODO |
| JSON 解析 | ParseResult.from_json() | 🔲 TODO |
| 错误处理 | 结构化错误返回 | 🔲 TODO |

### Epic 2.3: MCP Server (v0.2.0)

| Story | 描述 | 状态 |
|-------|------|------|
| MCP 框架搭建 | FastMCP 或原生 | 🔲 TODO |
| search_code 工具 | 语义搜索 | 🔲 TODO |
| get_callers 工具 | 调用者查询 | 🔲 TODO |
| get_callees 工具 | 被调用者查询 | 🔲 TODO |

---

## Phase 3: 生产就绪 - 未开始

> **目标**: 性能优化、部署文档

### Epic 3.1: 性能优化

| Story | 描述 | 状态 |
|-------|------|------|
| H200 批量优化 | Embedding 吞吐量 | 🔲 TODO |
| 图谱查询优化 | 索引调优 | 🔲 TODO |
| 基准测试 | 性能报告 | 🔲 TODO |

### Epic 3.2: 部署

| Story | 描述 | 状态 |
|-------|------|------|
| Docker Compose | 开发环境 | 🔲 TODO |
| H200 部署文档 | 生产环境 | 🔲 TODO |

---

## 测试覆盖

| 模块 | 测试文件 | 测试数 | 状态 |
|------|----------|--------|------|
| Config | test_config.py | 7 | ✅ |
| Mapper | test_mapper.py | 26 | ✅ |
| Injector | test_injector.py | 9 | ✅ |
| Embedding | test_embedding.py | 11 | ✅ |
| Indexer | test_indexer.py | 11 | ✅ |
| CLI | test_cli.py | 27 | ✅ |
| **Total** | | **91** | ✅ |

---

## 版本计划

| 版本 | 目标 | 主要功能 | semantic_enhancement |
|------|------|----------|---------------------|
| **v0.1.0 (MVP)** | 当前 | AST 关系 + 向量检索 + CLI | `false` |
| v0.2.0 | 下一个 | MCP 服务 + 查询优化 | `false` |
| v0.3.0 | 未来 | LLM 语义增强 (可选) | `true` (可选) |
| v1.0.0 | 长期 | 生产就绪 | 按需配置 |

### MVP v0.1.0 范围

```
✅ 已完成                         🔄 进行中                    ❌ 不包含 (v0.2.0+)
├── 数据模型和映射               ├── LightRAG 集成           ├── LLM 语义增强
├── Embedding 客户端             └── 集成测试                ├── MCP 服务接口
├── Injector Pipeline                                       └── File Watcher
├── Indexer Pipeline
├── 配置管理
├── CLI 工具 (JSON 输出)
└── 91 单元测试
```

---

## 设计决策摘要

| ADR | 决策 | 影响 |
|-----|------|------|
| ADR-001 | PostgreSQL 统一存储 | 简化运维，使用 LightRAG 内置存储 |
| ADR-002 | 选择 LightRAG | 轻量框架，复用现有 API |
| ADR-003 | tree-sitter 解析 | codeindex 负责，LoomGraph 不自己解析 |
| ADR-004 | LightRAG Fork 策略 | 最小改动，主要复用 |
| ADR-005 | AST 优先提取 | MVP 不使用 LLM 提取 |
| ADR-006 | MVP 简化 | 全量重建，无增量 GC |

---

## 更新日志

- **2025-02-03 (v0.2.0)**:
  - 更新实际进度 (Phase 1 核心模块完成)
  - 添加测试覆盖统计
  - 调整 Epic 结构匹配实际实现
- **2025-02-03 (v0.1.0)**: 初始化路线图文档
