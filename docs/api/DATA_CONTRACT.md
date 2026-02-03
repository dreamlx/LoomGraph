# LoomGraph 数据契约

**版本**: 0.1.0 (MVP)
**日期**: 2025-02-03

---

## 概述

本文档定义 codeindex → LoomGraph → LightRAG 之间的数据格式。

---

## 1. codeindex 输出格式

### ParseResult

```python
@dataclass
class ParseResult:
    path: Path
    symbols: list[Symbol]
    imports: list[Import]
    calls: list[Call]           # MVP 新增
    inheritances: list[Inheritance]  # MVP 新增
    module_docstring: str
    file_lines: int
    error: str | None
```

### Symbol

```json
{
  "name": "UserService.login",
  "kind": "method",
  "signature": "def login(self, username: str, password: str) -> bool",
  "docstring": "Authenticate user with username and password.",
  "line_start": 12,
  "line_end": 25
}
```

### Call (MVP 新增)

```json
{
  "caller": "UserService.login",
  "callee": "db.find_user",
  "line": 15,
  "is_method": true
}
```

### Inheritance (MVP 新增)

```json
{
  "child": "UserService",
  "parent": "BaseService"
}
```

---

## 2. LightRAG API 契约

### add_entity

**用途**: 添加代码实体（函数、类、方法）

```json
{
  "name": "UserService.login",
  "entity_type": "method",
  "description": "Authenticate user with username and password.",
  "file_path": "src/auth/service.py",
  "start_line": 12,
  "end_line": 25,
  "embedding": [0.001, -0.023, ...],
  "metadata": {
    "language": "python",
    "signature": "def login(self, username: str, password: str) -> bool"
  }
}
```

**幂等规则**: 基于 `(name, entity_type, file_path)` 做 upsert。

### add_relationship

**用途**: 添加实体间关系

```json
{
  "source_entity": "UserService.login",
  "target_entity": "db.find_user",
  "relation_type": "CALLS",
  "line_number": 15,
  "metadata": {
    "file_path": "src/auth/service.py"
  }
}
```

**关系类型**:
- `CALLS`: 函数调用
- `INHERITS`: 类继承
- `IMPORTS`: 模块导入
- `USES`: 变量使用

**幂等规则**: 基于 `(source_entity, target_entity, relation_type)` 做 upsert。

### add_chunk

**用途**: 添加代码块（用于语义检索）

```json
{
  "chunk_id": "src/auth/service.py:12:25",
  "content": "def login(self, username: str, password: str) -> bool:\n    ...",
  "content_hash": "sha256:a1b2c3d4...",
  "file_path": "src/auth/service.py",
  "start_line": 12,
  "end_line": 25,
  "embedding": [0.001, -0.023, ...],
  "metadata": {
    "language": "python",
    "chunk_type": "method",
    "name": "UserService.login"
  }
}
```

**幂等规则**: 基于 `content_hash` 做 upsert，相同内容不重复存储。

### delete_by_repo

**用途**: 删除指定仓库的所有数据（MVP 全量重建用）

```json
{
  "repo_path": "/path/to/repo"
}
```

---

## 3. 数据库 Schema (PostgreSQL)

### code_chunks 表

```sql
CREATE TABLE code_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT NOT NULL,
    chunk_type VARCHAR(50) NOT NULL,
    name TEXT,
    signature TEXT,
    start_line INT NOT NULL,
    end_line INT NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,  -- SHA256，用于去重
    language VARCHAR(20) NOT NULL,
    docstring TEXT,
    embedding vector(768),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(file_path, content_hash)
);
```

### entities 表

```sql
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    description TEXT,
    file_path TEXT NOT NULL,
    start_line INT,
    end_line INT,
    chunk_id UUID REFERENCES code_chunks(id) ON DELETE CASCADE,
    embedding vector(768),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(name, entity_type, file_path)
);
```

### relationships 表

```sql
CREATE TABLE relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    line_number INT,
    weight FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source_id, target_id, relation_type)
);
```

---

## 4. 查询 API

### search_code

**请求**:
```json
{
  "query": "用户登录验证",
  "mode": "hybrid",
  "limit": 10
}
```

**响应**:
```json
{
  "results": [
    {
      "entity": "UserService.login",
      "file_path": "src/auth/service.py",
      "line_start": 12,
      "line_end": 25,
      "score": 0.92,
      "snippet": "def login(self, username: str, password: str) -> bool:\n    ..."
    }
  ],
  "mode": "hybrid",
  "took_ms": 45
}
```

### get_callers

**请求**:
```json
{
  "entity": "db.find_user",
  "depth": 1
}
```

**响应**:
```json
{
  "entity": "db.find_user",
  "callers": [
    {
      "name": "UserService.login",
      "file_path": "src/auth/service.py",
      "line": 15
    },
    {
      "name": "AdminService.get_user",
      "file_path": "src/admin/service.py",
      "line": 42
    }
  ]
}
```

### get_callees

**请求**:
```json
{
  "entity": "UserService.login",
  "depth": 1
}
```

**响应**:
```json
{
  "entity": "UserService.login",
  "callees": [
    {
      "name": "db.find_user",
      "relation": "CALLS",
      "line": 15
    },
    {
      "name": "check_password",
      "relation": "CALLS",
      "line": 16
    }
  ]
}
```

---

## 5. 错误码

| 错误码 | 说明 |
|--------|------|
| `ENTITY_NOT_FOUND` | 实体不存在 |
| `INVALID_RELATION_TYPE` | 无效的关系类型 |
| `EMBEDDING_FAILED` | 向量化失败 |
| `DB_CONNECTION_ERROR` | 数据库连接失败 |
| `PARSE_ERROR` | 代码解析失败 |
