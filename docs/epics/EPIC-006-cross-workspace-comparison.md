# EPIC-006: 跨 Workspace 对比

**状态**: 📋 规划中（需技术验证）
**优先级**: P2
**预估**: 5-8 天
**ADR**: [ADR-009](../adr/ADR-009-workspace-as-knowledge-snapshot.md)
**依赖**: EPIC-005 (workspace 管理)
**支撑**: Skill B (智能同步), Skill C (演化观察)

---

## 背景

研发熵减解决方案的 Skill B（智能同步）和 Skill C（演化观察）需要跨分支/跨项目的代码知识对比能力：

- **Skill B**: "上游修了 AuthService，下游 3 个分支的对应代码在哪？有冲突吗？"
- **Skill C**: "这段逻辑在 3 个分支都实现了，维护代价是多少？"

LightRAG workspace 是隔离的，需要 LoomGraph 在上层实现跨 workspace 对比。

## 目标

1. `loomgraph compare` — 两个 workspace 的实体/关系结构化 diff
2. `loomgraph similar` — 跨 workspace 相似实体检测

---

## 技术前置验证（开发前必须完成）

| 问题 | 验证方法 | 影响 |
|------|----------|------|
| LightRAG 能否分别查两个 workspace 的 entity 列表 | 切换 header 调 API | compare 实现方式 |
| Entity 的 `source_id` 是否包含文件路径 | 查已注入数据 | 实体匹配准确度 |
| 跨 workspace embedding 对比是否可行 | LightRAG 是否暴露 embedding 向量 | similar 实现方式 |

### 如果 LightRAG 不暴露 embedding

备选方案：
- 基于实体名称做精确/模糊匹配（Phase 1，够用）
- LoomGraph 自己调 embedding API 做向量对比（Phase 2，更准确）

---

## Feature 1: `loomgraph compare`

### 需求

```bash
# 对比两个分支
loomgraph compare --ws1 zcyl-backend:main --ws2 zcyl-backend:feature-auth

# 对比两个项目
loomgraph compare --ws1 zcyl-gateway --ws2 zcyl-backend
```

### 输出

```json
{
  "success": true,
  "data": {
    "ws1": "zcyl-backend:main",
    "ws2": "zcyl-backend:feature-auth",
    "summary": {
      "only_in_ws1": 12,
      "only_in_ws2": 8,
      "in_both": 230,
      "relations_changed": 15
    },
    "added": [
      {"name": "NewAuthHandler", "type": "CLASS", "file": "src/auth/new_handler.py"}
    ],
    "removed": [
      {"name": "OldAuthValidator", "type": "CLASS", "file": "src/auth/validator.py"}
    ],
    "changed_relations": [
      {
        "entity": "AuthService",
        "ws1_relations": 12,
        "ws2_relations": 15,
        "new_calls": ["NewAuthHandler.validate"]
      }
    ]
  }
}
```

### 实现方式

1. 分别用 ws1 和 ws2 的 header 查询 LightRAG，获取 entity 列表
2. 按 entity name 做 set diff (added/removed/shared)
3. 对 shared entities，比较 relation 差异
4. 纯本地计算，不需要 LightRAG 跨 workspace 支持

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F1-S1 | LightRAGClient 新增 `get_all_entities(workspace)` | 1d |
| F1-S2 | 实现 entity diff 逻辑 | 1.5d |
| F1-S3 | 实现 relation diff 逻辑 | 1d |
| F1-S4 | CLI `loomgraph compare` | 0.5d |
| F1-S5 | 单元测试 | 1d |

---

## Feature 2: `loomgraph similar`

### 需求

```bash
# 跨所有 workspace 查找相似实体
loomgraph similar --entity "AuthService"

# 指定范围
loomgraph similar --entity "AuthService" --workspaces "zcyl-backend:main,zcyl-backend:v2,zcyl-backend:v3"
```

### 输出

```json
{
  "success": true,
  "data": {
    "query_entity": "AuthService",
    "matches": [
      {
        "workspace": "zcyl-backend:main",
        "entity": "AuthService",
        "match_type": "exact",
        "relations": 12
      },
      {
        "workspace": "zcyl-backend:feature-auth",
        "entity": "AuthService",
        "match_type": "exact",
        "relations": 15,
        "diff_note": "3 new CALLS relations"
      },
      {
        "workspace": "zcyl-backend:v2",
        "entity": "AuthValidator",
        "match_type": "fuzzy",
        "similarity": 0.85,
        "note": "Similar name and role, possibly renamed"
      }
    ]
  }
}
```

### 实现方式（分阶段）

**Phase 1 (名称匹配)**: 精确 + 模糊名称匹配，覆盖 80% 场景
**Phase 2 (语义匹配)**: 调用 embedding API 做向量相似度，覆盖重命名场景

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F2-S1 | 跨 workspace 实体名称匹配 (exact + fuzzy) | 1d |
| F2-S2 | CLI `loomgraph similar` | 0.5d |
| F2-S3 | 单元测试 | 0.5d |
| F2-S4 | (Phase 2) Embedding 向量相似度对比 | 2d |

---

## 与 Skill 层的接口约定

### Skill B (智能同步) 调用 LoomGraph 的方式

```bash
# Step 1: 索引上游和下游到命名 workspace
loomgraph index /path/to/upstream -w zcyl-backend:main
loomgraph index /path/to/downstream -w zcyl-backend:customer-a

# Step 2: 对比
loomgraph compare --ws1 zcyl-backend:main --ws2 zcyl-backend:customer-a

# Step 3: Skill B 拿到 diff 结果，结合 git diff + LLM 生成合并建议
```

### Skill C (演化观察) 调用 LoomGraph 的方式

```bash
# Step 1: 索引多个版本
loomgraph index /path/to/repo -w zcyl-backend:v1.0   # git checkout v1.0
loomgraph index /path/to/repo -w zcyl-backend:v2.0   # git checkout v2.0
loomgraph index /path/to/repo -w zcyl-backend:v3.0   # git checkout v3.0

# Step 2: 跨版本查找相似实体
loomgraph similar --entity "PaymentService" --workspaces "zcyl-backend:v1.0,zcyl-backend:v2.0,zcyl-backend:v3.0"

# Step 3: Skill C 拿到演化数据，LLM 生成趋势分析
```

---

## 验收标准

- [ ] `loomgraph compare` 能输出两个 workspace 的实体/关系 diff
- [ ] `loomgraph similar` 能跨 workspace 查找相似实体
- [ ] 用 zcyl-backend 的 main 和 feature 分支验证对比准确性
- [ ] 单元测试覆盖 diff 和匹配逻辑
- [ ] Skill B 能基于 compare 输出生成合并建议（集成验证）

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 大项目 entity 数量大，compare 慢 | 用户体验差 | `--module` 缩小范围 |
| 实体重名但含义不同 | diff 误判 | 结合文件路径 (source_id) 做精确匹配 |
| LightRAG API 频率限制 | 查询两个 workspace 耗时翻倍 | 并发查询 |
