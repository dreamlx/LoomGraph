# DreamLinx 代码智能工具箱架构

**状态**: 📝 设计中
**日期**: 2025-02-03

---

## 愿景

构建一套协同工作的代码智能工具，充分利用 H200 算力，解决代码开发中的特定问题。

---

## 工具箱组成

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   DreamLinx Code Intelligence Toolbox                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        codeindex                                  │  │
│  │                     (基础解析层)                                   │  │
│  │                                                                   │  │
│  │  功能:                                                            │  │
│  │  - tree-sitter AST 多语言解析                                     │  │
│  │  - Symbol/Import/Call/Inheritance 提取                           │  │
│  │  - README_AI.md 生成                                              │  │
│  │  - 技术债分析                                                     │  │
│  │                                                                   │  │
│  │  仓库: ~/Projects/codeindex                        │  │
│  │  状态: v0.5.0 (本地开发)                                          │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                    │                                    │
│                                    │ import                             │
│                                    ▼                                    │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        LoomGraph                                  │  │
│  │                    (图谱检索引擎)                                  │  │
│  │                                                                   │  │
│  │  功能:                                                            │  │
│  │  - Jina Code V2 向量化                                            │  │
│  │  - LightRAG 图谱构建                                              │  │
│  │  - 混合检索 (Keyword + Semantic + Graph)                          │  │
│  │  - MCP 服务                                                       │  │
│  │                                                                   │  │
│  │  仓库: ~/Projects/LoomGraph                        │  │
│  │  状态: v0.0.1 (规划中)                                            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                    │                                    │
│                                    │ import (fork)                      │
│                                    ▼                                    │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     LightRAG (Fork)                               │  │
│  │                   (RAG 框架定制)                                   │  │
│  │                                                                   │  │
│  │  定制内容:                                                        │  │
│  │  - PostgreSQL 存储后端                                            │  │
│  │  - 代码专用 Prompt 模板                                           │  │
│  │  - 跳过 LLM 实体提取 (使用 codeindex 结果)                        │  │
│  │                                                                   │  │
│  │  仓库: https://github.com/dreamlx/LightRAG                        │  │
│  │  上游: https://github.com/HKUDS/LightRAG                          │  │
│  │  状态: Fork (待定制)                                              │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## LightRAG 作为子项目的方案

### 方案比较

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A: Git Submodule** | LightRAG 作为 LoomGraph 的 submodule | 清晰的依赖关系 | submodule 操作复杂 |
| **B: 独立仓库 + 依赖** | 保持独立，通过 git URL 依赖 | 灵活，独立演进 | 多仓库管理 |
| **C: Monorepo** | 合并到 LoomGraph 仓库 | 统一管理 | 失去上游追踪 |

### 推荐: 方案 B - 独立仓库 + 本地开发依赖

理由：
1. **保持上游追踪**: 可以定期 `git fetch upstream` 同步
2. **独立版本管理**: LightRAG 定制版可以有自己的 tag/release
3. **灵活部署**: 生产环境可用 git URL，开发环境可用 editable

---

## 本地开发环境配置

### 目录结构建议

```
~/Projects/
├── codeindex/              # 基础解析层
│   ├── src/codeindex/
│   │   ├── parser.py       # tree-sitter 解析
│   │   └── ...
│   └── pyproject.toml
│
├── LightRAG/               # RAG 框架 (Fork)
│   ├── lightrag/
│   │   ├── storage.py      # 待定制
│   │   └── ...
│   └── pyproject.toml
│
└── LoomGraph/              # 图谱检索引擎
    ├── src/loomgraph/
    │   ├── core/
    │   ├── storage/
    │   └── ...
    └── pyproject.toml
```

### LoomGraph pyproject.toml 配置

