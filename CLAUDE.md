<!-- codeindex:start -->
## codeindex

This project uses codeindex for AI-friendly code documentation.

**First-time setup** (if no README_AI.md files exist):
1. Review `.codeindex.yaml` — verify `include`/`exclude` patterns match this project's structure
2. Run `codeindex scan-all` to generate indexes
3. Optional: `codeindex hooks install post-commit` for auto-updates on commit

**Daily usage**:
- **Always read README_AI.md** before exploring source code in any directory
- If README_AI.md is missing or outdated, run: `codeindex scan <dir>`
- Check documentation coverage: `codeindex status`
<!-- codeindex:end -->

# LoomGraph 项目开发规范

## 项目概述

LoomGraph 是一款基于 NVIDIA H200 的企业级代码智能理解引擎，结合 LightRAG 图谱技术与 Jina Code V2 向量化，实现千万行代码的语义检索与依赖分析。

**设计目标**: 作为 Claude Code Skill，主要用户是 AI Agent。

## 三仓库架构

```
codeindex (AST 解析)  →  LoomGraph (调度)  →  LightRAG (存储检索)
     CLI                    CLI/Skill              API
```

| 仓库 | 职责 | 路径 |
|------|------|------|
| **codeindex** | AST 解析，提取 Symbol/Call/Inheritance | `/Users/dreamlinx/Projects/codeindex` |
| **LoomGraph** | Pipeline 调度，Embedding，Claude Code Skill | 本项目 |
| **LightRAG** | 图谱存储，向量检索，查询 | `/Users/dreamlinx/Projects/LightRAG` |

## 存储所有权（重要）

LoomGraph **不直接操作数据库**。全部存储由 LightRAG 管理：

```
codeindex (解析) → LoomGraph (映射) → LightRAG API → PostgreSQL
                    ↑ 不碰 DB              ↑ 拥有 DB
```

- **PostgreSQL 实例**: 1 个，LightRAG 初始化时自动建表
- **LoomGraph 角色**: 纯调度 + 数据映射，通过 `rag.acreate_entity()` / `rag.acreate_relation()` / `rag.aquery()` 读写
- **docker-compose.yml**: 为 LightRAG 提供 PG 实例，LoomGraph 不直接连接
- **LoomGraph 无自有表**: `storage/` 目录预留，当前为空

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| Compute | NVIDIA H200 (141GB HBM3) | FP8 推理 + 批量 Embedding |
| Embedding | Jina Code V2 (8k context) | 代码语义向量化 |
| RAG Framework | LightRAG | 图谱构建与检索 (使用内置 API) |
| AST Parser | codeindex (tree-sitter) | 独立 CLI 工具 |
| Database | PostgreSQL + pgvector | 向量 + 图谱混合存储 (LightRAG 管理) |
| Protocol | MCP (Model Context Protocol) | Claude/Cursor 集成 |

## 项目结构

```
loomgraph/
├── src/loomgraph/
│   ├── core/           # 核心引擎（LightRAG 集成、配置管理）
│   ├── embedding/      # Embedding 客户端（Jina Code V2）
│   ├── mcp/            # MCP 服务接口
│   └── cli/            # 命令行工具
├── tests/              # 测试用例（单元 + 集成）
├── docs/               # 项目文档
│   ├── architecture/   # 架构设计文档
│   ├── api/            # API 文档
│   └── adr/            # 架构决策记录
└── scripts/            # 部署与工具脚本
```

## 开发流程

### GitFlow 分支策略

```
main (生产) ← release/* ← develop ← feature/*
                                  ← bugfix/*
                                  ← hotfix/*
```

- `main`: 生产就绪版本，只接受 release 合并
- `develop`: 开发主线，功能集成点
- `feature/*`: 功能分支，如 `feature/ast-chunker`
- `release/*`: 发布预备分支
- `hotfix/*`: 生产紧急修复

### TDD 开发循环

