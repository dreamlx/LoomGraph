# LightRAG API 增强需求

**请求方**: LoomGraph
**日期**: 2025-02-10
**优先级**: P1

---

## 背景

LoomGraph 需要实现 Hot/Warm/Cold 更新策略，需要 LightRAG 提供以下 HTTP API 支持。

---

## 需求列表

### 1. ✅ 已确认可用

| API | 用途 | 状态 |
|-----|------|------|
| `DELETE /documents` | Cold Rebuild 清空全部 | ✅ 已存在 |
| `POST /graph/entity/create` | 创建实体 | ✅ 已存在 |
| `POST /graph/relation/create` | 创建关系 | ✅ 已存在 |
| `POST /query` | 语义查询 | ✅ 已存在 |
| `GET /health` | 健康检查 | ✅ 已存在 |

### 2. 🔶 希望新增（性能优化，非阻塞）

| API | 用途 | 优先级 |
|-----|------|--------|
| `POST /insert_custom_kg` | 批量注入实体+关系 | P2 |

---

## API 详情

### `POST /insert_custom_kg`（希望新增）

**用途**: 批量注入自定义知识图谱，减少 HTTP 请求次数

**当前问题**:
- Python SDK 有 `rag.ainsert_custom_kg()`
- HTTP API 没有对应端点
- LoomGraph 使用 HTTP API，无法调用

**性能对比**:

| 方式 | 10k 实体 | 网络开销 |
|------|---------|---------|
| 逐个创建 | 10k 次请求 | 高 |
| 批量注入 | 1 次请求 | 低 |

**请求格式**（参考 Python SDK）:

```json
POST /insert_custom_kg
Content-Type: application/json

{
  "custom_kg": {
    "chunks": [
      {
        "content": "代码内容...",
        "source_id": "auth.py:42"
      }
    ],
    "entities": [
      {
        "entity_name": "AuthService.login",
        "entity_type": "method",
        "description": "用户登录方法",
        "source_id": "auth.py:42"
      }
    ],
    "relationships": [
      {
        "src_id": "AuthService.login",
        "tgt_id": "hashlib.sha256",
        "description": "调用关系",
        "keywords": "CALLS",
        "weight": 1.0
      }
    ]
  }
}
```

**响应格式**:

```json
{
  "success": true,
  "data": {
    "entities_created": 42,
    "relationships_created": 28,
    "chunks_created": 10
  }
}
```

---

## 时间线

| 阶段 | LoomGraph 动作 | LightRAG 依赖 |
|------|---------------|--------------|
| Phase 1 | 实现 Cold Rebuild | `DELETE /documents` ✅ |
| Phase 2 | 实现 Warm Update | 无新依赖 |
| Phase 3 | 批量注入优化 | `POST /insert_custom_kg` 🔶 |

**说明**: Phase 1-2 不阻塞，可以先用逐个创建 API。Phase 3 等 LightRAG 支持后再优化。

---

## 联系方式

如有问题，请联系 LoomGraph 团队。
