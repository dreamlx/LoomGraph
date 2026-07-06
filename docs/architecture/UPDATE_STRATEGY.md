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
3. **复杂度降低**：不需要 IDE 插件，不需要绕过存储层直接写向量库
4. **架构简化**：embedding 由 Ollama 在写入时一次性生成并连同实体落盘到 SQLite，无需单独管理向量层

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

> ✅ **#66 + PR-B 状态（已恢复 warm 增量）**：`loomgraph update` 走 **per-file warm-diff**（路 B）：whole-tree `codeindex graph-export` 出全部实体后，按 `git diff --since` 筛变更文件 → 对变更文件的 source-id prefix `delete_by_source`（GC 已删符号）→ 只 re-embed/re-inject 变更部分。命中 codeindex#110 点名的 re-embed 成本（parse 本身 ms 级，不是瓶颈）。
>
> **粒度**：文件级（改一行 → 该文件实体 re-embed）。symbol-span 粒度由 codeindex `content_hash`（#110 实施，门控）后续提供 —— 届时把路 B 的文件级 diff 升级为 hash diff 即可。
>
> **非 git / `--files`**：fallback 到 whole-tree upsert（`clear=False`，删除符号不 GC，需 `index --clear` 重建）。`--since` 指定 diff ref（默认 `HEAD~1`）；`--use-affected` / `--embedding-url` 保留兼容但 inert。

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
3. 按 source-id prefix 删除旧实体（GC 已删符号）后，re-embed/re-inject 新数据到 SQLite（不保留旧版本）

### SQLite + sqlite-vec 行为特征
Warm Update（路 B）是**按文件 upsert**的：对变更文件的 source-id prefix 做 `delete_by_source` 后重新写入。改写过的 `utils.py` 不会留下旧版本实体。

### 副作用
在 #66 + PR-B 的 per-file warm-diff 实现下，副作用已被 GC 控制；旧版"追加不删"的孤儿节点问题不再出现。

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
- 整个 workspace 的 SQLite 知识库（`~/.loomgraph/{workspace}.db`）

### 操作
```bash
# 清空后全量重建
loomgraph index --clear <repo_path>
```

内部流程：
1. 删除当前 workspace 的 SQLite 文件（或清空表数据）
2. 调用 `codeindex scan` 解析全部文件
3. 经 Ollama embed 后批量写入 entities / relations / embeddings 三张表

### 为什么必须重构？

1. **清理垃圾**: 清除长期 warm update 累积的残留（理论上路 B 已 GC，但跨大版本数据格式变更时仍需重建）
2. **重建一致性**: workspace 是某次索引的快照（ADR-009），全量重跑确保 entity/relation/embedding 三表自洽

### CLI 命令
```bash
# 全量重建（清空后重建）
loomgraph index --clear <repo_path>

# 全量重建（不清空，追加模式）
loomgraph index --no-clear <repo_path>
```

---

## 决策矩阵

| 场景 | 代码变动量 | 操作 | 命令 | 本地耗时预估 |
|------|-----------|------|------|------------|
| 日常 Commit | < 10 文件 | Warm Update | `loomgraph update` | < 30秒 |
| 提交 Feature | 10 - 50 文件 | Warm Update | `loomgraph update` | ~1-2 分钟 |
| 重构/Merge | > 50 文件 | Cold Rebuild | `loomgraph index --clear` | ~10-20 分钟 |
| 凌晨定时 | 全量 | Cold Rebuild | Cron job | - |

> 耗时维度现为本地 SQLite + Ollama（`gemma3:12b-it-qat` / `nomic-embed-text`），不再依赖远端 H200。

---

## 版本支持情况

| 功能 | v0.1.0 | v0.2.0 | v0.3.0+ |
|------|--------|--------|---------|
| Cold Rebuild | ⚠️ 假实现 | ✅ 真实现 | ✅ |
| Warm Update | ❌ | ✅ | ✅ |
| ~~Hot Update~~ | ❌ | ❌ 已取消 | ❌ |
| Git Hook 集成 | ❌ | ✅ | ✅ |
| 批量注入优化 | ❌ | ❌ | ✅ (SQLite 批量 upsert) |

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

---

## 实现参考

### Cold Rebuild

```python
# loomgraph/core/indexer.py

async def cold_rebuild(repo_path: str, store: SQLiteStore) -> IndexResult:
    """Cold Rebuild: 清空后全量重建."""

    # 1. 清空全部数据
    await store.clear_workspace()  # 删除当前 workspace 的 SQLite 表数据

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

async def warm_update(repo_path: str, store: SQLiteStore) -> UpdateResult:
    """Warm Update: per-file warm-diff（路 B）."""

    # 1. 获取 git 变动文件
    changed_files = get_git_changed_files()  # git diff --name-only HEAD~1

    # 2. 解析并按 source-id upsert（先 delete_by_source GC，再重新注入）
    for file_path in changed_files:
        result = parse_file(file_path)
        await store.delete_by_source(prefix=file_path)
        await inject_parse_result(store, result)

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

## 存储层依赖（SQLite + sqlite-vec）

> ADR-013 后 LoomGraph 不再依赖 LightRAG HTTP API；存储直接落在本地 `~/.loomgraph/{workspace}.db`。

| 操作 | 用途 | 状态 |
|-----|------|------|
| entities 表 upsert | 写入/更新实体（含 embedding 列） | ✅ 主写入路径 |
| relations 表 upsert | 写入 CALLS / INHERITS / IMPORTS 关系 | ✅ 主写入路径 |
| `delete_by_source(prefix)` | Warm Update 按 source-id 删除变更文件的旧实体 | ✅ 已使用（路 B） |
| workspace 整库删除 | Cold Rebuild 清空重建 | ✅ 已使用 |

---

## 相关文档

- [EPIC-003: 更新策略实现](../epics/EPIC-003-update-strategy.md) - 实现计划
- [ADR-013: SQLite + sqlite-vec 替换 LightRAG](../adr/ADR-013-sqlite-vec-replace-lightrag.md) - 存储后端决策
- [ADR-006: MVP 简化策略](../adr/ADR-006-mvp-simplification.md) - 全量重建决策
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) - CLI 命令设计

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2025-02-04 | 0.1.0 | 初始设计（Hot/Warm/Cold 三层） |
| 2025-02-10 | 0.2.0 | 简化设计：取消 Hot，统一到 git commit 触发 |
