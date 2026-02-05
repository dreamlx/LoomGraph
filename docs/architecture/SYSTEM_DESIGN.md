# LoomGraph 系统架构设计

**版本**: 0.2.0
**更新日期**: 2025-02-03
**状态**: ✅ 确认

---

## 1. 架构概览

### 1.1 三仓库分层架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              应用层 (Application)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌─────────────────────────────────────────────────────────────────────┐  │
│    │                      LoomGraph (指挥部)                              │  │
│    │                                                                     │  │
│    │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │  │
│    │   │  CLI Tool   │  │ MCP Server  │  │  Indexer    │                │  │
│    │   │ index/search│  │ Claude/IDE  │  │  Pipeline   │                │  │
│    │   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                │  │
│    │          │                │                │                        │  │
│    │          └────────────────┼────────────────┘                        │  │
│    │                           │                                         │  │
│    │   ┌───────────────────────┴───────────────────────┐                │  │
│    │   │              Core Layer                        │                │  │
│    │   │  ┌─────────┐ ┌─────────┐ ┌─────────┐         │                │  │
│    │   │  │ Mapper  │ │Injector │ │Embedding│         │                │  │
│    │   │  │         │ │         │ │ Client  │         │                │  │
│    │   │  └─────────┘ └─────────┘ └─────────┘         │                │  │
│    │   └───────────────────────────────────────────────┘                │  │
│    └─────────────────────────────────────────────────────────────────────┘  │
│                              │                    │                         │
│                              │                    │                         │
│              ┌───────────────┘                    └───────────────┐         │
│              │                                                   │         │
│              ▼                                                   ▼         │
│    ┌─────────────────────┐                         ┌─────────────────────┐ │
│    │      codeindex      │                         │       LightRAG      │ │
│    │   (AST 解析层)      │                         │    (RAG 引擎层)     │ │
│    │                     │                         │                     │ │
│    │  • Symbol 提取      │    ParseResult          │  • acreate_entity() │ │
│    │  • Call 提取        │ ──────────────────────► │  • acreate_relation│ │
│    │  • Inheritance 提取 │                         │  • aquery()         │ │
│    │  • Import 提取      │                         │  • PGGraphStorage   │ │
│    └─────────────────────┘                         └──────────┬──────────┘ │
│                                                               │            │
└───────────────────────────────────────────────────────────────┼────────────┘
                                                                │
                                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              外部服务 (External)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────────────┐   │
│  │   H200 GPU    │  │   H200 GPU    │  │         PostgreSQL            │   │
│  │  Jina TEI     │  │    vLLM       │  │  ┌─────────┬─────────────┐   │   │
│  │  :8080        │  │    :8000      │  │  │pgvector │ Apache AGE  │   │   │
│  │               │  │  (可选)       │  │  │         │ (图存储)     │   │   │
│  └───────────────┘  └───────────────┘  │  └─────────┴─────────────┘   │   │
│                                        │            :5432              │   │
│                                        └───────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 职责分工

| 仓库 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **codeindex** | AST 解析，提取代码结构 | 源代码文件 | ParseResult (Symbol, Call, Inheritance, Import) |
| **LoomGraph** | 协调调度，数据映射 | ParseResult | LightRAG API 调用 |
| **LightRAG** | 存储检索，图谱管理 | Entity/Relation Data | 查询结果 |

---

## 2. MVP 配置 (v0.1.0)

```yaml
# loomgraph.yaml - MVP 默认配置
indexing:
  # Layer 1: AST 提取 (始终启用，由 codeindex 完成)
  ast_extraction:
    enabled: true
    chunking: "ast"           # 按 Symbol 边界 (函数/类/方法)
    extract_calls: true       # 提取调用关系
    extract_inheritance: true # 提取继承关系

  # Layer 2: LLM 语义增强 (MVP 默认关闭)
  semantic_enhancement:
    enabled: false  # v0.2.0+ 可启用

embedding:
  provider: "jina"
  model: "jinaai/jina-embeddings-v2-base-code"
  base_url: "http://localhost:8080"
  batch_size: 32
  max_length: 8192
  dimension: 768
  timeout: 30.0

database:
  host: "localhost"
  port: 5432
  database: "loomgraph"
  user: "loomgraph"
  password: "loomgraph_dev"

retrieval:
  modes: ["keyword", "semantic", "graph"]
  default_mode: "hybrid"
  top_k: 10
```

---

## 3. 数据流架构

