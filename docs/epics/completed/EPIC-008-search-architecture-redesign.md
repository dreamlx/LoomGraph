# EPIC-008: 搜索体系重构 — find / query / graph 三分

**状态**: ✅ 已完成
**优先级**: P1
**版本**: v0.7.0
**ADR**: [ADR-010](../../adr/ADR-010-search-architecture-redesign.md)
**前置依赖**:
- v0.6.1 `insert_custom_kg` 已写入全层（graph + vdb + chunks）✅
- LightRAG `/query` endpoint 可用 ✅

---

## 背景

### 问题

LoomGraph v0.6.1 的搜索体系存在架构错位：

1. **`search` 命令和 Claude Code 原生能力重叠**：下载全量实体 + 客户端 SequenceMatcher 模糊匹配，本质等同于 Grep
2. **chunks 写了但没人查**：`build_chunks()` 将 docstring + signatures 注入 LightRAG 文档层，但无 CLI 命令检索
3. **`client.query()` 已存在但未暴露**：LightRAG RAG 引擎支持 local/global/hybrid/naive 模式，仅在 `impact` 和 `overview` 内部使用

### 用户画像

LoomGraph 面向企业用户，绑定 H200 算力。典型使用场景：

```
工程师 → 启动 Claude Code → 通过 LoomGraph Skill 进行代码分析
```

**关键前提**：企业用户不一定安装了 Serena MCP，Claude Code 的原生符号导航能力有限（仅 Glob + Grep + Read）。

### 能力矩阵分析

| 需求 | Claude Code 原生 | LoomGraph 当前 | LoomGraph 应提供 |
|------|-----------------|---------------|-----------------|
| 按名找符号 | Grep（无结构，噪音大） | `search`（有类型，但和 Grep 重叠） | `find`（结构化，可带关系） |
| 语义问答 | ❌ 不可能 | ❌ 未暴露 | `query`（RAG 引擎，真正差异化） |
| 精确关系遍历 | ❌ 不跨文件 | `graph` ✅ | `graph`（保持） |
| 模块依赖 | ❌ | `deps` ✅ | 保持 |
| 变更影响 | ❌ | `impact` ✅ | 保持 |

---

## 设计：三命令分工

```
┌─────────────────────────────────────────────────────────┐
│                    查询命令矩阵                          │
├──────────┬──────────────────┬──────────────────────────┤
│  find    │  结构化实体发现    │  "名字的一部分 → 找实体" │
│          │  无 LLM，快速      │  可选 --with-relations   │
├──────────┼──────────────────┼──────────────────────────┤
│  query   │  语义知识问答      │  "一个问题 → 知识图谱答" │
│          │  LLM 驱动，深度    │  local/global/hybrid     │
├──────────┼──────────────────┼──────────────────────────┤
│  graph   │  精确关系遍历      │  "确切名字 → 调用链"     │
│          │  无 LLM，精确      │  callers/callees/both    │
└──────────┴──────────────────┴──────────────────────────┘
```

### 对 Skill 的价值

| Skill 步骤 | 旧方式 | 新方式 |
|-----------|--------|--------|
| "找支付相关模块" | `search "pay"` → 逐个 `graph` (N+1 次) | `find "pay" --with-relations` (1 次) |
| "认证流程怎么工作的？" | 无法完成，需人工 Grep + 读文件 | `query "How does authentication work?"` |
| "AuthService 调用了谁？" | `graph "AuthService"` | `graph "AuthService"`（不变） |

---

## Feature 1: `find` — 结构化实体发现

### 命令接口

```bash
# 基础用法：按名匹配实体
loomgraph find "AuthService"

# 类型过滤
loomgraph find "auth" --type class

# 带关系上下文（一次到位，BFS depth=1）
loomgraph find "auth" --with-relations

# 扩展到 2 层关系（BFS depth=2）
loomgraph find "auth" --with-relations --depth 2

# 限制结果数
loomgraph find "service" --limit 10

# 指定 workspace
loomgraph find "auth" -w my-project
```

### 输出格式

**基础模式**：
```json
{
  "status": "success",
  "data": {
    "query": "auth",
    "total_entities": 1250,
    "matches_count": 3,
    "matches": [
      {
        "entity": "AuthService",
        "type": "class",
        "source_id": "src/auth/service.py",
        "description": "Python class | src/auth/service.py",
        "score": 0.95
      }
    ]
  }
}
```

