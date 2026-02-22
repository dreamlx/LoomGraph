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

> **一句话**: codeindex 负责**看**（AST 解析），LoomGraph 负责**想**和**说**（映射调度 + Skill 编排），LightRAG 负责**记**（存储检索）。

| 仓库 | 职责 | GitHub | 本地路径 |
|------|------|--------|----------|
| **codeindex** | AST 解析，提取 Symbol/Call/Inheritance | [dreamlx/codeindex](https://github.com/dreamlx/codeindex) | `/Users/dreamlinx/Projects/codeindex` |
| **LoomGraph** | Pipeline 调度，Embedding，CLI/Skill | [dreamlx/LoomGraph](https://github.com/dreamlx/LoomGraph) | 本项目 |
| **LightRAG** | 图谱存储，向量检索，查询 | [dreamlx/LightRAG](https://github.com/dreamlx/LightRAG) | `/Users/dreamlinx/Projects/LightRAG` |

数据流: `codeindex scan` → ParseResult → `LoomGraph embed/inject` → LightRAG API → PostgreSQL

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
│   ├── core/           # 核心引擎
│   │   ├── config.py           # Pydantic Settings 配置
│   │   ├── models.py           # 数据模型 (ParseResult, EntityData, RelationData)
│   │   ├── mapper.py           # Symbol → Entity/Relation 映射
│   │   ├── injector.py         # LightRAG 注入（insert_custom_kg）
│   │   ├── indexer.py          # 索引 Pipeline (scan + index)
│   │   ├── lightrag_client.py  # LightRAG HTTP 客户端
│   │   ├── deps.py             # DepsAnalyzer（模块依赖分析）
│   │   ├── overview.py         # OverviewAnalyzer（项目概览）
│   │   ├── compare.py          # CompareAnalyzer（跨 workspace diff）
│   │   ├── similar.py          # SimilarAnalyzer（相似实体检测）
│   │   ├── git.py              # Git 变更检测
│   │   └── impact/             # 变更影响分析
│   ├── embedding/      # Embedding 客户端（Jina Code V2）
│   ├── cli/            # CLI 命令（Click，按职责拆分为 8 个子模块）
│   │   ├── main.py              # Click group 入口 + re-export
│   │   ├── _common.py           # ErrorCode, output helpers, workspace auto-detect
│   │   ├── _deps_check.py       # check_codeindex/lightrag_api/embedding
│   │   ├── _indexing.py         # index, embed, inject, update
│   │   ├── _search.py           # find, query, graph
│   │   ├── _analysis.py         # impact, deps, overview
│   │   ├── _workspace.py        # workspace group + compare/similar
│   │   └── _setup.py            # status, install-skills, setup-config, version
│   └── mcp/            # MCP 服务接口（v0.7.0 规划）
├── skills/             # Claude Code Skills
│   ├── loomgraph-debt-radar/      # Skill A: 技术债务审计
│   ├── loomgraph-sync-advisor/    # Skill B: 跨分支同步建议
│   ├── loomgraph-evolution/       # Skill C: 代码演化趋势
│   ├── loomgraph-setup/           # 环境配置 Skill
│   └── loomgraph-init/            # 项目初始化 Skill
├── tests/              # 测试用例（265 tests）
│   ├── unit/           # 单元测试
│   └── integration/    # 集成测试
├── docs/               # 项目文档（详见「关键文档」）
└── scripts/            # 部署与工具脚本
```

## 开发流程

### 敏捷跟踪

完整流程详见 [docs/AGILE_GUIDE.md](docs/AGILE_GUIDE.md)。

**概念层级**: ADR → Epic → Feature → (Story, 可选) → Task

**GitHub 跟踪**:
- **Issues**: Epic（label: `epic`）和跨 PR 的 Feature（label: `feature`）建 Issue；Task 不建 Issue
- **Labels**: `epic` / `feature` / `bug` / `docs` / `refactor` / `infra`
- **Milestones**: 每个版本一个（如 v0.6.0 = EPIC-007）
- **文档**: Epic 详细设计在 `docs/epics/EPIC-NNN.md`，架构决策在 `docs/adr/ADR-NNN.md`

### GitFlow 分支策略

```
main (生产) ← develop ← feature/epic-NNN-short-name
                       ← bugfix/short-name
```

- `main`: 生产就绪版本
- `develop`: 开发主线，功能集成点
- `feature/*`: 功能分支，命名 `feature/epic-NNN-short-name`

### TDD 开发循环

1. **Red**: 先写失败的测试用例
2. **Green**: 写最小实现让测试通过
3. **Refactor**: 重构代码，保持测试通过

### 测试要求

- 核心模块覆盖率 ≥ 90%，整体 ≥ 80%
- 每个 Feature 必须包含单元测试 (`tests/unit/`) 和集成测试 (`tests/integration/`)

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

## 架构决策记录 (ADR)

| ADR | 决策 | 文档 |
|-----|------|------|
| ADR-001 | PostgreSQL 统一存储（LightRAG 管理） | [ADR-001](docs/adr/ADR-001-postgresql-unified-storage.md) |
| ADR-002 | 选择 LightRAG 框架 | [ADR-002](docs/adr/ADR-002-lightrag-framework.md) |
| ADR-003 | codeindex tree-sitter 解析 | [ADR-003](docs/adr/ADR-003-code-parser-strategy.md) |
| ADR-004 | LightRAG Fork 策略 | [ADR-004](docs/adr/ADR-004-lightrag-fork-strategy.md) |
| ADR-005 | AST 优先提取（不用 LLM） | [ADR-005](docs/adr/ADR-005-extraction-strategy.md) |
| ADR-006 | MVP 简化（全量重建，无增量 GC） | [ADR-006](docs/adr/ADR-006-mvp-simplification.md) |
| ADR-007 | 函数体内容注入策略 | [ADR-007](docs/adr/ADR-007-code-content-extraction.md) |
| ADR-008 | 双向调度器（能力边界） | [ADR-008](docs/adr/ADR-008-bidirectional-orchestrator.md) |
| ADR-009 | Workspace 即知识快照 | [ADR-009](docs/adr/ADR-009-workspace-as-knowledge-snapshot.md) |
| ADR-010 | 搜索体系重构 (find/query/graph) | [ADR-010](docs/adr/ADR-010-search-architecture-redesign.md) |

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
| `loomgraph find "<query>"` | 结构化实体发现（名字匹配 + 类型过滤） |
| `loomgraph find "<query>" --with-relations` | 实体 + callers/callees 一次返回 |
| `loomgraph query "<question>"` | 语义知识问答（RAG 引擎，LLM 驱动） |
| `loomgraph graph "<entity>"` | 查询调用关系 |
| `loomgraph topology` | 图谱拓扑债务分析（orphans/hubs/god/coupling） |
| `loomgraph topology --module cli` | 模块级拓扑分析 |
| `loomgraph check` | 索引新鲜度检查（source_id vs 磁盘文件） |
| `loomgraph impact [TARGET]` | 分析代码变更影响 |
| `loomgraph workspace list` | 列出所有 workspace |
| `loomgraph workspace info [NAME]` | 查看 workspace 详情（默认自动检测） |
| `loomgraph workspace delete NAME --yes` | 删除指定 workspace |
| `loomgraph compare --ws1 A --ws2 B` | 跨 workspace 实体/关系 diff |
| `loomgraph similar -e "<entity>"` | 跨 workspace 相似实体检测 |
| `/loomgraph-debt-radar [path]` | 生成技术债务审计报告（Claude Code Skill） |
| `/loomgraph-sync-advisor --ws1 A --ws2 B` | 跨分支同步建议 + 冲突预测（Claude Code Skill） |
| `/loomgraph-evolution --entity X` | 代码演化趋势分析（Claude Code Skill） |

详细用法见 [docs/api/CLI_DESIGN.md](docs/api/CLI_DESIGN.md)。

### 开始工作前

每次新开 Claude Code 窗口，先运行 `loomgraph status` 确认知识图谱状态：
- `workspace.name`: 当前读取的 workspace（格式 `项目-分支`，如 `loomgraph-develop`）
- `workspace.entities`: 实体数（0 = 需要先 `loomgraph index .`）

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

```
docs/
├── ROADMAP.md              # 版本路线图（规划 source of truth）
├── AGILE_GUIDE.md          # 敏捷开发流程（跨三仓库参考）
├── PACKAGING.md            # 打包发布流程 + CHANGELOG 维护策略
├── adr/                    # 架构决策记录（9 个 ADR，永久存档）
├── epics/                  # Epic 详细设计（EPIC-002 ~ EPIC-007）
├── architecture/
│   ├── SYSTEM_DESIGN.md    # 系统架构（v0.5.0，三层交付架构）
│   ├── FEATURE_BOUNDARY.md # LightRAG Fork vs LoomGraph 边界
│   └── UPDATE_STRATEGY.md  # Hot/Warm/Cold 更新策略
├── api/
│   ├── CLI_DESIGN.md           # CLI 命令详细说明
│   ├── DATA_CONTRACT.md        # codeindex ↔ LightRAG 数据映射
│   └── LIGHTRAG_INTEGRATION.md # LightRAG API 集成文档
├── guides/
│   └── CUSTOMER_PACKAGING.md   # 客户打包分发指南
├── images/                     # 截图资源
└── archive/                    # 已归档历史文档（可追溯）
```
