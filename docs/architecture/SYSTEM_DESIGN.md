# LoomGraph 系统架构设计

**版本**: 0.1.0
**更新日期**: 2025-02-03
**状态**: 📝 草稿

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           应用层 (Application)                           │
├──────────────────────────────┬──────────────────────────────────────────┤
│          CLI Tool            │            MCP Server                    │
│   loomgraph index/search     │    Claude Desktop / Cursor              │
└──────────────┬───────────────┴──────────────────┬───────────────────────┘
               │                                   │
               ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           服务层 (Service)                               │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ IndexService│  │SearchService│  │ GraphService│  │ WatchService│    │
│  │ 索引管道    │  │ 混合检索    │  │ 图谱查询    │  │ 增量更新    │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
└─────────┼────────────────┼────────────────┼────────────────┼───────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           核心层 (Core)                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │   AST Chunker   │  │   LightRAG      │  │    配置管理             │  │
│  │   (tree-sitter) │  │   Integration   │  │    (Settings)           │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────────────┘  │
└───────────┼────────────────────┼────────────────────────────────────────┘
            │                    │
            ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         基础设施层 (Infrastructure)                      │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────────┐   │
│  │ EmbeddingClient│  │   LLMClient   │  │   StorageRepository       │   │
│  │ (Jina V2)     │  │   (vLLM)      │  │   (PostgreSQL+pgvector)   │   │
│  └───────┬───────┘  └───────┬───────┘  └─────────────┬─────────────┘   │
└──────────┼──────────────────┼────────────────────────┼─────────────────┘
           │                  │                        │
           ▼                  ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         外部服务 (External)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────────┐   │
│  │   H200 GPU    │  │   H200 GPU    │  │      PostgreSQL           │   │
│  │  Jina TEI     │  │    vLLM       │  │     + pgvector            │   │
│  │  :8080        │  │    :8000      │  │       :5432               │   │
│  └───────────────┘  └───────────────┘  └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 数据流架构

### 2.1 索引流程 (Indexing Pipeline)

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  源代码  │───▶│ AST解析  │───▶│ 代码切片 │───▶│ 向量化   │───▶│ 图谱提取 │
│  Files   │    │ Parser   │    │ Chunks   │    │ Jina V2  │    │ LightRAG │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                     │               │
                                                     ▼               ▼
                                              ┌──────────────────────────┐
                                              │      PostgreSQL          │
                                              │  ┌────────┬────────────┐ │
                                              │  │ Vectors│   Graph    │ │
                                              │  │pgvector│   Tables   │ │
                                              │  └────────┴────────────┘ │
                                              └──────────────────────────┘
```

### 2.2 检索流程 (Query Pipeline)

```
┌──────────┐    ┌───────────────────────────────────────┐    ┌──────────┐
│  Query   │───▶│            LightRAG Query             │───▶│ Results  │
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

---

## 3. 核心模块设计

### 3.1 存储层 (Storage Layer)

#### 3.1.1 数据库 Schema

```sql
-- 代码块表
CREATE TABLE code_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT NOT NULL,
    chunk_type VARCHAR(50) NOT NULL,  -- 'function', 'class', 'module'
    name TEXT,                         -- 函数/类名
    start_line INT NOT NULL,
    end_line INT NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL, -- SHA256
    language VARCHAR(20) NOT NULL,
    embedding vector(768),             -- Jina Code V2 维度
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(file_path, content_hash)
);

-- 实体表 (LightRAG 提取)
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    entity_type VARCHAR(50) NOT NULL,  -- 'function', 'class', 'variable', 'module'
    description TEXT,
    chunk_id UUID REFERENCES code_chunks(id),
    embedding vector(768),
    metadata JSONB,

    UNIQUE(name, entity_type, chunk_id)
);

-- 关系表
CREATE TABLE relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES entities(id),
    target_id UUID REFERENCES entities(id),
    relation_type VARCHAR(50) NOT NULL,  -- 'calls', 'imports', 'inherits', 'uses'
    weight FLOAT DEFAULT 1.0,
    metadata JSONB,

    UNIQUE(source_id, target_id, relation_type)
);

-- 向量索引
CREATE INDEX idx_chunks_embedding ON code_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_entities_embedding ON entities
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 图查询索引
CREATE INDEX idx_relationships_source ON relationships(source_id);
CREATE INDEX idx_relationships_target ON relationships(target_id);
CREATE INDEX idx_relationships_type ON relationships(relation_type);
```