**`--with-relations` 模式**：
```json
{
  "status": "success",
  "data": {
    "query": "auth",
    "matches_count": 2,
    "matches": [
      {
        "entity": "AuthService",
        "type": "class",
        "source_id": "src/auth/service.py",
        "score": 0.95,
        "callers": [
          {"entity": "LoginController", "relation": "CALLS"},
          {"entity": "ApiFilter", "relation": "CALLS"}
        ],
        "callees": [
          {"entity": "UserRepository", "relation": "CALLS"},
          {"entity": "JwtProvider", "relation": "CALLS"}
        ]
      }
    ]
  }
}
```

### 实现要点

- 重命名 `search` → `find`，核心匹配逻辑保留
- `--with-relations`：匹配实体后，从 relations 数据中提取每个实体的 callers/callees
- 向后兼容：考虑保留 `search` 作为隐藏别名（一个版本过渡期）

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F1-S1 | 重命名 `search` → `find`，更新 CLI 注册 + 测试 | 0.5d |
| F1-S2 | 实现 `--with-relations` 逻辑（实体匹配后 join 关系） | 1d |
| F1-S3 | 可选：`search` 别名 + deprecation warning | 0.5d |

---

## Feature 2: `query` — 语义知识问答

### 命令接口

```bash
# 基础用法：自然语言问题
loomgraph query "How does the authentication flow work?"

# 指定查询模式
loomgraph query "What modules handle payment?" --mode local
loomgraph query "What are the main architectural patterns?" --mode global
loomgraph query "How is error handling implemented?" --mode hybrid

# 指定 workspace
loomgraph query "What are the core modules?" -w my-project
```

### 查询模式

| 模式 | LightRAG 行为 | 适用场景 |
|------|-------------|---------|
| `hybrid`（默认） | 图谱 + 向量 + LLM 综合 | 通用问题 |
| `local` | 以特定实体为中心展开 | "AuthService 怎么工作的？" |
| `global` | 全局主题提取 | "项目有哪些设计模式？" |
| `naive` | 纯向量搜索 + LLM | "找和错误处理相关的代码" |

### 输出格式

```json
{
  "status": "success",
  "data": {
    "query": "How does the authentication flow work?",
    "mode": "hybrid",
    "response": "The authentication flow in this project follows a layered architecture:\n\n1. **LoginController** receives login requests and delegates to AuthService\n2. **AuthService.authenticate()** validates credentials via UserRepository\n3. On success, **JwtTokenProvider.generateToken()** creates a JWT\n4. The token is validated on subsequent requests by **AuthenticationFilter**\n\nKey modules involved: src/auth/, src/security/",
    "workspace": "my-project"
  }
}
```

### 实现要点

- 封装 `LightRAGClient.query()` 为 CLI 命令
- 输出是 LightRAG RAG 引擎的 LLM 综合回答
- 依赖 H200 上的 LLM 服务（GLM-4.7）
- 需要评估回答质量（chunks 内容是否足够支撑好的 RAG 回答）

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F2-S1 | 实现 `query` CLI 命令，封装 `client.query()` | 0.5d |
| F2-S2 | 用真实项目评估 RAG 回答质量，调优 chunk 内容 | 1-2d |
| F2-S3 | 错误处理（LLM 不可用、超时、空结果） | 0.5d |

---

## Feature 3: `graph` 命令改进（可选）

当前 `graph` 命令已可用，本 EPIC 中仅做微调：

| 改进 | 说明 | 优先级 |
|------|------|--------|
| 支持模糊输入 | `graph "Auth"` 自动匹配最佳实体 | P2（可选） |
| 结果增强 | 添加 source_id 到每个 caller/callee | P1 |

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F3-S1 | `graph` 结果中添加 source_id（文件路径） | 0.5d |

---

## Feature 4: 文档与 Skill 更新

### 需更新的文档

| 文档 | 更新内容 |
|------|---------|
| `CLAUDE.md` | CLI 命令速查表：`search` → `find`，新增 `query` |
| `docs/api/CLI_DESIGN.md` | 完整的 find/query 接口说明 |
| `CHANGELOG.md` | v0.7.0 变更记录 |
| 现有 Skills | 如果引用了 `search` 命令，更新为 `find` |

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F4-S1 | 更新 CLAUDE.md + CLI_DESIGN.md + CHANGELOG | 0.5d |
| F4-S2 | 检查并更新现有 Skills 中的命令引用 | 0.5d |

---

## 外部贡献的可借鉴思路

来自已关闭的 PR #11/#13/#14（zengyayong918-create），以下技术点值得吸收：

### 1. BFS 图扩展模式（PR #14）

`find --with-relations` 的实现可借鉴 BFS 扩展思路：

```
种子实体（名字匹配）→ BFS depth=1 沿 CALLS/INHERITS/IMPORTS 边扩展 → 收集邻居实体 + 关系
```

