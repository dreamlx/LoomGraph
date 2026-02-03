# LoomGraph 项目开发规范

## 项目概述

LoomGraph 是一款基于 NVIDIA H200 的企业级代码智能理解引擎，结合 LightRAG 图谱技术与 Jina Code V2 向量化，实现千万行代码的语义检索与依赖分析。

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| Compute | NVIDIA H200 (141GB HBM3) | FP8 推理 + 批量 Embedding |
| Embedding | Jina Code V2 (8k context) | 代码语义向量化 |
| RAG Framework | LightRAG | 图谱构建与检索 |
| LLM | DeepSeek-Coder-V2 / Llama-3.1 | 实体关系提取 |
| Database | PostgreSQL + pgvector | 向量 + 图谱混合存储 |
| Protocol | MCP (Model Context Protocol) | Claude/Cursor 集成 |

## 项目结构

```
loomgraph/
├── src/loomgraph/
│   ├── core/           # 核心引擎（LightRAG 集成、配置管理）
│   ├── storage/        # 存储层（Postgres + pgvector）
│   ├── chunking/       # AST 代码切片器（Tree-sitter）
│   ├── graph/          # 图谱层（实体提取、关系映射）
│   ├── mcp/            # MCP 服务接口
│   └── cli/            # 命令行工具
├── tests/              # 测试用例（单元 + 集成）
├── docs/               # 项目文档
│   ├── architecture/   # 架构设计文档
│   ├── api/            # API 文档
│   └── adr/            # 架构决策记录
└── scripts/            # 部署与工具脚本
```

## 开发流程

### GitFlow 分支策略

```
main (生产) ← release/* ← develop ← feature/*
                                  ← bugfix/*
                                  ← hotfix/*
```

- `main`: 生产就绪版本，只接受 release 合并
- `develop`: 开发主线，功能集成点
- `feature/*`: 功能分支，如 `feature/ast-chunker`
- `release/*`: 发布预备分支
- `hotfix/*`: 生产紧急修复

### TDD 开发循环

1. **Red**: 先写失败的测试用例
2. **Green**: 写最小实现让测试通过
3. **Refactor**: 重构代码，保持测试通过

### 测试要求

- 核心模块覆盖率 ≥ 90%
- 整体覆盖率 ≥ 80%
- 每个 Feature 必须包含：
  - 单元测试 (`tests/unit/`)
  - 集成测试 (`tests/integration/`)
  - 性能基准 (`tests/benchmark/`)

## 代码规范

### Python 风格

- Python 3.11+
- 使用 `ruff` 进行 lint 和格式化
- 类型注解必须完整（mypy strict mode）
- Docstring 使用 Google 风格

### 命名约定

- 模块/文件: `snake_case.py`
- 类: `PascalCase`
- 函数/变量: `snake_case`
- 常量: `UPPER_SNAKE_CASE`
- 私有成员: `_leading_underscore`

### 提交规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

示例:
```
feat(chunking): implement Python AST parser with tree-sitter

- Add tree-sitter-python binding
- Support function and class extraction
- Preserve docstrings in chunks

Closes #12
```

## 环境配置

### 本地开发

```bash
# 创建虚拟环境
uv venv && source .venv/bin/activate

# 安装依赖
uv pip install -e ".[dev]"

# 运行测试
pytest tests/ -v --cov=src/loomgraph

# 代码检查
ruff check src/ tests/
mypy src/
```

### H200 服务器

- Jina Code V2 服务: `http://<H200_IP>:8080/embed`
- vLLM 服务: `http://<H200_IP>:8000/v1`

## 关键设计决策

### ADR-001: 选择 LightRAG 而非 Microsoft GraphRAG

- **决策**: 使用 LightRAG 作为图谱构建框架
- **原因**:
  - 构建速度快 100x（适合增量更新）
  - 内存占用低
  - 易于自定义 embedding 和 LLM 函数

### ADR-002: AST Pre-Chunking 策略

- **决策**: 在 LightRAG.insert() 之前进行 AST 解析
- **原因**:
  - LightRAG 默认按 token 切分会破坏代码逻辑完整性
  - Tree-sitter 可保证函数/类边界完整
  - Jina Code V2 需要完整代码块才能理解语义

### ADR-003: PostgreSQL 统一存储

- **决策**: 使用 PostgreSQL + pgvector 而非 Neo4j + Milvus
- **原因**:
  - 减少运维复杂度
  - pgvector 性能足够（百万级向量）
  - 事务一致性保证

## 性能目标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 索引吞吐量 | 10k files/min | 增量索引 |
| 向量检索延迟 | < 50ms | Top-100 |
| 图谱检索延迟 | < 200ms | 2-hop 查询 |
| 显存占用 | < 80GB | 留空间给 LLM |

## 常用命令

```bash
# 启动开发数据库
docker compose up -d postgres

# 运行特定测试
pytest tests/unit/test_chunking.py -v

# 生成测试覆盖报告
pytest --cov=src/loomgraph --cov-report=html

# 构建文档
mkdocs serve

# 索引代码库（开发模式）
python -m loomgraph index --path ./sample-repo --debug
```
