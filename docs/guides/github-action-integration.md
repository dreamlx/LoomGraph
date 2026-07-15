# GitHub Action 集成指南

**自动增量更新知识图谱** — push 代码后自动跑 `loomgraph update`（per-file warm-diff via git）。

> **存储说明（ADR-013）**: 知识图谱是本地 SQLite 文件（`~/.loomgraph/<workspace>.db`）。
> 在 GitHub-hosted runner 上，这个文件随 runner 销毁而消失 —— 所以本 workflow 的主要价值是
> **作为 reusable 模板**：push 后跑增量更新，验证索引管线在 CI 上正常工作。要持久化图谱需用
> self-hosted runner（持久 home 目录），或在 workflow 末尾把 `.db` 作为 artifact 上传。

---

## 快速开始

### 1. 在项目中添加 workflow

在你的项目仓库创建 `.github/workflows/update-knowledge-graph.yml`:

```yaml
name: Update Knowledge Graph

on: [push]

jobs:
  update-graph:
    uses: dreamlx/LoomGraph/.github/workflows/incremental-update.yml@main
    # embedding_endpoint 可省略（见下方说明）
```

### 2. 配置 Secrets（可选）

只有需要 **vec0 语义搜索向量** 时才配 `EMBEDDING_URL`；纯结构化索引（`find`/`graph`/`topology`/`deps`/`impact`）不需要任何 secret。

在项目的 **Settings → Secrets and variables → Actions** 添加:

| Secret Name | 值 | 示例 |
|-------------|-----|------|
| `EMBEDDING_URL` | Embedding API 地址（OpenAI-compatible，可选） | `http://your-embedding-endpoint:8000/v1` |

```yaml
jobs:
  update-graph:
    uses: dreamlx/LoomGraph/.github/workflows/incremental-update.yml@main
    with:
      embedding_endpoint: ${{ secrets.EMBEDDING_URL }}
```

> **注意**：GitHub Actions runner **无法连接你本地的 Ollama**。若要让 CI 索引的 workspace 带向量，
> 必须为 `embedding_endpoint` 配一个 runner 可达的远程 OpenAI-compatible endpoint（自托管 Ollama / TEI /
> 商用 API 均可）。本地开发默认的 Ollama `nomic-embed-text`（`http://localhost:11434/v1`）在 CI 不可达。
> 不配则产出无向量的结构化索引（语义搜索不可用，其余命令正常）。

### 3. 测试

提交代码触发 workflow:

```bash
git add .
git commit -m "test: trigger knowledge graph update"
git push
```

查看 Actions 标签页确认执行成功。

---

## 参数配置

### 输入参数

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `embedding_endpoint` | ❌ | `''`（空，跳过向量） | Embedding API URL（OpenAI-compatible；空则产出无向量的结构化索引） |
| `working_directory` | ❌ | `.` | 仓库工作目录 |
| `since` | ❌ | `HEAD~1` | git diff 起始点 |

### 高级示例

```yaml
name: Update Knowledge Graph

on:
  push:
    branches: [main]  # 仅在主分支触发

jobs:
  update-graph:
    uses: dreamlx/LoomGraph/.github/workflows/incremental-update.yml@main
    with:
      embedding_endpoint: ${{ secrets.EMBEDDING_URL }}
      working_directory: './backend'  # 仅索引 backend 目录
      since: 'HEAD~3'  # 检测最近 3 次 commit 的变更
```

---

## 工作原理

```
push → GitHub Action 触发
  ↓
安装 codeindex + loomgraph
  ↓
codeindex affected --json (检测变更文件)
  ↓
loomgraph update --files src/foo.py,src/bar.py
  ↓
  ├─ per-file warm-diff: 删除变更文件旧 entity/relation
  └─ 重新 parse + embed + insert 变更文件 (content_hash diff, #91)
  ↓
知识图谱更新完成 (SQLite + sqlite-vec)
```

**关键特性**：
- **智能检测**：使用 `codeindex affected` 而非简单的 `git diff`
- **增量更新**：仅处理变更文件（不是全量重建）
- **幂等性**：多次执行相同 commit 结果一致
- **并发安全**：多分支 push 不会冲突

---

## 故障排查

### 问题 1: codeindex 命令未找到

**现象**：
```
Error: codeindex command not found
```

**原因**：workflow 中未安装 `ai-codeindex`

**解决**：检查 `pip install` 步骤是否包含 `ai-codeindex`

---

### 问题 2: 知识图谱 / Embedding 服务连接失败

**现象**：
```
Error: Connection refused to http://...
```

**原因**：
- Secret 配置错误
- 知识图谱或 embedding 服务不可达（runner 无法访问本地 Ollama）
- 网络限制

**解决**：
1. 确认 Secrets 中的 URL 正确（CI 必须用 runner 可达的远程 endpoint，不能用 `localhost:11434`）
2. 测试 embedding endpoint 连通性: `curl http://your-embedding-endpoint:8000/v1/models`
3. 检查 GitHub Actions runner 网络访问权限

---

### 问题 3: 无变更文件但仍运行

**现象**：每次 push 都更新，即使没有代码变更

**原因**：`codeindex affected` 检测到配置文件等变更

**解决**：
- 正常行为（安全策略）
- 如需优化，可在 workflow 中添加路径过滤:

```yaml
on:
  push:
    paths:
      - 'src/**'
      - '!**/*.md'
```

---

### 问题 4: 文件路径错误

**现象**：
```
Error: File not found: src/foo.py
```

**原因**：`working_directory` 配置错误或 monorepo 路径问题

**解决**：
```yaml
with:
  working_directory: './your-app'  # 确保路径正确
```

---

## 与本地 hooks 对比

| 特性 | GitHub Action | post-commit hook |
|------|---------------|-----------------|
| **触发时机** | push 到远程 | 本地 commit |
| **适用场景** | CI/CD, 团队协作 | 个人开发 |
| **执行环境** | GitHub runner | 本地机器 |
| **配置复杂度** | 低（一次配置） | 需每台机器安装 |
| **错误可见性** | Actions 日志 | 本地日志 |

**推荐**：团队项目用 GitHub Action，个人项目可结合使用。

---

## 下一步

- **Feature-005**: 本地 post-commit hook 集成 ✅ —— `loomgraph hooks install` 已 ship(EPIC-003 归档)
- **Feature-006**: `codeindex affected` 智能检测 ✅ —— workflow 内已用 `codeindex affected --json`(EPIC-003 归档)

---

**相关文档**:
- [更新策略](../architecture/UPDATE_STRATEGY.md)
- [CLI 设计规范](../api/CLI_DESIGN.md)
