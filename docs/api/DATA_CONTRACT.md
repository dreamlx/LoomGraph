# LoomGraph 数据契约

**版本**: 0.2.0
**日期**: 2025-02-03
**状态**: ✅ 确认

---

## 概述

本文档定义 **codeindex → LoomGraph → LightRAG** 之间的数据映射规则。

**核心原则**：复用 LightRAG 已有 API，不重新造轮子。

```
codeindex                    LoomGraph                    LightRAG
(AST 解析)                   (映射转换)                   (存储检索)
    │                            │                            │
    │ ParseResult                │                            │
    ├──────────────────────────► │                            │
    │                            │ entity_data                │
    │                            ├──────────────────────────► │
    │                            │                            │ acreate_entity()
    │                            │                            │ acreate_relation()
    │                            │                            │ PGGraphStorage
```

---

## 1. codeindex 输出格式 (不变)

### ParseResult

```python
@dataclass
class ParseResult:
    path: Path
    symbols: list[Symbol]
    imports: list[Import]
    calls: list[Call]
    inheritances: list[Inheritance]
    module_docstring: str
    file_lines: int
    error: str | None
```

### Symbol

```python
@dataclass
class Symbol:
    name: str           # "UserService.login"
    kind: str           # "function", "class", "method"
    signature: str      # "def login(self, username: str, password: str) -> bool"
    docstring: str      # "Authenticate user..."
    line_start: int     # 12
    line_end: int       # 25
```

### Call

```python
@dataclass
class Call:
    caller: str         # "UserService.login"
    callee: str         # "db.find_user"
    line: int           # 15
    is_method: bool     # True
```

### Inheritance

```python
@dataclass
class Inheritance:
    child: str          # "UserService"
    parent: str         # "BaseService"
```

---

## 2. LightRAG 已有 API (复用)

### Entity 创建

```python
# lightrag/lightrag.py:3897
await rag.acreate_entity(
    entity_name: str,           # 实体唯一标识
    entity_data: Dict[str, Any] # 实体属性（灵活扩展）
)
```

### Relation 创建

```python
# lightrag/lightrag.py:3927
await rag.acreate_relation(
    src_id: str,                # 源实体 ID
    tgt_id: str,                # 目标实体 ID
    edge_data: Dict[str, Any]   # 关系属性
)
```

### 批量删除

```python
# 通过 PGGraphStorage
await graph.remove_nodes(node_ids: list[str])
await graph.remove_edges(edges: list[tuple])
```

---

## 3. 映射规则 (LoomGraph 负责实现)

### Symbol → Entity

```python
def map_symbol_to_entity(symbol: Symbol, file_path: str, language: str) -> tuple[str, dict]:
    """将 codeindex Symbol 映射为 LightRAG entity."""

    entity_name = symbol.name  # 唯一标识

    entity_data = {
        # LightRAG 标准字段
        "entity_type": symbol.kind,
        "description": symbol.docstring or f"{symbol.kind}: {symbol.name}",
        "source_id": f"{file_path}:{symbol.line_start}-{symbol.line_end}",

        # 代码专用扩展字段
        "file_path": file_path,
        "start_line": symbol.line_start,
        "end_line": symbol.line_end,
        "signature": symbol.signature,
        "language": language,
    }

    return entity_name, entity_data
```

**示例输入**:
```python
Symbol(
    name="UserService.login",
    kind="method",
    signature="def login(self, username: str, password: str) -> bool",
    docstring="Authenticate user with credentials.",
    line_start=12,
    line_end=25
)
```

**示例输出**:
```python
entity_name = "UserService.login"
entity_data = {
    "entity_type": "method",
    "description": "Authenticate user with credentials.",
    "source_id": "src/auth/service.py:12-25",
    "file_path": "src/auth/service.py",
    "start_line": 12,
    "end_line": 25,
    "signature": "def login(self, username: str, password: str) -> bool",
    "language": "python"
}
```

### Call → Relation

```python
def map_call_to_relation(call: Call, file_path: str) -> tuple[str, str, dict]:
    """将 codeindex Call 映射为 LightRAG relation."""

    src_id = call.caller
    tgt_id = call.callee

    edge_data = {
        "relation_type": "CALLS",
        "weight": 1.0,
        "file_path": file_path,
        "line_number": call.line,
        "is_method_call": call.is_method,
    }

    return src_id, tgt_id, edge_data
```

**示例输出**:
```python
src_id = "UserService.login"
tgt_id = "db.find_user"
edge_data = {
    "relation_type": "CALLS",
    "weight": 1.0,
    "file_path": "src/auth/service.py",
    "line_number": 15,
    "is_method_call": True
}
```

### Inheritance → Relation

```python
def map_inheritance_to_relation(inh: Inheritance, file_path: str) -> tuple[str, str, dict]:
    """将 codeindex Inheritance 映射为 LightRAG relation."""

    src_id = inh.child
    tgt_id = inh.parent

    edge_data = {
        "relation_type": "INHERITS",
        "weight": 1.0,
        "file_path": file_path,
    }

    return src_id, tgt_id, edge_data
```

---

## 4. 批量注入封装 (LoomGraph 实现)