1. **Red**: 先写失败的测试用例
2. **Green**: 写最小实现让测试通过
3. **Refactor**: 重构代码，保持测试通过

### 测试要求

- 核心模块覆盖率 ≥ 90%
- 整体覆盖率 ≥ 80%
- 每个 Feature 必须包含：
  - 单元测试 (`tests/unit/`)
  - 集成测试 (`tests/integration/`)
  - 性能基准 (`tests/benchmark/`)

## 代码规范

### Python 风格

- Python 3.11+
- 使用 `ruff` 进行 lint 和格式化
- 类型注解必须完整（mypy strict mode）
- Docstring 使用 Google 风格

### 命名约定

- 模块/文件: `snake_case.py`
- 类: `PascalCase`
- 函数/变量: `snake_case`
- 常量: `UPPER_SNAKE_CASE`
- 私有成员: `_leading_underscore`

### 提交规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

示例:
```
feat(chunking): implement Python AST parser with tree-sitter

- Add tree-sitter-python binding
- Support function and class extraction
- Preserve docstrings in chunks

Closes #12
```

## 环境配置

### 本地开发

```bash
# 创建虚拟环境
uv venv && source .venv/bin/activate

# 安装依赖
uv pip install -e ".[dev]"

# 运行测试
pytest tests/ -v --cov=src/loomgraph

# 代码检查
ruff check src/ tests/
mypy src/
```

### H200 服务器

| 服务 | 端口 | URL |
|------|------|-----|
| GLM-4.7-fp8 (LLM) | 3000 | http://117.131.45.179:3000 |
| LightRAG API | 3001 | http://117.131.45.179:3001 |
| TEI Jina Code V2 | 3002 | http://117.131.45.179:3002 |

### 配置文件

创建 `.loomgraph.yaml` 配置 H200 连接：

```yaml
# .loomgraph.yaml
lightrag:
  api_url: "http://117.131.45.179:3001"
  api_timeout: 30.0

embedding:
  base_url: "http://117.131.45.179:3002"
```

配置优先级：
1. 环境变量 (`LOOMGRAPH_LIGHTRAG__API_URL`)
2. `.loomgraph.yaml` 当前目录
3. `~/.config/loomgraph/config.yaml`
4. 默认值

## 关键设计决策

### ADR-001: 选择 LightRAG 而非 Microsoft GraphRAG

- **决策**: 使用 LightRAG 作为图谱构建框架
- **原因**:
  - 构建速度快 100x（适合增量更新）
  - 内存占用低
  - 易于自定义 embedding 和 LLM 函数

### ADR-002: AST Pre-Chunking 策略

- **决策**: 在 LightRAG.insert() 之前进行 AST 解析
- **原因**:
  - LightRAG 默认按 token 切分会破坏代码逻辑完整性
  - Tree-sitter 可保证函数/类边界完整
  - Jina Code V2 需要完整代码块才能理解语义

### ADR-003: PostgreSQL 统一存储

- **决策**: 使用 PostgreSQL + pgvector 而非 Neo4j + Milvus
- **原因**:
  - 减少运维复杂度
  - pgvector 性能足够（百万级向量）
  - 事务一致性保证

## 性能目标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 索引吞吐量 | 10k files/min | 增量索引 |
| 向量检索延迟 | < 50ms | Top-100 |
| 图谱检索延迟 | < 200ms | 2-hop 查询 |
| 显存占用 | < 80GB | 留空间给 LLM |

## CLI 命令 (AI Agent 友好)

所有命令输出 JSON 格式，便于 AI 解析。

### 命令速查表

| 命令 | 说明 |
|------|------|
| `loomgraph version` | 显示版本信息 |
| `loomgraph status` | 检查服务连接状态 |
| `loomgraph index <path>` | 一键索引代码库 |
| `loomgraph index --clear <path>` | Cold Rebuild（清空重建） |
| `loomgraph update [--since REF]` | Warm Update（增量索引 git 变更） |
| `loomgraph search "<query>"` | 语义搜索代码 |
| `loomgraph graph "<entity>"` | 查询调用关系 |
| `loomgraph impact [TARGET]` | 分析代码变更影响 |

