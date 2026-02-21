# EPIC-003: 增量更新策略

**状态**: ✅ 已完成 (Feature-001 ~ 003)
**优先级**: P1
**完成日期**: 2026-02-21

---

## 背景

实现完整的更新策略：
- **Cold Rebuild**: 清空后全量重建
- **Warm Update**: git commit 后增量更新（删旧 + 注入新）
- **批量注入优化**: 迁移到 `insert_custom_kg`

## 完成状态

| Feature | 状态 | 说明 |
|---------|------|------|
| Feature-001: Cold Rebuild | ✅ | `DELETE /graph/clear` + `insert_custom_kg` |
| Feature-002: Warm Update | ✅ | `delete_by_source` + `insert_custom_kg`（真增量） |
| Feature-003: 批量注入优化 | ✅ | 单次 `insert_custom_kg` 替代 N× HTTP，636x 提速 |

### 未实现（低优先级）

- **已删除文件处理**: `git diff --diff-filter=D` → 仅 `delete_by_source` 不重注入。当前由 Cold Rebuild 覆盖。

---

## 依赖关系

### LightRAG 侧

| API | 状态 |
|-----|------|
| `DELETE /graph/clear` | ✅ 已使用（Cold Rebuild 清空全部 11 层） |
| `POST /documents/insert_custom_kg` | ✅ 已使用（全层写入：graph + vdb + kv） |
| `DELETE /graph/by_source` | ✅ 已使用（Warm Update 删除变动文件旧数据） |

### LoomGraph 侧

| 组件 | 状态 |
|------|------|
| `lightrag_client.delete_all()` | ✅ 简化为单次 `/graph/clear` |
| `lightrag_client.delete_by_source()` | ✅ 新增 |
| `lightrag_client.insert_custom_kg()` | ✅ 已有 |
| `injector.build_chunks()` | ✅ 新增（per-file 语义内容） |
| `injector.create_external_stubs()` | ✅ 新增（外部依赖 stub） |
| `cli._async_index_pipeline()` | ✅ 重写 |
| `cli._async_warm_update()` | ✅ 重写 |

---

## API 调用流程（当前实现）

**Cold Rebuild**:
```
loomgraph index --clear /repo
    ↓
DELETE /graph/clear (清空全部 11 层)
    ↓
codeindex scan /repo
    ↓
collect_kg_data() + build_chunks() + create_external_stubs()
    ↓
POST /documents/insert_custom_kg (单次，全层写入)
```

**Warm Update**:
```
loomgraph update
    ↓
git diff --name-only HEAD~1 (获取变动文件)
    ↓
codeindex parse <changed_files>
    ↓
DELETE /graph/by_source (删除变动文件旧数据)
    ↓
collect_kg_data() + build_chunks() + create_external_stubs()
    ↓
POST /documents/insert_custom_kg (单次，全层写入)
```

---

## 相关文档

- [UPDATE_STRATEGY.md](../architecture/UPDATE_STRATEGY.md) - 更新策略设计
- [LIGHTRAG_INTEGRATION.md](../api/LIGHTRAG_INTEGRATION.md) - LightRAG API 集成
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) - CLI 规范

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2025-02-10 | 0.1 | 初始创建 |
| 2026-02-21 | 0.2 | Feature-001~003 全部完成，迁移到 insert_custom_kg |
