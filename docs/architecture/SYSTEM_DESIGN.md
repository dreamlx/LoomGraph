# LoomGraph 系统架构设计

**版本**: 0.7.0
**更新日期**: 2026-07-06
**状态**: ✅ 确认

> **本文已更新到 ADR-013 架构（SQLite + sqlite-vec + 本地 Ollama），H200 / LightRAG / Postgres 时代描述已移除（2026-07）。** v0.5.0 之前的三仓库"codeindex 看 / LoomGraph 想 / LightRAG 记"模型已被替换：LoomGraph 现在自带存储层（`SqliteGraphStore`），LightRAG 作为独立存储组件已退役。

---

## 1. 定位

> codeindex 负责"看"（AST 解析），LoomGraph 负责"想"、"说"和"记"（映射调度 + Skill 编排 + 自带 SQLite 存储）。

| 仓库 | 角色 | 职责 |
|------|------|------|
| **codeindex** | 看 | AST 解析，提取代码结构（Symbol / Call / Inheritance / Import） |
| **LoomGraph** | 想 + 说 + 记 | 写入调度 + 读取分析 + Skill 编排 + **自带存储（SQLite + sqlite-vec）**，对外提供 CLI 和 Claude Code Skills |

**存储所有权**：LoomGraph **直接拥有**存储层。`GraphStore` 抽象（`src/loomgraph/storage/`）当前唯一实现是 `SqliteGraphStore`，每个 workspace 对应一个单文件 SQLite 数据库（`~/.loomgraph/{workspace}.db`）。无 LightRAG、无 Postgres、无外部数据库进程。

---

## 2. 三层交付架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Skill 层 (Claude Code Skills)                   │
│                                                                     │
│  /loomgraph-init             项目初始化                              │
│  /loomgraph-setup            环境配置                                │
│                                                                     │
│  v0.15.0: 编排型 Skill (debt-radar / evolution / sync-advisor)      │
│  移除, 由 MCP composite 替代 (loomgraph_debt_audit 等, 见 MCP 层)    │
├─────────────────────────────────────────────────────────────────────┤
│                     能力层 (LoomGraph CLI)                           │
│                                                                     │
│  写入命令           读取命令             管理命令                     │
│  ┌───────────┐     ┌───────────────┐    ┌──────────────────┐        │
│  │ index     │     │ deps          │    │ workspace list   │        │
│  │ update    │     │ overview      │    │ workspace info   │        │
│  │ embed     │     │ compare       │    │ workspace delete │        │
│  │ inject    │     │ similar       │    │ status           │        │
│  │           │     │ search        │    │ version          │        │
│  │           │     │ graph         │    │                  │        │
│  │           │     │ impact        │    │                  │        │
│  └───────────┘     └───────────────┘    └──────────────────┘        │
│                                                                     │
│  输出: 全部 JSON，AI Agent 可直接解析                                 │
├─────────────────────────────────────────────────────────────────────┤
│                     基础设施层 (External + Local)                     │
│                                                                     │
│  ┌─────────────┐  ┌─────────────────────┐  ┌──────────────────────┐ │
│  │  codeindex  │  │   SqliteGraphStore  │  │   本地 Ollama         │ │
│  │  AST 解析   │  │   (in-process)      │  │  LLM       :11434    │ │
│  │  tech-debt  │  │   SQLite +          │  │  Embedding :11434/v1 │ │
│  │             │  │   sqlite-vec        │  │  (可选，默认 off)     │ │
│  └─────────────┘  │   ~/.loomgraph/    │  └──────────────────────┘ │
│                   │   {workspace}.db   │                            │
│                   └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

**关键变化（相对 v0.5.0）**：

- 存储**进程内**：`SqliteGraphStore` 是 LoomGraph 自有模块，无 HTTP 跳跃，无外部 DB 进程
- LLM / Embedding 走**本地 Ollama**（OpenAI-compatible），不再依赖远程 H200
- 单文件 DB，每个 workspace 一个 `.db` 文件，迁移 / 备份 / 删除 = `cp` / `rm`

---

## 3. 数据流

### 3.1 写入路径

```
源代码 → codeindex parse → LoomGraph mapper → SqliteGraphStore → SQLite 文件
```

详细流程：

