# LightRAG Fork vs LoomGraph 功能边界

> **⚠️ 历史文档（已过时，保留作追溯）**
>
> 本文档记录的是 v0.5.0 时代（2025-02）的三仓库架构规划：codeindex（解析）→ LoomGraph（调度）→ LightRAG Fork（图谱存储）。
>
> **ADR-013（2026）已终结 LightRAG Fork 路线**：LoomGraph 改用 **SQLite + sqlite-vec** 作为存储后端（`~/.loomgraph/{workspace}.db`），不再依赖 LightRAG / PostgreSQL。Embedding 从 Jina Code V2（H200 TEI）改为默认本地 **Ollama**（`nomic-embed-text`），LLM 同走 Ollama（`gemma3:12b-it-qat`）。H200 服务器（`117.131.45.179`）已于 2026-07 退役。
>
> 因此下方"LightRAG Fork 暴露 API"、"PostgreSQL 存储后端"、"Feature 3: Jina Code V2 Embedding"、"Story 3.3 (H200)"等均为**历史 feature 规划**，不再代表当前架构。当前架构与 CLI 见根 `CLAUDE.md` 与 `docs/architecture/SYSTEM_DESIGN.md`。

**日期**: 2025-02-03

---

## 核心原则

- **LightRAG fork**: 框架层定制，只做 RAG 引擎内部的修改
- **LoomGraph**: 应用层实现，组装和对外暴露服务

---

## 功能分配矩阵

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         功能分配建议                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Feature                    │ LightRAG Fork │ LoomGraph │ 理由          │
│  ──────────────────────────┼───────────────┼───────────┼────────────── │
│  F1: AST 实体直接注入       │      ✓        │           │ 修改核心逻辑  │
│  F2: 代码查询 Prompt        │      ✓        │           │ 修改 prompt  │
│  F3: Jina Embedding        │               │     ✓     │ 外部适配器    │
│  F4: MCP 服务              │               │     ✓     │ 应用层接口    │
│  F5: PostgreSQL 存储       │      ✓        │           │ 存储层扩展    │
│  F6: CLI 工具              │               │     ✓     │ 应用层        │
│  F7: 增量更新逻辑          │      部分     │    部分    │ 协作实现      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 调整后的 Epic 分配

### LightRAG Fork (https://github.com/dreamlx/LightRAG)

```
Epic: LightRAG 代码图谱引擎定制
│
├── Feature 1: AST 实体直接注入接口 (Must Have)
│   ├── Story 1.1: 设计实体/关系数据契约
│   ├── Story 1.2: 实现 bypass LLM 的插入路径
│   └── Story 1.3: 暴露 add_entity/add_relationship API
│
├── Feature 2: 代码领域查询优化 (Must Have)
│   ├── Story 2.1: 代码专用查询 Prompt 模板
│   ├── Story 2.2: 代码上下文组装策略
│   └── Story 2.3: 代码引用格式化输出
│
└── Feature 5: PostgreSQL 存储后端 (Should Have)
    ├── Story 5.1: KV 存储 PostgreSQL 实现
    └── Story 5.2: Graph 存储 PostgreSQL 实现
```

### LoomGraph (当前项目)

```
Epic: LoomGraph 代码智能检索服务
│
├── Feature 3: Jina Code V2 Embedding 集成 (Must Have)
│   ├── Story 3.1: Jina HTTP 客户端
│   ├── Story 3.2: LightRAG EmbeddingFunc 适配器
│   └── Story 3.3: 批量向量化优化 (H200)
│
├── Feature 4: MCP 服务接口 (Should Have)
│   ├── Story 4.1: 索引管理接口 (index, update, delete)
│   ├── Story 4.2: 查询接口 (search_code, get_dependencies)
│   └── Story 4.3: 状态监控接口
│
├── Feature 6: CLI 工具 (Should Have)
│   ├── Story 6.1: loomgraph init
│   ├── Story 6.2: loomgraph index
│   ├── Story 6.3: loomgraph search
│   └── Story 6.4: loomgraph serve
│
└── Feature 7: 索引管道 (Must Have)
    ├── Story 7.1: codeindex 集成 (AST 解析)
    ├── Story 7.2: LightRAG 集成 (图谱构建)
    └── Story 7.3: 增量更新协调
```

---