```python
# 参考实现思路（非全量下载，用已有 relations 数据 join）
adj = defaultdict(list)
for r in relations:
    adj[r["src_id"]].append({"neighbor": r["tgt_id"], **r})
    adj[r["tgt_id"]].append({"neighbor": r["src_id"], **r})

# BFS 从匹配的实体出发
frontier = [e["entity"] for e in matched]
for _ in range(depth):
    next_frontier = []
    for name in frontier:
        for edge in adj.get(name, []):
            # 收集邻居实体和关系
```

**采纳点**: `--with-relations` 可支持 `--depth N` 控制 BFS 扩展层数，默认 1 层。
**不采纳**: 每次调用全量下载 `get_all_entities()` + `get_all_relations()`（不可扩展）。`find` 已经需要下载全量实体做匹配，relations 也已经下载了（`graph` 命令同理），所以在当前架构下 join 的额外开销可接受。

### 2. Relation endpoint 校验（PR #13）

`collect_kg_data()` 在构建 relations 时，应预验证至少一个 endpoint 是已知实体：

```python
known_names = {e["entity_name"] for e in entities}
relations = [r for r in relations if r["src_id"] in known_names or r["tgt_id"] in known_names]
```

**采纳点**: 在 `injector.py` 的 `collect_kg_data()` 中添加 endpoint 校验，减少孤立关系。
**优先级**: P2，可在 EPIC-008 或后续小版本中实现。

### 3. 图遍历替代 NL 查询做 impact 分析（PR #11）

当前 `ImpactAnalyzer` 用 `client.query()` (NL 查询 + regex 解析) 找 caller，不如用图的 CALLS 边遍历更确定性：

```python
# 用关系图的 CALLS 边做 BFS，替代 "What functions call X?" 的 NL 查询
callers = [r["src_id"] for r in relations if r["tgt_id"] == symbol_name and r["keywords"] == "CALLS"]
```

**采纳点**: `impact` 命令的 caller 查找从 NL 查询迁移到图遍历。
**优先级**: P2，可作为 EPIC-008 的附带改进或独立 bugfix。

---

## 技术方案

### 架构变更

```
CLI 命令层:
  find    → _search.py (重命名，增强)
  query   → _search.py (新增)
  graph   → _search.py (微调)

Core 层:
  LightRAGClient.query()      → 已有，query 命令直接使用
  LightRAGClient.get_all_*()  → 已有，find/graph 继续使用

LightRAG API:
  POST /query                 → query 命令使用
  GET /graph/entities/all     → find 命令使用
  GET /graph/relations/all    → find --with-relations / graph 使用
```

### 向后兼容

- `search` 命令保留一个版本作为 `find` 的隐藏别名，输出 deprecation warning
- `graph` 命令接口不变，仅增强输出内容
- 所有 JSON 输出保持 `{"status": "success", "data": {...}}` 格式

---

## 开发顺序

```
Feature 1 (find)       ██████████░░  基础：重命名 + --with-relations
Feature 2 (query)      ████████████  核心差异化：语义问答
Feature 3 (graph 微调)  ████░░░░░░░░  可选增强
Feature 4 (文档)        ██████░░░░░░  同步更新
```

**建议顺序**：F1 → F2 → F4 → F3（F3 可选）

---

## 验收标准

- [ ] `loomgraph find "keyword"` 返回结构化实体匹配结果
- [ ] `loomgraph find "keyword" --with-relations` 一次返回实体 + callers/callees
- [ ] `loomgraph find "keyword" --type class` 类型过滤正常
- [ ] `loomgraph query "question"` 返回 LightRAG RAG 综合回答
- [ ] `loomgraph query "question" --mode local|global|hybrid|naive` 四种模式可选
- [ ] `loomgraph graph` 结果包含 source_id
- [ ] 现有 265+ 测试全部通过
- [ ] 新增 find/query 单元测试
- [ ] CLI 帮助文档 (`--help`) 准确
- [ ] CLAUDE.md + CLI_DESIGN.md 已更新

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| `query` 的 RAG 回答质量取决于 chunks 内容 | 回答可能不准确或太泛 | 评估后调优 `build_chunks()` 内容（加入更多上下文） |
| `query` 依赖 H200 LLM 服务可用 | LLM 离线时 `query` 不可用 | 明确错误信息 + `find` 作为 fallback |
| `search` → `find` 重命名可能破坏现有 Skill | Skill 引用了 `search` 命令 | 检查所有 SKILL.md，保留一版本过渡期 |
| `--with-relations` 在大项目上性能 | 全量下载 + join 可能慢 | 限制 `--limit` 默认值，按需优化 |
