# LoomGraph 更新策略：Warm/Cold 分层

**版本**: 0.2.0
**日期**: 2025-02-10
**状态**: ✅ 确认

---

## 核心原则

**读写分离，快慢分层**

不要试图在一个时间点解决所有问题。将更新分为：
- ~~**Hot Update (热更新)**: 毫秒级，仅向量~~ → 已取消，合并到 Warm
- **Warm Update (温更新)**: 秒级，增量追加
- **Cold Rebuild (冷重构)**: 分钟级，全量重建

---

## 设计简化 (v0.2.0)

### 取消 Hot Update 的原因

1. **实际场景**：开发者 Ctrl+S 后很快就会 commit，间隔通常几分钟到几小时
2. **收益有限**：Hot 的"毫秒级"优势在 commit 粒度下不明显
3. **复杂度降低**：不需要 IDE 插件，不需要绕过 LightRAG 直接写向量库
4. **架构简化**：LightRAG 自动生成 embedding，无需单独管理向量层

### 统一触发时机：Git Commit

```
git commit
    ↓
post-commit hook (可选)
    ↓
loomgraph update
    ↓
增量追加变动文件
```

---

## 1. 🐢 温更新 (Warm Update) - 增量追加

### 触发时机
- **git commit** (推荐，通过 post-commit hook)
- 手动执行 `loomgraph update`

### 处理对象
- 变动文件的 Entity & Relation

### 操作
```bash
# 自动检测 git 变动并追加
loomgraph update
```

1. 获取变动文件列表：`git diff --name-only HEAD~1`
2. 调用 codeindex 解析变动文件
3. 追加到 LightRAG（不删除旧数据）

### LightRAG 行为特征
LightRAG 是**追加式**的。如果 `utils.py` 变了，它会生成新的节点和边。

### 副作用
图数据库里会同时存在 `utils.py (旧)` 和 `utils.py (新)` 的节点。

**这没关系**，因为：
- 检索时通常会根据相关性得分过滤掉旧的
- 或者根据 `file_path` + `source_id` 过滤
- Cold Rebuild 会定期清理

### 目的
确保新的函数调用关系被记录

### CLI 命令
```bash
# 增量更新，仅处理变动文件
loomgraph update

# 指定比较基准
loomgraph update --since HEAD~3
```

---

## 2. ❄️ 冷重构 (Cold Rebuild) - 全局重置

### 触发时机
- 每晚凌晨 (Nightly Build / Cron)
- 累计变动文件超过 30%
- 手动触发

### 处理对象
- 整个 LightRAG 知识图谱

### 操作
```bash
# 清空后全量重建
loomgraph index --clear <repo_path>
```

内部流程：
1. 调用 `DELETE /documents` 清空全部数据
2. 调用 `codeindex scan` 解析全部文件
3. 逐个调用 `POST /graph/entity/create` 和 `POST /graph/relation/create`

### 为什么必须重构？

1. **清理垃圾**: 清除温更新产生的"孤儿节点"和"幽灵边"
2. **更新摘要**: LightRAG 最核心的功能是 Community Summary（全局摘要）
   - 如果只做增量插入，底层的摘要永远是旧的
   - 只有全量重跑，算法（如 Leiden）才能根据新的代码结构重新划分社区
   - 生成准确的"代码库架构说明书"

### CLI 命令
```bash
# 全量重建（清空后重建）
loomgraph index --clear <repo_path>

# 全量重建（不清空，追加模式）
loomgraph index --no-clear <repo_path>
```

---

## 决策矩阵

| 场景 | 代码变动量 | 操作 | 命令 | H200 耗时预估 |
|------|-----------|------|------|--------------|
| 日常 Commit | < 10 文件 | Warm Update | `loomgraph update` | < 30秒 |
| 提交 Feature | 10 - 50 文件 | Warm Update | `loomgraph update` | ~1-2 分钟 |
| 重构/Merge | > 50 文件 | Cold Rebuild | `loomgraph index --clear` | ~10-20 分钟 |
| 凌晨定时 | 全量 | Cold Rebuild | Cron job | - |

---

## 版本支持情况

