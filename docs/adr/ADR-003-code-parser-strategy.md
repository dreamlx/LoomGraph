# ADR-003: 代码解析器复用与整合策略

**状态**: ✅ 已批准
**日期**: 2025-02-03
**决策者**: DreamLinx

---

## 决策

采用**混合策略**，三个仓库独立管理：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   DreamLinx Code Intelligence Toolbox                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  codeindex (matrix-codeindex on PyPI)                                   │
│  ├── 功能: tree-sitter AST 解析                                         │
│  ├── 扩展: 添加 Call + Inheritance 提取                                 │
│  └── 状态: 准备发布 PyPI                                                │
│       │                                                                 │
│       │ pip install matrix-codeindex                                    │
│       ▼                                                                 │
│  LightRAG (Fork: github.com/dreamlx/LightRAG)                          │
│  ├── 分支: loomgraph-main (定制版)                                      │
│  ├── 定制: 直接摄入 codeindex 产出，跳过内置 Chunking                    │
│  └── 定制: PostgreSQL 存储后端                                          │
│       │                                                                 │
│       │ pip install git+...@loomgraph-main                              │
│       ▼                                                                 │
│  LoomGraph (主项目 - 指挥部)                                            │
│  ├── 功能: 协调 H200 资源                                               │
│  ├── 功能: Jina Code V2 向量化                                          │
│  ├── 功能: 混合检索 + MCP 服务                                          │
│  └── 状态: 私有仓库                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 关键决策点

### 1. codeindex 扩展 (由你负责 Epic)

- 添加 `Call` 数据类（调用关系提取）
- 添加 `Inheritance` 数据类（继承关系提取）
- 准备发布到 PyPI (名称: `matrix-codeindex`)

### 2. LightRAG 定制 (loomgraph-main 分支)

- **跳过内置 Chunking**: 直接接收 codeindex 的 `ParseResult`
- **跳过 LLM 实体提取**: 使用 codeindex 的 Symbol/Call/Inheritance
- **LLM 仅做语义增强**: 生成描述、识别架构模式
- **PostgreSQL 存储**: 替换默认的 JSON/LevelDB

### 3. LoomGraph 作为指挥部

- 协调 codeindex → LightRAG 数据流
- 管理 H200 资源分配 (Embedding vs LLM)
- 提供统一的 CLI 和 MCP 接口

## 本地开发路径

```
~/Projects/
├── codeindex/              # ~/Projects/codeindex
├── LightRAG/               # ~/Projects/LightRAG (fork)
└── LoomGraph/              # ~/Dropbox/.../LoomGraph
```

## 依赖关系

```toml
# LoomGraph pyproject.toml
[project]
dependencies = [
    "matrix-codeindex>=0.5.0",  # 发布后
]

[tool.uv.sources]
# 开发时使用本地路径
matrix-codeindex = { path = "~/Projects/codeindex" }
lightrag-hku = { path = "~/Projects/LightRAG" }
```