```
┌──────────┐    ┌──────────┐    ┌───────────────┐    ┌──────────────────┐    ┌──────────┐
│  源代码  │───▶│codeindex │───▶│   LoomGraph   │───▶│ SqliteGraphStore │───▶│ SQLite   │
│  Files   │    │ parse    │    │   mapper +     │    │  (in-process)    │    │ +        │
│          │    │          │    │   injector     │    │                  │    │ sqlite-vec│
└──────────┘    └──────────┘    └───────────────┘    │ entities         │    │          │
                     │                │               │ relations        │    │ ~/.loom- │
                     ▼                ▼               │ vec_node_desc    │    │ graph/   │
               ParseResult      entities +            └──────────────────┘    │ {ws}.db  │
               • Symbol         relations +                                   └──────────┘
               • Call           (optional)
               • Inheritance    embedding
               • Import         (单次事务写入)
```

**两种写入模式**：

| 模式 | 命令 | 场景 |
|------|------|------|
| Cold Rebuild | `loomgraph index <path>` | 首次索引，清空后全量重建 |
| Warm Update | `loomgraph update --since HEAD~5` | 增量索引 git 变更文件 |

**Workspace 隔离**：每个 workspace 对应独立的 SQLite 文件（`~/.loomgraph/{workspace}.db`），文件级隔离，无并发跨 workspace 写入冲突。

### 3.2 读取路径 — 能力层

```
用户/Agent → LoomGraph CLI → SqliteGraphStore (SQL + vec 查询) → JSON 结果
```

| 命令 | 存储访问 | 数据处理 |
|------|---------|----------|
| `find` | `entities` 表（名称/类型过滤） | 结构化实体发现 |
| `query` | `vec_node_descriptions` + LLM | 语义知识问答（可选 embedding 时启用） |
| `graph` | `entities` + `relations`（CALLS/INHERITS/IMPORTS 边遍历） | 实体关系查询 |
| `deps` | `entities` + `relations` 全表 | 本地聚合：按模块分组依赖 |
| `overview` | `entities` + `relations` + 可选 LLM | 本地聚合 + 可选 LLM 摘要 |
| `compare` | 两个 workspace 各读全量 entities + relations | 本地 set diff + relation diff |
| `similar` | N 个 workspace 各读全量 entities + relations | 本地 exact + fuzzy 名称匹配 |
| `impact` | `relations` 反向边遍历 + git diff | 变更影响分析 + 风险评估 |
| `topology` | `entities` + `relations` | orphans / hubs / god / coupling 拓扑分析 |

**设计原则**：存储只做 SQL 检索 + 向量相似度（sqlite-vec），LoomGraph 在本地完成所有分析逻辑（聚合、diff、匹配、排序、拓扑）。

### 3.3 读取路径 — Skill 层

```
/skill 触发 → 编排多个 CLI 命令 + codeindex → 收集 JSON → LLM 综合分析 → Markdown 报告
```

| Skill | 编排的命令 | LLM 分析内容 |
|-------|-----------|-------------|
| `/loomgraph-debt-radar` | `codeindex tech-debt` + `loomgraph deps` + `loomgraph overview` + `loomgraph workspace info` | 债务等级评定 + 模块健康度排名 + 重构优先级 |
| `/loomgraph-sync-advisor` | `loomgraph compare` + `loomgraph graph` + `git diff` | 冲突预测 + 合并策略 + 操作顺序 |
| `/loomgraph-evolution` | `loomgraph similar` + `loomgraph compare` (逐对) + `loomgraph graph` | 分叉类型判断 + 维护代价量化 + 收敛建议 |

**Skill 不做数据计算**，只做流程控制和 LLM 推理。数据全部来自 CLI 的 JSON 输出。

---

## 4. 核心模块

### 4.1 GraphStore / SqliteGraphStore (`src/loomgraph/storage/`)

LoomGraph 自带的存储抽象。`GraphStore` 是协议（protocol），当前唯一实现是 `SqliteGraphStore`，进程内直接读写 SQLite 文件，无 HTTP 跳跃。

**三张表**：

| 表 | 用途 |
|----|------|
| `entities` | 实体（Symbol → EntityData），含 name / type / source_id / description 等字段 |
| `relations` | 关系（CALLS / INHERITS / IMPORTS），含 source_entity / target_entity / relation_type |
| `vec_node_descriptions` | 实体描述的向量列（sqlite-vec），用于 `query` 命令的语义检索 |

**主要方法**：

