# 🧶 LoomGraph: Enterprise Code Intelligence Engine

**让 TB 级代码资产在 H200 算力巅峰上复活。**

LoomGraph 是一款专为企业私有化部署设计的超大规模代码智能理解与搜索引擎。它通过结合 NVIDIA H200 的极致算力与 LightRAG 图谱技术，解决大型企业在面对"超大项目、复杂依赖、技术债务"时的代码理解成本问题。

## 🚀 快速开始

### 安装

```bash
pip install loomgraph ai-codeindex
```

### 配置 H200 服务

创建 `.loomgraph.yaml`:

```yaml
lightrag:
  api_url: "http://internal.example.invalid:3001"

embedding:
  base_url: "http://internal.example.invalid:3002"
```

### 使用

```bash
# 检查服务状态
loomgraph status

# 语义搜索代码
loomgraph search "用户认证逻辑"

# 查询函数调用关系
loomgraph graph "UserService.login" --direction callers
```

## 🛠 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Compute | NVIDIA H200 | 141GB HBM3, FP8 推理 |
| Embedding | Jina Code V2 | 8k context, 代码语义 |
| RAG | LightRAG | 图谱存储与检索 |
| Parser | codeindex | Tree-sitter AST 解析 |
| Database | PostgreSQL + pgvector | LightRAG 管理 |

## 📦 架构

```
codeindex (AST 解析)  →  LoomGraph (调度)  →  LightRAG API (存储)
     CLI                    CLI/Skill              HTTP
```

- **codeindex**: 解析代码，提取 Symbol/Import 等结构
- **LoomGraph**: 数据映射，调用 LightRAG API 注入图谱
- **LightRAG**: 图谱存储、向量检索、语义查询

## 🌟 核心特性

- **Hybrid Search**: Keyword + Semantic + Graph 三路索引
- **AST-Aware Chunking**: 基于 Tree-sitter，尊重函数/类边界
- **Privacy First**: 100% 私有化部署，代码不出机房
- **AI Agent Friendly**: JSON 输出，结构化错误

## 📂 CLI 命令

| 命令 | 说明 |
|------|------|
| `loomgraph status` | 检查服务状态 |
| `loomgraph search <query>` | 语义搜索 |
| `loomgraph graph <entity>` | 查询调用关系 |
| `loomgraph index <path>` | 索引代码库 (开发中) |

## 🔧 开发

```bash
# 克隆
git clone https://github.com/dreamlx/LoomGraph.git
cd LoomGraph

# 安装
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 测试
pytest tests/ -v
```

## 📚 文档

- [系统设计](docs/architecture/SYSTEM_DESIGN.md)
- [CLI 设计](docs/api/CLI_DESIGN.md)
- [数据契约](docs/api/DATA_CONTRACT.md)

## 📄 License

Apache-2.0
