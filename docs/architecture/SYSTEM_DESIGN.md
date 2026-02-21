# LoomGraph 系统架构设计

**版本**: 0.5.0
**更新日期**: 2026-02-20
**状态**: ✅ 确认

---

## 1. 定位

> codeindex 负责"看"，LoomGraph 负责"想"和"说"，LightRAG 负责"记"。

| 仓库 | 角色 | 职责 |
|------|------|------|
| **codeindex** | 看 | AST 解析，提取代码结构（Symbol / Call / Inheritance / Import） |
| **LoomGraph** | 想 + 说 | 写入调度 + 读取分析 + Skill 编排，对外提供 CLI 和 Claude Code Skills |
| **LightRAG** | 记 | 图谱存储 + 向量检索，通过 HTTP API 提供 CRUD |

**存储所有权**：LoomGraph 不直接操作数据库。全部存储由 LightRAG 管理，LoomGraph 通过 `LightRAGClient`（HTTP）读写。

---

## 2. 三层交付架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Skill 层 (Claude Code Skills)                   │
│                                                                     │
│  /loomgraph-debt-radar       技术债务审计报告                        │
│  /loomgraph-sync-advisor     跨分支同步建议 + 冲突预测               │
│  /loomgraph-evolution        代码演化趋势分析                        │
│                                                                     │
│  原则: Skill 是编排者，不做数据计算                                   │
│        编排 CLI 命令 + codeindex + LLM → 生成 Markdown 报告          │
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
│                     基础设施层 (External)                            │
│                                                                     │
│  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────────┐    │
│  │  codeindex  │  │   LightRAG API  │  │     H200 GPU         │    │
│  │  AST 解析   │  │   :3001         │  │  Jina TEI  :3002     │    │
│  │  tech-debt  │  │   /graph/*      │  │  GLM-4 vLLM :3000    │    │
│  └─────────────┘  │   /api/*        │  └──────────────────────┘    │
│                   │   /query        │                               │
│                   └────────┬────────┘                               │
│                            │                                        │
│                   ┌────────┴────────┐                               │
│                   │   PostgreSQL    │                               │
│                   │   pgvector      │                               │
│                   │   :5432         │                               │
│                   └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据流

### 3.1 写入路径

```
源代码 → codeindex parse → LoomGraph mapper → LightRAG HTTP API → PostgreSQL
```

详细流程：

```
┌──────────┐    ┌──────────┐    ┌───────────────┐    ┌──────────────────┐    ┌──────────┐
│  源代码  │───▶│codeindex │───▶│   LoomGraph   │───▶│  LightRAG API    │───▶│PostgreSQL│
│  Files   │    │ parse    │    │   mapper +     │    │                  │    │          │
│          │    │          │    │   injector     │    │ /documents/      │    │ pgvector │
└──────────┘    └──────────┘    └───────────────┘    │  insert_custom_kg│    │ graph    │
                     │                │               │ (全层写入:        │    │          │
                     ▼                ▼               │  graph+vdb+kv)   │    └──────────┘
               ParseResult      entities +            └──────────────────┘
               • Symbol         relations +
               • Call           chunks
               • Inheritance    (单次 HTTP 调用)
               • Import
```

**两种写入模式**：

| 模式 | 命令 | 场景 |
|------|------|------|
| Cold Rebuild | `loomgraph index <path>` | 首次索引，清空后全量重建 |
| Warm Update | `loomgraph update --since HEAD~5` | 增量索引 git 变更文件 |

**Workspace 隔离**：每次写入通过 `LIGHTRAG-WORKSPACE` HTTP header 隔离，不同项目/分支写入不同 workspace。

### 3.2 读取路径 — 能力层

```
用户/Agent → LoomGraph CLI → LightRAG HTTP API → JSON 结果
```

| 命令 | LightRAG 端点 | 数据处理 |
|------|---------------|----------|
| `search` | `/query` | 语义检索 (local/global/hybrid) |
| `graph` | `/query` | 实体关系查询 |
| `deps` | `/graph/entities/all` + `/graph/relations/all` | 本地聚合：按模块分组依赖 |
| `overview` | `/graph/entities/all` + `/graph/relations/all` + `/query` | 本地聚合 + 可选 LLM 摘要 |
| `compare` | 两个 workspace 各调 `/graph/entities/all` + `/graph/relations/all` | 本地 set diff + relation diff |
| `similar` | N 个 workspace 各调 `/graph/entities/all` + `/graph/relations/all` | 本地 exact + fuzzy 名称匹配 |
| `impact` | `/query` + git diff | 变更影响分析 + 风险评估 |

**设计原则**：LightRAG 只做存储检索，LoomGraph 在本地完成所有分析逻辑（聚合、diff、匹配、排序）。

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

### 4.1 LightRAGClient (`src/loomgraph/core/lightrag_client.py`)

LoomGraph 与 LightRAG 通信的唯一通道。基于 httpx，通过 HTTP API 读写。

| 方法 | HTTP 端点 | 用途 |
|------|-----------|------|
| `insert_custom_kg()` | `POST /documents/insert_custom_kg` | **主写入路径**: 单次调用写入全层 (graph+vdb+kv) |
| `delete_by_source()` | `DELETE /graph/by_source` | 按 source_id 删除（Warm Update 用） |
| `delete_all()` | `DELETE /graph/clear` | 清空 workspace 全部 11 层存储 |
| `query()` | `POST /query` | 语义查询 |
| `get_all_entities()` | `GET /graph/entities/all` | 获取 workspace 全部实体 |
| `get_all_relations()` | `GET /graph/relations/all` | 获取 workspace 全部关系 |
| `list_workspaces()` | `GET /api/workspaces` | 列出所有 workspace |
| `health_check()` | `GET /health` | 健康检查 |
| `create_entity()` | `POST /graph/entity/create` | 创建单个实体（已弃用，保留兼容） |
| `create_relation()` | `POST /graph/relation/create` | 创建单个关系（已弃用，保留兼容） |
| `batch_create_graph()` | 批量调用上述两个 | 旧注入路径（已弃用，保留兼容） |

Workspace 隔离通过 `LIGHTRAG-WORKSPACE` header 实现，每个 client 实例绑定一个 workspace。

### 4.2 写入模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **Mapper** | `core/mapper.py` | codeindex ParseResult → EntityData / RelationData |
| **Injector** | `core/injector.py` | 数据收集 (`collect_kg_data` + `build_chunks` + `create_external_stubs`)，CLI 调用 `insert_custom_kg` 注入 |
| **Indexer** | `core/indexer.py` | 扫描文件 + 编排 parse → map → inject 流水线 |
| **Adapter** | `core/adapter.py` | codeindex JSON → LoomGraph ParseResult 适配 |

### 4.3 分析模块

| 模块 | 文件 | 输入 | 输出 |
|------|------|------|------|
| **DepsAnalyzer** | `core/deps.py` | 全部 entities + relations | 模块级依赖图 |
| **OverviewAnalyzer** | `core/overview.py` | 全部 entities + relations + 可选 LLM | 模块概览 + 摘要 |
| **CompareAnalyzer** | `core/compare.py` | 两个 workspace 的 entities + relations | 实体/关系 diff |
| **SimilarAnalyzer** | `core/similar.py` | N 个 workspace 的 entities + relations | 相似实体匹配 |
| **ImpactAnalyzer** | `core/impact/` | git diff + LightRAG query | 变更影响 + 风险评估 |

所有 Analyzer 遵循相同模式：

```python
@dataclass
class XxxAnalyzer:
    client: Any  # LightRAGClient
    async def analyze(self) -> XxxResult: ...

@dataclass
class XxxResult:
    def to_dict(self) -> dict[str, Any]: ...
```

### 4.4 Embedding 模块 (`src/loomgraph/embedding/jina.py`)

Jina Code V2 客户端，支持 TEI (Text Embeddings Inference) 部署。

- 8K context window
- 自动分批 (batch_size=32)
- 带重试的向量化

---

## 5. 存储架构

### 5.1 存储所有权

```
LoomGraph  ──(HTTP)──▶  LightRAG API  ──(SQL)──▶  PostgreSQL
  不碰 DB                  拥有 DB                  1 个实例
```

LoomGraph **无自有数据库表**。`storage/` 目录预留，当前为空。

### 5.2 LightRAG 管理的存储

| 组件 | 用途 |
|------|------|
| pgvector | Embedding 向量存储 + 相似度检索 |
| Graph tables | 实体/关系图谱 |
| KV store | 配置、缓存 |

### 5.3 Workspace 隔离

每个 workspace 在 LightRAG 内部是独立的数据空间。LoomGraph 通过 HTTP header 切换：

```
LIGHTRAG-WORKSPACE: myproject        # 单 workspace 操作
LIGHTRAG-WORKSPACE: myproject:main   # 分支级 workspace
```

跨 workspace 操作（compare / similar）通过创建多个 `LightRAGClient` 实例实现，每个绑定不同 workspace。

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
| | `inject <parse> <embed>` | 单独注入 LightRAG |
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
lightrag:
  api_url: "http://117.131.45.179:3001"
  api_timeout: 30.0

embedding:
  base_url: "http://117.131.45.179:3002"
```

### 9.2 配置优先级

1. 环境变量 (`LOOMGRAPH_LIGHTRAG__API_URL`)
2. `.loomgraph.yaml`（当前目录）
3. `~/.config/loomgraph/config.yaml`
4. 默认值

---

## 10. 部署架构

### 10.1 H200 服务器

| 服务 | 端口 | 说明 |
|------|------|------|
| GLM-4.7-fp8 (vLLM) | 3000 | LLM 推理（LightRAG 内部使用） |
| LightRAG API | 3001 | 图谱存储 + 检索 |
| Jina Code V2 (TEI) | 3002 | 代码 Embedding |
| PostgreSQL | 5432 | pgvector + 图存储（LightRAG 管理） |

### 10.2 本地开发

```yaml
# docker-compose.yml — 仅为 LightRAG 提供 PostgreSQL
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
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
| LightRAGClient | 18 |
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
| 向量存储 | pgvector (LightRAG 管理) | 简化运维，事务一致性 |
| 图存储 | PostgreSQL graph tables (LightRAG 管理) | 单一数据库，LightRAG 内置 |
| AST 解析 | codeindex (tree-sitter) | 外部 CLI，职责分离 |
| RAG 框架 | LightRAG (HTTP API) | 轻量，workspace 隔离 |
| Embedding | Jina Code V2 (8K context) | 代码语义优化 |
| HTTP 客户端 | httpx (async) | 并发连接复用 |

### 12.2 关键 ADR

| ADR | 决策 | 影响 |
|-----|------|------|
| ADR-001 | PostgreSQL 统一存储 | 单一数据库，LightRAG 管理 |
| ADR-002 | 选择 LightRAG | 轻量框架，HTTP API |
| ADR-005 | AST 优先提取 | MVP 不使用 LLM 提取 |
| ADR-006 | MVP 简化 | 全量重建，无增量 GC |
| ADR-008 | 双向调度器 | codeindex/LoomGraph 能力边界 |
| ADR-009 | Workspace 即知识快照 | 从隔离机制到可对比的知识切片 |

### 12.3 相关文档

- [DATA_CONTRACT.md](../api/DATA_CONTRACT.md) — codeindex ↔ LightRAG 数据映射
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) — CLI 命令详细设计
- [ROADMAP.md](../ROADMAP.md) — 开发路线图
- [EPIC-004](../epics/EPIC-004-bidirectional-orchestrator.md) — deps / overview
- [EPIC-005](../epics/EPIC-005-workspace-management.md) — workspace 管理
- [EPIC-006](../epics/EPIC-006-cross-workspace-comparison.md) — compare / similar
- [EPIC-007](../epics/EPIC-007-entropy-reduction-skills.md) — 研发熵减 Skills
