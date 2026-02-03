# ADR-004: LightRAG Fork 与定制策略

**状态**: 🔄 讨论中
**日期**: 2025-02-03
**决策者**: DreamLinx

---

## 上下文

基于 Q2 的决策，我们将**直接定制 LightRAG** 而非仅作为黑盒使用。需要确定：
1. 如何管理 LightRAG 源码
2. 如何跟踪上游更新
3. 如何组织定制代码

LightRAG 仓库: https://github.com/HKUDS/LightRAG

## 可选方案

### 方案 A: Git Submodule

```
loomgraph/
├── vendor/
│   └── lightrag/        # git submodule
├── src/loomgraph/
│   └── lightrag_ext/    # 扩展代码
└── ...
```

```bash
git submodule add https://github.com/HKUDS/LightRAG vendor/lightrag
```

**优点**:
- 清晰的上游追踪
- 可选择性更新上游版本
- 不污染主仓库历史

**缺点**:
- submodule 操作复杂（clone --recursive）
- 修改上游代码需要 fork
- CI/CD 配置更复杂

### 方案 B: Fork + Remote Tracking

```bash
# 1. Fork LightRAG 到你的 GitHub
# 2. Clone 你的 fork
git clone https://github.com/dreamlinx/LightRAG loomgraph-lightrag

# 3. 添加上游 remote
cd loomgraph-lightrag
git remote add upstream https://github.com/HKUDS/LightRAG

# 4. 在 LoomGraph 中作为依赖安装
# pyproject.toml
dependencies = [
    "lightrag @ git+https://github.com/dreamlinx/LightRAG@loomgraph-main"
]
```

**优点**:
- 可直接修改 LightRAG 源码
- 上游更新可通过 `git fetch upstream && git merge` 合并
- 清晰的版本管理

**缺点**:
- 需要维护额外仓库
- 合并上游更新可能有冲突

### 方案 C: Vendorize (复制到项目中)

```
loomgraph/
├── src/loomgraph/
│   └── _vendor/
│       └── lightrag/    # 完整复制 LightRAG 源码
└── ...
```

**优点**:
- 完全控制
- 无外部依赖
- 简单直接

**缺点**:
- 上游更新需手动合并
- 代码膨胀
- 失去版本追踪

### 方案 D: Editable Install + Patch

```bash
# 1. Clone LightRAG 到本地
git clone https://github.com/HKUDS/LightRAG ~/Projects/LightRAG-fork

# 2. Editable install
pip install -e ~/Projects/LightRAG-fork

# 3. 直接修改本地 LightRAG 代码
```

**优点**:
- 开发时最灵活
- 即时生效

**缺点**:
- 不适合生产部署
- 依赖本地路径

---

## 推荐方案

**方案 B: Fork + Remote Tracking**

理由：
1. **清晰的版本管理**: 可在 fork 中创建 `loomgraph-main` 分支，记录所有定制
2. **上游同步方便**: `git fetch upstream && git merge upstream/main`
3. **生产部署友好**: 可通过 git URL 安装

### 实施步骤

```bash
# Step 1: Fork LightRAG
# 在 GitHub 上 fork https://github.com/HKUDS/LightRAG

# Step 2: Clone 你的 fork
git clone https://github.com/dreamlinx/LightRAG ~/Projects/LightRAG-fork
cd ~/Projects/LightRAG-fork

# Step 3: 创建 LoomGraph 定制分支
git checkout -b loomgraph-main
git push -u origin loomgraph-main

# Step 4: 添加上游追踪
git remote add upstream https://github.com/HKUDS/LightRAG

# Step 5: 在 LoomGraph 中配置依赖
# pyproject.toml
[project]
dependencies = [
    "lightrag-hku @ git+https://github.com/dreamlinx/LightRAG@loomgraph-main",
]

# 或开发时用 editable
[tool.uv]
dev-dependencies = [
    "lightrag-hku @ file://~/Projects/LightRAG-fork",
]
```

### 定制计划

在 `loomgraph-main` 分支上的预期修改：

| 文件 | 修改内容 |
|------|----------|
| `lightrag/storage.py` | 添加 PostgreSQL 存储后端 |
| `lightrag/kg/postgres_impl.py` | 新文件：PostgreSQL KV 和 Graph 存储 |
| `lightrag/operate.py` | 调整实体提取 prompt（针对代码） |
| `lightrag/prompt.py` | 添加代码专用 prompt 模板 |

### 上游同步流程

```bash
# 每月检查上游更新
git fetch upstream
git checkout loomgraph-main
git merge upstream/main

# 解决冲突后
git push origin loomgraph-main
```

---

## 目录结构

最终 LoomGraph 项目结构：

```
loomgraph/
├── src/loomgraph/
│   ├── core/
│   │   ├── rag.py          # LightRAG 集成封装
│   │   ├── embedding.py    # Jina 适配器
│   │   └── llm.py          # vLLM 适配器
│   ├── storage/
│   │   ├── postgres.py     # 基础 Postgres 操作
│   │   └── lightrag_pg.py  # LightRAG PostgreSQL 后端
│   └── ...
├── pyproject.toml          # 依赖 fork 的 LightRAG
└── ...

# 另一个仓库
LightRAG-fork/              # 你的 fork
├── lightrag/
│   ├── storage.py          # 修改：添加 PostgreSQL 支持
│   ├── kg/
│   │   └── postgres_impl.py # 新增：PostgreSQL 实现
│   └── ...
└── ...
```

---

## 待确认

1. **GitHub 用户名**: 你的 GitHub 用户名是什么？（用于 fork URL）
2. **Fork 仓库名**: 保持 `LightRAG` 还是重命名为 `LightRAG-loomgraph`？
3. **是否立即 Fork**: 现在就创建 fork，还是等需要定制时再创建？

---

## 风险与缓解

| 风险 | 可能性 | 缓解措施 |
|------|--------|----------|
| 上游大版本重构导致合并困难 | 中 | 保持定制最小化，使用扩展而非修改 |
| Fork 与上游分歧过大 | 低 | 定期同步，关注上游 release notes |
| PyPI 包名冲突 | 低 | 使用 git URL 安装，不发布到 PyPI |
