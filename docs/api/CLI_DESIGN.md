# LoomGraph CLI 设计

**版本**: 0.2.0
**日期**: 2025-02-03
**状态**: ✅ 确认

---

## 设计原则

本 CLI 设计针对 **AI Agent (Claude Code)** 作为主要用户：

| 原则 | 说明 |
|------|------|
| **原子命令** | 每个命令只做一件事，可组合 |
| **JSON 输出** | 机器可读，便于 AI 解析 |
| **结构化错误** | 包含错误码、建议、文档链接 |
| **幂等操作** | 重复执行产生相同结果 |
| **无交互** | 不需要用户输入确认 |

---

## 命令概览

```
loomgraph
├── index      # 一键索引 (codeindex graph-export → embed → inject; qualified id, #66)
├── update     # whole-tree re-export + upsert (post-commit; --since/--files 已废弃)
├── embed      # 生成向量 (从 ParseResult JSON)
├── inject     # 注入图谱 (ParseResult + Embeddings → LightRAG)
├── find       # 结构化实体发现 (名字匹配 + 可选关系)
├── search     # 语义搜索 (按含义, embedding KNN; find 的对等项)
├── embed-backfill  # 为已有 workspace 补充向量 (不重新解析)
├── graph      # 精确关系遍历 (callers/callees + source_id)
├── status     # 检查系统状态
└── version    # 版本信息
```

---

## 命令详情

### 1. `loomgraph index` - 一键索引

**用途**: 调用完整 Pipeline (`codeindex graph-export` → embed → inject)。实体用 **module-qualified id**（修复跨模块同名函数冲突，#66），边带 `resolution_qualifier` + 跨文件 callee 解析。需要 `ai-codeindex >= 0.28.0`。

```bash
loomgraph index <repo_path> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<repo_path>` | 仓库路径 | 必填 |
| `--clear` | 清除旧数据后重建（Cold Rebuild） | `true` |
| `-w, --workspace` | workspace 名（默认: 当前目录名） | 自动 |

**成功输出** (exit code: 0):
```json
{
  "success": true,
  "data": {
    "mode": "cold_rebuild",
    "workspace": "myproj:main",
    "repo_path": "/path/to/repo",
    "cleared": true,
    "entities_created": 1250,
    "relations_created": 3400,
    "embedded": 1250,
    "store_stats": {"entities": 1250, "relations": 3400},
    "duration_seconds": 45.2
  }
}
```

> **#66 Breaking**: 旧版本（legacy `codeindex scan` 路径）索引的 workspace 用简单名 key，升级后**必须 `loomgraph index --clear .` 一次**重建，否则同名符号（`handle`/`run`/`__init__` 等）仍冲突。

**错误输出** (exit code: 1):
```json
{
  "success": false,
  "error": {
    "code": "CODEINDEX_NOT_FOUND",
    "message": "codeindex command not found in PATH",
    "suggestion": "Install codeindex: pip install ai-codeindex",
    "docs": "https://github.com/dreamlx/codeindex#installation"
  }
}
```

`loomgraph update` 走同一管线（`clear=False`，upsert 语义），但每次 **whole-tree re-export**（不再是 per-file 增量；`--since`/`--files` 已废弃但保留兼容，会被忽略）。warm-incremental 由 content_hash diff 恢复（跟进项）。

---

### 2. `loomgraph import-export` - 消费 codeindex graph-export artifact

**用途**: 读取 codeindex `graph-export` 写出的 NDJSON 文件（codeindex#102 契约），把其中的 entities + edges 落入一个 workspace。LoomGraph#30 spike 验证过 round-trip 语义保真。

```bash
loomgraph import-export <artifact> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<artifact>` | codeindex graph-export 产出的 NDJSON 路径 | 必填 |
| `--workspace`, `-w` | 写入 workspace 名 | `<basename>:imported` |
| `--clear` / `--no-clear` | 写入前清空 workspace | `false`（非破坏性默认） |
| `--dry-run` | 只读取 + 校验 + 映射，不写存储 | `false` |

**默认 workspace 命名**: `<artifact-basename>:imported`（`:imported` 后缀避免与 `loomgraph index .` 的 workspace 撞名）