### 3.1 索引流程 (MVP: 全量重建)

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  源代码  │───▶│codeindex │───▶│ LoomGraph│───▶│  Jina    │───▶│ LightRAG │
│  Files   │    │ parse()  │    │ mapper   │    │ embed()  │    │ create() │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                     │                │               │               │
                     │                │               │               │
                     ▼                ▼               ▼               ▼
               ParseResult      EntityData/     Embeddings      PostgreSQL
               • Symbol        RelationData    list[float]     • PGKVStorage
               • Call                                          • PGVectorStorage
               • Inheritance                                   • PGGraphStorage
               • Import
```

### 3.2 检索流程

```
┌──────────┐    ┌───────────────────────────────────────┐    ┌──────────┐
│  Query   │───▶│            LightRAG aquery()          │───▶│ Results  │
│ "用户登录"│    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ │    │  排序    │
└──────────┘    │  │Keyword  │ │Semantic │ │ Graph   │ │    │  融合    │
                │  │Search   │ │ Search  │ │ Search  │ │    └──────────┘
                │  └────┬────┘ └────┬────┘ └────┬────┘ │
                │       │          │          │       │
                │       ▼          ▼          ▼       │
                │  ┌─────────────────────────────────┐│
                │  │        Hybrid Ranking           ││
                │  └─────────────────────────────────┘│
                └───────────────────────────────────────┘
```

### 3.3 Pipeline 架构 (AI Agent 友好)

#### 3.3.1 设计理念

LoomGraph 设计为 **Claude Code Skill**，主要用户是 AI Agent：

```
┌─────────────────────────────────────────────────────────────────┐
│                     Claude Code (AI Agent)                       │
│                                                                 │
│  • 读取 docs/ 理解工作流程                                        │
│  • 执行 CLI 命令                                                 │
│  • 解读 JSON 错误信息                                            │
│  • 自动修复问题 (安装依赖、调整参数)                               │
│  • 按需分步执行或一键执行                                         │
└─────────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
    │codeindex│   │loomgraph│   │loomgraph│   │loomgraph│
    │  scan   │   │  embed  │   │ inject  │   │ search  │
    └─────────┘   └─────────┘   └─────────┘   └─────────┘
```

**Pipeline 不在代码里，在 AI Agent 的推理中。**

#### 3.3.2 设计原则

| 原则 | 传统设计 (人类) | AI Agent 设计 |
|------|----------------|---------------|
| 复杂度 | 隐藏，自动处理 | 暴露，让 AI 理解 |
| 错误恢复 | 自动重试 | 返回详细错误，AI 决定 |
| 命令风格 | 单命令完成 | 原子命令可组合 |
| 输出格式 | 人类友好文本 | 机器可读 JSON |
| 依赖检查 | 内置自动安装 | 错误信息说明缺什么 |

#### 3.3.3 4-Step Pipeline

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│codeindex │───▶│loomgraph │───▶│loomgraph │───▶│ LightRAG │
│  scan    │    │  embed   │    │  inject  │    │    DB    │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │
     ▼               ▼               ▼               ▼
  JSON file      JSON file      JSON file       Graph DB
```

| Step | CLI 命令 | 输入 | 输出 |
|------|----------|------|------|
| **Parse** | `codeindex scan <repo> --output json` | 源代码目录 | `parse_results.json` |
| **Embed** | `loomgraph embed <json>` | ParseResult JSON | `embeddings.json` |
| **Inject** | `loomgraph inject <parse> <embed>` | 两个 JSON | LightRAG DB |
| **Search** | `loomgraph search <query>` | 查询文本 | 搜索结果 JSON |

#### 3.3.4 codeindex CLI 集成

LoomGraph 通过 **CLI 调用** codeindex（非 Library 导入），确保三个项目完全独立：

```bash
# codeindex 作为独立工具
codeindex scan /path/to/repo --output json > parse_results.json
```

**codeindex CLI 输出格式**：

```json
{
  "success": true,
  "results": [
    {
      "path": "src/auth/user.py",
      "symbols": [
        {"name": "UserService", "kind": "class", "signature": "class UserService:", ...}
      ],
      "calls": [{"caller": "UserService.login", "callee": "db.find", "line": 15}],
      "inheritances": [{"child": "UserService", "parent": "BaseService"}],
      "imports": [{"module": "typing", "names": ["Optional"]}]
    }
  ],
  "summary": {"total_files": 5, "total_symbols": 120, "errors": 0}
}
```

#### 3.3.5 错误处理策略

**简单原则：快速失败 + 详细错误信息**

```json
{
  "success": false,
  "error": {
    "code": "CODEINDEX_NOT_FOUND",
    "message": "codeindex command not found in PATH",
    "suggestion": "pip install matrix-codeindex",
    "docs": "https://github.com/dreamlx/codeindex#installation"
  }
}
```

AI Agent 看到这个输出后会：
1. 理解问题：codeindex 未安装
2. 执行修复：`pip install matrix-codeindex`
3. 重试命令

