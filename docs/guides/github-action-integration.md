# GitHub Action 集成指南

**自动增量更新知识图谱** — push 代码后自动同步到 LightRAG

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
    with:
      lightrag_endpoint: ${{ secrets.LIGHTRAG_URL }}
      embedding_endpoint: ${{ secrets.EMBEDDING_URL }}
```

### 2. 配置 Secrets

在项目的 **Settings → Secrets and variables → Actions** 添加:

| Secret Name | 值 | 示例 |
|-------------|-----|------|
| `LIGHTRAG_URL` | LightRAG API 地址 | `http://internal.example.invalid:3020` |
| `EMBEDDING_URL` | Embedding API 地址 | `http://internal.example.invalid:3002` |

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
| `lightrag_endpoint` | ✅ | - | LightRAG API URL |
| `embedding_endpoint` | ✅ | - | Embedding API URL |
| `working_directory` | ❌ | `.` | 仓库工作目录 |
| `since` | ❌ | `HEAD~1` | git diff 起始点 |

### 高级示例

```yaml
name: Update Knowledge Graph

on:
  push:
    branches: [main, develop]  # 仅在主分支触发

jobs:
  update-graph:
    uses: dreamlx/LoomGraph/.github/workflows/incremental-update.yml@main
    with:
      lightrag_endpoint: ${{ secrets.LIGHTRAG_URL }}
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
  ├─ 删除旧数据 (delete_by_source)
  └─ 重新注入 (insert_custom_kg)
  ↓
知识图谱更新完成
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

### 问题 2: LightRAG 连接失败

**现象**：
```
Error: Connection refused to http://...
```

**原因**：
- Secret 配置错误
- LightRAG 服务不可达
- 网络限制

**解决**：
1. 确认 Secrets 中的 URL 正确
2. 测试 LightRAG API: `curl http://your-lightrag-url/health`
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

- **Feature-005**: 本地 post-commit hook 集成 (进行中)
- **Feature-006**: `codeindex affected` 智能检测 (计划中)

---

**相关文档**:
- [EPIC-003: 增量更新策略](../epics/EPIC-003-update-strategy.md)
- [LightRAG API 集成](../api/LIGHTRAG_INTEGRATION.md)
- [CLI 设计规范](../api/CLI_DESIGN.md)
