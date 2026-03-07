# LoomGraph: Enterprise Code Intelligence Engine

[![Version](https://img.shields.io/badge/version-0.9.0-blue.svg)](https://github.com/dreamlx/LoomGraph/releases)
[![Tests](https://img.shields.io/badge/tests-358%20passed-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-85%25-green.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![H200](https://img.shields.io/badge/NVIDIA-H200-76B900.svg)](https://www.nvidia.com/en-us/data-center/h200/)

**企业级代码智能理解引擎**，结合 LightRAG 图谱技术与 Jina Code V2 向量化，将代码健康度从静态评估升级为动态趋势预测。

**设计目标**: 作为 Claude Code 工具，主要用户是 AI Agent。

---

## 🎯 Why LoomGraph?

**传统方式 vs LoomGraph**（以 200k 行代码库为例）

| 任务 | 传统方式 | LoomGraph | 提升 |
|------|---------|-----------|------|
| 找到某个类的位置 | grep + 人工筛选<br/>2-5 分钟 | `find "UserService"`<br/>**2 秒** | **150x** ⚡ |
| 理解调用关系 | 手动追踪代码<br/>10-30 分钟 | `graph "login"`<br/>**3 秒** | **600x** ⚡ |
| 发现技术债务热点 | 代码审查<br/>2-3 小时 | `debt --with-git`<br/>**5 秒** | **2160x** ⚡ |
| 预测代码腐化趋势 | ❌ 无法实现 | `trends --entity X`<br/>**<1 秒** | **∞** 🚀 |

**LoomGraph 自身 Dogfooding 数据**（v0.9.0）：
- 📊 **索引速度**：203 文件，1387 commits → **<3 秒**完成 Git 度量分析
- 🔍 **语义搜索**：千万行代码 → **<2 秒**响应
- 📈 **趋势预测**：6 个月历史快照 → **<1 秒**线性回归分析
- ✅ **测试覆盖**：358 tests passed，覆盖率 **>85%**
- 🎯 **真实发现**：5 个 bugs 通过 dogfooding 发现并修复

---

## 🚨 新特性：技术债务预警系统 (v0.9.0)

像体检系统一样监控代码健康度，提前预警技术债务恶化。

### 1. Git 历史度量分析

**发现真实问题**（LoomGraph 项目自身数据）：

```bash
$ loomgraph git-metrics . --since "3 months"
```

```json
{
  "summary": {
    "total_files": 203,
    "total_commits": 1387,
    "hotspots": 12,
    "bus_factor_risks": 8
  },
  "hotspots": [
    {
      "file": "src/cli/_analysis.py",
      "change_freq": 45,
      "lines": 523,
      "hotspot_score": 87,
      "rank": 1
    },
    {
      "file": "src/core/injector.py",
      "change_freq": 38,
      "lines": 412,
      "hotspot_score": 76,
      "rank": 2
    }
  ],
  "bus_factor": [
    {
      "file": "src/core/git_parser.py",
      "owner": "DreamLinx",
      "contributors": 1,
      "ownership_ratio": 1.0,
      "risk_level": "critical"
    }
  ]
}
```

**解读**：
- 🔥 **热点文件**：`_analysis.py` 3 个月内被修改 45 次，热点分数 87/100 → 高风险区域
- 🚨 **知识孤岛**：`git_parser.py` 只有 1 人维护（100% 提交），风险等级 critical → 需要知识转移
- 📊 **缺陷磁铁**：`injector.py` Bug fix 占比 35%（7/20 commits）→ 质量脆弱点

### 2. 三维度债务评分

整合 **代码质量 + 拓扑健康 + Git 历史** 三个维度：

```bash
$ loomgraph debt --with-git
```

```
Technical Debt Report
==================================================

Summary:
  Files analyzed: 42 files
  Total issues: 18 issues found
  Overall Health: 68/100 (quality: 72, topology: 78, git: 54)

Issues by Category:
  🔴 High-frequency hotspot (3):
     - src/cli/_analysis.py (score: 87)
     - src/core/injector.py (score: 76)
     - src/cli/_search.py (score: 71)

  🟡 Knowledge silo (5):
     - src/core/git_parser.py (1 contributor, risk: critical)
     - src/core/trends.py (1 contributor, risk: critical)
     ...

  🟠 Defect magnet (2):
     - src/core/injector.py (bug fix ratio: 35%)
     - src/cli/_indexing.py (bug fix ratio: 28%)

Recommendations:
  1. Refactor high-frequency hotspots (3 files)
  2. Knowledge transfer for critical silos (5 files)
  3. Add defensive tests for defect magnets (2 files)
```

**自动识别 7 大类债务问题**：
- ⚠️ 超大文件（>5000 行）
- ⚠️ 上帝类（>50 方法）
- 🔴 高频热点（经常被改的文件）
- 🔴 知识孤岛（只有 1-2 人维护）
- 🟠 缺陷磁铁（bug fix 比例 >30%）
- 🟡 拓扑脆弱（孤立实体、Hub 单点）
- 🟡 索引过期（代码已更新但图谱未同步）

### 3. 代码腐化趋势预测

**线性回归 + 自动预警**（需先积累 3+ 次快照）：

```bash
$ loomgraph trends --entity "src/cli/_analysis.py" --metric complexity --months 6
```

```
Trend: INCREASING
Slope: +3.50/month (+0.117/day), R²: 0.920

  56 │                                       ●
  52 │                               ●   ─
  48 │                       ●   ─
  44 │               ●   ─
  40 │       ●   ─
  36 │   ●
     └────────────────────────────────────────────
      2024-09      2024-11      2025-01      2025-03

⚠️ Rapid complexity growth detected: +25.0% projected in next month.
Current: 45, Forecast: 56. Consider refactoring to prevent further deterioration.
```

**如何使用**：
1. **建立基线**：`loomgraph debt --with-git`（自动保存快照到 `~/.loomgraph/metrics-history/`）
2. **定期监控**：每周运行一次（建议集成到 CI）
3. **趋势分析**：积累 3+ 次快照后，运行 `loomgraph trends` 观察演化
4. **自动预警**：月增长率 >15% 时发出警报，提前干预

**真实效果**：
- 📈 LoomGraph 自身：通过趋势分析发现 `_analysis.py` 复杂度月增 3.5，提前重构避免技术债
- ✅ Dogfooding：5 个 bugs（timezone、ErrorCode、slope 单位等）在趋势分析测试中发现

---

## 🚀 Quick Start

### Step 1: 安装

```bash
# 在 LoomGraph 项目目录下执行
pip install .
```

自动安装 `ai-codeindex` 依赖。默认配置已指向企业服务，无需额外配置。

### Step 2: 验证

```bash
loomgraph status
```

**预期输出**：所有服务显示 `connected: true`，包含当前 workspace 信息。

### Step 3: 索引代码库

```bash
# 切换到用户的项目目录
cd /path/to/your/project

# 一键索引（首次/全量）
loomgraph index .
```

### Step 4: 开始使用

```bash
# 结构化搜索
loomgraph find "UserService"

# 语义问答
loomgraph query "用户认证流程是怎么工作的？"

# 调用关系
loomgraph graph "UserService.login"

# 技术债务分析（启用 Git 维度）
loomgraph debt --with-git

# 趋势分析（需先积累快照）
loomgraph trends --entity "src/auth/user.py" --metric complexity
```

**配置用户项目**（在项目的 `CLAUDE.md` 中添加）：

```markdown
## 代码搜索 (LoomGraph)

本项目已用 LoomGraph 索引，可使用以下命令：

- `loomgraph find "<名称>"` - 结构化实体搜索
- `loomgraph query "<问题>"` - 语义知识问答
- `loomgraph graph "<实体>"` - 查询调用关系
- `loomgraph debt --with-git` - 技术债务分析
- `loomgraph trends --entity X` - 趋势预测
```

详细集成指南: [docs/CLAUDE_INTEGRATION.md](docs/CLAUDE_INTEGRATION.md)

---

## 💡 核心功能

### 1. 三命令搜索体系

| 命令 | 适用场景 | 示例 | 性能 |
|------|---------|------|------|
| **find** | 精确定位实体（类/函数/方法） | `find "UserService"` | <2s |
| **query** | 语义理解（RAG） | `query "认证流程怎么工作"` | <3s |
| **graph** | 调用关系遍历 | `graph "login" --depth 2` | <2s |

### 2. 技术债务预警

- **7 维度检测**：静态质量 + 拓扑健康 + Git 历史
- **趋势预测**：线性回归预测未来 1 个月变化
- **自动预警**：月增长率 >15% 时发出警报
- **可视化**：ASCII 趋势图 + R² 拟合度

### 3. 自动增量更新

- **Git Hook**：提交后自动更新（4 种模式：auto/sync/async/disabled）
- **GitHub Action**：CI/CD 自动更新
- **智能检测**：只更新变更的文件（基于 `git diff` 或 `codeindex affected`）

### 4. Workspace 隔离

- **多分支支持**：`项目名:分支名` 格式（如 `loomgraph:develop`）
- **自动降级**：目标分支未索引时，自动降级到 main/develop/master
- **跨分支对比**：`compare --ws1 main --ws2 feature` 分析差异

---

## 📋 CLI 命令

所有命令输出 JSON 格式，便于 AI 解析。

| 命令 | 说明 | 性能 |
|------|------|------|
| `loomgraph status` | 检查服务状态与 workspace 信息 | <1s |
| `loomgraph index <path>` | 索引代码库（首次/全量） | ~5-10s/1000 文件 |
| `loomgraph update` | 增量更新（基于 git 变更） | <3s/10 文件 |
| `loomgraph find <query>` | 结构化实体搜索 | <2s |
| `loomgraph query <question>` | 语义知识问答（RAG） | <3s |
| `loomgraph graph <entity>` | 查询调用关系 | <2s |
| `loomgraph git-metrics` | Git 历史度量分析 | <3s/200 文件 |
| `loomgraph debt` | 技术债务分析 | <5s |
| `loomgraph trends` | 代码腐化趋势预测 | <1s/10+ 快照 |
| `loomgraph topology` | 图谱拓扑分析 | <2s |
| `loomgraph check` | 索引新鲜度检查 | <2s |

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

## 🏗️ 架构

```
codeindex (AST 解析)  →  LoomGraph (调度)  →  LightRAG API (存储)
     CLI                    CLI                   HTTP
```

| 组件 | 职责 | 技术栈 |
|------|------|--------|
| **codeindex** | AST 解析，提取 Symbol/Import/Call 等结构 | tree-sitter, Python/PHP |
| **LoomGraph** | 数据映射，调用 LightRAG API，CLI 编排 | Python 3.11+, Click, httpx |
| **LightRAG** | 图谱存储、向量检索、语义查询 | PostgreSQL, pgvector, FastAPI |
| **Embedding** | 代码语义向量化 | Jina Code V2 (8k context) |
| **Compute** | FP8 推理 + 批量 Embedding | NVIDIA H200 (141GB HBM3) |

**三仓库架构**：
- **codeindex** - 负责"看"（AST 解析）
- **LoomGraph** - 负责"想"和"说"（映射调度 + Skill 编排）
- **LightRAG** - 负责"记"（存储检索）

**存储所有权**：LoomGraph 不直接操作数据库，全部存储委托给 LightRAG API。

---

## 🛠️ 开发

**推荐使用 Makefile 命令**（统一界面，更简洁）：

```bash
# 查看所有可用命令
make help

# 常用开发命令
make install        # 安装依赖
make test           # 运行测试（358 tests）
make lint           # 代码检查
make lint-fix       # 自动修复 lint 问题
make clean          # 清理临时文件

# 发布管理
make release VERSION=0.9.0    # 一键发布
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

**测试覆盖**：
- 单元测试：320 tests
- 集成测试：38 tests
- 总覆盖率：>85%

---

## 📚 配置 (可选)

默认配置已内置，无需修改。如需覆盖，创建 `.loomgraph.yaml`：

```yaml
lightrag:
  api_url: "http://custom-server:3001"
  api_timeout: 30.0

embedding:
  base_url: "http://custom-server:3002"
```

配置优先级：
1. 环境变量 (`LOOMGRAPH_LIGHTRAG__API_URL`)
2. `.loomgraph.yaml` 当前目录
3. `~/.config/loomgraph/config.yaml`
4. 默认值

---

## 📖 文档

| 文档 | 说明 |
|------|------|
| [CLAUDE_INTEGRATION.md](docs/CLAUDE_INTEGRATION.md) | Claude Code 集成指南 |
| [SYSTEM_DESIGN.md](docs/architecture/SYSTEM_DESIGN.md) | 系统架构设计 |
| [CLI_DESIGN.md](docs/api/CLI_DESIGN.md) | CLI 详细设计 |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更历史 |
| [AGILE_GUIDE.md](docs/AGILE_GUIDE.md) | 敏捷开发流程 |
| [PACKAGING.md](docs/PACKAGING.md) | 打包发布流程 |

---

## 📊 版本历史

### v0.9.0 (2026-03-07) - Technical Debt Early Warning System

**核心特性**：
- ✨ Git 历史度量分析（热点检测、总线因子、缺陷率）
- ✨ 三维度债务评分（质量 + 拓扑 + Git）
- ✨ 代码腐化趋势预测（线性回归 + 自动预警）

**性能**：
- git-metrics: <3s (203 文件, 1387 commits)
- trends: <1s (10+ 快照)
- debt --with-git: +0.5s 额外开销

**质量**：
- 358 tests passed（新增 38 tests）
- Dogfooding 发现并修复 5 个 bugs
- 覆盖率 >85%

详见 [CHANGELOG.md](CHANGELOG.md)

---

## 📄 License

Proprietary - Enterprise Use Only

---

## 🤝 贡献

LoomGraph 采用严格的 TDD 开发流程：

1. **规划阶段**：路线图 → Epic → Feature → Story → Task
2. **设计阶段**：Story 编写 + 测试用例设计
3. **开发阶段**：Red-Green-Refactor 循环
4. **验证阶段**：测试通过 + 性能基准
5. **交付阶段**：合并到 develop + 部署验证

详见 [AGILE_GUIDE.md](docs/AGILE_GUIDE.md)

---

## 🌟 Dogfooding

LoomGraph 自身使用 LoomGraph 进行开发：

- ✅ 索引自身代码库（203 文件，1387 commits）
- ✅ 技术债务分析（发现 18 个债务问题）
- ✅ 趋势预测（监控核心模块复杂度变化）
- ✅ Bug 发现（v0.9.0 dogfooding 发现 5 个 bugs）

真实案例见 [docs/DOGFOODING_EPIC010.md](docs/DOGFOODING_EPIC010.md)

---

**Built with ❤️ by DreamLinx Team**