| 方法 | 实现 | 用途 |
|------|------|------|
| `acreate_entity()` | `INSERT INTO entities` | 单实体写入 |
| `acreate_relation()` | `INSERT INTO relations` | 单关系写入 |
| `adelete_by_source()` | `DELETE FROM ... WHERE source_id=?` | 按 source_id 删除（Warm Update 用） |
| `aclear_workspace()` | `DELETE FROM entities; DELETE FROM relations; ...` | 清空 workspace（Cold Rebuild 用） |
| `aget_all_entities()` | `SELECT * FROM entities` | 全量实体读取（deps / overview / compare / similar 用） |
| `aget_all_relations()` | `SELECT * FROM relations` | 全量关系读取 |
| `aquery()` | sqlite-vec KNN + LLM 综合（可选） | 语义问答 |
| `alist_workspaces()` | 扫描 `~/.loomgraph/*.db` | 列出所有 workspace |

**并发安全**：SQLite 文件启用 WAL 模式 + `busy_timeout`（ADR-013 / commit dfd8646），支持多进程读写安全。

**Workspace 隔离**：通过文件路径实现 —— 每个 workspace 一个独立 `.db` 文件，跨 workspace 操作（compare / similar）打开多个 `SqliteGraphStore` 实例。

### 4.2 写入模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **Mapper** | `core/mapper.py` | codeindex ParseResult → EntityData / RelationData |
| **Injector** | `core/injector.py` | 数据收集 (`collect_kg_data` + `build_chunks` + `create_external_stubs`)，CLI 调用 `GraphStore.acreate_entity/acreate_relation` 写入 |
| **Indexer** | `core/indexer.py` | 扫描文件 + 编排 parse → map → inject 流水线 |
| **Adapter** | `core/adapter.py` | codeindex JSON → LoomGraph ParseResult 适配 |

### 4.3 分析模块

| 模块 | 文件 | 输入 | 输出 |
|------|------|------|------|
| **DepsAnalyzer** | `core/deps.py` | 全部 entities + relations | 模块级依赖图 |
| **OverviewAnalyzer** | `core/overview.py` | 全部 entities + relations + 可选 LLM | 模块概览 + 摘要 |
| **CompareAnalyzer** | `core/compare.py` | 两个 workspace 的 entities + relations | 实体/关系 diff |
| **SimilarAnalyzer** | `core/similar.py` | N 个 workspace 的 entities + relations | 相似实体匹配 |
| **ImpactAnalyzer** | `core/impact/` | git diff + GraphStore 反向边遍历 | 变更影响 + 风险评估 |

所有 Analyzer 遵循相同模式：

```python
@dataclass
class XxxAnalyzer:
    store: Any  # GraphStore (SqliteGraphStore)
    async def analyze(self) -> XxxResult: ...

@dataclass
class XxxResult:
    def to_dict(self) -> dict[str, Any]: ...
```

### 4.4 Embedding 模块 (`src/loomgraph/embedding/`)

OpenAI-compatible Embedding 客户端，默认走本地 Ollama。

- **默认 provider**：`ollama`（`http://localhost:11434/v1`，`model=nomic-embed-text`，`dimension=768`）
- **可选 provider**：`openai` / `voyage` / `glm` / `custom`（均为 OpenAI-compatible `/v1/embeddings`）
- **默认状态**：off（`query` 命令降级为纯结构化查询；开启后向 `vec_node_descriptions` 写入向量并支持语义检索）
- 自动分批、带重试的向量化

---

## 5. 存储架构

### 5.1 存储所有权

```
LoomGraph  ──(SQL + sqlite-vec, in-process)──▶  SQLite 文件
  直接拥有 DB                                    ~/.loomgraph/{workspace}.db
```

LoomGraph **直接拥有存储层**。`src/loomgraph/storage/` 实现 `GraphStore` 抽象，当前唯一实现 `SqliteGraphStore`。无外部数据库进程，无 HTTP API 中间层。

### 5.2 SqliteGraphStore 管理的存储

| 表 | 用途 |
|----|------|
| `entities` | 实体（图谱节点） |
| `relations` | 关系（CALLS / INHERITS / IMPORTS 边） |
| `vec_node_descriptions` | 实体描述向量列（sqlite-vec，仅 embedding 开启时填充） |

**文件格式**：单个 SQLite 文件，启用 WAL（write-ahead logging）+ `busy_timeout`，支持多进程并发读写安全（ADR-013 / commit dfd8646）。

### 5.3 Workspace 隔离

每个 workspace 在文件系统层面隔离 —— 一个独立 `.db` 文件：

```
~/.loomgraph/myproject.db            # 单 workspace 操作
~/.loomgraph/myproject:main.db       # 分支级 workspace
```

