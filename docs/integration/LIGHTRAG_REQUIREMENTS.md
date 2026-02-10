# LoomGraph → LightRAG 集成需求

**版本**: 0.2.0
**日期**: 2025-02-04
**状态**: ✅ 已确认

---

## 背景

LoomGraph 是代码智能引擎，负责：
1. 接收 codeindex 解析的代码结构（Symbol, Call, Inheritance）
2. 生成 Embedding 向量（可选，让 LightRAG 自动生成）
3. **注入到 LightRAG 进行存储和检索**

---

## MVP 方案 - 零改动利用现有 API ✅

**结论**: LightRAG 现有 API 完全满足 MVP 需求，双方都不需要改代码。

---

## 1. 确认的 API 用法

### 1.1 Entity 创建

```python
await rag.acreate_entity(
    entity_name="auth.login",
    entity_data={
        "entity_type": "method",
        # 拼接额外信息到 description
        "description": "def login(username, password) -> bool | Python | src/auth.py:12-25",
        "source_id": "src/auth.py:12-25",
        "file_path": "src/auth.py",
    }
)
```

### 1.2 Relation 创建

```python
await rag.acreate_relation(
    source_entity="auth.login",
    target_entity="db.query_user",
    relation_data={
        "keywords": "CALLS",              # relation_type 放这里
        "description": "login calls query_user at line 15",
        "weight": 1.0,
        "source_id": "src/auth.py:15",
    }
)
```

### 1.3 语义搜索

```python
result = await rag.aquery("用户认证相关的方法", param=QueryParam(mode="local"))
```

### 1.4 图遍历

```python
edges = await rag.chunk_entity_relation_graph.get_node_edges("auth.login")
```

### 1.5 全量重建 (删除后重建)

```python
await rag.adelete_by_entity("auth.login")  # 自动删除关联 relation
```

---

## 2. 字段映射约定 (已确认)

| LoomGraph 字段 | 存入位置 | 格式 |
|---------------|---------|------|
| entity_type | entity_type | 直接用 |
| signature | description | 拼接到 description |
| language | description | 拼接到 description |
| docstring | description | 拼接到 description |
| file_path | file_path | 直接用 |
| line_range | source_id | 如 "src/auth.py:12-25" |
| relation_type | keywords | 如 "CALLS", "INHERITS" |
| embedding | 不传 | **让 LightRAG 自动生成** |

---

## 3. 待确认问题 (已解决)

| 问题 | 答案 |
|------|------|
| `acreate_entity()` 是否支持带 `embedding` 字段？ | ❌ 不支持传入，LightRAG 自动生成（MVP 符合预期） |
| `acreate_relation()` 是否支持自定义 `relation_type`？ | ✅ 使用 `keywords` 字段 |
| 是否支持 Upsert 语义？ | ⏳ MVP 后考虑 |
| `get_node_edges()` 是否支持按 `edge_type` 过滤？ | ⏳ MVP 后考虑，应用层处理 |
| 删除 entity 时是否自动删除关联 relation？ | ✅ 是，`adelete_by_entity()` 自动处理 |

---

## 4. MVP 后可考虑的优化 (非阻塞)

| 优化项 | 场景 | 优先级 |
|-------|------|-------|
| Upsert 语义 | 增量更新代码索引 | 后续 |
| relation_type 独立字段 | 更清晰的数据模型 | 后续 |
| `get_node_edges(edge_type=)` | 大规模图遍历性能 | 后续 |

---

## 5. 集成时间线

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | LoomGraph 实现完成 (models, mapper, injector, CLI) | ✅ 已完成 |
| Phase 2 | LightRAG API 确认 | ✅ 已确认 |
| Phase 3 | codeindex v0.7.0 JSON 输出 | 🔄 进行中 |
| Phase 4 | 实际集成测试 | 🔲 待开始 |

---

## 6. 示例数据流

```
codeindex 输出 (v0.7.0 JSON):
{
  "success": true,
  "results": [
    {
      "path": "src/auth.py",
      "symbols": [
        {"name": "login", "kind": "method", "signature": "def login(...)", "line_start": 12}
      ],
      "calls": [
        {"caller": "login", "callee": "db.query_user", "line": 15}
      ]
    }
  ]
}

    ↓ LoomGraph 转换 (mapper.py)

LightRAG API 调用:

  acreate_entity("auth.login", {
    "entity_type": "method",
    "description": "def login(username, password) -> bool | Authenticate user | Python | src/auth.py:12-25",
    "source_id": "src/auth.py:12-25",
    "file_path": "src/auth.py"
  })

  acreate_relation("auth.login", "db.query_user", {
    "keywords": "CALLS",
    "description": "auth.login calls db.query_user at line 15",
    "weight": 1.0,
    "source_id": "src/auth.py:15"
  })
```

---

## 7. 相关文档

- [DATA_CONTRACT.md](../api/DATA_CONTRACT.md) - 完整数据映射规范
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) - CLI 命令设计
- [UPDATE_STRATEGY.md](../architecture/UPDATE_STRATEGY.md) - Hot/Warm/Cold 更新策略