```python
# loomgraph/core/injector.py

async def inject_parse_result(
    rag: LightRAG,
    result: ParseResult,
    embeddings: dict[str, list[float]]  # name -> embedding
) -> InjectResult:
    """将 codeindex 解析结果批量注入 LightRAG."""

    file_path = str(result.path)
    language = detect_language(file_path)

    # 1. 注入实体
    entity_count = 0
    for symbol in result.symbols:
        entity_name, entity_data = map_symbol_to_entity(symbol, file_path, language)

        # 添加预计算的 embedding（可选）
        if entity_name in embeddings:
            entity_data["embedding"] = embeddings[entity_name]

        await rag.acreate_entity(entity_name, entity_data)
        entity_count += 1

    # 2. 注入调用关系
    relation_count = 0
    for call in result.calls:
        src_id, tgt_id, edge_data = map_call_to_relation(call, file_path)
        await rag.acreate_relation(src_id, tgt_id, edge_data)
        relation_count += 1

    # 3. 注入继承关系
    for inh in result.inheritances:
        src_id, tgt_id, edge_data = map_inheritance_to_relation(inh, file_path)
        await rag.acreate_relation(src_id, tgt_id, edge_data)
        relation_count += 1

    return InjectResult(
        file_path=file_path,
        entities=entity_count,
        relations=relation_count
    )
```

---

## 5. 全量重建策略 (MVP)

```python
# loomgraph/core/indexer.py

async def index_repository(repo_path: str, rag: LightRAG) -> IndexResult:
    """MVP 索引策略：全量重建."""

    # Step 1: 获取该仓库的所有已有实体
    existing_entities = await get_entities_by_file_prefix(rag, repo_path)

    # Step 2: 删除旧数据
    if existing_entities:
        await rag.graph_storage.remove_nodes([e["entity_name"] for e in existing_entities])

    # Step 3: 扫描并解析所有文件
    files = scan_code_files(repo_path)
    total_entities = 0
    total_relations = 0

    for file_path in files:
        # 解析
        result = codeindex.parse_file(file_path)
        if result.error:
            continue

        # 向量化
        texts = [s.signature or s.name for s in result.symbols]
        embeddings = await jina_client.embed(texts)
        embedding_map = {s.name: emb for s, emb in zip(result.symbols, embeddings)}

        # 注入
        inject_result = await inject_parse_result(rag, result, embedding_map)
        total_entities += inject_result.entities
        total_relations += inject_result.relations

    return IndexResult(
        repo_path=repo_path,
        files=len(files),
        entities=total_entities,
        relations=total_relations
    )
```

---

## 6. 查询接口 (复用 LightRAG)

### 语义搜索

```python
# 复用 LightRAG 的 aquery
result = await rag.aquery(
    query="用户登录验证的代码",
    param=QueryParam(mode="hybrid")
)
```

### 图遍历查询

```python
# 复用 LightRAG 的 graph_storage
callers = await rag.graph_storage.get_node_edges(
    source_node_id="db.find_user",
    edge_type="CALLS"
)
```

---

## 7. 关系类型定义

| 类型 | 说明 | 来源 |
|------|------|------|
| `CALLS` | 函数调用 | codeindex.Call |
| `INHERITS` | 类继承 | codeindex.Inheritance |
| `IMPORTS` | 模块导入 | codeindex.Import |

---

## 8. 存储说明

**使用 LightRAG 内置的 PostgreSQL 存储**，无需自定义表结构。

| 组件 | LightRAG 类 | 用途 |
|------|------------|------|
| KV 存储 | `PGKVStorage` | 配置、缓存 |
| 向量存储 | `PGVectorStorage` | Embedding 检索 |
| 图存储 | `PGGraphStorage` | 实体关系图（Apache AGE） |
| 文档状态 | `PGDocStatusStorage` | 索引状态追踪 |

---

## 9. 错误处理

| 场景 | 处理方式 |
|------|----------|
| codeindex 解析失败 | 跳过该文件，记录日志 |
| Jina 向量化失败 | 重试 3 次，失败则跳过 |
| LightRAG 写入失败 | 抛出异常，终止当前文件 |
| 实体已存在 | Upsert（MERGE 语义） |

---

## 附录：字段映射速查表

### Entity 字段

| codeindex | LightRAG entity_data | 必填 |
|-----------|---------------------|------|
| `symbol.name` | `entity_name` (参数) | ✅ |
| `symbol.kind` | `entity_type` | ✅ |
| `symbol.docstring` | `description` | ✅ |
| `file_path:line` | `source_id` | ✅ |
| `file_path` | `file_path` | ✅ |
| `symbol.line_start` | `start_line` | ✅ |
| `symbol.line_end` | `end_line` | ✅ |
| `symbol.signature` | `signature` | ⚪ |
| 检测 | `language` | ⚪ |

### Relation 字段

| codeindex | LightRAG edge_data | 必填 |
|-----------|-------------------|------|
| `call.caller` | `src_id` (参数) | ✅ |
| `call.callee` | `tgt_id` (参数) | ✅ |
| `"CALLS"` | `relation_type` | ✅ |
| `1.0` | `weight` | ⚪ |
| `call.line` | `line_number` | ⚪ |
| `file_path` | `file_path` | ⚪ |