### 版本与状态

```bash
loomgraph version  # 显示版本
loomgraph status   # 检查 codeindex、LightRAG、embedding 服务
```

### 索引代码库

```bash
# 一键索引（默认 Cold Rebuild）
loomgraph index /path/to/repo

# 明确 Cold Rebuild（清空后重建）
loomgraph index --clear /path/to/repo

# Warm Update（仅索引 git 变更文件）
loomgraph update                 # 对比 HEAD~1
loomgraph update --since HEAD~5  # 对比最近 5 个提交
```

### 分步索引（高级用法）

```bash
# Step 1: AST 解析
codeindex scan /repo --output json > parse_results.json

# Step 2: 生成 Embedding
loomgraph embed parse_results.json --output embeddings.json

# Step 3: 注入 LightRAG
loomgraph inject parse_results.json embeddings.json
```

### 语义搜索

```bash
loomgraph search "用户认证逻辑"
loomgraph search "how to validate password" --mode local
loomgraph search "database connection" --mode hybrid --limit 20
```

搜索模式：`local`（实体优先）、`global`（全局）、`hybrid`（混合，默认）

### 查询调用图

```bash
# 谁调用了这个函数
loomgraph graph "UserService.login" --direction callers

# 这个函数调用了谁
loomgraph graph "UserService.login" --direction callees

# 指定深度和关系类型
loomgraph graph "MyClass" --depth 3 --relation-type INHERITS
```

注意：调用图查询依赖 codeindex 输出 calls 关系。

### 变更影响分析

```bash
# 分析最近提交的影响
loomgraph impact HEAD

# 分析暂存区变更
loomgraph impact --staged

# 分析指定文件
loomgraph impact --file src/auth/login.py
```

### 错误处理

命令失败时返回结构化错误，AI Agent 可据此修复：

```json
{
  "success": false,
  "error": {
    "code": "CODEINDEX_NOT_FOUND",
    "message": "codeindex command not found",
    "suggestion": "pip install ai-codeindex"
  }
}
```

## 开发命令

```bash
# 启动开发数据库
docker compose up -d postgres

# 运行特定测试
pytest tests/unit/test_mapper.py -v

# 运行所有测试
pytest tests/ -v --cov=src/loomgraph

# 代码检查
ruff check src/ tests/
mypy src/
```

## 变更日志维护

项目维护两份 CHANGELOG（详见 `docs/PACKAGING.md` "CHANGELOG 维护策略"）：

- **`CHANGELOG.md`**（根目录）：开发者完整记录，[Keep a Changelog](https://keepachangelog.com) 格式
- **`customers/CHANGELOG.md`**：客户可见变更，中文，含更新指引

**触发规则**：
- 合并 feature 分支到 develop 时 → 更新根 `CHANGELOG.md` 的 `[Unreleased]`
- 执行 `python scripts/package.py` 打包发布时 → 先阅读 `docs/PACKAGING.md` 中的发布流程

## 关键文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 变更日志 | `CHANGELOG.md` | 完整版本变更记录 |
| 打包指南 | `docs/PACKAGING.md` | 打包流程 + CHANGELOG 维护策略 |
| 系统设计 | `docs/architecture/SYSTEM_DESIGN.md` | 整体架构和 Pipeline |
| 数据契约 | `docs/api/DATA_CONTRACT.md` | codeindex ↔ LightRAG 映射 |
| CLI 设计 | `docs/api/CLI_DESIGN.md` | 命令详细说明 |
| ADR-005 | `docs/adr/ADR-005-extraction-strategy.md` | AST 优先策略 |
| ADR-006 | `docs/adr/ADR-006-mvp-simplification.md` | MVP 简化决策 |