**不需要 LoomGraph 内置复杂的重试/恢复逻辑。**

#### 3.3.6 使用示例

**AI Agent 分步执行**:
```bash
# 1. 检查环境
loomgraph status

# 2. 解析代码
codeindex scan /repo --output json > parse_results.json

# 3. 生成向量
loomgraph embed parse_results.json --output embeddings.json

# 4. 注入图谱
loomgraph inject parse_results.json embeddings.json

# 5. 搜索
loomgraph search "用户认证逻辑"
```

**AI Agent 一键执行**:
```bash
loomgraph index /repo  # 内部调用上述步骤
```

详见: [CLI_DESIGN.md](../api/CLI_DESIGN.md)

---

## 4. 核心模块设计

### 4.1 Mapper 模块 (`src/loomgraph/core/mapper.py`)

将 codeindex 输出映射为 LightRAG 输入格式。

```python
def map_symbol_to_entity(symbol: Symbol, file_path: str, language: str) -> EntityData:
    """Symbol → LightRAG entity_data"""
    return EntityData(
        entity_name=symbol.name,
        entity_data={
            "entity_type": symbol.kind,
            "description": symbol.docstring or f"{symbol.kind}: {symbol.name}",
            "source_id": f"{file_path}:{symbol.line_start}-{symbol.line_end}",
            "file_path": file_path,
            "start_line": symbol.line_start,
            "end_line": symbol.line_end,
            "signature": symbol.signature,
            "language": language,
        }
    )

def map_call_to_relation(call: Call, file_path: str) -> RelationData:
    """Call → LightRAG edge_data"""
    return RelationData(
        src_id=call.caller,
        tgt_id=call.callee,
        edge_data={
            "relation_type": "CALLS",
            "weight": 1.0,
            "file_path": file_path,
            "line_number": call.line,
        }
    )
```

### 4.2 Injector 模块 (`src/loomgraph/core/injector.py`)

批量注入 ParseResult 到 LightRAG。

```python
async def inject_parse_result(
    rag: LightRAG,
    result: ParseResult,
    embeddings: dict[str, list[float]] | None = None,
) -> InjectResult:
    """将 codeindex 解析结果注入 LightRAG"""

    # 1. 注入实体
    for symbol in result.symbols:
        entity = map_symbol_to_entity(symbol, file_path, language)
        if embeddings:
            entity.entity_data["embedding"] = embeddings[entity.entity_name]
        await rag.acreate_entity(entity.entity_name, entity.entity_data)

    # 2. 注入调用关系
    for call in result.calls:
        rel = map_call_to_relation(call, file_path)
        await rag.acreate_relation(rel.src_id, rel.tgt_id, rel.edge_data)

    # 3. 注入继承关系
    for inh in result.inheritances:
        rel = map_inheritance_to_relation(inh, file_path)
        await rag.acreate_relation(rel.src_id, rel.tgt_id, rel.edge_data)
```

### 4.3 Indexer 模块 (`src/loomgraph/core/indexer.py`)

完整索引流水线。

```python
async def index_repository(
    repo_path: str,
    rag: LightRAG,
    embedding_client: EmbeddingClient,
    parse_file: Callable,
) -> IndexResult:
    """MVP 索引策略：全量重建"""

    # Step 1: 清空该仓库的旧数据
    await clear_repo_entities(rag, repo_path)

    # Step 2: 扫描代码文件
    files = scan_code_files(repo_path)

    # Step 3: 解析 → 向量化 → 注入
    for file_path in files:
        result = parse_file(file_path)
        if result.error:
            continue

        texts = [s.signature or s.name for s in result.symbols]
        embeddings = await embedding_client.embed(texts)
        embedding_map = {s.name: emb for s, emb in zip(result.symbols, embeddings)}

        await inject_parse_result(rag, result, embedding_map)

    return IndexResult(repo_path=repo_path, files=len(files), ...)
```

### 4.4 Embedding 模块 (`src/loomgraph/embedding/jina.py`)

Jina Code V2 客户端，支持 TEI 和 Jina API。

```python
class JinaEmbeddingClient(EmbeddingClient):
    """Jina Code V2 via TEI (8K context)"""

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """批量向量化，自动分批"""
        all_embeddings = []
        for batch in batched(texts, self._config.batch_size):
            result = await self._embed_batch(batch)
            all_embeddings.extend(result)
        return EmbeddingResult(embeddings=all_embeddings, ...)

    async def embed_with_retry(self, texts: list[str], max_retries: int = 3):
        """带重试的向量化"""
        ...
```

---

## 5. 存储架构

### 5.1 使用 LightRAG 内置存储

