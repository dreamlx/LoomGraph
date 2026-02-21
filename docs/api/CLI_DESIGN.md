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
├── index      # 一键索引 (调用 codeindex → embed → inject)
├── embed      # 生成向量 (从 ParseResult JSON)
├── inject     # 注入图谱 (ParseResult + Embeddings → LightRAG)
├── find       # 结构化实体发现 (名字匹配 + 可选关系)
├── query      # 语义知识问答 (RAG 引擎, LLM 驱动)
├── graph      # 精确关系遍历 (callers/callees + source_id)
├── status     # 检查系统状态
└── version    # 版本信息
```

---

## 命令详情

### 1. `loomgraph index` - 一键索引

**用途**: 调用完整 Pipeline (scan → parse → embed → inject)

```bash
loomgraph index <repo_path> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<repo_path>` | 仓库路径 | 必填 |
| `--output-format` | 输出格式 | `json` |
| `--clear` | 清除旧数据后重建 | `true` |
| `--verbose` | 显示详细日志 | `false` |

**成功输出** (exit code: 0):
```json
{
  "success": true,
  "data": {
    "repo_path": "/path/to/repo",
    "files_scanned": 150,
    "files_indexed": 148,
    "files_skipped": 2,
    "entities_created": 1250,
    "relations_created": 3400,
    "duration_seconds": 45.2
  },
  "skipped_files": [
    {"path": "src/broken.py", "reason": "parse_error", "detail": "SyntaxError line 42"}
  ]
}
```

**错误输出** (exit code: 1):
```json
{
  "success": false,
  "error": {
    "code": "CODEINDEX_NOT_FOUND",
    "message": "codeindex command not found in PATH",
    "suggestion": "Install codeindex: pip install matrix-codeindex",
    "docs": "https://github.com/dreamlx/codeindex#installation"
  }
}
```

---

### 2. `loomgraph embed` - 生成向量

**用途**: 从 ParseResult JSON 生成 Embeddings

```bash
loomgraph embed <input_json> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<input_json>` | codeindex 输出的 JSON 文件 | 必填 |
| `--output` | 输出文件路径 | stdout |
| `--batch-size` | 批处理大小 | `32` |

**输入格式** (codeindex scan 输出):
```json
{
  "results": [
    {
      "path": "src/user.py",
      "symbols": [{"name": "UserService", "signature": "class UserService:", ...}],
      "calls": [...],
      "inheritances": [...]
    }
  ]
}
```

**成功输出**:
```json
{
  "success": true,
  "data": {
    "embeddings": {
      "UserService": [0.123, -0.456, ...],
      "UserService.login": [0.789, -0.012, ...]
    },
    "model": "jinaai/jina-embeddings-v2-base-code",
    "dimension": 768,
    "count": 125
  }
}
```

**错误输出**:
```json
{
  "success": false,
  "error": {
    "code": "EMBEDDING_SERVICE_UNAVAILABLE",
    "message": "Cannot connect to embedding service at http://localhost:8080",
    "suggestion": "Start TEI server: docker compose up -d embedding",
    "docs": "docs/deployment/DOCKER.md"
  }
}
```

---

### 3. `loomgraph inject` - 注入图谱

**用途**: 将 ParseResult + Embeddings 注入 LightRAG

```bash
loomgraph inject <parse_json> <embeddings_json> [options]
```

**参数**:
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<parse_json>` | codeindex 输出 | 必填 |
| `<embeddings_json>` | embed 输出 | 必填 |
| `--clear` | 清除旧数据 | `false` |

**成功输出**:
```json
{
  "success": true,
  "data": {
    "entities_created": 125,
    "relations_created": 340,
    "entities_updated": 15,
    "duration_seconds": 2.3
  }
}
```

**错误输出**:
```json
{
  "success": false,
  "error": {
    "code": "DATABASE_CONNECTION_FAILED",
    "message": "Cannot connect to PostgreSQL at localhost:5432",
    "suggestion": "Start database: docker compose up -d postgres",
    "docs": "docs/deployment/DOCKER.md"
  }
}
```

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

> **向后兼容**: `loomgraph search` 作为隐藏别名保留一个版本，会输出 deprecation warning。

---

### 4.5. `loomgraph query` - 语义知识问答

**用途**: 用自然语言提问，RAG 引擎从知识图谱生成回答

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

### AI Agent 分步执行

```bash
# Step 1: 检查环境
loomgraph status

# Step 2: 解析代码 (调用 codeindex)
codeindex scan /path/to/repo --output json > parse_results.json

# Step 3: 生成向量
loomgraph embed parse_results.json --output embeddings.json

# Step 4: 注入图谱
loomgraph inject parse_results.json embeddings.json

# Step 5: 查找实体
loomgraph find "用户认证" --with-relations

# Step 6: 语义问答
loomgraph query "用户认证逻辑是怎样的？"
```

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