跨 workspace 操作（compare / similar）通过打开多个 `SqliteGraphStore` 实例实现，每个绑定不同的 `.db` 文件。

---

## 6. 关系类型

| 类型 | 说明 | 来源 |
|------|------|------|
| `CALLS` | 函数/方法调用 | codeindex Call |
| `INHERITS` | 类继承 | codeindex Inheritance |
| `IMPORTS` | 模块导入 | codeindex Import |

---

## 7. CLI 设计

### 7.1 设计原则

LoomGraph 的主要用户是 AI Agent（Claude Code Skills / MCP 客户端）。

| 原则 | 实现 |
|------|------|
| 输出格式 | 全部 JSON（`{"success": true, "data": {...}}`） |
| 错误处理 | 结构化错误 + suggestion 字段，Agent 可据此修复 |
| 命令风格 | 原子命令可组合，Skill 负责编排 |
| Workspace | 默认自动检测（当前目录名），`-w` 可覆盖 |
| 日志 | stderr 输出，不干扰 stdout JSON（pipe-safe） |

### 7.2 命令全览

| 分类 | 命令 | 说明 |
|------|------|------|
| **写入** | `index <path>` | 一键索引（Cold Rebuild） |
| | `index --clear <path>` | 清空后重建 |
| | `update [--since REF]` | 增量索引 git 变更 |
| | `embed <json>` | 单独生成 Embedding |
| | `inject <parse> <embed>` | 单独写入 SqliteGraphStore |
| **单 Workspace 读取** | `search "<query>"` | 语义搜索 |
| | `graph "<entity>"` | 调用关系查询 |
| | `deps [--depth N]` | 模块级依赖图 |
| | `overview [--no-summary]` | 项目模块概览 |
| | `impact [TARGET]` | 变更影响分析 |
| **跨 Workspace 读取** | `compare --ws1 A --ws2 B` | 实体/关系结构 diff |
| | `similar -e "<entity>"` | 相似实体检测 |
| **管理** | `workspace list` | 列出所有 workspace |
| | `workspace info [NAME]` | 查看 workspace 详情 |
| | `workspace delete NAME --yes` | 删除 workspace |
| | `status` | 服务连接状态 |
| | `version` | 版本信息 |
| | `install-skills` | 安装 Skills 到 `~/.claude/skills/` |

### 7.3 MCP Server (v0.7.0 规划)

封装全部 CLI 命令为 MCP Tools，服务 Cursor/IDE 用户。当前未实现。

---

## 8. Skill 设计

### 8.1 交付形态

```
skills/
├── loomgraph-debt-radar/SKILL.md      # Skill A: 债务雷达
├── loomgraph-sync-advisor/SKILL.md    # Skill B: 智能同步
├── loomgraph-evolution/SKILL.md       # Skill C: 演化观察
├── loomgraph-setup/SKILL.md           # 配置向导
└── loomgraph-init/SKILL.md            # CLAUDE.md 注入
```

打包进 wheel → `loomgraph install-skills` → 安装到 `~/.claude/skills/` → Claude Code 自动发现。

### 8.2 Skill 工作模式

每个 Skill 是一个 SKILL.md 文件，包含：
1. **前置检查** — 验证工具可用、workspace 存在
2. **数据收集** — 分步执行 CLI 命令，收集 JSON 结果
3. **LLM 分析** — 将收集的数据汇总，按模板生成报告
4. **输出** — Markdown 格式的分析报告

Skill 运行在 Claude Code Agent 上下文中，Agent 负责执行 bash 命令和 LLM 推理。

---

## 9. 配置

### 9.1 配置文件

```yaml
# .loomgraph.yaml
llm:
  provider: ollama                              # ollama | glm | openrouter | vllm | custom
  api_url: "http://localhost:11434"             # OpenAI-compatible base
  model: "gemma3:12b-it-qat"
  api_timeout: 60.0

embedding:
  enabled: false                                # 默认 off；query 命令降级为纯结构化查询
  provider: ollama                              # ollama | openai | voyage | glm | custom
  api_url: "http://localhost:11434/v1"          # OpenAI-compatible /v1/embeddings
  model: "nomic-embed-text"
  dimension: 768
```

### 9.2 配置优先级

1. 环境变量（如 `LOOMGRAPH_LLM__API_URL`、`LOOMGRAPH_EMBEDDING__ENABLED`）
2. `.loomgraph.yaml`（当前目录）
3. `~/.config/loomgraph/config.yaml`
4. 默认值

