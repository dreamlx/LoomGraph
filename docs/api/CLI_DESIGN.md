# LoomGraph CLI 设计

> **权威声明**: 本文档是写作时快照,**不是权威命令面**。唯一权威是 `loomgraph --help`
> 与各命令的 `loomgraph <cmd> --help`。若本文与 `--help` 冲突,以 `--help` 为准。
> CLI 命令会随版本演进,本文可能滞后;做集成前请务必跑一次 `--help` 核对参数与输出。

**设计原则**: 针对 AI Agent (Claude Code / Codex / Cursor) 作为主要用户。

| 原则 | 说明 |
|------|------|
| **原子命令** | 每个命令只做一件事,可组合 |
| **JSON 输出** | 机器可读,便于 AI 解析(stdout 纯 JSON,日志走 stderr) |
| **结构化错误** | 包含错误码 (`code`)、建议 (`suggestion`)、文档链接 (`docs`) |
| **幂等操作** | 重复执行产生相同结果 |
| **无交互** | 不需要用户输入确认(workspace 删除需 `--yes`) |

---

## 命令概览

> 下表是写作时快照,以 `loomgraph --help` 为唯一权威。

```
loomgraph
├── index           # 一键索引 (codeindex graph-export → embed → insert 内部 pipeline; qualified id, #66)
├── update          # 增量更新 (per-file warm-diff via git, 路 B; --since 默认 HEAD~1)
├── import-export   # 消费 codeindex graph-export NDJSON artifact (不走 subprocess)
├── find            # 结构化实体发现 (名字匹配 + 可选 callers/callees)
├── search          # 语义搜索 (按含义, embedding KNN; opt-in, 需 embedding.enabled)
├── embed-backfill  # 为已有 workspace 补充向量 (不重新解析)
├── graph           # 精确关系遍历 (callers/callees + source_id, --depth BFS)
├── topology        # 拓扑债务分析 (orphans/hubs/god functions/coupling)
├── deps            # 模块依赖分析
├── debt            # 多维度技术债务评分 (--with-git)
├── impact          # 变更影响分析 (git diff → affected callers)
├── overview        # 项目模块概览 (--no-summary 跳过 LLM)
├── check           # 索引新鲜度检查 (source_id vs 磁盘文件)
├── git-metrics     # Git 热点 / 总线因子 / 缺陷率
├── trends          # 代码复杂度趋势
├── workspace       # workspace 管理 (list/info/delete)
├── compare/similar # 跨 workspace diff / 相似实体
├── hooks           # git hooks 管理 (post-commit 自动更新)
├── mcp             # MCP server (install-config / serve)
├── install-skills  # 安装 Claude Code Skills 到 ~/.claude/skills/
├── status          # 检查系统状态 (storage/codeindex/embedding)
└── version         # 版本信息
```

