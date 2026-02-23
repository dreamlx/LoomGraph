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

## 自动更新与 Claude Code 感知

### 增量更新机制（EPIC-003）

LoomGraph 提供 **2 种自动更新方式**，确保代码变更后知识图谱保持最新：

#### 1. Git Post-commit Hook（推荐用于本地开发）

**安装**：
```bash
# 安装 post-commit hook
loomgraph hooks install

# 检查状态
loomgraph hooks status
```

**4 种工作模式**（通过环境变量配置）：

| 模式 | 触发条件 | 行为 | 用例 |
|------|---------|------|------|
| `auto`（默认） | ≤3 个文件变更 | 同步更新（阻塞提交） | 小改动，立即可用 |
| | >3 个文件变更 | 后台异步更新 | 大改动，不阻塞 |
| `sync` | 任意变更 | 同步更新 | 开发调试，需要立即验证 |
| `async` | 任意变更 | 后台异步更新 | 大规模重构 |
| `disabled` | — | 不执行更新 | 临时禁用 |

**配置示例**（添加到 `~/.zshrc` 或 `~/.bashrc`）：
```bash
# 自定义模式
export LOOMGRAPH_HOOK_MODE=auto            # auto | sync | async | disabled

# 自定义同步阈值（默认 3）
export LOOMGRAPH_MAX_FILES_SYNC=5          # ≤5 文件同步，>5 异步

# 自定义日志路径
export LOOMGRAPH_HOOK_LOG=~/.loomgraph/hooks/post-commit.log
```

#### 2. GitHub Actions（推荐用于 CI/CD）

**集成方法**（在 `.github/workflows/ci.yml` 中）：

```yaml
name: CI

on:
  push:
    branches: [main, develop]

jobs:
  # 其他 CI 任务（lint、test 等）...

  update-knowledge-graph:
    needs: test  # 测试通过后再更新
    uses: dreamlx/LoomGraph/.github/workflows/incremental-update.yml@main
    with:
      lightrag_endpoint: "http://117.131.45.179:3001"
      embedding_endpoint: "http://117.131.45.179:3002"
    secrets: inherit
```

**特性**：
- ✅ 使用 `codeindex affected --json` 智能检测变更（过滤非代码文件、考虑业务影响）
- ✅ 自动跳过无代码变更的提交（如纯文档/配置修改）
- ✅ 并行处理（如果有多个文件）
- ✅ 失败不阻塞主流程（`continue-on-error: true`）

详细配置：[docs/guides/github-action-integration.md](docs/guides/github-action-integration.md)

### Claude Code 如何感知更新？

**数据流转路径**：

```
┌───────────────┐
│ 开发者提交代码  │
└───────┬───────┘
        │
        ├─────────────┬──────────────┐
        │             │              │
   Git Hook    GitHub Action    手动命令
  (本地开发)     (CI/CD)      (loomgraph update)
        │             │              │
        └─────────────┴──────────────┘
                      │
          ┌───────────▼────────────┐
          │  loomgraph update       │
          │  ├─ git diff / affected │  智能变更检测
          │  ├─ codeindex parse     │  AST 解析
          │  ├─ embed (Jina)        │  向量化
          │  └─ inject (LightRAG)   │  写入图谱
          └───────────┬─────────────┘
                      │
          ┌───────────▼─────────────┐
          │ LightRAG PostgreSQL     │  知识图谱存储
          │ ├─ entities (实体表)     │
          │ ├─ relations (关系表)    │
          │ └─ embeddings (向量表)   │
          └───────────┬─────────────┘
                      │
                      │ HTTP API
                      │
          ┌───────────▼─────────────┐
          │ Claude Code (AI Agent)  │
          │                         │
          │ 通过 MCP Skills 读取：    │
          │ ├─ /mo:arch "架构"       │  → find + query
          │ ├─ /mo:index <path>     │  → 重新索引
          │ └─ loomgraph find/query │  → 直接查询
          └─────────────────────────┘
```

**关键点**：