#### 3.1.2 Repository 接口

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

class ChunkRepository(ABC):
    @abstractmethod
    async def save(self, chunk: CodeChunk) -> UUID: ...

    @abstractmethod
    async def find_by_hash(self, content_hash: str) -> Optional[CodeChunk]: ...

    @abstractmethod
    async def search_by_vector(
        self,
        embedding: List[float],
        limit: int = 10
    ) -> List[CodeChunk]: ...

    @abstractmethod
    async def delete_by_file(self, file_path: str) -> int: ...


class EntityRepository(ABC):
    @abstractmethod
    async def save_batch(self, entities: List[Entity]) -> List[UUID]: ...

    @abstractmethod
    async def find_by_name(self, name: str) -> List[Entity]: ...


class RelationshipRepository(ABC):
    @abstractmethod
    async def save_batch(self, relationships: List[Relationship]) -> List[UUID]: ...

    @abstractmethod
    async def find_callers(self, entity_id: UUID, depth: int = 1) -> List[Entity]: ...

    @abstractmethod
    async def find_callees(self, entity_id: UUID, depth: int = 1) -> List[Entity]: ...
```

### 3.2 Embedding 模块

#### 3.2.1 Jina Client

```python
from dataclasses import dataclass
from typing import List, Protocol
import numpy as np

@dataclass
class EmbeddingConfig:
    base_url: str = "http://localhost:8080"
    model_name: str = "jinaai/jina-embeddings-v2-base-code"
    batch_size: int = 32
    max_length: int = 8192
    timeout: float = 30.0

class EmbeddingClient(Protocol):
    async def embed(self, texts: List[str]) -> np.ndarray:
        """将文本列表转换为向量矩阵"""
        ...

class JinaEmbeddingClient:
    def __init__(self, config: EmbeddingConfig):
        self.config = config

    async def embed(self, texts: List[str]) -> np.ndarray:
        """批量调用 Jina TEI 服务"""
        # 实现批量请求，利用 H200 吞吐量
        ...
```

#### 3.2.2 LightRAG 适配器

```python
from lightrag.utils import EmbeddingFunc

def create_embedding_func(client: EmbeddingClient) -> EmbeddingFunc:
    """创建 LightRAG 兼容的 embedding 函数"""

    async def embedding_func(texts: list[str]) -> np.ndarray:
        return await client.embed(texts)

    return EmbeddingFunc(
        embedding_dim=768,      # Jina Code V2
        max_token_size=8192,    # 8k context
        func=embedding_func
    )
```

### 3.3 AST Chunker 模块

#### 3.3.1 切片策略

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

@dataclass
class CodeChunk:
    file_path: str
    chunk_type: str      # 'function', 'class', 'module'
    name: str
    content: str
    start_line: int
    end_line: int
    language: str
    docstring: Optional[str] = None

class Chunker(ABC):
    @abstractmethod
    def chunk(self, source_code: str, file_path: str) -> List[CodeChunk]:
        """将源代码切分为逻辑块"""
        ...

class PythonChunker(Chunker):
    def __init__(self):
        self.parser = Parser()
        self.parser.set_language(Language(tspython.language(), "python"))

    def chunk(self, source_code: str, file_path: str) -> List[CodeChunk]:
        tree = self.parser.parse(bytes(source_code, "utf8"))
        chunks = []

        # 遍历 AST，提取 function_definition 和 class_definition
        for node in self._traverse(tree.root_node):
            if node.type in ("function_definition", "class_definition"):
                chunk = self._extract_chunk(node, source_code, file_path)
                chunks.append(chunk)

        return chunks
```

#### 3.3.2 多语言支持

```python
class ChunkerFactory:
    _chunkers = {
        "python": PythonChunker,
        "javascript": JavaScriptChunker,
        "typescript": TypeScriptChunker,
    }

    @classmethod
    def get_chunker(cls, language: str) -> Chunker:
        if language not in cls._chunkers:
            raise ValueError(f"Unsupported language: {language}")
        return cls._chunkers[language]()

    @classmethod
    def detect_language(cls, file_path: str) -> str:
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
        }
        ext = Path(file_path).suffix
        return ext_map.get(ext, "unknown")
```

### 3.4 LightRAG 集成

