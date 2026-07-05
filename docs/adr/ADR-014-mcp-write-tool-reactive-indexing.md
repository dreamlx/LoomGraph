# ADR-014: MCP 写 tool(reactive indexing)+ 存储跨进程并发硬化

**状态**: 已批准
**日期**: 2026-07-05
**决策者**: LoomGraph 架构团队
**相关 ADR**: ADR-007（code content 提取）, ADR-009（Workspace 即知识快照）, ADR-013（sqlite-vec 替换 LightRAG）

---

## 背景与问题

LoomGraph 的图谱更新在 #66/#85 之后是**单 push 模式**：

```
开发者 git commit → post-commit hook → loomgraph update（HEAD~1..HEAD warm-diff）
```

消费侧则是 **pull 模式**：AI agent 通过 MCP 的 12 个**只读** tool（`find`/`graph`/`topology`/…）查询图谱。当 agent 发现图谱 stale（刚编辑的文件不在图里、`find` 返回空、`check` 报不一致）时，**没有能力主动补** —— 只能提示用户跑 CLI。

`mcp/server.py:8-11` 原本明确写「Write tools 故意不暴露 MCP」。这是 push-only 架构的典型缺口，也是 agent-native middleware 该补的一跃。

### 并发风险（写 tool 的前置约束）

一旦 MCP 暴露写 tool，会出现跨进程并发写同一 `~/.loomgraph/{ws}.db`：

- **MCP server**：长驻 stdio 进程，agent 调 `refresh` 写
- **git hook**：`loomgraph update` 子进程，commit 后写

存储层现状（ADR-013 引入的 `SqliteGraphStore`）：`asyncio.Lock` 只串行**进程内**操作；跨进程靠 SQLite 自身。但 `journal_mode=delete`（默认 rollback journal，写阻塞读），且无显式 `busy_timeout`（Python `sqlite3.connect` 默认 `timeout=5.0` 隐式设了 5000ms，但未自文档化）。两个 writer 撞上会 `database is locked`。

---

## 决策

### 1. 打破「MCP 只读」立场，加 `loomgraph_refresh`（首个写 tool）

`refresh` 是 **reactive / pull-mode** 互补 `update`：

| | `update`（CLI + git hook） | `refresh`（MCP，新） |
|---|---|---|
| 触发 | `git commit`（push） | agent 按需（pull） |
| 数据源 | committed `HEAD~1..HEAD` | **working tree**（含未提交 + untracked） |
| 谁用 | 开发者工作流 | agent 编辑文件后立即查询 |

定位：agent 编辑文件（不 commit）后调 `refresh` → 该文件 GC 旧实体 + reinject 新实体，图谱立即可查。这正是 push-only 漏掉的场景（agent 工作在 working tree，不在 committed history）。

参数（KISS，不要 `mode` enum —— agent 不知道何时选 `full`）：
- `path`（可选）：文件/目录前缀，scope 到精确刷新目标
- `force_full`（bool，default false）：cold rebuild（= `index --clear`），仅在 incremental 调和不了 drift 时用
- 默认：per-file warm-diff over working tree

**实现位置**：异步核心 `_async_refresh` 放 `cli/_indexing.py`（`_async_update` 后），共享 import + 结构；MCP `handle` 放 `mcp/tools/refresh.py`（薄包装，镜像 `topology.py`）。`refresh` 是 MCP-only，无 CLI command。

### 2. 存储并发：WAL + busy_timeout + close checkpoint

`storage/sqlite_store.py`：
- `_open()`：`PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000`。WAL 让读在写时进行（读多写少场景关键），busy_timeout 让第二个 writer 等 5s 而非立即 `database is locked`。
- `close()`：`PRAGMA wal_checkpoint(TRUNCATE)`（best-effort）。让 customer bundle 的 `.db` 自洽 —— 无写卡在 `-wal` 边车。

**为什么不选 file lock**：WAL 给读并发 + 写串行 + 自动重试，读多写少场景严格优于 file lock，且无新依赖。file lock 还需 `fcntl`/`filelock` 新 surface。

**这是通用硬化**：所有写路径（CLI `update`/`index`/`import-export` + MCP `refresh`）受益，不只 refresh。

### 3. working-tree 数据源：`git status --porcelain`，非 `git diff HEAD`

`refresh` 默认刷 working tree。`get_working_tree_files`（`core/git.py`，与 `get_changed_files`/`get_staged_files` 同族）用 `git status --porcelain=v1 -z --no-renames`：
- `--no-renames`：rename 退化为 delete-old + new-untracked，避开 porcelain 双段 rename 解析
- 过滤 `D`（已删，无内容可 re-export）
- 含 `??`（untracked）—— **这是关键**：`git diff HEAD` 会漏 untracked 新文件，而 agent 创建新文件是核心场景

### 4. noop 短路 + staleness 不内置

- working-tree 干净 + 无 path + 非 force_full → 返回 `{"mode": "noop"}`，**跳过 codeindex export**（省 subprocess）
- `refresh` **不内置 staleness 门控**：`check` tool 查「文件是否删」，`refresh` 关心「内容是否变」，语义不同。内置会 under-trigger（文件存在但内容变 → 误判 fresh）。agent 想门控就先调 `check`。

---

## 非目标

- **codeindex path-filter**：`graph-export` 无 path 参数（whole-tree export 是 codeindex 的契约）。`refresh` 仍全量 export（ms 级，#110 实测非瓶颈），靠 `ingest_incremental` 按 `changed_files` 筛写入。
- **symbol-span content-hash diff（路 A）**：`refresh` 文件级粒度。当 codeindex emit `content_hash`（codeindex#110 实施），可升级为 hash diff，跳过未变 symbol 的 re-embed。
- **进程级 file lock**：WAL + busy_timeout 覆盖跨进程安全，无需额外锁。
- **`mode: incremental|full` enum**：用 `force_full: bool` 替代。
- **refresh 内置 staleness 判断**：用现有 `check` tool。

---

## 影响与风险

- **MCP server 依赖面**：`refresh` 调用时需 codeindex。但 query-only 部署仍可不装 codeindex（`refresh` 不调就不触发）。`server.py` docstring 已更新说明。
- **WAL 边车文件**：WAL 模式产生 `.db-wal` / `.db-shm`。graceful close 的 `wal_checkpoint(TRUNCATE)` 清空边车，正常分发不受影响。仅复制 `.db` 的客户需确保进程已正常退出（已在 customers/CHANGELOG 注明）。
- **`force_full` 误用**：agent 可能 over-trigger cold rebuild。文档明确「仅在 incremental 调和不了 drift 时用」；noop 短路 + working-tree 默认降低该风险。

---

## 验证

- `tests/unit/test_mcp_refresh.py`（11 测试）：force_full / path / working-tree / noop / 非 git fallback / envelope / 注册
- `tests/unit/test_sqlite_concurrency.py`（4 测试，PR-1）：WAL / busy_timeout / 两 writer / close checkpoint
- e2e on loomgraph-self：refresh 单文件 / untracked / noop / 并发 refresh+update