| 功能 | v0.1.0 | v0.2.0 | v0.3.0+ |
|------|--------|--------|---------|
| Cold Rebuild | ⚠️ 假实现 | ✅ 真实现 | ✅ |
| Warm Update | ❌ | ✅ | ✅ |
| ~~Hot Update~~ | ❌ | ❌ 已取消 | ❌ |
| Git Hook 集成 | ❌ | ✅ | ✅ |
| 批量注入优化 | ❌ | ❌ | ✅ (待 LightRAG 支持) |

---

## CLI 命令总览

### 当前命令 (v0.2.0)

| 命令 | 说明 | 更新类型 |
|------|------|---------|
| `loomgraph status` | 检查服务状态 | - |
| `loomgraph index <repo>` | 全量索引（追加模式） | Cold |
| `loomgraph index --clear <repo>` | 清空后全量重建 | Cold |
| `loomgraph update` | 增量追加 git 变动文件 | Warm |
| `loomgraph search <query>` | 语义搜索代码 | - |
| `loomgraph graph <entity>` | 查询调用关系 | - |

### 调试命令

| 命令 | 说明 |
|------|------|
| `loomgraph embed <json>` | 生成 embeddings（分步调试） |
| `loomgraph inject <parse> <embed>` | 注入到 LightRAG（分步调试） |

---

## 实现参考

### Cold Rebuild

```python
# loomgraph/core/indexer.py

async def cold_rebuild(repo_path: str, client: LightRAGClient) -> IndexResult:
    """Cold Rebuild: 清空后全量重建."""

    # 1. 清空全部数据
    await client.delete_all()  # DELETE /documents

    # 2. 扫描所有文件
    files = scan_code_files(repo_path)

    # 3. 解析 + 注入
    for file_path in files:
        result = parse_file(file_path)
        await inject_parse_result(client, result)

    return IndexResult(...)
```

### Warm Update

```python
# loomgraph/core/updater.py

async def warm_update(repo_path: str, client: LightRAGClient) -> UpdateResult:
    """Warm Update: 追加变动文件（不删除旧数据）."""

    # 1. 获取 git 变动文件
    changed_files = get_git_changed_files()  # git diff --name-only HEAD~1

    # 2. 解析并追加（不删旧数据）
    for file_path in changed_files:
        result = parse_file(file_path)
        await inject_parse_result(client, result)

    return UpdateResult(
        mode="warm",
        files_updated=len(changed_files),
        ...
    )
```

### Git 变动检测

```python
# loomgraph/core/git.py

import subprocess

def get_git_changed_files(since: str = "HEAD~1") -> list[str]:
    """获取 git 变动文件列表."""

    result = subprocess.run(
        ["git", "diff", "--name-only", since],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise GitError(result.stderr)

    files = result.stdout.strip().split("\n")
    return [f for f in files if f]  # 过滤空行
```

---

## LightRAG API 依赖

| API | 用途 | 状态 |
|-----|------|------|
| `POST /documents/insert_custom_kg` | 批量全层注入（主写入路径） | ✅ 已迁移 |
| `DELETE /graph/by_source` | 按 source_id 跨层删除（Warm Update） | ✅ 已使用 |
| `DELETE /graph/clear` | Cold Rebuild 清空全部 11 层 | ✅ 已使用 |
| `POST /graph/entity/create` | 创建单个实体（已弃用） | ✅ 保留兼容 |
| `POST /graph/relation/create` | 创建单个关系（已弃用） | ✅ 保留兼容 |

---

## 相关文档

- [EPIC-003: 更新策略实现](../epics/EPIC-003-update-strategy.md) - 实现计划
- [LIGHTRAG_API_REQUEST.md](../integration/LIGHTRAG_API_REQUEST.md) - LightRAG API 需求
- [ADR-006: MVP 简化策略](../adr/ADR-006-mvp-simplification.md) - 全量重建决策
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) - CLI 命令设计

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2025-02-04 | 0.1.0 | 初始设计（Hot/Warm/Cold 三层） |
| 2025-02-10 | 0.2.0 | 简化设计：取消 Hot，统一到 git commit 触发 |
