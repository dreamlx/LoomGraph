# EPIC-005: Workspace 管理

**状态**: ✅ 已完成
**优先级**: P1
**预估**: 2-3 天
**ADR**: [ADR-009](../../adr/ADR-009-workspace-as-knowledge-snapshot.md)
**依赖**: 无（可与 EPIC-004 并行）

---

## 背景

客户有多个项目索引到不同 workspace，但无法查看有哪些 workspace、每个 workspace 的状态、或清理不再需要的 workspace。

## 目标

1. `loomgraph workspace list` — 列出所有 workspace + 基本统计
2. `loomgraph workspace info` — 当前/指定 workspace 的详细信息
3. `loomgraph workspace delete` — 删除指定 workspace
4. 文档：workspace 命名约定

---

## Feature 1: `loomgraph workspace list`

### 需求

```bash
loomgraph workspace list
```

### 输出

```json
{
  "success": true,
  "data": {
    "workspaces": [
      {"name": "[customer]-backend", "entities": 245, "relations": 1024},
      {"name": "[customer]-gateway", "entities": 89, "relations": 312},
      {"name": "[customer]-all", "entities": 380, "relations": 1520}
    ],
    "count": 3
  }
}
```

### 实现

1. 调用 LightRAG API 获取 workspace 列表
2. 需要调研：LightRAG 是否提供 workspace 列表 API
3. 备选方案：扫描 LightRAG 的 PostgreSQL 表获取 distinct workspace

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| S1 | 调研 LightRAG workspace 列表 API | 0.5d |
| S2 | LightRAGClient 新增 `list_workspaces()` | 0.5d |
| S3 | CLI `loomgraph workspace list` | 0.5d |

---

## Feature 2: `loomgraph workspace info`

### 需求

```bash
loomgraph workspace info                  # 当前 workspace (auto-detect)
loomgraph workspace info [customer]-backend     # 指定 workspace
```

### 输出

```json
{
  "success": true,
  "data": {
    "name": "[customer]-backend",
    "entities": 245,
    "relations": 1024,
    "entity_types": {"CLASS": 45, "FUNCTION": 120, "METHOD": 80},
    "relation_types": {"CALLS": 600, "IMPORTS": 300, "INHERITS": 124}
  }
}
```

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| S4 | LightRAGClient 新增 `get_workspace_info()` | 0.5d |
| S5 | CLI `loomgraph workspace info` | 0.5d |

---

## Feature 3: `loomgraph workspace delete`

### 需求

```bash
loomgraph workspace delete [customer]-backend:old-branch
```

### 实现

复用已有的 `client.delete_all()`，指定 workspace header。

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| S6 | CLI `loomgraph workspace delete`（含确认提示） | 0.5d |

---

## Feature 4: Workspace 命名约定文档

更新 SKILL.md 和客户 README，加入 workspace 使用指南：

```
{project}              默认（目录名，日常使用）
{project}:{branch}     分支快照（对比分析时）
{project}:{tag}        版本快照
{project}-all          多仓库联合
```

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| S7 | 文档更新 (SKILL.md + README.template.md) | 0.5d |

---

## 技术前置验证

| 问题 | 阻塞 | 验证方式 |
|------|------|----------|
| LightRAG 有 workspace 列表 API 吗？ | Feature 1 | 查 LightRAG 文档/源码 |
| LightRAG delete_all 是否按 workspace 隔离？ | Feature 3 | 已验证 ✅ |

## 验收标准

- [x] `loomgraph workspace list` 返回所有 workspace 及统计
- [x] `loomgraph workspace info` 返回指定 workspace 详情
- [x] `loomgraph workspace delete` 能清理指定 workspace
- [ ] 客户文档包含 workspace 命名约定
- [x] 单元测试覆盖 (18 new tests: 4 client + 14 CLI)