#### 3.4.1 初始化配置

```python
from lightrag import LightRAG, QueryParam

class LoomGraphRAG:
    def __init__(
        self,
        working_dir: str,
        embedding_client: EmbeddingClient,
        llm_client: LLMClient,
        storage: StorageRepository
    ):
        self.rag = LightRAG(
            working_dir=working_dir,
            llm_model_func=self._create_llm_func(llm_client),
            embedding_func=create_embedding_func(embedding_client),
            # PostgreSQL 存储适配（需要定制）
            # kv_storage=PostgresKVStorage(storage),
            # graph_storage=PostgresGraphStorage(storage),
        )

    async def index(self, chunks: List[CodeChunk]) -> None:
        """索引代码块到图谱"""
        # 将 chunks 转换为 LightRAG 可接受的格式
        texts = [self._format_chunk(chunk) for chunk in chunks]
        await self.rag.ainsert(texts)

    async def search(
        self,
        query: str,
        mode: str = "hybrid"
    ) -> List[SearchResult]:
        """混合检索"""
        return await self.rag.aquery(
            query,
            param=QueryParam(mode=mode)
        )
```

---

## 4. API 设计

### 4.1 CLI 接口

```bash
# 初始化配置
loomgraph init --db-url postgresql://... --embedding-url http://...

# 索引代码库
loomgraph index --path /path/to/repo [--incremental]

# 代码搜索
loomgraph search "处理用户登录的函数" [--mode hybrid|semantic|keyword]

# 图谱查询
loomgraph graph --entity "UserService.login" --query callers

# 启动 MCP 服务
loomgraph serve --port 8080
```

### 4.2 MCP Tools

```json
{
  "tools": [
    {
      "name": "search_code",
      "description": "搜索代码库中相关的代码片段",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "搜索查询" },
          "mode": { "type": "string", "enum": ["hybrid", "semantic", "keyword"] },
          "limit": { "type": "integer", "default": 10 }
        },
        "required": ["query"]
      }
    },
    {
      "name": "get_dependencies",
      "description": "获取代码实体的依赖关系",
      "inputSchema": {
        "type": "object",
        "properties": {
          "entity": { "type": "string", "description": "实体名称" },
          "direction": { "type": "string", "enum": ["callers", "callees", "both"] }
        },
        "required": ["entity"]
      }
    }
  ]
}
```

---

## 5. 部署架构

### 5.1 开发环境 (Docker Compose)

```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: loomgraph
      POSTGRES_USER: loomgraph
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  # Jina Embedding (开发模式，CPU)
  embedding:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.1
    command: --model-id jinaai/jina-embeddings-v2-base-code
    ports:
      - "8080:80"

volumes:
  pgdata:
```

### 5.2 生产环境 (H200)

```yaml
# H200 专用配置
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

  llm:
    image: vllm/vllm-openai:latest
    command: --model deepseek-ai/deepseek-coder-v2-lite-instruct --tensor-parallel-size 1
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

---

## 6. 测试策略

### 6.1 测试金字塔

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
     │  (Chunker, Repository, Services)          │
     └───────────────────────────────────────────┘
```

### 6.2 测试分类

| 类型 | 目录 | 工具 | 说明 |
|------|------|------|------|
| 单元测试 | `tests/unit/` | pytest | 纯逻辑测试，mock 外部依赖 |
| 集成测试 | `tests/integration/` | pytest + testcontainers | 真实 DB/服务 |
| E2E 测试 | `tests/e2e/` | pytest | CLI/MCP 端到端 |
| 性能测试 | `tests/benchmark/` | pytest-benchmark | 吞吐量/延迟 |

---

## 7. 附录

### 7.1 技术选型理由

| 选项 | 选择 | 理由 |
|------|------|------|
| 向量数据库 | pgvector | 简化运维，事务一致性 |
| 图数据库 | PostgreSQL 表 | 避免引入 Neo4j 复杂度 |
| AST 解析 | tree-sitter | 速度快，多语言支持 |
| RAG 框架 | LightRAG | 轻量，易定制 |

### 7.2 性能估算

基于 H200 141GB 显存：

- Jina Code V2: ~50,000 texts/min (batch=32, 8k tokens)
- DeepSeek-Coder 图谱提取: ~1,000 chunks/min
- 预估索引速度: ~10,000 files/min (主要瓶颈在 LLM 提取)