## 数据流向

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          完整数据流                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  用户代码库                                                              │
│      │                                                                  │
│      ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  LoomGraph: 索引管道 (Feature 7)                                │   │
│  │                                                                 │   │
│  │  1. 扫描文件                                                    │   │
│  │      │                                                          │   │
│  │      ▼                                                          │   │
│  │  2. codeindex.parse_file()                                      │   │
│  │      │ → Symbol, Import, Call, Inheritance                      │   │
│  │      ▼                                                          │   │
│  │  3. Jina Embedding (Feature 3)                                  │   │
│  │      │ → 向量化代码块                                            │   │
│  │      ▼                                                          │   │
│  │  4. LightRAG.add_entity() (Feature 1 提供的 API)                │   │
│  │      │                                                          │   │
│  └──────┼──────────────────────────────────────────────────────────┘   │
│         │                                                              │
│         ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  LightRAG Fork: 图谱引擎                                        │   │
│  │                                                                 │   │
│  │  - 存储实体和关系                                               │   │
│  │  - 构建检索索引                                                 │   │
│  │  - 处理查询请求                                                 │   │
│  │                                                                 │   │
│  └──────┬──────────────────────────────────────────────────────────┘   │
│         │                                                              │
│         ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  LoomGraph: MCP 服务 (Feature 4)                                │   │
│  │                                                                 │   │
│  │  - search_code tool                                             │   │
│  │  - get_dependencies tool                                        │   │
│  │                                                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│         │                                                              │
│         ▼                                                              │
│  Claude Desktop / Cursor                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 接口契约

### LightRAG Fork 需要暴露的新 API

```python
# lightrag/lightrag.py (新增方法)

class LightRAG:
    async def add_entity(
        self,
        name: str,
        entity_type: str,
        description: str = "",
        source_id: str = "",
        embedding: list[float] | None = None,
        metadata: dict | None = None
    ) -> str:
        """
        直接添加实体，跳过 LLM 提取。

        Args:
            name: 实体名称 (如 "UserService.login")
            entity_type: 实体类型 (如 "function", "class")
            description: 实体描述 (来自 docstring)
            source_id: 源代码块 ID
            embedding: 预计算的向量 (可选，否则内部计算)
            metadata: 额外元数据

        Returns:
            entity_id: 实体 ID
        """
        ...

    async def add_relationship(
        self,
        source_entity: str,
        target_entity: str,
        relation_type: str,
        weight: float = 1.0,
        metadata: dict | None = None
    ) -> str:
        """
        直接添加关系，跳过 LLM 提取。

        Args:
            source_entity: 源实体名称
            target_entity: 目标实体名称
            relation_type: 关系类型 (如 "CALLS", "INHERITS")
            weight: 关系权重
            metadata: 额外元数据

        Returns:
            relationship_id: 关系 ID
        """
        ...

    async def add_chunk(
        self,
        content: str,
        chunk_id: str,
        embedding: list[float] | None = None,
        metadata: dict | None = None
    ) -> str:
        """
        添加代码块 (用于语义检索)。

        Args:
            content: 代码内容
            chunk_id: 块 ID
            embedding: 预计算的向量
            metadata: 文件路径、行号等

        Returns:
            chunk_id: 块 ID
        """
        ...
```

### LoomGraph 调用示例

```python
# loomgraph/core/indexer.py

from codeindex.parser import parse_file
from lightrag import LightRAG

class CodeIndexer:
    def __init__(self, rag: LightRAG, embedding_client: JinaClient):
        self.rag = rag
        self.embedding = embedding_client

    async def index_file(self, file_path: Path) -> None:
        # 1. AST 解析
        result = parse_file(file_path)

        # 2. 向量化
        embeddings = await self.embedding.embed([s.signature for s in result.symbols])

        # 3. 添加实体
        for i, symbol in enumerate(result.symbols):
            await self.rag.add_entity(
                name=symbol.name,
                entity_type=symbol.kind,
                description=symbol.docstring,
                source_id=str(file_path),
                embedding=embeddings[i].tolist(),
                metadata={"line_start": symbol.line_start, "line_end": symbol.line_end}
            )

        # 4. 添加关系 (调用)
        for call in result.calls:
            await self.rag.add_relationship(
                source_entity=call.caller,
                target_entity=call.callee,
                relation_type="CALLS"
            )

        # 5. 添加关系 (继承)
        for inh in result.inheritances:
            await self.rag.add_relationship(
                source_entity=inh.child,
                target_entity=inh.parent,
                relation_type="INHERITS"
            )
```

---

## 待确认

1. **同意这个功能边界划分？**
   - LightRAG fork: F1, F2, F5
   - LoomGraph: F3, F4, F6, F7

2. **接口契约是否合理？**
   - `add_entity()`, `add_relationship()`, `add_chunk()`

3. **开发顺序建议：**
   - 并行 1: LightRAG F1 (AST 注入 API)
   - 并行 2: LoomGraph F3 (Jina Embedding)
   - 然后: LoomGraph F7 (索引管道，依赖前两者)
