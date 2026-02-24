# LoomGraph: Enterprise Code Intelligence Engine

LoomGraph 是企业级代码智能理解引擎，结合 LightRAG 图谱技术与 Jina Code V2 向量化，实现大规模代码的语义检索与依赖分析。

**设计目标**: 作为 Claude Code 工具，主要用户是 AI Agent。

---

## Quick Start (Claude 执行)

> **Note**: 以下步骤由 Claude Code 读取后自动执行。

### Step 1: 安装 LoomGraph

```bash
# 在 LoomGraph 项目目录下执行
pip install .
```

这会自动安装 `ai-codeindex` 依赖。默认配置已指向企业服务，无需额外配置。

### Step 2: 验证安装

```bash
loomgraph status
```

**预期输出**: 所有服务显示 `connected: true`。

**如果失败**:
- `codeindex installed: false` → 执行 `pip install ai-codeindex`
- `lightrag connected: false` → 检查网络白名单权限

### Step 3: 索引用户代码库

```bash
# 切换到用户的项目目录
cd /path/to/user/project

# 索引整个代码库
loomgraph index .
```

### Step 4: 配置用户项目

在用户项目的 `CLAUDE.md` 中添加以下内容：

```markdown
## 代码搜索 (LoomGraph)

本项目已用 LoomGraph 索引，可使用以下命令：

- `loomgraph find "<名称>"` - 结构化实体搜索（类/函数/方法）
- `loomgraph query "<问题>"` - 语义知识问答（RAG）
- `loomgraph graph "<实体>"` - 查询调用关系
- `loomgraph topology` - 技术债务分析
- `loomgraph status` - 检查服务状态
```

详细集成指南: [docs/CLAUDE_INTEGRATION.md](docs/CLAUDE_INTEGRATION.md)

---

## CLI 命令

所有命令输出 JSON 格式，便于 AI 解析。

| 命令 | 说明 | 示例 |
|------|------|------|
| `loomgraph status` | 检查服务状态与 workspace 信息 | `loomgraph status` |
| `loomgraph index <path>` | 索引代码库（首次/全量） | `loomgraph index .` |
| `loomgraph update` | 增量更新（基于 git 变更） | `loomgraph update --since HEAD~5` |
| `loomgraph find <query>` | 结构化实体搜索（名称匹配） | `loomgraph find "UserService"` |
| `loomgraph query <question>` | 语义知识问答（RAG） | `loomgraph query "用户认证流程"` |
| `loomgraph graph <entity>` | 查询调用关系 | `loomgraph graph "UserService.login"` |
| `loomgraph topology` | 图谱拓扑债务分析 | `loomgraph topology --module cli` |
| `loomgraph check` | 索引新鲜度检查 | `loomgraph check` |

完整命令列表见 [CLI_DESIGN.md](docs/api/CLI_DESIGN.md)。

### 错误处理

命令失败时返回结构化错误，Claude 可据此自动修复：

```json
{
  "success": false,
  "error": {
    "code": "CODEINDEX_NOT_FOUND",
    "message": "codeindex command not found",
    "suggestion": "pip install ai-codeindex"
  }
}
```

---

## 架构

```
codeindex (AST 解析)  →  LoomGraph (调度)  →  LightRAG API (存储)
     CLI                    CLI                   HTTP
```

| 组件 | 职责 |
|------|------|
| **codeindex** | AST 解析，提取 Symbol/Import 等结构 |
| **LoomGraph** | 数据映射，调用 LightRAG API |
| **LightRAG** | 图谱存储、向量检索、语义查询 (云端服务) |

---

## 配置 (可选)

默认配置已内置，无需修改。如需覆盖，创建 `.loomgraph.yaml`：

```yaml
lightrag:
  api_url: "http://custom-server:3001"

embedding:
  base_url: "http://custom-server:3002"
```

---

## 开发

**推荐使用 Makefile 命令**（统一界面，更简洁）：

```bash
# 查看所有可用命令
make help

# 常用开发命令
make install        # 安装依赖
make test           # 运行测试
make lint           # 代码检查
make lint-fix       # 自动修复 lint 问题
make clean          # 清理临时文件

# 发布管理
make release VERSION=0.8.0    # 一键发布
make delivery-summary         # 生成交付总结
make token-list               # 查看客户 Token 状态
```

**直接使用脚本**（如果不想用 Makefile）：

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/ tests/
mypy src/
```

---

## 文档

| 文档 | 说明 |
|------|------|
| [CLAUDE_INTEGRATION.md](docs/CLAUDE_INTEGRATION.md) | Claude Code 集成指南 |
| [SYSTEM_DESIGN.md](docs/architecture/SYSTEM_DESIGN.md) | 系统架构设计 |
| [CLI_DESIGN.md](docs/api/CLI_DESIGN.md) | CLI 详细设计 |

---

## License

Proprietary - Enterprise Use Only