**资格保真**: 每条 edge 的 `resolution_qualifier`（`resolved` / `ambiguous` / `unresolved`）原样保留在 `edge_data` 里，让下游 `find` / `graph` 查询能显式过滤。`unresolved` edges 不入库（避免单一 sentinel target 造成虚假 hub），但 `summary.edge_qualifiers["unresolved"]` 保留完整计数。

**成功输出**（`--dry-run`）:
```json
{
  "success": true,
  "data": {
    "workspace": "customer:imported",
    "artifact": "/tmp/customer.ndjson",
    "dry_run": true,
    "summary": {
      "meta": {"schema_version": 0, "provenance_completeness": "ast-only..."},
      "entity_count": 2931,
      "relation_count": 5057,
      "entity_types": {"class": 541, "function": 655, "method": 1735},
      "edge_kinds": {"CALLS": 12284, "INHERITS": 30},
      "edge_qualifiers": {"resolved": 2890, "ambiguous": 2167, "unresolved": 7257},
      "skipped_records": 0,
      "schema_warnings": []
    },
    "would_write": {"entities": 2931, "relations": 5057}
  }
}
```

**成功输出**（实写）增加 `store_stats`，删去 `dry_run` / `would_write`。

**错误输出**:
```json
{
  "success": false,
  "error": {
    "code": "INVALID_INPUT",
    "message": "Artifact malformed: meta record missing schema_version",
    "suggestion": "Validate with: head -1 <file> | python3 -m json.tool"
  }
}
```

错误码: `FILE_NOT_FOUND` / `INVALID_INPUT` / `STORAGE_ERROR`

---

### 4. `loomgraph find` - 结构化实体发现

**用途**: 按名字匹配实体，可选带关系上下文

```bash
loomgraph find <query> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<query>` | 名字匹配关键词 | 必填 |
| `--type/-t` | 实体类型过滤 (class/function/module) | 全部 |
| `--limit/-n` | 结果数量 | `20` |
| `--with-relations` | 附带 callers/callees | 否 |
| `--depth` | BFS 扩展层数（需 `--with-relations`） | `1` |
| `--workspace/-w` | Workspace 名称 | 当前目录名 |

**基础输出**:
```json
{
  "success": true,
  "data": {
    "query": "auth",
    "total_entities": 1250,
    "matches_count": 3,
    "matches": [
      {
        "entity": "AuthService",
        "type": "class",
        "source_id": "src/auth/service.py",
        "description": "Python class | src/auth/service.py",
        "score": 0.95
      }
    ]
  }
}
```

**`--with-relations` 输出**:
```json
{
  "success": true,
  "data": {
    "query": "auth",
    "matches_count": 1,
    "matches": [
      {
        "entity": "AuthService",
        "type": "class",
        "source_id": "src/auth/service.py",
        "score": 0.95,
        "callers": [
          {"entity": "LoginController", "relation": "CALLS"},
          {"entity": "ApiFilter", "relation": "CALLS"}
        ],
        "callees": [
          {"entity": "UserRepository", "relation": "CALLS"},
          {"entity": "JwtProvider", "relation": "CALLS"}
        ]
      }
    ]
  }
}
```

---

### 4.5. `loomgraph search` - 语义搜索 (按含义)