`setup-config` 已 deprecated (v0.16+, #114) —— 零配置默认可用,仅在手写 config stub 时用。

---

## 命令详情

> 以下各命令的参数表与输出示例为写作时快照。参数权威以 `loomgraph <cmd> --help` 为准;
> 输出字段权威以实际运行为准(版本演进可能增删字段)。

### `index` — 一键索引

**用途**: 一键索引。内部 pipeline 为 `codeindex graph-export` → (可选)embed → insert,
不是独立的 `embed`/`inject` 命令(v0.13 起 legacy programmatic API + embed/inject CLI 已移除,#84)。
实体用 **module-qualified id**(修复跨模块同名函数冲突,#66),边带 `resolution_qualifier` +
跨文件 callee 解析。需要 `ai-codeindex >= 0.33.3`。

```bash
loomgraph index [<repo_path>] [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<repo_path>` | 仓库路径 | 当前目录 |
| `--clear` / `--no-clear` | 清除旧数据后重建(Cold Rebuild) | `true` |
| `-w, --workspace` | workspace 名(默认: 当前目录名) | 自动 |
| `--at-ref REF` | 从 git ref 创建独立快照 workspace；默认名为 `<repo>:<ref>` | — |

`--at-ref` 使用 `branch-diff` 的 worktree + cold-index provisioning 内核，适合把
历史 tag/branch 固定成可查询的 workspace：

```bash
loomgraph index --at-ref v1.2
loomgraph index /path/to/repo --at-ref v1.2 --workspace customer:v1.2
```

该模式始终是 cold snapshot，不接受 `--no-clear`；v1 仅支持默认的 `codeindex`
backend。完成后可直接把返回的 `workspace` 传给 `find`、`graph`、`topology` 等查询命令。

**成功输出** (exit code 0):
```json
{
  "success": true,
  "data": {
    "mode": "cold_rebuild",
    "workspace": "myproj:main",
    "repo_path": "/path/to/repo",
    "cleared": true,
    "entities_created": 1250,
    "relations_created": 3400,
    "embedded": 1250,
    "store_stats": {"entities": 1250, "relations": 3400},
    "duration_seconds": 45.2
  }
}
```

> **#66 Breaking**: 旧版本(legacy `codeindex scan` 路径)索引的 workspace 用简单名 key,
> 升级后**必须 `loomgraph index --clear .` 一次**重建,否则同名符号(`handle`/`run`/`__init__` 等)仍冲突。

**0-entity 防护** (#120): 若 `graph-export` 返回 0 个实体(常见于 `.codeindex.yaml` 的
`languages` 没覆盖该仓库语言),`index` 会输出 warning + `mode: "zero_entity_skipped"` 并写入
空 workspace(空仓库合法)。`update` / `refresh` 遇到同样情况则**硬停**(它们会 clear/GC,
0-entity 下继续会丢数据)。warning 文案会提示装对应的 `loomgraph[<lang>]` extra。

### `branch-diff` — 两个 git ref 的结构性 diff

```bash
loomgraph branch-diff <base>..<head> [--backend codeindex|codegraph]
```

命令会为两侧 ref 自动创建或复用隔离的 detached worktree + snapshot
workspace，然后返回实体、边、调用链、内容变化和模块耦合的方向性 diff。
默认使用本地 `codeindex`；`--backend codegraph` 会在每个 detached worktree
中调用 PATH 上解析到的 npm `codegraph` CLI（新 worktree 先 `init`，已有数据库才
`sync`），再由 loomgraph 读取 `.codegraph/codegraph.db`。`diff` 的
`content_comparison` 是 version 1 的 L2 契约：只有同 backend 的 codeindex
graph-export schema v1 快照会返回 `status: "available"` 或 `"partial"` 与确认过
的 `changed` 列表；旧 schema / 无 span symbol 会导致 `partial`。codegraph 返回
`status: "unavailable"`、`changed: null` 和原因。空列表只在可比较时表示未发现内容
变化，跨 backend hash 也永不比较。

codegraph 是显式的成本选择：默认最多处理 10,000 个 git tracked 文件，单个
worktree provision 最长 30 分钟；可用 `LOOMGRAPH_CODEGRAPH_MAX_FILES` 调高或
调低文件数上限。缺少 npm CLI、超过上限或 provision 失败会返回结构化
`CODEGRAPH_FAILED` 错误。

---

### `update` — 增量更新(per-file warm-diff via git, 路 B)

**用途**: git 仓库内,基于 `--since`(默认 `HEAD~1`)检测变更文件,只对变更文件 re-embed/re-inject,
未变更文件零 embed 调用(embed 是最贵的一步,per codeindex#110),并 garbage-collect 自上次索引后删除的符号。
symbol-level 增量由 content_hash diff 恢复(#91)。

```bash
loomgraph update [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--since` | git diff 起始 ref | `HEAD~1` |
| `-w, --workspace` | workspace 名 | 当前目录名 |
| `--files` | 逗号分隔文件列表(跳过 git 检测) | — |
| `--embedding-url` | 覆盖 config 的 embedding URL(**inert**,仅 CI-script/肌肉记忆兼容) | — |
| `--use-affected` | 用 `codeindex affected` 代替 `git diff`(**inert**) | `false` |

**两种模式**:
- **git 仓库 + 未设 `--files`**: warm-diff。re-export whole tree,但只对 `--since` 后变更的文件做 embed/inject,GC 删除的符号。
- **非 git 仓库 或 设了 `--files`**: 回退 whole-tree upsert(`clear=False`)。addition/modification 收敛,但**删除的符号不会被 GC**;要彻底干净跑 `index --clear .`。

> `--use-affected` / `--embedding-url` 接受但 inert(保留是为了不 break 已部署的 CI 脚本)。
> `--files` 的路径存在性会校验(CI 脚本可能 gate 在 exit code 上),且会强制走 whole-tree fallback。

**0-entity 防护** (#120): 同 `index`,但 `update` 遇 0-entity export 会硬停(`mode: "zero_entity_skipped"`)而非继续。

---

### `import-export` — 消费 codeindex graph-export artifact

**用途**: 读取 codeindex `graph-export` 写出的 NDJSON 文件(codeindex#102 契约),把其中的 entities + edges
落入一个 workspace。LoomGraph#30 spike 验证过 round-trip 语义保真。

```bash
loomgraph import-export <artifact> [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<artifact>` | codeindex graph-export 产出的 NDJSON 路径 | 必填 |
| `--workspace`, `-w` | 写入 workspace 名 | `<basename>:imported` |
| `--clear` / `--no-clear` | 写入前清空 workspace | `false`(非破坏性默认) |
| `--dry-run` | 只读取 + 校验 + 映射,不写存储 | `false` |

**默认 workspace 命名**: `<artifact-basename>:imported`(`:imported` 后缀避免与 `loomgraph index .` 的 workspace 撞名)。

**资格保真**: 每条 edge 的 `resolution_qualifier`(`resolved` / `ambiguous` / `unresolved`)原样保留在 `edge_data` 里。
`unresolved` 边(target 不在仓库 entity 表内)被计入 summary 但**不入库**(插占位符会在 topology 分析里制造假 hub)。
`summary.edge_qualifiers` 保留各 qualifier 完整计数。

**查询默认只信 resolved**(#113): `graph` 与 `find --with-relations` 默认只返回 `resolved` 边,
避免 `unresolved` / `ambiguous` 的 phantom target(`source_id=""`)淹没真实 callees/callers。
`graph` 加 `--include-unresolved` 可带回低信任边供 raw-call 调试。`deps` / `topology` 不受影响。

**成功输出**(`--dry-run`):
```json
{
  "success": true,
  "data": {
    "workspace": "customer:imported",
    "artifact": "/tmp/customer.ndjson",
    "dry_run": true,
    "summary": {
      "meta": {"schema_version": 0, "provenance_completeness": "ast-only..."},
      "entity_count": 2931,
      "relation_count": 5057,
      "entity_types": {"class": 541, "function": 655, "method": 1735},
      "edge_kinds": {"CALLS": 12284, "INHERITS": 30},
      "edge_qualifiers": {"resolved": 2890, "ambiguous": 2167, "unresolved": 7257},
      "skipped_records": 0,
      "schema_warnings": []
    },
    "would_write": {"entities": 2931, "relations": 5057}
  }
}
```

实写输出增加 `store_stats`,删去 `dry_run` / `would_write`。

错误码: `FILE_NOT_FOUND` / `INVALID_INPUT` / `STORAGE_ERROR`

---

### `find` — 结构化实体发现

**用途**: 按名字匹配实体,可选带关系上下文。

```bash
loomgraph find <query> [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<query>` | 名字匹配关键词 | 必填 |
| `--type/-t` | 实体类型过滤 (class/function/module) | 全部 |
| `--limit/-n` | 结果数量 | `20` |
| `--with-relations` | 附带 callers/callees | 否 |
| `--depth` | BFS 扩展层数(需 `--with-relations`) | `1` |
| `--workspace/-w` | workspace 名 | 当前目录名 |

**基础输出**:
```json
{
  "success": true,
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

`--with-relations` 输出在每个 match 里追加 `callers` / `callees` 数组(默认只含 `resolved` 边,#113)。

---

### `search` — 语义搜索(按含义)

**用途**: 按自然语言含义检索实体 —— `find` 的语义对等项。`find` 按名字匹配,`search` 按意图/含义
(把 query 嵌入实体描述向量空间做 KNN)。互补关系:知道符号名用 `find`,知道"它做什么"用 `search`。

```bash
loomgraph search <query> [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<query>` | 自然语言意图或描述性短语 | 必填 |
| `--type/-t` | 实体类型过滤 (class/function/method/module) | 全部 |
| `--limit/-n` | 结果数量 | `20` |
| `--workspace/-w` | workspace 名 | 自动检测 |

**前置条件**: workspace 必须在 embedding 开启时索引过(`LOOMGRAPH_EMBEDDING__ENABLED=true`)。
否则返回 `EMBEDDING_NOT_INDEXED`。

**输出**:
```json
{
  "success": true,
  "data": {
    "query": "where are hotspots computed",
    "mode": "semantic",
    "workspace": "loomgraph:main",
    "vector_count": 338,
    "matches_count": 5,
    "matches": [
      {"entity": "core.git_metrics.GitMetricsAnalyzer._detect_hotspots", "type": "method",
       "source_id": "core/git_metrics.py:88", "description": "...", "score": 0.157}
    ]
  }
}
```

> **历史**: `search` 曾是 `find` 的隐藏 deprecated 别名(v0.10 前)。EPIC-015 回收这个名字给语义搜索
> —— `find`(按名)/ `search`(按义)/ `graph`(按关系)三个对等检索模式。

---

### `embed-backfill` — 为已有 workspace 补充向量

**用途**: 对于已有 entities 但缺少 embedding vectors 的 workspace(例如通过 `import-export` 导入的
workspace,导入时不携带向量数据),嵌入现有 entity 描述并写入 `vec_node_descriptions`。
**不重新解析、不重新注入** —— 只对已存在的 entities 做向量化。

```bash
loomgraph embed-backfill [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--workspace/-w` | workspace 名 | 自动检测 |

**前置条件**:
- workspace 必须已有 entities(通过 `index .` 或 `import-export` 创建)
- 必须启用 embedding: `LOOMGRAPH_EMBEDDING__ENABLED=true` + 配置 provider

**幂等性**: 如果 workspace 已有向量(`vector_count() > 0`),直接跳过,不报错、不重新嵌入。

错误码: `EMBEDDING_NOT_INDEXED` / `EMBEDDING_FAILED`

---

### `graph` — 精确关系遍历

**用途**: 查询实体的调用关系(含 source_id 文件路径)。

```bash
loomgraph graph <entity_name> [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<entity_name>` | 实体名称 | 必填 |
| `--direction` | 查询方向 `[callers\|callees\|both]` | `both` |
| `--depth` | 遍历深度(BFS) | `1` |
| `--relation-type` | 关系类型 `[CALLS\|INHERITS\|IMPORTS\|all]` | `all` |
| `--include-unresolved` | 包含 unresolved/ambiguous 低信任边(target 为调用表达式,可能不在仓库 entity 表内,显示为 `source_id=""`) | `false` |
| `--workspace/-w` | workspace 名 | 当前目录名 |

**方向**: `callers`(谁调用了它) / `callees`(它调用了谁) / `both`(双向)

**关系类型**: `CALLS`(调用) / `INHERITS`(继承) / `IMPORTS`(导入) / `all`

> **#113 信任过滤**: 默认只返回 `resolved` 边。`unresolved`(builtin/stdlib/动态分发,如 `len`/`click.echo`)
> 与 `ambiguous`(同名猜测,#101)边的 target 是调用表达式而非仓库实体,默认过滤掉以免 phantom callees/callers
> (`source_id=""`)淹没真实结果。需要查看原始调用表达式时加 `--include-unresolved`。

**成功输出**:
```json
{
  "success": true,
  "data": {
    "entity": "UserService.login",
    "source_id": "src/auth/service.py",
    "callers": [
      {"entity": "AuthController.handle_login", "relation": "CALLS", "source_id": "src/api/auth.py"}
    ],
    "callees": [
      {"entity": "db.find_user", "relation": "CALLS", "source_id": "src/db/query.py"}
    ],
    "callers_count": 1,
    "callees_count": 1
  }
}
```

---

### `topology` — 图谱拓扑分析

**用途**: 分析知识图谱拓扑结构,检测结构级代码坏味道。

```bash
loomgraph topology [options]
```

> ✅ **#66 已修复**: `index`/`update` 已迁到 `codeindex graph-export` 契约,实体用 module-qualified id。
> 跨模块同名函数不再合并成幻影 god_function。升级后需 `index --clear .` 重建一次 workspace。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--hub-threshold` | Hub 实体的最小 in-degree | `5` |
| `--god-threshold` | God Function 的最小 out-degree | `5` |
| `--scope` | 绝对路径前缀过滤(如 `src/`),排除 docs/scripts/tests;优先于 `--module` (#61) | 全部 |
| `--module` | 模块前缀过滤;**已弃用,优先用 `--scope`** | 全部 |
| `--workspace/-w` | workspace 名 | 当前目录名 |

**检测项**:
- **Orphans**: 0 in-degree + 0 out-degree(排除 module 类型和 external)
- **Hubs**: 高 in-degree 实体(修改会产生广泛涟漪)
- **God Functions**: 高 out-degree 实体(职责过重)
- **Placeholder Modules**: 仅含 `__init__` 的模块
- **Coupling Density**: cross_module_relations / total_relations

**拓扑分数** (`topology_score`, 0-100,越高越健康):
- orphan_ratio > 20% → -25, > 10% → -15
- hub (in >= 15) → -5 per entity
- god_function (out >= 20) → -5 per, (out >= 10) → -3 per
- placeholder_modules → -5 per module
- coupling_density > 0.5 → -10, > 0.3 → -5

---

### `deps` — 模块依赖分析

**用途**: 聚合 CALLS / IMPORTS / INHERITS 边,构建模块级依赖图(模块间入站 + 出站依赖)。

```bash
loomgraph deps [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-d, --depth` | 目录深度(模块分组粒度) | 默认 |
| `-w, --workspace` | workspace 名 | 当前目录名 |

**输出**:
```json
{
  "success": true,
  "data": {
    "modules": ["src/loomgraph", "scripts", "docs/spikes"],
    "dependencies": [
      {
        "from": "scripts",
        "to": "src/loomgraph",
        "count": 26,
        "types": {"CALLS": 26}
      }
    ]
  }
}
```

> **价值定位**: 一次 BFS 给出模块级聚合图,而单点查调用关系用 `graph` + Serena `find_referencing_symbols`(后者更精但 N+1)。

---

### `debt` — 多维度技术债务评分

**用途**: 结合 codeindex 静态分析 + LoomGraph 图拓扑 + (可选)git 历史度量,给出技术债评分。

```bash
loomgraph debt --codeindex-data <path> [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--codeindex-data` | codeindex `tech-debt` JSON 输出文件路径 | 必填 |
| `--format` | 输出格式 `[json\|markdown\|console]` | `json` |
| `-w, --workspace` | topology 分析用的 workspace 名 | 自动检测 |
| `--scope` | 路径前缀过滤(如 `src/`),限 static + topology 层 | 全部 |
| `--module` | 模块过滤;**已弃用,优先 `--scope`** | 全部 |
| `--skip-topology` | 跳过图拓扑分析(更快,仅 codeindex) | `false` |
| `--with-git` | 启用 git 度量分析 | `false` |
| `--git-since` | git 分析时间窗 | `3 months` |

> 注: `debt` 需要先用 `codeindex tech-debt ./src > debt.json` 生成静态层数据,再喂给本命令。
> MCP 侧的 `loomgraph_debt_audit` 把这步内部化了(一次调用跑完整三维度)。

---

### `impact` — 变更影响分析

**用途**: 给定 git ref / staged diff / 单文件,沿调用图返回所有受影响实体(caller chain up to N hops)。只读,
不写 workspace。

```bash
loomgraph impact [TARGET] [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `[TARGET]` | commit ref(默认 `HEAD`) | `HEAD` |
| `--staged` | 分析 staged 改动 | `false` |
| `--base` | range 比较的 base(如 `main..HEAD`) | — |
| `--depth` | caller 遍历深度 | 默认 |
| `--file` | 分析指定文件 | — |
| `-w, --workspace` | workspace 名 | 当前目录名 |

**输出**:
```json
{
  "success": true,
  "data": {
    "commit": "cc2d059",
    "changed_symbols": [],
    "impact_analysis": {
      "direct_callers": [],
      "indirect_callers": [],
      "affected_modules": [],
      "affected_tests": []
    },
    "risk_assessment": {
      "level": "low",
      "reason": "Low risk: no callers found, isolated change",
      "suggestions": ["Run unit tests for changed modules", "Consider adding tests for changed code"]
    }
  }
}
```

---

### `overview` — 项目模块概览

**用途**: 高层视图:每个模块的 entity 计数、类型分布、关键 public surface,可选 LLM 生成的模块 summary。

```bash
loomgraph overview [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-d, --depth` | 目录深度(模块分组粒度) | 默认 |
| `-w, --workspace` | workspace 名 | 当前目录名 |
| `--no-summary` | 跳过 LLM module summaries(只返回结构计数,免费/快) | `false` |

> `--no-summary` 跳过 LLM 调用,只给 per-module entity 计数 + top entities。多数场景足够。
> 大多数命令不需要 LLM;只有 overview 的 summary 模式调 LLM。

---

### `check` — 索引新鲜度检查

**用途**: 验证知识图谱中的 source_id 是否仍指向磁盘上存在的文件。

```bash
loomgraph check [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--repo-path` | 项目根目录(用于验证文件路径) | `.` |
| `-w, --workspace` | workspace 名 | 当前目录名 |

**输出**:
```json
{
  "success": true,
  "data": {
    "freshness": {
      "total_source_paths": 150,
      "valid": 116,
      "stale": 34,
      "freshness_ratio": 0.773
    },
    "stale_entries": [
      {
        "source_id": "cli/main.py:66-81",
        "file_path": "cli/main.py",
        "reason": "file_not_found",
        "suggestion": "Run 'loomgraph update' or 'loomgraph index --clear .'"
      }
    ],
    "suggestion": "34 source paths are stale. Run 'loomgraph index --clear .' to rebuild."
  }
}
```

---

### `git-metrics` — Git 历史度量

**用途**: 变更频率热点、总线因子(single-owner files)、缺陷磁铁。独立命令,路径非 git 仓时报错。

```bash
loomgraph git-metrics [PATH] [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `[PATH]` | 仓库根路径 | 当前目录 |
| `--since` | 时间窗(如 `3 months` / `6 months` / `1 year`) | `3 months` |
| `-o, --output` | 保存到 JSON 文件 | — |

---

### `trends` — 代码复杂度趋势

**用途**: 追踪单个代码实体跨 N 个 workspace snapshot 的复杂度演化。需要历史 snapshot(多次跑 `debt` 积累)。

```bash
loomgraph trends [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-e, --entity` | 实体标识(如 `src/auth/user_service.py`) | **必填** |
| `-m, --metric` | 分析指标 | `complexity` |
| `--months` | 分析月数 | `6` |
| `-w, --workspace` | 按 workspace 过滤 | 全部 |

---

### `workspace` — workspace 管理

**用途**: workspace 是一个代码库的索引 snapshot,存为单个 SQLite 文件 `~/.loomgraph/<workspace>.db`。
名字自动从当前目录 + git 分支派生(`<repo-dir>:<branch>`,如 `loomgraph:main`)。

```bash
loomgraph workspace <subcommand>
```

| 子命令 | 说明 |
|--------|------|
| `list` | 列出所有 workspace |
| `info [NAME]` | 查看 workspace 详情(默认自动检测当前);`-w` 覆盖 NAME |
| `delete NAME --yes` | 删除 workspace 及全部数据(`-y/--yes` 跳过确认,AI Agent 必备) |

> **自动降级**: 查询命令(`find`/`graph`/`topology` 等)在当前分支 workspace 为空时,自动降级到
> `main` → `develop` → `master`,保证仍能拿到结果。多 workspace 比较命令(`compare`/`similar`)
> **不降级**,必须显式指定两个 workspace。

---

### `compare` / `similar` — 跨 workspace 对比

**`compare`** — 两 workspace 间实体/关系 diff(必须显式指定两个,不降级):
```bash
loomgraph compare --ws1 <name> --ws2 <name>
```

**`similar`** — 跨 workspace 找相似实体(实体名搜索,默认所有 workspace):
```bash
loomgraph similar -e "<entity>" [-w "<comma-separated-workspaces>"]
```

---

### `hooks` — git hooks 管理

**用途**: 安装/卸载 post-commit hook,本地 `git commit` 后自动跑 `update`。

```bash
loomgraph hooks <subcommand>
```

| 子命令 | 说明 |
|--------|------|
| `install [--all] [--force]` | 装 post-commit hook(`--all` 装全部支持 hook;`--force` 覆盖现有) |
| `status` | 查看 hook 安装状态 |
| `uninstall` | 卸载 loomgraph hooks |

---

### `mcp` — MCP server

**用途**: LoomGraph 原生说 Model Context Protocol,AI agent 可把 `find` / `graph` / `topology` /
`impact` / `deps` / `overview` / `workspace_*` 等作为原生工具调用(无 CLI subprocess 开销)。

```bash
loomgraph mcp <subcommand>
```

| 子命令 | 说明 |
|--------|------|
| `install-config --path <p>` | 打印或写入 Claude Code MCP config 条目 |
| `serve` | 经 stdio 启动 MCP server |

完整 MCP tool 参考见 [MCP_DESIGN.md](MCP_DESIGN.md)。

---

### `status` — 系统状态

**用途**: 检查依赖与 workspace 状态。返回 codeindex / storage(SQLite + sqlite-vec)/ embedding 三项依赖,
加当前 workspace 的 entity/relation 计数。

```bash
loomgraph status
```

**成功输出**(本地零配置默认):
```json
{
  "success": true,
  "data": {
    "version": "0.16.0",
    "workspace": {
      "name": "loomgraph:main",
      "entities": 422,
      "relations": 2507
    },
    "config": {
      "storage_backend": "sqlite",
      "db_path_template": "~/.loomgraph/{workspace}.db",
      "embedding_url": "http://localhost:11434/v1",
      "llm_provider": "ollama"
    },
    "dependencies": {
      "codeindex": {
        "installed": true,
        "version": "codeindex, version 0.33.3",
        "path": "/path/to/venv/bin/codeindex"
      },
      "storage": {
        "connected": true,
        "backend": "sqlite",
        "vec_version": "v0.1.9",
        "db_path_template": "~/.loomgraph/{workspace}.db"
      },
      "embedding": {
        "enabled": false,
        "connected": false
      }
    }
  }
}
```

> embedding 默认 `enabled: false`(本地零配置)。开启语义搜索需 `LOOMGRAPH_EMBEDDING__ENABLED=true`
> + 配置 provider(默认本地 Ollama `nomic-embed-text`,详见 README "Configuration")。

---

### `version` — 版本信息

```bash
loomgraph version
```

---

## 错误码定义

> 权威定义见 `src/loomgraph/cli/_common.py` 的 `ErrorCode` 类。下表为写作时快照。

| 错误码 | 说明 | 建议操作 |
|--------|------|----------|
| `CODEINDEX_NOT_FOUND` | codeindex 未安装 | `pip install ai-codeindex` |
| `CODEINDEX_FAILED` | codeindex 执行失败 | 检查 codeindex 输出 |
| `CODEINDEX_TIMEOUT` | codeindex 超时 | 尝试更小的目录 |
| `EMBEDDING_SERVICE_UNAVAILABLE` | Embedding 服务不可用 | 检查 embedding provider(默认本地 Ollama) |
| `EMBEDDING_FAILED` | Embedding 生成失败 | 检查输入格式 / provider 配置 |
| `EMBEDDING_NOT_INDEXED` | workspace 未在 embedding 开启时索引 | 用 `LOOMGRAPH_EMBEDDING__ENABLED=true` 重新 index |
| `DATABASE_CONNECTION_FAILED` | SQLite 打开失败 | 检查 `~/.loomgraph/` 可写 / db 文件未损坏 |
| `DATABASE_ERROR` | 存储操作错误 | 检查 workspace 状态 |
| `STORAGE_ERROR` | 存储层错误 | 检查 workspace 状态 |
| `INVALID_INPUT` | 输入格式错误 | 检查参数 / JSON 格式 |
| `FILE_NOT_FOUND` | 文件不存在 | 检查路径 |
| `DEPENDENCIES_MISSING` | 部分依赖不可用 | 见 status 输出 |
| `GIT_ERROR` | git 操作失败(非 git 仓 / ref 不存在) | 检查 git 仓库状态 / ref |
| `NO_CHANGES` | `update` 检测到无变更 | 正常,无需操作 |

---

## 使用示例

### AI Agent 一键执行

```bash
# 一键完成所有步骤
loomgraph index /path/to/repo
```

### 错误恢复示例

```bash
# 如果 index 失败,AI 可以分步调试
$ loomgraph index /repo
{"success": false, "error": {"code": "CODEINDEX_NOT_FOUND", ...}}

# AI 根据错误信息安装依赖
$ pip install ai-codeindex

# 重新执行
$ loomgraph index /repo
{"success": true, ...}
```

---

## 环境变量

> 配置权威见 README "Configuration" 段。环境变量用 `LOOMGRAPH_<SECTION>__<KEY>` 双下划线层级。
> 文件配置走 `.loomgraph.yaml`(当前目录)或 `~/.config/loomgraph/config.yaml`。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LOOMGRAPH_EMBEDDING__ENABLED` | 启用语义搜索向量索引 | `false` |
| `LOOMGRAPH_EMBEDDING__API_URL` | OpenAI-compatible embedding endpoint | `http://localhost:11434/v1`(Ollama) |
| `LOOMGRAPH_EMBEDDING__MODEL` | embedding 模型 | `nomic-embed-text` |
| `LOOMGRAPH_LLM__API_URL` | LLM endpoint(仅 overview summary) | `http://localhost:11434`(Ollama) |
| `LOOMGRAPH_LLM__MODEL` | LLM 模型 | `gemma3:12b-it-qat` |

> v0.11+ 起 LightRAG / PostgreSQL / Jina / Docker embedding 全部退役(ADR-013)。
> 历史的 `LOOMGRAPH_DB_URL`(PostgreSQL)/ `LOOMGRAPH_EMBEDDING_URL`(旧格式)已无效。