```toml
[project]
name = "loomgraph"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # 基础依赖
    "asyncpg>=0.29",
    "pgvector>=0.2",
    "httpx>=0.26",
    "pydantic>=2.0",

    # codeindex - 本地开发包
    # 生产环境改为: "codeindex>=0.5.0"
]

[tool.uv]
# 开发时使用本地路径
dev-dependencies = [
    # 本地 codeindex
    "codeindex @ file://~/Projects/codeindex",
    # 本地 LightRAG fork
    "lightrag-hku @ file://~/Projects/LightRAG",
]

[project.optional-dependencies]
# 生产环境使用 git URL
prod = [
    "codeindex @ git+https://github.com/dreamlx/codeindex",
    "lightrag-hku @ git+https://github.com/dreamlx/LightRAG@loomgraph-main",
]
```

### 开发工作流

```bash
# 1. Clone 所有项目
cd ~/Projects
git clone https://github.com/dreamlx/codeindex
git clone https://github.com/dreamlx/LightRAG
git clone https://github.com/dreamlx/LoomGraph

# 2. 设置 LightRAG 上游追踪
cd ~/Projects/LightRAG
git remote add upstream https://github.com/HKUDS/LightRAG
git checkout -b loomgraph-main
git push -u origin loomgraph-main

# 3. 创建 LoomGraph 虚拟环境
cd ~/Projects/LoomGraph
uv venv && source .venv/bin/activate

# 4. 安装本地依赖 (editable mode)
uv pip install -e ~/Projects/codeindex
uv pip install -e ~/Projects/LightRAG
uv pip install -e ".[dev]"

# 5. 验证安装
python -c "from codeindex.parser import parse_file; print('codeindex OK')"
python -c "from lightrag import LightRAG; print('LightRAG OK')"
```

---

## 跨项目开发流程

### 场景 1: 在 codeindex 中添加调用提取

```bash
# 1. 在 codeindex 中开发
cd ~/Projects/codeindex
git checkout -b feature/call-extraction

# 2. 修改 parser.py
# 添加 Call 数据类和 _extract_calls 函数

# 3. 测试
pytest tests/test_parser.py

# 4. 在 LoomGraph 中验证
cd ~/Projects/LoomGraph
python -c "
from codeindex.parser import parse_file
result = parse_file('sample.py')
print(result.calls)  # 验证新功能
"

# 5. 提交 codeindex
cd ~/Projects/codeindex
git add . && git commit -m 'feat(parser): add call extraction'
git checkout develop && git merge feature/call-extraction
```

### 场景 2: 定制 LightRAG PostgreSQL 后端

```bash
# 1. 在 LightRAG fork 中开发
cd ~/Projects/LightRAG
git checkout loomgraph-main

# 2. 添加 PostgreSQL 存储
# 新建 lightrag/kg/postgres_impl.py

# 3. 在 LoomGraph 中测试
cd ~/Projects/LoomGraph
pytest tests/integration/test_lightrag_pg.py

# 4. 提交 LightRAG
cd ~/Projects/LightRAG
git add . && git commit -m 'feat: add PostgreSQL storage backend'
git push origin loomgraph-main
```

### 场景 3: 同步 LightRAG 上游更新

```bash
cd ~/Projects/LightRAG
git fetch upstream
git checkout loomgraph-main
git merge upstream/main

# 解决冲突后
git push origin loomgraph-main

# 在 LoomGraph 中验证
cd ~/Projects/LoomGraph
pytest tests/
```

---

## 待确认

1. **同意保持三个独立仓库**？
   - codeindex (你的)
   - LightRAG (fork)
   - LoomGraph (你的)

2. **LightRAG fork 分支策略**：
   - `main`: 保持与上游同步
   - `loomgraph-main`: LoomGraph 定制版本
   - 是否需要其他分支？

3. **codeindex 是否计划发布 PyPI**？
   - 如果发布，LoomGraph 生产依赖可简化

4. **本地开发目录**：
   - 当前 codeindex: `~/Projects/codeindex`
   - 当前 LoomGraph: `~/Dropbox/Projects/NetBeansProjects/LoomGraph`
   - LightRAG fork 放哪里？建议: `~/Projects/LightRAG`