---

## 10. 部署架构

### 10.1 本地服务（Ollama）

| 服务 | 端口 | 说明 |
|------|------|------|
| Ollama LLM | 11434 | LLM 推理（OpenAI-compatible `/v1/chat/completions`），默认 `gemma3:12b-it-qat` |
| Ollama Embedding | 11434/v1 | 代码 Embedding（OpenAI-compatible `/v1/embeddings`），默认 `nomic-embed-text`，可选关闭 |

**前置**：`ollama serve` + `ollama pull gemma3:12b-it-qat`（embedding 开启时另 `ollama pull nomic-embed-text`）。

> v0.5.0 之前依赖的远程 H200 服务器（`internal.example.invalid`，GLM-4 vLLM :3000 / LightRAG API :3001 / TEI Jina :3002）已于 2026-07 全部退役，所有推理与 Embedding 切换到本地 Ollama。

### 10.2 本地开发

无需外部基础设施。LoomGraph 自带 SQLite 存储（in-process），无 PostgreSQL / docker-compose 依赖：

```bash
# 唯一前置：本地 Ollama（可选 embedding）
ollama serve
ollama pull gemma3:12b-it-qat
```

---

## 11. 测试覆盖

| 模块 | 测试数 |
|------|--------|
| Config | 7 |
| Mapper | 26 |
| Injector | 8 |
| Embedding | 11 |
| Indexer | 11 |
| CLI | 49 |
| SqliteGraphStore | 18 |
| Impact | 19 |
| Git | 8 |
| DepsAnalyzer | 14 |
| OverviewAnalyzer | 10 |
| CompareAnalyzer | 11 |
| SimilarAnalyzer | 10 |
| Integration | 22 |
| **Total** | **224** |

---

## 12. 附录

### 12.1 技术选型

| 选项 | 选择 | 理由 |
|------|------|------|
| 存储 | SQLite + sqlite-vec（单文件） | 零运维、单文件可拷贝、WAL 多进程安全（ADR-013） |
| 向量存储 | sqlite-vec（`vec_node_descriptions` 表） | 与图存储同库，事务一致性 |
| 图存储 | SQLite `entities` + `relations` 表 | 单一数据库，进程内直读直写 |
| AST 解析 | codeindex (tree-sitter) | 外部 CLI，职责分离 |
| LLM | 本地 Ollama（OpenAI-compatible） | 默认 `gemma3:12b-it-qat`，可切 glm/openrouter/vllm/custom |
| Embedding | 本地 Ollama `nomic-embed-text` (768d) | 默认 off，开启时 OpenAI-compatible `/v1/embeddings` |
| HTTP 客户端 | httpx (async) | LLM / Embedding 远程调用（存储不再走 HTTP） |

### 12.2 关键 ADR

| ADR | 决策 | 影响 |
|-----|------|------|
| ADR-005 | AST 优先提取 | MVP 不使用 LLM 提取 |
| ADR-006 | MVP 简化 | 全量重建，无增量 GC |
| ADR-008 | 双向调度器 | codeindex/LoomGraph 能力边界 |
| ADR-009 | Workspace 即知识快照 | 从隔离机制到可对比的知识切片 |
| **ADR-013** | **SQLite + sqlite-vec 替换 LightRAG** | **supersedes ADR-001 / 002 / 010(部分) / 011**，LoomGraph 自带存储，移除 Postgres / LightRAG API 依赖 |
| ADR-014 | MCP 写 tool `loomgraph_refresh` | reactive working-tree re-index |
| ADR-015 | Git × 知识图谱时空融合 | 独立分析 + 后期 join |

### 12.3 相关文档

- [DATA_CONTRACT.md](../api/DATA_CONTRACT.md) — codeindex ↔ LoomGraph 数据映射
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) — CLI 命令详细设计
- [ADR-013](../adr/ADR-013-sqlite-vec-replace-lightrag.md) — SQLite + sqlite-vec 替换 LightRAG
- [EPIC-004](../epics/completed/EPIC-004-bidirectional-orchestrator.md) — deps / overview
- [EPIC-005](../epics/completed/EPIC-005-workspace-management.md) — workspace 管理
- [EPIC-006](../epics/completed/EPIC-006-cross-workspace-comparison.md) — compare / similar
- [EPIC-007](../epics/completed/EPIC-007-entropy-reduction-skills.md) — 研发熵减 Skills
