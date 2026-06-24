# ADR-013: 用 SQLite + sqlite-vec 单文件后端替换 LightRAG

**状态**: ✅ 已批准
**日期**: 2026-06-24
**决策者**: DreamLinx
**关联**: EPIC-011 (#31), codeindex ADR-007, Supersedes ADR-001, ADR-002, ADR-010 (部分)

---

## 上下文

### 一年实践后浮出的三个事实

ADR-001（PostgreSQL 统一存储，2025-02-03）+ ADR-002（LightRAG 框架，2025-02-03）+ ADR-010（搜索体系，2026-02-21 — 把语义问答当 LoomGraph 差异化能力）共同定义了当前架构：codeindex 解析 → loomgraph 通过 LightRAG → PostgreSQL + pgvector + LightRAG 4 套存储后端。

一年后三个事实站不住：

1. **LightRAG 在代码场景是 layer 错配**。它的 LLM 实体抽取在 Layer 3（设计文档，自然语言推断）有价值，但在 Layer 1（代码 AST）是多此一举——tree-sitter 已经给出 100% 确定性结构图，再走一遍 LLM 推断是浪费 + 引入幻觉。详见 `code-governance/notes/three-layer-architecture.md`。

2. **LightRAG 的 4 套存储后端服务零现有用户**。loomgraph 实际只用到「entities/relations CRUD + analytics + 偶尔 LLM 调用」。LightRAG 的 KV_STORAGE（LLM 缓存）/ DOC_STATUS_STORAGE 在我们的用法里几乎是死代码。

3. **`loomgraph query`（ADR-010 视为差异化能力）已被 Claude Code / codex / Cursor 卷死**。一年前还没有的通用代码 agent 现在做自然语言代码问答比我们好得多。loomgraph 真正的护城河是「结构精确 + 跨层 JOIN」，不是 RAG-style 问答。

### sqlite-vec 在我们场景的实测优势

来源：`code-governance/notes/sqlite-vec-vs-lightrag.md`，bge-m3 模型 1024 维实测（数据等比例可推到 Jina Code V2 768 维）：

| 数据量 | 查询提速 vs 手动 |
|---|---|
| 100 | 5.6× |
| 1,000 | 61× |
| 10,000 | 88× |

codeindex 目标用户的典型代码库 <100k 函数，正好在 sqlite-vec 舒适区。

更关键的是 sqlite-vec 提供 `vec0` 虚拟表 + 普通 SQLite 表在同库的 JOIN 能力——「找到与这段设计文档语义相似的代码函数，且它们调用了 redis」这种**跨层联合查询**在 LightRAG 上做不到（向量在 VECTOR_STORAGE，图在 GRAPH_STORAGE，两套后端无法 JOIN）。这是未来 Layer 3 设计文档接入时的关键基础设施。

## 决策

**完全砍掉 LightRAG 依赖**，本地 SQLite + sqlite-vec 单文件接手所有 loomgraph 持久化与查询：

```
codeindex (AST 解析)
    ↓ ParseResult
loomgraph (映射 + 写入)
    ↓
~/.loomgraph/<workspace>.db (单文件)
    ├── nodes        (实体)
    ├── edges        (关系: CALLS / INHERITS / IMPORTS / ...)
    ├── file_hashes  (增量索引)
    ├── workspaces   (元数据)
    ├── vec_node_descriptions  (vec0 虚拟表: 实体描述向量)
    └── vec_code_snippets      (vec0 虚拟表: 代码片段向量)
```

### 具体决策

| 议题 | 决策 |
|---|---|
| 存储后端 | SQLite + sqlite-vec（单文件 `~/.loomgraph/<workspace>.db`） |
| Embedding service | 保留 H200 上的 Jina Code V2 (3002 端口) — 仅作 embedding 调用 |
| H200 LightRAG API (3001) | **完全停服**，v0.10.0 起官方不再支持 LightRAG 后端 |
| `loomgraph query` 命令 | **立删**（让位 Claude Code / codex / Cursor 等通用 agent） |
| 内部 LLM 调用（overview / impact） | 抽 `LLMClient` abstraction，直连 GLM-4.7 或 OpenRouter，绕开 LightRAG RAG pipeline |
| 数据迁移 | **不迁移**，cold rebuild（数据从 codeindex 重生成成本低） |
| 实施顺序 | 先做 sqlite-vec 替换，吃当前 codeindex parse 结果；等 codeindex#102 graph-export 完成后另开 importer |
| 消费侧 spike (#30) 门控 | **不挂门控**（spike 验证的是"图谱是否值得作为对外契约固化"，与本 Epic 范围正交） |

### 三层架构定位

按 `code-governance/notes/three-layer-architecture.md`：

| Layer | 内容 | 工具 | 本 ADR 状态 |
|---|---|---|---|
| L1 | 代码结构（AST） | codeindex tree-sitter | 由 codeindex 提供，loomgraph 持久化 |
| L2 | 代码注释规范化 | codeindex DocstringProcessor | 由 codeindex 提供，loomgraph 持久化 |
| L3 | 设计文档语义图 | LLM 抽取 | **不在本 Epic 范围**，但 sqlite-vec 后端为其预留架构（vec0 + nodes/edges 单库 JOIN） |

LightRAG 的 LLM 实体抽取能力**不被替换，是被拆解**：能力（LLM）保留给 L3，存储（4 套后端）砍掉。L3 真要做时一段几十行 prompt + JSON schema 就能起步，不需要扛 LightRAG 整套包袱。

## 理由

### 1. 服务零现有用户的依赖应当砍掉

LightRAG 的 4 套存储（KV/Vector/Graph/DocStatus）+ 5 种查询模式（local/global/hybrid/naive/mix）+ 复杂并发参数（MAX_ASYNC_LLM 等十多个）对应不上 loomgraph 的真实用法。绝大部分调用是 entities/relations CRUD（70%）和 analytics（12.5%），剩下的 LLM 调用（3 处）不需要 RAG pipeline。

### 2. 部署门槛崩塌带来分发杠杆

现在客户 onboarding 需要：H200 部署 LightRAG + PostgreSQL + Jina embedding service + 配置 4 套存储 + 调 10+ 并发参数。替换后：`pipx install loomgraph` + 一个 `.db` 文件（embedding service 仍保留，但可走 OpenAI/Voyage/本地等通用 provider）。

这跟 codeindex ADR-006 的「pipx + plugin 两行 onboarding」是同向决策。

### 3. 跨层 JOIN 能力是未来 L3 的杀手锏

sqlite-vec 的 vec0 虚拟表 + 普通 SQLite 表同库 JOIN 能做这样的查询：

```sql
-- 找到与这段设计文档语义相似的代码函数，且它们调用了 redis
SELECT n.qualified_name, n.file_path, v.distance
FROM vec_design_docs v
JOIN nodes n ON n.id = v.rowid
WHERE v.embedding MATCH :query_embedding
  AND n.label = 'Function'
  AND n.id IN (SELECT source_id FROM edges WHERE type='CALLS'
               AND target_id IN (SELECT id FROM nodes WHERE name LIKE '%redis%'))
ORDER BY v.distance LIMIT 10;
```

LightRAG 做不到——向量与图在不同后端。这是「Predictive Refactoring」等未来 killer feature 的基础设施。

### 4. 自然语言代码问答不是 loomgraph 该卷的赛道

ADR-010（2026-02-21）的判断是「语义问答是 LoomGraph 真正的差异化能力」，那时 Claude Code 还没有 plugin/skill 生态。今天 Claude Code / codex / Cursor 都能做这事，且做得比基于 LightRAG mode=hybrid 的 `loomgraph query` 好。loomgraph 该聚焦的是「结构精确 + 跨层 JOIN + AST 确定性」——这是 LLM agent 本身做不好的事。

### 5. 与 codeindex ADR-007 同源

codeindex ADR-007 决定「codeindex 保持无状态发射器，持久化图谱归 loomgraph」。本 ADR 是 loomgraph 侧的镜像决策：既然要接手持久化，那就用对的工具（SQLite + sqlite-vec），不要扛 LightRAG 这套用错了层的包袱。

## 实施路径

详见 **EPIC-011 (#31)**，5 个 Phase / Feature：

- **#32 Phase 1**: GraphStore + LLMClient abstraction + 双写门控（2-3 天）
- **#33 Phase 2**: Storage 写读路径切换到 SQLite + sqlite-vec（3-4 天）
- **#34 Phase 3**: Analytics 本地 SQL（topology/debt/overview/impact/deps）（1-2 天）
- **#35 Phase 4**: LLM 拆解 + `loomgraph query` 立删（1-2 天）
- **#36 Phase 5**: 拆 LightRAG 依赖 + 文档迁移 + v0.10.0 发布（2-3 天）

## 后果

### 正面

- 部署面砍掉一个完整服务（LightRAG API）+ PostgreSQL 可选化
- 查询性能在 codeindex 目标规模（<100k 函数）下提升 5-88×（in-process + 去 HTTP）
- 跨层 JOIN 能力解锁未来 L3 / 演化预测等场景
- 配置项从 10+ 调优参数降到 ~3 个
- 客户 onboarding 时间从小时级降到分钟级
- 代码量减少（删除 `lightrag_client.py` ~750 行 + 相关测试 / mock）

### 负面

- Breaking Change：v0.10.0 起客户必须 cold rebuild
- `loomgraph query` 用户面命令删除（自然语言问答能力丧失）
- sqlite-vec pre-v1，API 可能 breaking（用 `GraphStore` abstraction 隔离）
- 大规模向量（>100k）性能未实测（codeindex 目标用户在舒适区，超规模另议）
- 失去 LightRAG 社区生态（社区做的优化、bug 修复不再 inherit）

### 风险缓解

- **sqlite-vec API 不稳定** → Phase 1 引入 `GraphStore` abstraction，未来可换 DuckDB / 自研后端
- **客户回滚需求** → release notes 标注 v0.9.x 是最后支持 LightRAG 的版本，pip pin 该版本可回滚
- **H200 LightRAG 关停影响其他项目** → Phase 5 实施前确认 H200 上仅 loomgraph 在用
- **migration guide 漏 case** → 至少一个已部署客户 staging 实测 cold rebuild

## 验证计划

详见 EPIC-011 Phase 1-5 各 Feature 验收条件。Epic 级关键验证：

1. 全新 macOS 环境一键 onboarding：`pipx install loomgraph && loomgraph index . && loomgraph find "..."` 全绿，无 LightRAG 服务依赖
2. `grep -r "lightrag\|LightRAG" src/` 仅命中本 ADR 与 CHANGELOG 引用
3. 双写一致性测试（Phase 1）：同一 fixture，LightRAG vs SQLite 后端 entities/relations 集合等价
4. 性能 benchmark（Phase 2）：写入 sqlite-vec ≤ LightRAG × 2；读取 sqlite-vec ≥ LightRAG × 5

## 撤销的 ADR

| ADR | 原决策 | 撤销原因 |
|---|---|---|
| ADR-001 | PostgreSQL + pgvector 统一存储 | 4 套存储后端服务零现有用户；SQLite 单文件更简单 |
| ADR-002 | LightRAG 框架做代码图谱 | Layer 错配；AST 已确定性提取，LLM 推断多此一举 |
| ADR-010（部分） | 语义问答是 LoomGraph 差异化能力 | 一年后 Claude Code/codex 卷死该赛道；`loomgraph query` 立删；ADR-010 中 `find` / `graph` 命令的结构化能力保留 |

## 参考

- codeindex ADR-007: `docs/architecture/adr/007-codeindex-stateless-graph-ownership.md`
- `code-governance/notes/sqlite-vec-vs-lightrag.md` — sqlite-vec vs LightRAG 深度对比
- `code-governance/notes/three-layer-architecture.md` — 三层架构 + provenance 模型
- `code-governance/notes/codeindex-loomgraph-division.md` — L1+L2 vs L3 分工
- [sqlite-vec](https://github.com/asg017/sqlite-vec) — Mozilla Builders 赞助，活跃维护
- [LightRAG](https://github.com/HKUDS/LightRAG) — 不再使用，保留链接供历史参考
