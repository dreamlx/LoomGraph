# EPIC-004: 双向调度器 — 项目级智能查询

**状态**: ✅ 已完成 (v0.2.5, 2026-02-19)
**优先级**: P1
**预估**: 5-8 天
**ADR**: [ADR-008](../adr/ADR-008-bidirectional-orchestrator.md)

---

## 背景

LoomGraph 注入完成后，LightRAG 里已有完整的 entity + relation 图谱。但当前只能通过 `search`/`graph` 被动查询，缺乏**主动**的项目级智能分析。

benchmark 显示 `architecture_comprehension` 分数 3/10，反馈需要：
- 模块功能推断（跨文件语义聚合）
- 跨模块依赖图（relation 按目录聚合）

这两个能力需要全局图谱支撑，属于 LoomGraph 的职责（ADR-008）。

## 目标

1. `loomgraph deps` — 模块级依赖图，纯图查询，不需 LLM
2. `loomgraph overview` — 项目模块概览，查询 + LLM 摘要

## 与 codeindex 的协作

| 改进点 | 负责方 | 说明 |
|--------|--------|------|
| 目录层级展开（树形） | codeindex | 纯结构，v0.19.0 |
| 单目录 AI 描述增强 | codeindex | AI 模式优化 |
| 跨模块依赖图 | **LoomGraph** | 本 Epic |
| 模块功能推断 | **LoomGraph** | 本 Epic |

---

## Feature 1: `loomgraph deps` — 模块依赖图

### 需求

```bash
# 显示所有顶级模块间的依赖
loomgraph deps

# 指定模块深度
loomgraph deps --depth 2

# 聚焦某个模块
loomgraph deps --module src/gateway
```

### 输出格式

```json
{
  "success": true,
  "data": {
    "modules": [
      {"path": "src/gateway", "entity_count": 45},
      {"path": "src/common", "entity_count": 20}
    ],
    "dependencies": [
      {
        "from": "src/gateway",
        "to": "src/common",
        "relation_count": 12,
        "relation_types": {"IMPORTS": 8, "CALLS": 4}
      }
    ]
  }
}
```

### 实现方式

1. 查询 LightRAG graph 获取所有 relations
2. 从 entity 的 `source_id`（文件路径）提取模块前缀
3. 按模块前缀聚合 relation 计数
4. 纯图查询，不需要 LLM

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F1-S1 | LightRAGClient 新增 `get_all_relations()` 方法 | 0.5d |
| F1-S2 | 实现模块聚合逻辑 `aggregate_by_module()` | 1d |
| F1-S3 | CLI `loomgraph deps` 命令 | 0.5d |
| F1-S4 | 单元测试 | 0.5d |

---

## Feature 2: `loomgraph overview` — 项目模块概览

### 需求

```bash
# 生成项目概览
loomgraph overview

# 指定深度（顶级 vs 二级模块）
loomgraph overview --depth 1
```

### 输出格式

```json
{
  "success": true,
  "data": {
    "project": "zcyl-backend",
    "modules": [
      {
        "path": "src/gateway",
        "entity_count": 45,
        "key_entities": ["GatewayFilter", "AuthInterceptor", "RouteConfig"],
        "summary": "API 网关层，负责请求路由、鉴权拦截和过滤器链管理",
        "depends_on": ["src/common", "src/auth"]
      }
    ]
  }
}
```

### 实现方式

1. 查询 LightRAG graph 获取所有 entities，按文件路径分组
2. 每个模块取 top entities（按关系数排序）
3. 调用 LightRAG query（LLM）为每个模块生成功能摘要
4. 合并 deps 数据

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F2-S1 | LightRAGClient 新增 `get_entities_by_prefix()` 方法 | 0.5d |
| F2-S2 | 实现模块摘要生成逻辑（调用 LightRAG query） | 1.5d |
| F2-S3 | CLI `loomgraph overview` 命令 | 0.5d |
| F2-S4 | 单元测试 + 集成测试 | 1d |

---

## 技术依赖

| 依赖 | 状态 | 阻塞 |
|------|------|------|
| LightRAG `/graphs` API（获取全量 relation） | ✅ 已有 | 不阻塞 |
| LightRAG `/graph/label/entities` API | ✅ 已有 | 不阻塞 |
| LightRAG query API（LLM 摘要） | ✅ 已有 | 不阻塞 |
| Entity 包含 `source_id`（文件路径） | ✅ 注入时已设置 | 不阻塞 |

## 验收标准

- [ ] `loomgraph deps` 能输出模块级依赖图（JSON）
- [ ] `loomgraph overview` 能输出带功能摘要的模块概览
- [ ] 用 zcyl-backend 项目验证：正确识别 gateway→common 依赖关系
- [ ] 单元测试覆盖聚合逻辑
- [ ] 集成测试覆盖 LightRAG 查询

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| LightRAG 返回的 entity 缺少文件路径信息 | deps 无法聚合 | 检查注入时 source_id 是否正确 |
| overview 的 LLM 摘要质量不稳定 | 用户体验差 | 提供 `--no-summary` 跳过 LLM |
| 大项目 relation 数量巨大 | 查询慢 | 支持 `--module` 缩小范围 |
