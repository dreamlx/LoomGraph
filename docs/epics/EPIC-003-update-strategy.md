# EPIC-003: Hot/Warm/Cold 更新策略实现

**状态**: 📋 规划中
**优先级**: P1
**预估**: 3-5 天

---

## 背景

当前 `loomgraph index` 只支持全量索引，且 `--clear` 参数未真正实现。需要实现完整的更新策略以支持：
- **Warm Update**: git commit 后增量追加
- **Cold Rebuild**: 清空后全量重建

## 目标

1. 实现真正的 Cold Rebuild（清空 + 重建）
2. 实现 Warm Update（增量追加）
3. 提供 Git 集成用于自动触发更新

---

## 依赖关系

### LightRAG 侧（外部依赖）

| API | 状态 | 阻塞 |
|-----|------|------|
| `DELETE /documents` | ✅ 已存在 | 不阻塞 |
| `POST /insert_custom_kg` | ❌ 待实现 | 非阻塞（可先用逐个创建） |

### LoomGraph 侧（本项目）

| 组件 | 依赖 |
|------|------|
| Feature-001: Cold Rebuild | LightRAG `DELETE /documents` |
| Feature-002: Warm Update | Feature-001 + Git 集成 |
| Feature-003: 批量注入优化 | LightRAG `POST /insert_custom_kg` |

---

## Feature 分解

### Feature-001: Cold Rebuild 实现 ⭐ MVP

**目标**: `loomgraph index --clear` 真正清空后重建

**Story 列表**:
- Story-001.1: `lightrag_client.py` 添加 `delete_all()` 方法
- Story-001.2: `cli/main.py` 实现 `--clear` 真实逻辑
- Story-001.3: 添加测试用例

**验收标准**:
```bash
# 清空后重建
loomgraph index /repo --clear

# 预期输出
{
  "success": true,
  "data": {
    "cleared": true,
    "files_indexed": 42,
    "entities_created": 128
  }
}
```

---

### Feature-002: Warm Update 实现

**目标**: `loomgraph update` 增量追加变动文件

**Story 列表**:
- Story-002.1: 创建 `core/git.py` 实现 Git 变动检测
- Story-002.2: 添加 `loomgraph update` CLI 命令
- Story-002.3: 实现 post-commit hook 模板
- Story-002.4: 添加测试用例

**验收标准**:
```bash
# 自动检测 git 变动并追加
loomgraph update

# 预期输出
{
  "success": true,
  "data": {
    "mode": "warm",
    "changed_files": 3,
    "entities_created": 12,
    "relations_created": 8
  }
}
```

---

### Feature-003: 批量注入优化（后续）

**目标**: 使用 `/insert_custom_kg` 提升性能

**依赖**: LightRAG 添加 HTTP 端点

**Story 列表**:
- Story-003.1: `lightrag_client.py` 添加 `insert_custom_kg()` 方法
- Story-003.2: `injector.py` 添加批量注入模式
- Story-003.3: 性能测试对比

---

## 实现计划

### Phase 1: Cold Rebuild（2 天）

```
Day 1:
- [ ] Story-001.1: lightrag_client.delete_all()
- [ ] Story-001.2: CLI --clear 实现

Day 2:
- [ ] Story-001.3: 测试用例
- [ ] 集成测试
```

### Phase 2: Warm Update（2 天）

```
Day 3:
- [ ] Story-002.1: core/git.py
- [ ] Story-002.2: CLI update 命令

Day 4:
- [ ] Story-002.3: post-commit hook
- [ ] Story-002.4: 测试用例
```

### Phase 3: 优化（待 LightRAG 支持）

```
- [ ] Story-003.1-3: 批量注入
```

---

## 技术设计

### 更新策略总览

```
┌─────────────────────────────────────────────────────────────┐
│                     LoomGraph 更新策略                       │
├───────────┬─────────────────┬───────────────────────────────┤
│   层级    │     触发时机     │            操作               │
├───────────┼─────────────────┼───────────────────────────────┤
│   Warm    │  git commit     │ 追加变动文件（不删旧数据）     │
├───────────┼─────────────────┼───────────────────────────────┤
│   Cold    │  手动 / 凌晨    │ DELETE /documents → 全量重建  │
└───────────┴─────────────────┴───────────────────────────────┘
```

### API 调用流程

**Cold Rebuild**:
```
loomgraph index --clear /repo
    ↓
DELETE /documents (清空全部)
    ↓
codeindex scan /repo
    ↓
POST /graph/entity/create (逐个)
POST /graph/relation/create (逐个)
```

**Warm Update**:
```
loomgraph update
    ↓
git diff --name-only HEAD~1 (获取变动文件)
    ↓
codeindex scan <changed_files>
    ↓
POST /graph/entity/create (追加)
POST /graph/relation/create (追加)
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LightRAG DELETE API 不可用 | 阻塞 Cold Rebuild | 先确认 API 可用性 |
| Warm 追加产生重复实体 | 搜索结果冗余 | Cold Rebuild 定期清理 |
| 大仓库 Cold Rebuild 慢 | 用户体验差 | 后台运行 + 进度提示 |

---

## 相关文档

- [UPDATE_STRATEGY.md](../architecture/UPDATE_STRATEGY.md) - 原始设计
- [LIGHTRAG_REQUIREMENTS.md](../integration/LIGHTRAG_REQUIREMENTS.md) - API 需求
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) - CLI 规范

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2025-02-10 | 0.1 | 初始创建 |
