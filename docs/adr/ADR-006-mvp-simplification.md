# ADR-006: MVP 简化策略 - 全量重建优先

**状态**: ✅ 已批准
**日期**: 2025-02-03
**决策者**: DreamLinx

---

## 上下文

在 GPT-5 的评审建议中，提出了以下"企业级"特性：
- `commit_sha` 版本追踪
- `active` 软删除标记
- Ghost Nodes GC 策略
- 增量更新幂等性

这些特性会增加系统复杂度。需要决定 MVP 阶段是否实现。

## 决策

**MVP 采用"全量重建"策略，不实现复杂的增量更新和 GC。**

## 理由

### 1. H200 算力充足

- 全量重建 10 万行代码预计 < 5 分钟
- 每日 nightly rebuild 完全可行
- 复杂度换取的性能提升在 MVP 阶段 ROI 低

### 2. 简化胜于过度设计

| 特性 | 复杂度 | MVP 价值 | 决策 |
|------|--------|----------|------|
| commit_sha 版本追踪 | 高 | 低 | ❌ 延后 |
| active 软删除 | 中 | 低 | ❌ 延后 |
| 增量 GC | 高 | 中 | ❌ 用全量重建替代 |
| content_hash 去重 | 低 | 高 | ✅ 保留 |

### 3. MVP 目标是验证价值

- 核心验证：AST 关系 + 向量检索能否准确回答"谁调用了 X"
- 不是验证：能否支持千人团队的增量协作

## 实施

### MVP 索引策略

```python
async def index_repository(repo_path: str) -> None:
    """MVP 索引策略：全量重建"""

    # Step 1: 清空该仓库的所有数据
    await db.delete_all_by_repo(repo_path)

    # Step 2: 扫描所有文件
    files = scan_directory(repo_path)

    # Step 3: 解析并索引
    for file in files:
        result = codeindex.parse_file(file)
        embeddings = await jina.embed(result.symbols)
        await lightrag.add_entities(result, embeddings)

    # 完成，无需 GC
```

### MVP 更新策略

```bash
# 用户修改代码后，重新运行 index
loomgraph index --path /repo

# 或设置 cron job 每日重建
0 2 * * * loomgraph index --path /repo --quiet
```

### 去重机制（保留）

```sql
-- 使用 content_hash 去重，避免重复向量化
INSERT INTO code_chunks (file_path, content_hash, ...)
ON CONFLICT (file_path, content_hash) DO UPDATE SET updated_at = NOW();
```

## 延后到 v0.2.0+ 的特性

| 特性 | 版本 | 触发条件 |
|------|------|----------|
| 增量更新（只处理变更文件） | v0.2.0 | 用户反馈全量太慢 |
| commit_sha 版本追踪 | v0.3.0 | 需要查询历史版本 |
| 软删除 + 审计日志 | v1.0.0 | 企业合规需求 |
| File Watcher 实时更新 | v0.3.0 | IDE 集成需求 |

## 后果

### 正面

- MVP 开发速度加快 50%+
- 代码简单，易于调试
- 无 Ghost Nodes 问题（每次都是干净重建）

### 负面

- 大型仓库（100 万行+）索引时间较长
- 无法保留历史版本图谱

### 缓解

- 大型仓库可分模块索引
- 历史版本需求出现时再实现

## 验收标准

MVP 索引验收：
- [ ] 能索引 10 万行代码仓库
- [ ] 全量重建时间 < 10 分钟
- [ ] 重复运行 index 不产生重复数据（content_hash 去重）
- [ ] 删除文件后重建，旧实体被清理
