# LoomGraph 更新策略：Hot/Warm/Cold 分层

**版本**: 0.1.0
**日期**: 2025-02-04
**状态**: ✅ 确认

---

## 核心原则

**读写分离，快慢分层**

不要试图在一个时间点解决所有问题。将更新分为：
- **Hot Update (热更新)**: 毫秒级，仅向量
- **Warm Update (温更新)**: 秒级，增量图
- **Cold Rebuild (冷重构)**: 分钟级，全量重建

---

## 1. ⚡️ 热更新 (Hot Update) - 向量层

### 触发时机
- 开发者按下 `Ctrl+S` (IDE 插件)
- `git add` 时

### 处理对象
- 仅针对 Jina Code V2 Embedding

### 操作
1. 利用 H200 极致速度，毫秒级计算当前修改文件的 Vector
2. 直接 Upsert 到向量库（Postgres/pgvector）

### 目的
保证 Semantic Search（语义搜索）立刻能搜到刚刚写的代码

### GraphRAG 动作
**不做任何操作**

此时不要动图，因为：
- 图的构建太重
- 局部小修改（如改个变量名）几乎不影响全局图拓扑

### CLI 命令 (v0.2.0+)
```bash
# 仅更新向量，不动图
loomgraph embed-only <file_path>
```

---

## 2. 🐢 温更新 (Warm Update) - 增量图层

### 触发时机
- `git merge` / `git push` 到主分支
- CI/CD 流水线触发

### 处理对象
- LightRAG 的 Entity & Relation Extraction

### 操作
1. 识别出变动文件列表
2. 调用 `lightrag.insert(new_code_chunks)`

### LightRAG 行为特征
LightRAG 是**追加式**的。如果 `utils.py` 变了，它会生成新的节点和边。

### 副作用
图数据库里会同时存在 `utils.py (旧)` 和 `utils.py (新)` 的节点。

**这没关系**，因为：
- 检索时通常会根据相关性得分过滤掉旧的
- 或者根据 `file_path` 强制过滤

### 目的
确保新的函数调用关系被记录

### CLI 命令 (v0.2.0+)
```bash
# 增量更新，仅处理变动文件
loomgraph index --mode=incremental <repo_path>
```

---

## 3. ❄️ 冷重构 (Cold Rebuild) - 全局重置

### 触发时机
- 每晚凌晨 (Nightly Build)
- 累计变动文件超过 30%
- 手动触发

### 处理对象
- 整个 LightRAG 索引目录

### 操作
```bash
# 删除旧数据
rm -rf index_dir

# 全量重新跑索引
loomgraph index --clear <repo_path>
```

### 为什么必须重构？

1. **清理垃圾**: 清除温更新产生的"孤儿节点"和"幽灵边"
2. **更新摘要**: LightRAG 最核心的功能是 Community Summary（全局摘要）
   - 如果只做增量插入，底层的摘要永远是旧的
   - 只有全量重跑，算法（如 Leiden）才能根据新的代码结构重新划分社区
   - 生成准确的"代码库架构说明书"

### CLI 命令 (MVP)
```bash
# 全量重建 (MVP 默认行为)
loomgraph index <repo_path>
```

---

## 决策矩阵

| 场景 | 代码变动量 | 操作指令 | H200 耗时预估 |
|------|-----------|---------|--------------|
| 日常 Coding | < 10 个文件 | 不做图更新，仅更 Vector | < 1秒 |
| 提交 Feature | 10 - 50 个文件 | 增量 Insert，不更新摘要 | ~30秒 - 2分钟 |
| 重构/Merge | > 50 个文件 | 触发全量重建 (后台运行) | ~10 - 20分钟 |
| 凌晨 3 点 | 定时任务 | 强制全量重建 | - |

---

## MVP 范围 vs 未来版本

| 功能 | MVP (v0.1.0) | v0.2.0+ |
|------|-------------|---------|
| Cold Rebuild | ✅ 支持 | ✅ 支持 |
| Warm Update | ❌ 不支持 | ✅ 计划 |
| Hot Update | ❌ 不支持 | ✅ 计划 |
| 自动检测变动量 | ❌ 不支持 | ✅ 计划 |
| IDE 插件集成 | ❌ 不支持 | ✅ 计划 |

---

## 实现参考

### MVP (Cold Rebuild Only)

```python
# loomgraph/core/indexer.py
import shutil

async def index_repository(repo_path: str, rag: LightRAG, clear: bool = True) -> IndexResult:
    """MVP: 全量重建策略."""

    # 1. 删除旧数据 (清空整个 working_dir)
    if clear:
        await rag.finalize_storages()
        shutil.rmtree(rag.working_dir, ignore_errors=True)
        await rag.initialize_storages()

    # 2. 扫描所有文件
    files = scan_code_files(repo_path)

    # 3. 解析 + 注入
    for file_path in files:
        result = codeindex.parse_file(file_path)
        await inject_parse_result(rag, result)

    return IndexResult(...)
```

### v0.2.0+ (Hot Update)

```python
# loomgraph/core/hot_update.py (未来实现)

async def hot_update_file(file_path: str, embedding_client: EmbeddingClient):
    """热更新: 仅更新向量."""

    # 1. 解析文件
    result = codeindex.parse_file(file_path)

    # 2. 生成向量
    texts = [s.signature for s in result.symbols]
    embeddings = await embedding_client.embed(texts)

    # 3. Upsert 到向量库 (不动图)
    await vector_store.upsert(file_path, embeddings)
```

### v0.2.0+ (Warm Update)

```python
# loomgraph/core/warm_update.py (未来实现)

async def warm_update_files(changed_files: list[str], rag: LightRAG):
    """温更新: 增量更新图.

    注意: acreate_entity() 不支持 upsert，如果 entity 已存在会抛错。
    因此需要先删除旧的，再创建新的。
    """

    for file_path in changed_files:
        # 1. 删除该文件相关的旧 entities (需要维护 file -> entities 的映射)
        old_entities = await get_entities_by_file(file_path)
        for entity_name in old_entities:
            await rag.adelete_by_entity(entity_name)  # 自动删除关联 relations

        # 2. 解析并注入新数据
        result = codeindex.parse_file(file_path)
        await inject_parse_result(rag, result)
```

> **注意**: Warm Update 需要维护 `file_path -> entity_names` 的映射关系，
> 以便知道哪些 entities 需要删除。可以利用 LightRAG 的 `source_id` 字段查询。

---

## 相关文档

- [ADR-006: MVP 简化策略](../adr/ADR-006-mvp-simplification.md) - 全量重建决策
- [LIGHTRAG_REQUIREMENTS.md](../integration/LIGHTRAG_REQUIREMENTS.md) - LightRAG API 需求
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) - CLI 命令设计
