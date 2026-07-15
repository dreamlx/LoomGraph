# EPIC-003: 增量更新策略

> **归档说明 (2026-07-15, #124)**: 本 EPIC 的核心目标 —— 完整的增量更新策略 ——
> **已达成**,迁移到 `completed/`。当前真实实现:
> - Cold Rebuild / Warm Update: `loomgraph index --clear` / `loomgraph update`(per-file warm-diff via git,路 B)
> - symbol-level 增量: content_hash diff(#91)
> - post-commit hook 自动触发: `loomgraph hooks install`(核对时已 ship)
> - MCP 写入触发的 reactive re-index: `loomgraph_refresh`(ADR-014)
>
> **下方正文保留作历史参考**。注意:正文中的 LightRAG 时代实现细节(`lightrag_client`、
> `insert_custom_kg`、11 层写入、`DELETE /graph/clear` 等)已于 v0.10-0.11 退役,
> 被 [ADR-013](../adr/ADR-013-sqlite-vec-replace-lightrag.md)(SQLite + sqlite-vec)supersede。
> 正文不再逐字维护,权威实现以 `src/loomgraph/cli/_indexing.py` + `src/loomgraph/core/graph_export_ingest.py` 为准。

**状态**: ✅ 已完成 (核心目标达成,2026-07-15 归档)
**优先级**: P1
**开始日期**: 2026-02-10
**完成日期**: 2026-07-15

---

## 背景

实现完整的增量更新策略，包括：
- **核心逻辑**: Cold Rebuild + Warm Update（✅ 已完成）
- **自动化触发**: GitHub Action + post-commit hook（🚧 进行中）
- **智能检测**: 集成 `codeindex affected` 替代 `git diff`（🚧 进行中）

## 完成状态

| Feature | 状态 | 优先级 | 说明 |
|---------|------|--------|------|
| Feature-001: Cold Rebuild | ✅ | P0 | `DELETE /graph/clear` + `insert_custom_kg` |
| Feature-002: Warm Update | ✅ | P0 | `delete_by_source` + `insert_custom_kg`（真增量） |
| Feature-003: 批量注入优化 | ✅ | P1 | 单次 `insert_custom_kg` 替代 N× HTTP，636x 提速 |
| Feature-004: GitHub Action 集成 | 🚧 | P1 | 可复用 action，push 触发 warm update |
| Feature-005: post-commit hook | 🚧 | P2 | `loomgraph hooks install` 本地自动触发 |
| Feature-006: codeindex affected 集成 | 🚧 | P2 | 替换 `git diff`，智能检测影响范围 |

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

## Feature-004: GitHub Action 集成

### 目标

用户项目 push 后，自动触发增量更新到 LightRAG 知识图谱。

### 设计方案

**架构**：LoomGraph 发布可复用 GitHub Action，用户项目一行引用

**LoomGraph 侧**（`.github/workflows/incremental-update.yml`）:
```yaml
name: Incremental Update (Reusable)

on:
  workflow_call:
    inputs:
      lightrag_endpoint:
        required: true
        type: string
      embedding_endpoint:
        required: true
        type: string
      working_directory:
        required: false
        type: string
        default: '.'

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # 需要 HEAD~1 来检测变更

      - name: Install dependencies
        run: |
          pip install ai-codeindex loomgraph

      - name: Detect changed files
        id: changes
        run: |
          codeindex affected --json --since HEAD~1 > changed.json
          echo "files=$(cat changed.json | jq -r '.affected_files[]')" >> $GITHUB_OUTPUT

      - name: Incremental update
        if: steps.changes.outputs.files != ''
        run: |
          loomgraph update --incremental \
            --lightrag-url ${{ inputs.lightrag_endpoint }} \
            --embedding-url ${{ inputs.embedding_endpoint }} \
            --files $(cat changed.json | jq -r '.affected_files[]' | tr '\n' ' ')
```

**用户项目侧**（`.github/workflows/update-knowledge-graph.yml`）:
```yaml
name: Update Knowledge Graph

on: [push]

jobs:
  update-graph:
    uses: dreamlx/LoomGraph/.github/workflows/incremental-update.yml@main
    with:
      lightrag_endpoint: ${{ secrets.LIGHTRAG_URL }}
      embedding_endpoint: ${{ secrets.EMBEDDING_URL }}
```

### 实施步骤

1. ✅ **依赖确认**: codeindex 无需改动（`affected --json` 已存在）
2. 🚧 **LoomGraph CLI**: 实现 `loomgraph update --incremental --files <list>`
3. 🚧 **GitHub Action YAML**: 编写可复用 workflow
4. 🚧 **测试**: 在 LoomGraph 自身仓库测试
5. 🚧 **文档**: 用户集成指南

### 依赖关系

- **codeindex**: `codeindex affected --json` (✅ 已有)
- **LoomGraph**: `loomgraph update --incremental` (🚧 待实现)
- **LightRAG**: `DELETE /graph/by_source` + `POST /documents/insert_custom_kg` (✅ 已有)

---

## Feature-005: post-commit hook

### 目标

本地 `git commit` 后，自动触发增量更新（可选同步/异步/禁用）。

### 设计方案

**hook 管理**：`loomgraph hooks install/uninstall/status`（参考 codeindex hooks）

**`.git/hooks/post-commit`**:
```bash
#!/bin/bash
# LoomGraph auto-update hook

MODE=$(loomgraph config get hooks.post_commit.mode)  # auto | sync | async | disabled

if [ "$MODE" == "disabled" ]; then
    exit 0
fi

# 检测变更文件
CHANGED=$(git diff-tree --no-commit-id --name-only -r HEAD | wc -l | tr -d ' ')

if [ "$CHANGED" -eq 0 ]; then
    exit 0
fi

# 触发更新
if [ "$MODE" == "sync" ]; then
    loomgraph update --incremental
elif [ "$MODE" == "async" ]; then
    nohup loomgraph update --incremental > ~/.loomgraph/hooks/post-commit.log 2>&1 &
else
    # auto: ≤3 files = sync, >3 = async
    if [ "$CHANGED" -le 3 ]; then
        loomgraph update --incremental
    else
        nohup loomgraph update --incremental > ~/.loomgraph/hooks/post-commit.log 2>&1 &
    fi
fi
```

**配置示例**（`.loomgraph.yaml`）:
```yaml
hooks:
  post_commit:
    mode: auto          # auto | sync | async | disabled
    max_files_sync: 3   # auto 模式下，≤3 files = sync
    log_file: ~/.loomgraph/hooks/post-commit.log
```

### 实施步骤

1. 🚧 **CLI 命令**: `loomgraph hooks install/uninstall/status`
2. 🚧 **Hook 模板**: `scripts/hooks/post-commit`（版本控制）
3. 🚧 **配置管理**: 读取 `.loomgraph.yaml` 中的 hooks 配置
4. 🚧 **测试**: 单元测试 + 本地手动验证
5. 🚧 **文档**: hooks 用户指南

### 与 codeindex hooks 解耦

**关键区别**：
- **codeindex hooks**: 更新 README_AI.md（文档层面）
- **loomgraph hooks**: 更新知识图谱（数据层面）
- **独立安装**: `codeindex hooks install` 和 `loomgraph hooks install` 互不影响
- **可共存**: 同一个 repo 可以同时装两个 hook（不冲突）

---

## Feature-006: codeindex affected 集成

### 目标

用 `codeindex affected --json` 替换 `git diff`，获得更智能的变更检测（包括影响分析）。

### 当前 vs 目标

| 方法 | 当前（Feature-002） | 目标（Feature-006） |
|------|-------------------|-------------------|
| 变更检测 | `git diff --name-only HEAD~1` | `codeindex affected --json --since HEAD~1` |
| 返回内容 | 文件路径列表 | 文件路径 + 影响分析（调用关系） |
| 智能度 | 低（仅文件级） | 高（符号级 + 依赖追踪） |

### 设计方案

**`loomgraph update --incremental` 流程升级**:

```python
# 当前实现（Feature-002）
changed_files = subprocess.run(
    ["git", "diff", "--name-only", "HEAD~1"],
    capture_output=True, text=True
).stdout.splitlines()

# 目标实现（Feature-006）
affected_result = subprocess.run(
    ["codeindex", "affected", "--json", "--since", "HEAD~1"],
    capture_output=True, text=True
).stdout

affected_data = json.loads(affected_result)
# {
#   "affected_files": ["src/foo.py", "src/bar.py"],
#   "affected_symbols": [
#     {"file": "src/foo.py", "symbol": "calculate", "kind": "function"},
#     {"file": "src/bar.py", "symbol": "process", "kind": "function"}
#   ],
#   "impact_analysis": {
#     "src/foo.py": ["src/baz.py", "tests/test_foo.py"]  # 谁引用了它
#   }
# }
```

**增强功能**：
- 仅删除/重注入**真正受影响**的文件（而非所有变更文件）
- 利用 `impact_analysis` 触发测试（未来扩展）
- 记录变更原因到 LightRAG（审计日志）

### 实施步骤

1. ✅ **codeindex 侧**: `affected --json` 已存在
2. 🚧 **LoomGraph 解析**: 实现 `affected_data` 结构解析
3. 🚧 **CLI 参数**: `loomgraph update --use-affected`（默认关闭，可选启用）
4. 🚧 **测试**: 对比 `git diff` vs `affected` 结果差异
5. 🚧 **文档**: 何时使用 `--use-affected` 的最佳实践

### 优先级说明

**P2（低于 Feature-004/005）原因**：
- Feature-002 的 `git diff` 方案已足够可用
- `codeindex affected` 是性能优化，非功能性需求
- 可以在 Feature-004/005 稳定后再升级

---

## 讨论附录: codeindex 侧是否需要新建 git diff 解析器

**结论**: 不需要。codeindex 零改动，全部工作在 LoomGraph 侧。

### 现有能力全景

```bash
codeindex affected --json              # 已有：返回变更文件列表 + 行数 + 影响目录
codeindex parse <file> --output json   # 已有：返回单文件完整 ParseResult
```

`incremental.py` 中的 `get_changed_files()` 已经封装了 `git diff --numstat`，返回 `FileChange` 对象（path, additions, deletions）。post-commit hook 已经在用这套逻辑自动更新 README_AI.md。

### 为什么"符号级 git diff 解析器"不值得做

| 粒度 | 做法 | 耗时 | 收益 |
|------|------|------|------|
| 文件级（推荐） | `affected --json` → 已有 | 0 | 覆盖 95% 场景 |
| 符号级 | 解析旧版+新版 → diff symbols | 几周 | 10MB 图谱规模下收益极小 |

**核心原因**: 瓶颈不在"发现变更"，而在 LightRAG 侧的 embedding + 注入。即使精确到符号级 diff，每个文件仍然需要调用 embedding API（秒级），tree-sitter 解析是毫秒级的。省掉的只是 parse 时间，但 parse 不是瓶颈。

### LoomGraph 侧实际实现

```python
# loomgraph update --incremental [--since HEAD~1]
affected = run("codeindex affected --json --since HEAD~1")

for file in affected["files"]:
    if file.exists():                              # Modified / Added
        parse_result = run(f"codeindex parse {file} --output json")
        lightrag.delete_by_source_id(file.path)    # 擦除旧图谱
        lightrag.inject(parse_result)              # 注入新数据
    else:                                          # Deleted
        lightrag.delete_by_source_id(file.path)    # 仅擦除
```

### 触发层对比

| 触发方式 | 适用场景 | 实现 |
|---------|---------|------|
| Post-commit hook | 本地开发，实时更新 | 在现有 hook 中加一行 `loomgraph update --incremental` |
| GitHub Action | CI/CD，合并到 main 后更新 | 薄壳 wrapper 调用同一个命令 |

两者共用同一个 `loomgraph update --incremental` 命令，触发方式只是 trigger 的差异。GitHub Action 作为 trigger 是合理的，但不应该把逻辑写在 Action YAML 里，而应该调用 LoomGraph CLI。

### 优先级建议

1. **LightRAG 侧**: 先实现 `DELETE /api/entities?source_id=xxx` 端点
2. **LoomGraph 侧**: 实现 `loomgraph update --incremental`，内部调用 codeindex + LightRAG
3. **触发层**: GitHub Action（几行 YAML）+ post-commit hook（一行添加）
4. **codeindex 侧**: 零改动

---

## 相关文档

- [UPDATE_STRATEGY.md](../architecture/UPDATE_STRATEGY.md) - 更新策略设计
- [CLI_DESIGN.md](../api/CLI_DESIGN.md) - CLI 规范

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2025-02-10 | 0.1 | 初始创建 |
| 2026-02-21 | 0.2 | Feature-001~003 全部完成，迁移到 insert_custom_kg |
| 2026-02-22 | 0.3 | 添加 Feature-004~006：GitHub Action + hooks + affected 集成 |
| 2026-06-03 | 0.4 | 追加讨论附录：codeindex 零改动结论（来源：inbox 笔记） |
