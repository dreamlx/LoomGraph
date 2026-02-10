# 工作流分配确认

**日期**: 2025-02-03
**状态**: ✅ 确认

---

## MVP 范围定义

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MVP v0.1.0 范围                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ✅ 包含 (In Scope)                                                     │
│  ├── AST 实体提取 (Symbol)                                              │
│  ├── AST 关系提取 (Call, Inheritance, Import)                           │
│  ├── Jina Code V2 向量化                                                │
│  ├── 向量检索 + 图检索                                                  │
│  ├── CLI: index / search                                                │
│  ├── PostgreSQL 存储                                                    │
│  └── 全量重建策略 (无复杂 GC)                                           │
│                                                                         │
│  ❌ 不包含 (Out of Scope - v0.2.0+)                                     │
│  ├── LLM 语义增强 (semantic_enhancement: false)                         │
│  ├── MCP 服务接口                                                       │
│  ├── 增量更新 (File Watcher)                                            │
│  ├── commit_sha 版本追踪                                                │
│  └── 软删除 + 审计日志                                                  │
│                                                                         │
│  📋 简化决策 (ADR-006)                                                  │
│  ├── 索引策略: 全量重建 (删除旧数据 → 重新索引)                         │
│  ├── 去重机制: content_hash (避免重复向量化)                            │
│  └── GC 策略: 无需 (全量重建自动清理)                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 三仓库职责总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          工作流分配                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  codeindex (matrix-codeindex)                                     │  │
│  │  角色: 基础解析层 - AST 提取工厂                                   │  │
│  ├───────────────────────────────────────────────────────────────────┤  │
│  │  输入: 源代码文件                                                  │  │
│  │  输出: ParseResult (Symbol, Import, Call, Inheritance)            │  │
│  │                                                                   │  │
│  │  Epic: 扩展 AST 关系提取                                          │  │
│  │  ├── Feature: Call 调用关系提取                                   │  │
│  │  ├── Feature: Inheritance 继承关系提取                            │  │
│  │  └── Feature: 发布 PyPI (matrix-codeindex)                        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              │ ParseResult                              │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  LoomGraph (指挥部)                                               │  │
│  │  角色: 应用层 - 协调调度中心                                       │  │
│  ├───────────────────────────────────────────────────────────────────┤  │
│  │  职责:                                                            │  │
│  │  1. 调用 codeindex 解析代码                                       │  │
│  │  2. 调用 Jina TEI 向量化                                          │  │
│  │  3. 调用 LightRAG API 构建图谱                                    │  │
│  │  4. 管理 H200 资源分配                                            │  │
│  │  5. 提供 CLI 和 MCP 接口                                          │  │
│  │                                                                   │  │
│  │  Epic: 代码智能检索服务                                           │  │
│  │  ├── Feature: Jina Code V2 Embedding 适配器                       │  │
│  │  ├── Feature: 索引管道 (codeindex → LightRAG)                     │  │
│  │  ├── Feature: CLI 工具 (init/index/search/serve)                  │  │
│  │  └── Feature: MCP 服务接口                                        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              │ add_entity / add_chunk                   │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  LightRAG Fork (loomgraph-main)                                   │  │
│  │  角色: 核心引擎层 - RAG 框架定制                                   │  │
│  ├───────────────────────────────────────────────────────────────────┤  │
│  │  定制点:                                                          │  │
│  │  1. 跳过内置 Chunking (由 codeindex 完成)                         │  │
│  │  2. 跳过 LLM 实体提取 (由 codeindex 完成)                         │  │
│  │  3. 暴露 add_entity/add_chunk API                                 │  │
│  │  4. LLM 仅做语义增强                                              │  │
│  │  5. PostgreSQL 存储后端                                           │  │
│  │                                                                   │  │
│  │  Epic: LightRAG 代码图谱引擎定制                                  │  │
│  │  ├── Feature: AST 实体直接注入 API                                │  │
│  │  ├── Feature: 代码领域查询优化                                    │  │
│  │  └── Feature: PostgreSQL 存储后端                                 │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Feature 分配明细

| Feature | codeindex | LoomGraph | LightRAG | 说明 |
|---------|-----------|-----------|----------|------|
| AST Symbol 提取 | ✓ 已有 | | | 函数/类/方法 |
| AST Import 提取 | ✓ 已有 | | | 导入关系 |
| **AST Call 提取** | ⬜ 待做 | | | 调用关系 |
| **AST Inheritance 提取** | ⬜ 待做 | | | 继承关系 |
| Jina Embedding 适配 | | ✓ | | HTTP 客户端 |
| 索引管道编排 | | ✓ | | 数据流协调 |
| CLI 工具 | | ✓ | | 用户接口 |
| MCP 服务 | | ✓ | | Claude/Cursor |
| 直接摄入 API | | | ✓ | add_entity/add_chunk |
| 代码查询 Prompt | | | ✓ | 查询优化 |
| PostgreSQL 存储 | | | ✓ | 持久化 |

---

## 开发顺序

### Phase 0: 项目初始化 (当前)

```
并行:
├── [LoomGraph] 初始化 pyproject.toml, Git
├── [LightRAG]  创建 loomgraph-main 分支
└── [codeindex] 设计 Call/Inheritance 数据类
```

### Phase 1: 核心能力 (MVP)

```
并行:
├── [codeindex]  实现 Python Call/Inheritance 提取
├── [LightRAG]   实现 add_entity/add_chunk API
└── [LoomGraph]  实现 Jina Embedding 适配器

然后:
└── [LoomGraph]  实现索引管道 (组装以上三者)
```

### Phase 2: 查询能力

```
├── [LightRAG]   代码领域查询 Prompt 优化
└── [LoomGraph]  CLI search 命令
```

### Phase 3: 服务化

```
├── [LightRAG]   PostgreSQL 存储后端
└── [LoomGraph]  MCP 服务接口
```

---

## 接口契约

### codeindex → LoomGraph

```python
# codeindex 输出
@dataclass
class ParseResult:
    path: Path
    symbols: list[Symbol]       # 实体: 函数、类、方法
    imports: list[Import]       # 导入关系
    calls: list[Call]           # 调用关系 (新增)
    inheritances: list[Inheritance]  # 继承关系 (新增)
    module_docstring: str
    file_lines: int
```

### LoomGraph → LightRAG

```python
# LightRAG 接收 (新增 API)
class LightRAG:
    async def add_entity(
        name: str,
        entity_type: str,
        description: str,
        embedding: list[float],
        metadata: dict
    ) -> str: ...

    async def add_relationship(
        source: str,
        target: str,
        relation_type: str,
        weight: float
    ) -> str: ...

    async def add_chunk(
        content: str,
        chunk_id: str,
        embedding: list[float],
        metadata: dict
    ) -> str: ...
```

---

## 确认清单

- [x] codeindex 扩展 Call/Inheritance
- [x] codeindex 发布为 matrix-codeindex
- [x] LightRAG fork 创建 loomgraph-main 分支
- [x] LightRAG 实现 add_entity/add_chunk API
- [x] LightRAG 实现 PostgreSQL 存储
- [x] LoomGraph 实现 Jina Embedding 适配
- [x] LoomGraph 实现索引管道
- [x] LoomGraph 实现 CLI/MCP

---

## 本地路径确认

| 项目 | 路径 | Git Remote |
|------|------|------------|
| codeindex | `~/Projects/codeindex` | github.com/dreamlx/codeindex |
| LightRAG | `~/Projects/LightRAG` | github.com/dreamlx/LightRAG |
| LoomGraph | `~/Dropbox/.../LoomGraph` | github.com/dreamlx/LoomGraph |