LoomGraph **不自定义数据库表结构**，完全复用 LightRAG 的 PostgreSQL 存储：

| 组件 | LightRAG 类 | 用途 |
|------|------------|------|
| KV 存储 | `PGKVStorage` | 配置、缓存 |
| 向量存储 | `PGVectorStorage` | Embedding 检索 |
| 图存储 | `PGGraphStorage` | 实体关系图 (Apache AGE) |
| 文档状态 | `PGDocStatusStorage` | 索引状态追踪 |

### 5.2 数据库初始化

```sql
-- scripts/init-db.sql (仅启用扩展)
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- 文本模糊搜索
-- Apache AGE 由 LightRAG 自动管理
```

---

## 6. 关系类型定义

| 类型 | 说明 | 来源 |
|------|------|------|
| `CALLS` | 函数/方法调用 | codeindex.Call |
| `INHERITS` | 类继承 | codeindex.Inheritance |
| `IMPORTS` | 模块导入 | codeindex.Import |

---

## 7. API 设计

### 7.1 CLI 接口

```bash
# 初始化配置
loomgraph init --db-url postgresql://... --embedding-url http://...

# 索引代码库 (全量重建)
loomgraph index --path /path/to/repo

# 代码搜索
loomgraph search "处理用户登录的函数" [--mode hybrid|semantic|keyword]

# 图谱查询
loomgraph graph --entity "UserService.login" --query callers

# 启动 MCP 服务
loomgraph serve --port 8080
```

### 7.2 MCP Tools (v0.2.0+)

```json
{
  "tools": [
    {
      "name": "search_code",
      "description": "搜索代码库中相关的代码片段",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string" },
          "mode": { "enum": ["hybrid", "semantic", "keyword"] },
          "limit": { "type": "integer", "default": 10 }
        },
        "required": ["query"]
      }
    },
    {
      "name": "get_callers",
      "description": "获取调用指定函数的所有函数",
      "inputSchema": {
        "type": "object",
        "properties": {
          "entity": { "type": "string" },
          "depth": { "type": "integer", "default": 1 }
        },
        "required": ["entity"]
      }
    }
  ]
}
```

---

## 8. 部署架构

### 8.1 开发环境 (Docker Compose)

```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: loomgraph
      POSTGRES_USER: loomgraph
      POSTGRES_PASSWORD: ${DB_PASSWORD:-loomgraph_dev}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  embedding:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.1
    command: --model-id jinaai/jina-embeddings-v2-base-code
    ports:
      - "8080:80"

volumes:
  pgdata:
```

### 8.2 生产环境 (H200)

```yaml
services:
  embedding:
    image: ghcr.io/huggingface/text-embeddings-inference:89-1.1
    command: --model-id jinaai/jina-embeddings-v2-base-code --max-batch-tokens 65536
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

---

## 9. 测试策略

### 9.1 测试金字塔

```
                    ┌─────────────┐
                    │   E2E Tests │  10%
                    │  (MCP/CLI)  │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │    Integration Tests    │  30%
              │  (DB, Embedding, RAG)   │
              └────────────┬────────────┘
                           │
     ┌─────────────────────┴─────────────────────┐
     │              Unit Tests                    │  60%
     │  (Mapper, Injector, Indexer, Embedding)   │
     └───────────────────────────────────────────┘
```

### 9.2 当前测试覆盖

| 模块 | 测试文件 | 测试数 |
|------|----------|--------|
| Config | `tests/unit/test_config.py` | 7 |
| Mapper | `tests/unit/test_mapper.py` | 26 |
| Injector | `tests/unit/test_injector.py` | 9 |
| Embedding | `tests/unit/test_embedding.py` | 11 |
| Indexer | `tests/unit/test_indexer.py` | 11 |
| **Total** | | **64** |

---

## 10. 附录

### 10.1 技术选型

| 选项 | 选择 | 理由 |
|------|------|------|
| 向量存储 | pgvector (via LightRAG) | 简化运维，事务一致性 |
| 图存储 | Apache AGE (via LightRAG) | LightRAG 内置支持 |
| AST 解析 | codeindex (tree-sitter) | 外部依赖，职责分离 |
| RAG 框架 | LightRAG | 轻量，已有 API 可复用 |
| Embedding | Jina Code V2 | 8K context，代码优化 |

### 10.2 相关文档

- [DATA_CONTRACT.md](../api/DATA_CONTRACT.md) - 数据映射契约
- [ADR-005](../adr/ADR-005-extraction-strategy.md) - AST 优先策略
- [ADR-006](../adr/ADR-006-mvp-simplification.md) - MVP 简化决策
- [WORKSTREAM_ASSIGNMENT.md](../WORKSTREAM_ASSIGNMENT.md) - 工作流分配
