# LightRAG API 需求：Workspace 列表端点

**请求方**: LoomGraph (EPIC-005)
**日期**: 2026-02-19

---

## 需要什么

新增一个 HTTP 端点，返回 PostgreSQL 中所有已使用的 workspace 及基本统计。

## 端点定义

```
GET /api/workspaces
```

### 响应

```json
{
  "workspaces": [
    {
      "name": "customer-backend",
      "entity_count": 245,
      "relation_count": 1024
    },
    {
      "name": "customer-gateway",
      "entity_count": 89,
      "relation_count": 312
    }
  ],
  "count": 2
}
```

如果只返回 name 列表也可以接受（统计可以由调用方自行查询）：

```json
{
  "workspaces": ["customer-backend", "customer-gateway"],
  "count": 2
}
```

## 实现参考

已有的代码基础：

- `WorkspaceManager.list_workspaces()` 已存在（`lightrag/api/workspace_manager.py`），但只返回内存中已加载的，不完整
- 所有 PG 表都有 `workspace VARCHAR(255)` 列，复合主键 `(workspace, id)`

建议的 SQL（从 `LIGHTRAG_DOC_STATUS` 查最轻量）：

```sql
SELECT DISTINCT workspace FROM LIGHTRAG_DOC_STATUS ORDER BY workspace;
```

如果需要带统计：

```sql
SELECT
    e.workspace,
    COALESCE(e.cnt, 0) AS entity_count,
    COALESCE(r.cnt, 0) AS relation_count
FROM
    (SELECT workspace, COUNT(*) AS cnt FROM LIGHTRAG_VDB_ENTITY GROUP BY workspace) e
FULL OUTER JOIN
    (SELECT workspace, COUNT(*) AS cnt FROM LIGHTRAG_VDB_RELATION GROUP BY workspace) r
    ON e.workspace = r.workspace
ORDER BY e.workspace;
```

## 路由注册位置

`lightrag/api/lightrag_server.py` — 与现有 `/graph/*` 路由同级。

这个端点**不需要** `LIGHTRAG-WORKSPACE` header（它查的是所有 workspace）。

## 优先级

LoomGraph v0.4.0 (EPIC-005 workspace management) 阻塞于此端点。不急，但越早越好。
