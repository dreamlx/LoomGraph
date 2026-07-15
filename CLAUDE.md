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

LoomGraph 是一款本地代码知识图谱引擎：**SQLite + sqlite-vec** 单文件存储，
[codeindex](https://github.com/dreamlx/codeindex)（tree-sitter）作为 parser engine
作为依赖自动安装，无 RAG framework、无 Postgres、无远程服务、默认全本地。
主要用户是 AI Agent（Claude Code / Codex / Cursor），CLI 全 JSON 输出，
MCP server 原生集成。

**用户视角**：`pipx install loomgraph` 一条命令安装，`loomgraph index .` 一条命令
索引，`loomgraph find` / `graph` / `topology` / `deps` / `impact` 走 SQLite 不调 LLM。
语义搜索（`loomgraph search`）opt-in，需配置 embedding provider。

**架构权威 source**：[README.md](README.md) + [ADR-013](docs/adr/ADR-013-sqlite-vec-replace-lightrag.md)。
本文件下方命令速查/环境配置若与 README.md 冲突，以 README.md 为准。

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| Storage | SQLite + sqlite-vec | 单文件 `~/.loomgraph/<workspace>.db` |
| AST Parser | codeindex (tree-sitter) | 独立仓 PyPI `ai-codeindex`，作为 loomgraph 依赖自动装 |
| Embedding | opt-in，OpenAI-compatible | Ollama 默认（`nomic-embed-text`），可配 OpenAI/Voyage/GLM |
| LLM | opt-in | 仅 `loomgraph overview` summary 模式调用 |
| Protocol | MCP (Model Context Protocol) | Claude Code / Cursor 原生集成 |

> LightRAG / PostgreSQL / Jina Code V2 / NVIDIA H200 / 远程 endpoint (117.131.x) 均已退役（v0.10-0.11）。
> 历史决策见 [docs/adr/](docs/adr/)（ADR-001/002/004 是 LightRAG 时代，被 ADR-013 supersede）。

## 项目结构

```
loomgraph/
├── src/loomgraph/
│   ├── core/           # 核心引擎
│   │   ├── config.py           # Pydantic Settings 配置
│   │   ├── models.py           # 数据模型 (EntityData, RelationData)
│   │   ├── mapper.py           # Symbol → Entity/Relation 映射
│   │   ├── graph_export_ingest.py  # graph-export 读取 + ingest
│   │   ├── deps.py             # DepsAnalyzer（模块依赖分析）
│   │   ├── overview.py         # OverviewAnalyzer（项目概览）
│   │   ├── compare.py / similar.py  # 跨 workspace diff / 相似实体
│   │   ├── topology.py         # 拓扑债务分析
│   │   ├── debt_analyzer.py    # 技术债务评分
│   │   ├── git.py / git_metrics.py  # Git 变更检测 + 度量
│   │   └── impact/             # 变更影响分析
│   ├── storage/        # SQLite + sqlite-vec 存储层
│   │   └── sqlite_store.py     # GraphStore 实现（entities/relations/vec0）
│   ├── io/             # import/export（NDJSON reader）
│   ├── embedding/      # Embedding 客户端（OpenAI-compatible）
│   ├── cli/            # CLI 命令（Click，按职责拆分为子模块）
│   │   ├── main.py             # Click group 入口 + re-export
│   │   ├── _common.py          # ErrorCode, output helpers, workspace auto-detect
│   │   ├── _deps_check.py      # check_codeindex/embedding/storage
│   │   ├── _indexing.py        # index, update, MCP refresh (_async_refresh)
│   │   ├── _search.py          # find, search, graph
│   │   ├── _analysis.py        # impact, deps, overview, topology, check, git-metrics, trends
│   │   ├── _workspace.py       # workspace group + compare/similar
│   │   ├── _setup.py           # status, install-skills, setup-config(deprecated), version
│   │   └── _mcp.py             # mcp install-config / serve
│   └── mcp/            # MCP server（tools/ 下各 tool 模块）
├── skills/             # Claude Code Skills（打入 wheel，force-include）
│   ├── loomgraph-setup/        # 配置 codeindex + 生成 .codeindex.yaml
│   └── loomgraph-init/         # 初始化项目 CLAUDE.md
├── tests/              # 测试用例
├── docs/               # 项目文档（详见「关键文档」）
└── scripts/            # 打包/版本/部署脚本
```

## 开发流程

### 敏捷跟踪

完整流程详见 [docs/AGILE_GUIDE.md](docs/AGILE_GUIDE.md)。

**概念层级**: ADR → Epic → Feature → (Story, 可选) → Task

**GitHub 跟踪**:
- **Issues**: Epic（label: `epic`）和跨 PR 的 Feature（label: `feature`）建 Issue；Task 不建 Issue
- **Labels**: `epic` / `feature` / `bug` / `docs` / `refactor` / `infra`
- **文档**: Epic 详细设计在 `docs/epics/`，架构决策在 `docs/adr/`

### 分支策略（trunk-based，main-only）

```
main ← feature/epic-NNN-short-name
     ← fix/NN-short-name        # bug 修复，关联 issue 号
```

- `main`: 生产就绪版本，PR 直接合入（无 develop 中间层）
- `feature/*` / `fix/*`: 短命分支，命名带 issue/epic 号，squash merge 后删

> 历史：曾按 GitFlow 规划 `main ← develop ← feature`，但实际未启用 develop 分支，
> 2026-07 起明确 trunk-based（commit `ec2477a`）。

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

### 运行时服务（默认全本地）

默认零配置即可用：LLM 与 embedding 默认关闭，结构化命令走本地 SQLite。
需要语义搜索（`loomgraph search`）或 overview summary 时才配 provider。

| 服务 | 默认 URL | 默认模型 | 用途 |
|------|----------|----------|------|
| Embedding | http://localhost:11434/v1 | nomic-embed-text | 语义搜索（opt-in） |
| LLM(chat) | http://localhost:11434 | gemma3:12b-it-qat | overview summary（opt-in） |

默认 provider 是本地 Ollama；第三方 OpenAI-compatible endpoint 可配（`provider: openai|voyage|glm|custom`）。

### 配置文件

默认零配置即可用。自定义时创建 `.loomgraph.yaml`（当前目录）或 `~/.config/loomgraph/config.yaml`：

```yaml
# .loomgraph.yaml
embedding:
  enabled: true                 # off by default; turn on for semantic search
  provider: ollama              # ollama | openai | voyage | glm | custom
  api_url: "http://localhost:11434/v1"
  model: "nomic-embed-text"
  dimension: 768

llm:
  provider: ollama              # ollama | glm | openrouter | vllm
  api_url: "http://localhost:11434"
  model: "gemma3:12b-it-qat"
```

配置优先级：
1. 环境变量 (`LOOMGRAPH_LLM__API_URL` 等)
2. `.loomgraph.yaml` 当前目录
3. `~/.config/loomgraph/config.yaml`
4. 默认值（本地 Ollama，embedding off）

> `loomgraph setup-config` 已 deprecated（v0.16+，#114）——零配置默认可用，仅在需手写 config stub 时使用。

## 架构决策记录 (ADR)

| ADR | 决策 | 状态 |
|-----|------|------|
| ADR-013 | SQLite + sqlite-vec 替换 LightRAG | **当前**（supersedes 001/002/010 部分/011） |
| ADR-014 | MCP write tool：`loomgraph_refresh`（reactive working-tree re-index） | 当前 |
| ADR-015 | Git × 知识图谱时空融合 | 当前 |
| ADR-001 ~ 012 | LightRAG/PostgreSQL 时代决策 | 历史归档（被 013 supersede） |

详见 [docs/adr/](docs/adr/)。

## CLI 命令 (AI Agent 友好)

所有命令输出 JSON 格式，便于 AI 解析。命令面以 `loomgraph --help` 为准。

### 命令速查表

| 命令 | 说明 |
|------|------|
| `loomgraph version` | 显示版本信息 |
| `loomgraph status` | 检查系统状态（storage / codeindex / embedding） |
| `loomgraph index <path>` | 一键索引代码库（graph-export → embed → insert 内部 pipeline，非独立命令） |
| `loomgraph index --clear <path>` | Cold Rebuild（清空重建） |
| `loomgraph update [--since REF]` | Warm Update（per-file 增量，git diff） |
| `loomgraph find "<query>"` | 结构化实体发现（名字匹配 + 类型过滤） |
| `loomgraph find "<query>" --with-relations` | 实体 + callers/callees 一次返回 |
| `loomgraph search "<query>"` | 语义搜索（向量 KNN，需 embedding.enabled） |
| `loomgraph graph "<entity>"` | 查询调用关系（`--include-unresolved` 看低信任边） |
| `loomgraph graph "<entity>" --depth N` | BFS 遍历 N 层 callers/callees |
| `loomgraph topology` | 图谱拓扑债务分析（orphans/hubs/god/coupling） |
| `loomgraph topology --scope src/` | 按 source 前缀过滤的拓扑分析 |
| `loomgraph deps` | 模块依赖分析 |
| `loomgraph debt [--with-git]` | 多维度技术债务评分 |
| `loomgraph overview` | 项目模块概览（可 `--no-summary` 跳过 LLM） |
| `loomgraph check` | 索引新鲜度检查（source_id vs 磁盘文件） |
| `loomgraph impact [TARGET]` | 分析代码变更影响 |
| `loomgraph git-metrics` | Git 热点 / 总线因子 / 缺陷率 |
| `loomgraph trends --entity X` | 代码复杂度趋势 |
| `loomgraph embed-backfill` | 为无向量 workspace 补向量 |
| `loomgraph workspace list` | 列出所有 workspace |
| `loomgraph workspace info [NAME]` | 查看 workspace 详情（默认自动检测） |
| `loomgraph workspace delete NAME --yes` | 删除指定 workspace |
| `loomgraph compare --ws1 A --ws2 B` | 跨 workspace 实体/关系 diff |
| `loomgraph similar -e "<entity>"` | 跨 workspace 相似实体检测 |
| `loomgraph import-export <artifact>` | 消费 codeindex graph-export NDJSON |
| `loomgraph mcp install-config --path <p>` | 配置 MCP（Claude Code/Cursor） |
| `loomgraph install-skills` | 安装 Claude Code Skills（setup/init） |

详细用法见 [docs/api/CLI_DESIGN.md](docs/api/CLI_DESIGN.md)。

### MCP 集成

LoomGraph 原生 MCP server（v0.12+）。`loomgraph mcp install-config --path ~/.claude/mcp.json`
后重启 Claude Code，`loomgraph_find` / `loomgraph_graph` / `loomgraph_topology` /
`loomgraph_impact` / `loomgraph_deps` / `loomgraph_debt_audit` 等作为原生工具出现，
无 subprocess 开销。完整参考见 [docs/api/MCP_DESIGN.md](docs/api/MCP_DESIGN.md)。

### 开始工作前

每次新开 Claude Code 窗口，先运行 `loomgraph status` 确认知识图谱状态：
- `workspace.name`: 当前读取的 workspace（格式 `项目:分支`，如 `loomgraph:main`）
- `workspace.entities`: 实体数（0 = 需要先 `loomgraph index .`）

### Workspace 自动降级

查询命令（`find`、`graph`、`topology`、`check`、`impact`、`deps`、`overview`）在目标
workspace 为空时，**自动降级到主分支**：当前分支 → main → develop → master。

多 workspace 比较命令（`compare`、`similar`）**不降级**，必须显式指定两个 workspace。

## 开发命令

```bash
# 运行特定测试
pytest tests/unit/test_mapper.py -v

# 运行所有测试
pytest tests/ -v --cov=src/loomgraph

# 代码检查（CI 范围）
ruff check src/ tests/
mypy src/
```

> 本地 SQLite，无需 docker / postgres（v0.11+ 起 LightRAG/Postgres 已移除）。

## 操作前必读清单（MUST READ）

> **强制规则**：执行以下操作前，必须先读取对应文档。

| 当你准备... | 先读... | 同步检查 |
|------------|---------|---------|
| 发版（`git tag vX.Y.Z`） | `docs/PACKAGING.md` | 确认三处版本一致 + release.yml 流程 |
| 新增/修改/删除 CLI 命令 | 根 `README.md` + `loomgraph --help` | 同步 CLI 命令表 + 前置条件列 |
| bump 版本 | `customers/CHANGELOG.md` + 根 `CHANGELOG.md` | 同步变更日志 |
| 修改架构 | `docs/adr/` 对应 ADR | 确认是否需要新 ADR |

## 变更日志维护

项目维护两份 CHANGELOG（详见 `docs/PACKAGING.md`）：

- **`CHANGELOG.md`**（根目录）：开发者完整记录，[Keep a Changelog](https://keepachangelog.com) 格式
- **`customers/CHANGELOG.md`**：客户可见变更，中文，含更新指引

**触发规则**：
- 合并 feature 分支到 main 时 → 更新根 `CHANGELOG.md` 的 `[Unreleased]`
- 执行 `git tag vX.Y.Z` 发版时 → 先阅读 `docs/PACKAGING.md` 发布流程

## 关键文档

```
docs/
├── ROADMAP.md              # 版本路线图
├── AGILE_GUIDE.md          # 敏捷开发流程
├── PACKAGING.md            # 打包发布流程 + CHANGELOG 维护策略
├── adr/                    # 架构决策记录（ADR-013/014/015 是当前，001-012 历史归档）
├── epics/                  # Epic 详细设计
├── architecture/
│   └── UPDATE_STRATEGY.md  # Hot/Warm/Cold 更新策略
├── api/
│   ├── CLI_DESIGN.md       # CLI 命令详细说明
│   └── MCP_DESIGN.md       # MCP tool 参考
├── guides/                 # 使用指南
└── benchmarks/             # dogfood 基准
```