1. **更新是透明的**：无论是 Hook、Action 还是手动更新，数据最终都写入同一个 LightRAG 数据库
2. **Claude Code 无感知延迟**：
   - 同步模式（≤3 文件）：提交完成即可查询最新数据
   - 异步模式（>3 文件）：后台更新，Claude Code 可能查到旧数据（通常 1-2 分钟后更新完成）
3. **查询方式**：
   - **MCP Skill `/mo:arch`**：最常用，语义查询 + 结构化搜索
   - **CLI `loomgraph find/query`**：直接命令行查询
   - **编程式**：通过 LoomGraph SDK/API（未来支持）

### 验证更新生效

```bash
# 提交代码后验证
git commit -m "feat: add new feature"

# 检查 workspace 状态（实体数应增加）
loomgraph status

# 搜索新增的符号
loomgraph find "NewClassName"

# 或在 Claude Code 中运行
/mo:arch "where is NewClassName implemented"
```

### 初始化与升级场景

#### 场景 1：新项目初始化（客户第一次使用）

**完整流程**：

```bash
# Step 1: 安装 codeindex（AST 解析器）
pip install codeindex

# Step 2: 初始化 codeindex 配置
cd /path/to/your/project
codeindex init

# Step 3: 生成项目文档索引（供 Claude Code 阅读）
codeindex scan-all

# Step 4: 安装 LoomGraph（知识图谱引擎）
pip install loomgraph

# Step 5: 配置 LightRAG 服务地址
cat > .loomgraph.yaml <<EOF
lightrag:
  api_url: "http://117.131.45.179:3001"
embedding:
  base_url: "http://117.131.45.179:3002"
EOF

# Step 6: 首次索引代码库到知识图谱
loomgraph index .

# Step 7: 安装自动更新 Hook（可选）
loomgraph hooks install

# Step 8: 验证 Claude Code 可以感知
loomgraph status   # 确认 entities > 0
```

**Claude Code 感知时间轴**：

| 时间点 | 可用功能 | 数据来源 |
|--------|---------|---------|
| **Step 3 完成后** | ✅ 架构理解、代码导航 | `README_AI.md` 文件（静态文档） |
| **Step 6 完成前** | ❌ 语义搜索、调用关系 | 知识图谱未建立 |
| **Step 6 完成后** | ✅ 语义搜索、调用关系、依赖分析 | LightRAG 知识图谱（动态查询） |
| **Step 7 完成后** | ✅ 自动增量更新 | 每次 commit 自动同步 |

**关键理解**：
- **codeindex** 生成的 `README_AI.md` 是**静态文档**，Claude Code 直接读取文件
- **LoomGraph** 构建的知识图谱是**动态数据库**，Claude Code 通过 MCP Skills（如 `/mo:arch`）查询 LightRAG API

#### 场景 2：版本升级（从旧版本升级）

**升级检查清单**：

```bash
# Step 1: 升级工具（推荐使用虚拟环境）
pip install --upgrade codeindex loomgraph

# Step 2: 检查配置兼容性
codeindex config check      # 检查 .codeindex.yaml
loomgraph status            # 检查 LightRAG 连接

# Step 3: 判断是否需要重建索引
# 如果是小版本升级（v0.5.x → v0.5.y）：
loomgraph update            # 增量更新即可

# 如果是大版本升级（v0.5.x → v0.6.0）或数据格式变更：
loomgraph index --clear .   # Cold Rebuild（清空重建）

# Step 4: 验证升级成功
loomgraph version           # 确认版本号
loomgraph find "SomeClass"  # 测试查询功能
```

**版本兼容性**：

| 升级类型 | 配置文件 | 知识图谱 | Claude Code 影响 |
|---------|---------|---------|----------------|
| **Patch 升级**（v0.5.0 → v0.5.1） | 兼容 | 无需重建 | 无影响，透明升级 |
| **Minor 升级**（v0.5.x → v0.6.0） | 可能新增字段 | 建议重建（可选） | 新增 Skills 可用 |
| **Major 升级**（v0.x → v1.0） | **需要迁移** | **必须重建** | 查看迁移指南 |

**升级后 Claude Code 感知**：