**用途**: 按自然语言含义检索实体——`find` 的语义对等项。`find` 按名字匹配,`search` 按意图/含义(把 query 嵌入实体描述向量空间做 KNN)。互补关系:知道符号名用 `find`,知道"它做什么"用 `search`。(EPIC-015 / #70)

```bash
loomgraph search <query> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<query>` | 自然语言意图或描述性短语 | 必填 |
| `--type/-t` | 实体类型过滤 (class/function/method/module) | 全部 |
| `--limit/-n` | 结果数量 | `20` |
| `--workspace/-w` | Workspace 名称 | 当前目录名(带降级) |

**前置条件**: workspace 必须在 embedding 开启时索引过(`LOOMGRAPH_EMBEDDING__ENABLED=true`)。否则返回 `EMBEDDING_NOT_INDEXED`。

**输出**:
```json
{
  "query": "where are hotspots computed",
  "mode": "semantic",
  "workspace": "loomgraph:main",
  "vector_count": 338,
  "matches_count": 5,
  "matches": [
    {"entity": "core.git_metrics.GitMetricsAnalyzer._detect_hotspots", "type": "method",
     "source_id": "core/git_metrics.py:88", "description": "...", "score": 0.157}
  ]
}
```

> **历史**: `search` 曾是 `find` 的隐藏 deprecated 别名(v0.10 前)。EPIC-015 回收这个名字给语义搜索——`find`(按名)/`search`(按义)/`graph`(按关系)三个对等检索模式。旧的 deprecation warning 已移除。

---
### 4.5b. `loomgraph embed-backfill` - 为已有 workspace 补充向量

**用途**: 对于已有 entities 但缺少 embedding vectors 的 workspace（例如通过 `import-export` 导入的 workspace，导入时不携带向量数据），嵌入现有 entity 描述并写入 `vec_node_descriptions`。**不重新解析、不重新注入**——只对已存在的 entities 做向量化。(EPIC-015 Phase 3 / #70)

```bash
loomgraph embed-backfill [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--workspace/-w` | Workspace 名称 | 当前目录名(带降级) |

**前置条件**:
- Workspace 必须已有 entities（通过 `loomgraph index .` 或 `loomgraph import-export` 创建）
- 必须启用 embedding: `LOOMGRAPH_EMBEDDING__ENABLED=true` + 配置 provider

**幂等性**: 如果 workspace 已有向量（`vector_count() > 0`），直接跳过，不报错、不重新嵌入。

**成功输出**（首次回填）:
```json
{
  "success": true,
  "data": {
    "workspace": "customer:imported",
    "embedded": 2931,
    "total_entities": 2931,
    "model": "jina-code-v2"
  }
}
```

**成功输出**（已嵌入，跳过）:
```json
{
  "success": true,
  "data": {
    "workspace": "customer:imported",
    "skipped": true,
    "reason": "workspace already embedded",
    "vector_count": 2931,
    "total_entities": 2931
  }
}
```

**错误输出**:
```json
{
  "success": false,
  "error": {
    "code": "EMBEDDING_NOT_INDEXED",
    "message": "Workspace 'customer:imported' has no entities.",
    "suggestion": "Index first: loomgraph index <path>  (with LOOMGRAPH_EMBEDDING__ENABLED=true for semantic search)."
  }
}
```

错误码: `EMBEDDING_NOT_INDEXED` / `EMBEDDING_FAILED`

---

---

### 4.6. `loomgraph query` - 语义知识问答 (v0.10.0 已移除)

> **已移除（v0.10.0, EPIC-011 Phase 4）**: 自然语言代码问答让位给 Claude Code / Codex / Cursor 等通用 agent，LoomGraph 聚焦结构精确的 `find` / `graph` / `topology`。本节保留作为历史参考。详见 [ADR-013](../adr/ADR-013-sqlite-vec-replace-lightrag.md)。

**用途**（历史）: 用自然语言提问，RAG 引擎从知识图谱生成回答

```bash
loomgraph query <question> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<question>` | 自然语言问题 | 必填 |
| `--mode` | 查询模式 | `hybrid` |
| `--workspace/-w` | Workspace 名称 | 当前目录名 |

**查询模式**:
| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `hybrid`（默认） | 图谱 + 向量 + LLM | 通用问题 |
| `local` | 以实体为中心展开 | 特定组件深入 |
| `global` | 全局主题提取 | 架构级问题 |
| `naive` | 纯向量搜索 + LLM | 代码内容搜索 |

**成功输出**:
```json
{
  "success": true,
  "data": {
    "query": "How does the authentication flow work?",
    "mode": "hybrid",
    "response": "The authentication flow follows a layered architecture...",
    "workspace": "my-project"
  }
}
```

> **注意**: `query` 依赖 H200 上的 LLM 服务。LLM 不可用时会返回错误并建议使用 `find` 作为 fallback。

---

### 5. `loomgraph graph` - 精确关系遍历

**用途**: 查询实体的调用关系（含 source_id 文件路径）

```bash
loomgraph graph <entity_name> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<entity_name>` | 实体名称（精确匹配） | 必填 |
| `--direction` | 查询方向 | `both` |
| `--depth` | 遍历深度 | `1` |
| `--relation-type` | 关系类型 | `all` |
| `--workspace/-w` | Workspace 名称 | 当前目录名 |

**方向**:
- `callers` - 谁调用了这个实体
- `callees` - 这个实体调用了谁
- `both` - 双向

**关系类型**:
- `CALLS` - 调用关系
- `INHERITS` - 继承关系
- `IMPORTS` - 导入关系
- `all` - 所有关系

**成功输出**:
```json
{
  "success": true,
  "data": {
    "entity": "UserService.login",
    "source_id": "src/auth/service.py",
    "callers": [
      {
        "entity": "AuthController.handle_login",
        "relation": "CALLS",
        "source_id": "src/api/auth.py"
      }
    ],
    "callees": [
      {
        "entity": "db.find_user",
        "relation": "CALLS",
        "source_id": "src/db/query.py"
      }
    ],
    "callers_count": 1,
    "callees_count": 1
  }
}
```

---

### 5.5. `loomgraph topology` - 图谱拓扑分析

**用途**: 分析知识图谱拓扑结构，检测结构级代码坏味道

```bash
loomgraph topology [options]
```

> ✅ **#66 已修复**：`loomgraph index`/`update` 已迁到 `codeindex graph-export` 契约，实体用 module-qualified id。跨模块同名函数不再合并成幻影 god_function。升级后需 `loomgraph index --clear .` 重建一次 workspace。

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--hub-threshold` | Hub 实体的最小 in-degree | `5` |
| `--god-threshold` | God Function 的最小 out-degree | `5` |
| `--module` | 模块前缀过滤（source_id 前缀匹配） | 全部 |
| `--workspace/-w` | Workspace 名称 | 当前目录名 |

**成功输出**:
```json
{
  "success": true,
  "data": {
    "summary": {
      "total_entities": 586,
      "total_relations": 952,
      "orphan_count": 46,
      "hub_count": 28,
      "god_function_count": 72,
      "placeholder_module_count": 3,
      "coupling_density": 0.35,
      "topology_score": 62
    },
    "orphans": [
      {"entity": "ChangedFile", "type": "class", "source_id": "core/impact/models.py:10-15"}
    ],
    "hubs": [
      {"entity": "output_success", "type": "function", "source_id": "cli/_common.py:88-93",
       "in_degree": 18, "callers_sample": ["index", "update", "find", "graph", "deps"]}
    ],
    "god_functions": [
      {"entity": "_async_index_pipeline", "type": "function", "source_id": "cli/_indexing.py:...",
       "out_degree": 28, "callees_sample": ["collect_kg_data", "LightRAGClient.__init__"]}
    ],
    "placeholder_modules": [
      {"module": "chunking", "entities": ["chunking.__init__"], "status": "empty"}
    ],
    "coupling": {
      "cross_module_relations": 21,
      "intra_module_relations": 931,
      "density": 0.35,
      "most_coupled_pairs": [{"from": "cli", "to": "core", "count": 19}]
    }
  }
}
```

**检测项**:
- **Orphans**: 0 in-degree + 0 out-degree（排除 module 类型和 external）
- **Hubs**: 高 in-degree 实体（修改会产生广泛涟漪）
- **God Functions**: 高 out-degree 实体（职责过重）
- **Placeholder Modules**: 仅含 `__init__` 的模块
- **Coupling Density**: cross_module_relations / total_relations

**拓扑分数 (topology_score, 0-100)**:
- orphan_ratio > 20% → -25, > 10% → -15
- hub (in >= 15) → -5 per entity
- god_function (out >= 20) → -5 per, (out >= 10) → -3 per
- placeholder_modules → -5 per module
- coupling_density > 0.5 → -10, > 0.3 → -5

---

### 5.6. `loomgraph check` - 索引新鲜度检查

**用途**: 验证知识图谱中的 source_id 是否仍指向磁盘上存在的文件

```bash
loomgraph check [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--repo-path` | 项目根目录（用于验证文件路径） | `.` |
| `--workspace/-w` | Workspace 名称 | 当前目录名 |

**成功输出**:
```json
{
  "success": true,
  "data": {
    "freshness": {
      "total_source_paths": 150,
      "valid": 116,
      "stale": 34,
      "freshness_ratio": 0.773
    },
    "stale_entries": [
      {
        "source_id": "cli/main.py:66-81",
        "file_path": "cli/main.py",
        "reason": "file_not_found",
        "suggestion": "Run 'loomgraph update' or 'loomgraph index --clear .'"
      }
    ],
    "suggestion": "34 source paths are stale. Run 'loomgraph index --clear .' to rebuild."
  }
}
```

---

### 6. `loomgraph status` - 系统状态

**用途**: 检查依赖和服务状态

```bash
loomgraph status [options]
```

**成功输出**:
```json
{
  "success": true,
  "data": {
    "version": "0.1.0",
    "dependencies": {
      "codeindex": {"installed": true, "version": "0.5.0", "path": "/usr/local/bin/codeindex"},
      "postgres": {"connected": true, "version": "16.1", "host": "localhost:5432"},
      "embedding": {"connected": true, "model": "jina-embeddings-v2-base-code", "url": "http://localhost:8080"},
      "lightrag": {"installed": true, "version": "1.0.0"}
    },
    "index_stats": {
      "total_entities": 5420,
      "total_relations": 12350,
      "indexed_files": 230
    }
  }
}
```

**部分失败输出**:
```json
{
  "success": false,
  "data": {
    "version": "0.1.0",
    "dependencies": {
      "codeindex": {"installed": false, "error": "command not found"},
      "postgres": {"connected": true, "version": "16.1"},
      "embedding": {"connected": false, "error": "connection refused"}
    }
  },
  "error": {
    "code": "DEPENDENCIES_MISSING",
    "message": "Some dependencies are not available",
    "suggestions": [
      "Install codeindex: pip install matrix-codeindex",
      "Start embedding service: docker compose up -d embedding"
    ]
  }
}
```

---

## 错误码定义

| 错误码 | 说明 | 建议操作 |
|--------|------|----------|
| `CODEINDEX_NOT_FOUND` | codeindex 未安装 | `pip install matrix-codeindex` |
| `CODEINDEX_FAILED` | codeindex 执行失败 | 检查 codeindex 输出 |
| `CODEINDEX_TIMEOUT` | codeindex 超时 | 尝试更小的目录 |
| `EMBEDDING_SERVICE_UNAVAILABLE` | Embedding 服务不可用 | 启动 TEI 服务 |
| `EMBEDDING_FAILED` | Embedding 生成失败 | 检查输入格式 |
| `DATABASE_CONNECTION_FAILED` | 数据库连接失败 | 启动 PostgreSQL |
| `DATABASE_ERROR` | 数据库操作错误 | 检查数据库状态 |
| `LIGHTRAG_ERROR` | LightRAG 错误 | 检查 LightRAG 配置 |
| `INVALID_INPUT` | 输入格式错误 | 检查 JSON 格式 |
| `FILE_NOT_FOUND` | 文件不存在 | 检查路径 |

---

## 使用示例

### AI Agent 一键执行

```bash
# 一键完成所有步骤
loomgraph index /path/to/repo
```

### 错误恢复示例

```bash
# 如果 index 失败，AI 可以分步调试
$ loomgraph index /repo
{"success": false, "error": {"code": "CODEINDEX_NOT_FOUND", ...}}

# AI 根据错误信息安装依赖
$ pip install matrix-codeindex

# 重新执行
$ loomgraph index /repo
{"success": true, ...}
```

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LOOMGRAPH_DB_URL` | PostgreSQL 连接串 | `postgresql://localhost:5432/loomgraph` |
| `LOOMGRAPH_EMBEDDING_URL` | Embedding 服务 URL | `http://localhost:8080` |
| `LOOMGRAPH_LOG_LEVEL` | 日志级别 | `INFO` |
| `LOOMGRAPH_OUTPUT_FORMAT` | 默认输出格式 | `json` |
