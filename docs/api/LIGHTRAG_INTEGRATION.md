# LightRAG 集成文档

**版本**: 0.5.0
**更新日期**: 2026-02-20

> 本文档合并自原 `integration/LIGHTRAG_REQUIREMENTS.md`、`integration/LIGHTRAG_API_REQUEST.md`、`api/LIGHTRAG-WORKSPACE-API-REQUEST.md`。

---

## 1. 集成概述

LoomGraph 通过 LightRAG HTTP API 完成所有存储操作，不直接操作 PostgreSQL。

```
codeindex (AST 解析) → LoomGraph (映射调度) → LightRAG API → PostgreSQL
                        ↑ 不碰 DB                ↑ 拥有 DB
```

---

## 2. 已使用的 API

| API | 用途 | 状态 |
|-----|------|------|
| `POST /graph/entity/create` | 创建实体 | ✅ 使用中 |
| `POST /graph/relation/create` | 创建关系 | ✅ 使用中 |
| `GET /graph/entities/all` | 获取所有实体 | ✅ 使用中 (EPIC-004+) |
| `GET /graph/relations/all` | 获取所有关系 | ✅ 使用中 (EPIC-004+) |
| `DELETE /documents` | Cold Rebuild 清空全部 | ✅ 使用中 |
| `POST /query` | 语义查询 | ✅ 使用中 |
| `GET /health` | 健康检查 | ✅ 使用中 |
| Header: `LIGHTRAG-WORKSPACE` | Workspace 隔离 | ✅ 使用中 (v0.2.3+) |

---

## 3. 字段映射约定

| LoomGraph 字段 | 存入位置 | 格式 |
|---------------|---------|------|
| entity_type | entity_type | 直接用 |
| signature | description | 拼接到 description |
| language | description | 拼接到 description |
| docstring | description | 拼接到 description |
| file_path | file_path | 直接用 |
| line_range | source_id | 如 `src/auth.py:12-25` |
| relation_type | keywords | 如 `CALLS`, `INHERITS` |
| embedding | 不传 | LightRAG 自动生成 |

---

## 4. 数据流示例

```
codeindex 输出 (JSON):
{
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

    ↓ LoomGraph mapper 转换

LightRAG API 调用:

  POST /graph/entity/create
  {"entity_name": "auth.login", "entity_type": "method", "description": "...", "source_id": "src/auth.py:12-25"}

  POST /graph/relation/create
  {"src_id": "auth.login", "tgt_id": "db.query_user", "keywords": "CALLS", "description": "...", "weight": 1.0}
```

---

## 5. API 增强需求

### 5.1 Workspace 列表端点 (EPIC-005)

**需求**: 返回 PostgreSQL 中所有已使用的 workspace 及基本统计。

```
GET /api/workspaces
```

**期望响应**:

```json
{
  "workspaces": [
    {"name": "customer-backend", "entity_count": 245, "relation_count": 1024}
  ],
  "count": 1
}
```

**实现建议**:

```sql
-- 轻量版：仅名称
SELECT DISTINCT workspace FROM LIGHTRAG_DOC_STATUS ORDER BY workspace;

-- 带统计版
SELECT e.workspace,
       COALESCE(e.cnt, 0) AS entity_count,
       COALESCE(r.cnt, 0) AS relation_count
FROM (SELECT workspace, COUNT(*) AS cnt FROM LIGHTRAG_VDB_ENTITY GROUP BY workspace) e
FULL OUTER JOIN
     (SELECT workspace, COUNT(*) AS cnt FROM LIGHTRAG_VDB_RELATION GROUP BY workspace) r
     ON e.workspace = r.workspace
ORDER BY e.workspace;
```

路由注册: `lightrag/api/lightrag_server.py`，与 `/graph/*` 同级。此端点**不需要** `LIGHTRAG-WORKSPACE` header。

### 5.2 批量注入端点 (P2, 非阻塞)

**需求**: 减少 HTTP 请求次数的批量注入接口。

```
POST /insert_custom_kg
```

**说明**: Python SDK 已有 `rag.ainsert_custom_kg()`，但 HTTP API 尚无对应端点。当前 LoomGraph 使用 `batch_create_graph()` 逐个创建（并发 10 连接），性能可接受。

### 5.3 已确认的 FAQ

| 问题 | 答案 |
|------|------|
| `acreate_entity()` 支持传 `embedding` 吗？ | ❌ 不支持，LightRAG 自动生成 |
| `acreate_relation()` 自定义 `relation_type`？ | ✅ 使用 `keywords` 字段 |
| 删除 entity 自动删除关联 relation？ | ✅ `adelete_by_entity()` 自动处理 |
| `insert_custom_kg` 数据进图层吗？ | ❌ 只进文档层，不出现在 `/graphs` 查询 |

---

## 6. 相关文档

- [DATA_CONTRACT.md](DATA_CONTRACT.md) — 完整数据映射规范
- [CLI_DESIGN.md](CLI_DESIGN.md) — CLI 命令设计
- [UPDATE_STRATEGY.md](../architecture/UPDATE_STRATEGY.md) — Hot/Warm/Cold 更新策略
- [SYSTEM_DESIGN.md](../architecture/SYSTEM_DESIGN.md) — 系统架构