```bash
# Claude Code 在升级后的首次查询
/mo:arch "show me the architecture"

# LoomGraph MCP Server 自动处理：
# 1. 连接新版本的 LightRAG API
# 2. 使用新的查询格式（如果有）
# 3. 返回结果给 Claude Code

# 用户无需额外操作，除非：
# - 配置文件格式变更（需要手动更新 .loomgraph.yaml）
# - 数据格式不兼容（需要 loomgraph index --clear .）
```

#### 场景 3：Claude Code 如何"发现"新版本功能？

**MCP Skills 自动更新机制**：

```
┌─────────────────────────────────────┐
│ 用户升级 LoomGraph                   │
│ pip install --upgrade loomgraph     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Claude Code 启动时自动加载 MCP       │
│ ~/.claude/mcp.json 指向的 server     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ LoomGraph MCP Server 初始化          │
│ ├─ 读取新版本的 tool definitions     │
│ ├─ 注册新增的 Skills（如有）         │
│ └─ 连接 LightRAG API                │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Claude Code 自动感知新功能           │
│ ├─ 新增 Skills 出现在 /help 中       │
│ ├─ 旧 Skills 保持兼容                │
│ └─ 用户直接使用，无需配置             │
└─────────────────────────────────────┘
```

**实际示例**：

```bash
# 假设 v0.6.0 新增了 /mo:refactor Skill

# 升级前（v0.5.0）
$ claude code
> /mo:arch "architecture"  # ✅ 可用
> /mo:refactor "suggest"   # ❌ Unknown skill

# 升级后（v0.6.0）- 重启 Claude Code
$ pip install --upgrade loomgraph
$ claude code  # 重新启动
> /mo:arch "architecture"  # ✅ 仍可用（向后兼容）
> /mo:refactor "suggest"   # ✅ 新增功能自动可用

# Claude Code 自动感知机制：
# - MCP Server 重新加载时注册新 tools
# - Claude 的 tool registry 自动更新
# - 用户无需手动配置
```

**关键点**：
1. **无需手动更新 MCP 配置**：`~/.claude/mcp.json` 只需配置一次，指向 `loomgraph mcp` 命令
2. **重启 Claude Code 生效**：升级后需要重启 Claude Code 窗口，让 MCP Server 重新初始化
3. **配置文件向后兼容**：旧的 `.loomgraph.yaml` 在新版本中仍然有效（除非有 Breaking Changes）

### 故障排查

| 问题 | 检查方法 | 解决方案 |
|------|---------|---------|
| Hook 未执行 | `loomgraph hooks status` | `loomgraph hooks install --force` |
| 异步更新未完成 | `tail -f ~/.loomgraph/hooks/post-commit.log` | 等待后台任务完成或手动 `loomgraph update` |
| Claude Code 查不到新代码 | `loomgraph find "<NewSymbol>"` | 确认 Hook/Action 成功执行 + workspace 正确 |
| GitHub Action 失败 | 查看 Actions 日志 | 检查 LightRAG/Embedding 服务可达性 |

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
- `workspace.name`: 当前读取的 workspace（格式 `项目:分支`，如 `loomgraph:develop`）
- `workspace.entities`: 实体数（0 = 需要先 `loomgraph index .`）

### Workspace 自动降级

查询命令（`find`、`query`、`graph`、`topology`、`check`、`impact`、`deps`、`overview`）在目标 workspace 为空时，**自动降级到主分支**：

**降级链**: 当前分支 → main → develop → master

**示例**：
```bash
# 场景：在 feature-A 分支，但未索引
loomgraph find "UserService"
# ℹ️  Workspace 'myproject:feature-A' not found, using 'myproject:main'
# → 自动使用 main 分支的知识图谱
```

**多 workspace 比较命令**（`workspace compare`、`workspace similar`）**不降级**，必须显式指定两个 workspace：
```bash
# 必须两个 workspace 都存在
loomgraph compare --ws1 myproject:main --ws2 myproject:feature-A
```

**禁用降级**（仅在特殊情况下使用）：
```bash
# 如果需要强制检查特定 workspace 是否存在，可在代码中设置 allow_fallback=False
# 正常用户使用无需关注此选项
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
