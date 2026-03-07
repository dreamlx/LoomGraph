# EPIC-009: 图谱拓扑债务分析 — 知识图谱驱动的坏味道检测

**状态**: 📋 规划中
**优先级**: P1
**版本**: v0.7.1
**前置依赖**:
- EPIC-008 find/query/graph 三分 ✅
- EPIC-004 deps/overview ✅
- EPIC-007 Skill A (debt-radar) ✅
**跨仓库依赖**:
- LightRAG: 4 个图分析 API endpoint ([dreamlx/LightRAG#1](https://github.com/dreamlx/LightRAG/issues/1)) — 并行开发

---

## 背景

### 问题

LoomGraph 已有的技术债务分析存在维度盲区：

1. **codeindex tech-debt 是"显微镜"**: 只看单文件结构（LOC、方法数、噪音比），对我们这种重构后的项目报告 0 issues / 100 分
2. **Skill A (debt-radar) 是数据的搬运工**: 收集 codeindex + deps + overview 数据，交给 LLM 综合分析，但缺少图谱拓扑维度的专用数据
3. **知识图谱的关系网络未被分析**: 586 个实体 + 952 条关系蕴含丰富的拓扑信号，目前无命令可直接提取

### dogfooding 发现

对 LoomGraph 自身运行图谱分析，codeindex 全绿的情况下，知识图谱发现：

| 发现 | 数量 | codeindex 能检测？ |
|------|:---:|:---:|
| 孤岛实体 (0 in + 0 out, 非 module) | 46 | No |
| 上帝函数 (>=5 callees) | 72 | Partial |
| 过时索引 (source_id 指向旧文件) | 34 | No |
| 占位模块 (只有 __init__) | 3 | No |
| Hub 脆弱点 (>=5 callers) | 28 | No |
| 僵尸代码 (已弃用但仍在图谱) | 1+ | No |

### 核心洞见

```
codeindex = 显微镜 → 看单个文件的细胞结构 (LOC, 方法数, 噪音比)
知识图谱  = 望远镜 → 看实体间的关系网络 (拓扑, 耦合, 演化)
```

两者互补，而非替代。当前 Skill A 只用了显微镜，需要加上望远镜。

---

## 设计：三层增强

```
┌─────────────────────────────────────────────────────────┐
│                    增强层次                              │
├──────────┬──────────────────┬──────────────────────────┤
│  CLI 层  │  loomgraph       │  图谱拓扑指标计算          │
│          │  topology        │  orphans/hubs/god/coupling │
├──────────┼──────────────────┼──────────────────────────┤
│  CLI 层  │  loomgraph       │  索引新鲜度检查            │
│          │  check           │  source_id vs 磁盘文件     │
├──────────┼──────────────────┼──────────────────────────┤
│  Skill层 │  debt-radar      │  集成拓扑维度              │
│          │  增强             │  报告模板 + 评分体系扩展   │
└──────────┴──────────────────┴──────────────────────────┘
```

---

## Feature 1: `loomgraph topology` — 图谱拓扑分析命令

### 命令接口

```bash
# 完整拓扑分析
loomgraph topology

# 调整阈值
loomgraph topology --hub-threshold 5 --god-threshold 5

# 指定 workspace
loomgraph topology -w my-project
```

### 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--hub-threshold` | Hub 实体的最小 in-degree | `5` |
| `--god-threshold` | God Function 的最小 out-degree | `5` |
| `--module` | 模块级分治（source_id 前缀过滤） | 全部 |
| `--workspace/-w` | Workspace 名称 | 当前目录名 |

### 输出格式

```json
{
  "success": true,
  "data": {
    "summary": {
      "total_entities": 586,
      "total_relations": 952,
      "orphan_count": 46,
      "hub_count": 28,
      "god_function_count": 72,
      "placeholder_module_count": 3,
      "coupling_density": 0.35,
      "topology_score": 62
    },
    "orphans": [
      {
        "entity": "ChangedFile",
        "type": "class",
        "source_id": "core/impact/models.py:10-15",
        "category": "data_class"
      }
    ],
    "hubs": [
      {
        "entity": "output_success",
        "type": "function",
        "source_id": "cli/_common.py:88-93",
        "in_degree": 18,
        "callers_sample": ["index", "update", "find", "graph", "deps"]
      }
    ],
    "god_functions": [
      {
        "entity": "_async_index_pipeline",
        "type": "function",
        "source_id": "cli/_indexing.py:...",
        "out_degree": 28,
        "callees_sample": ["collect_kg_data", "LightRAGClient.__init__", "inject_parse_result"]
      }
    ],
    "placeholder_modules": [
      {
        "module": "chunking",
        "entities": ["chunking.__init__"],
        "status": "empty"
      }
    ],
    "coupling": {
      "density": 0.35,
      "cross_module_relations": 21,
      "intra_module_relations": 931,
      "most_coupled_pairs": [
        {"from": "cli", "to": "core", "count": 19}
      ]
    }
  }
}
```

### 拓扑分数计算 (topology_score: 0-100, 越高越健康)

```
topology_score = 100 - penalties

penalties:
  - orphan_ratio > 10%        → -15
  - orphan_ratio > 20%        → -25
  - hub (in_degree >= 15)      → -5 per entity
  - god_function (out >= 20)   → -5 per entity
  - god_function (out >= 10)   → -3 per entity
  - placeholder_modules > 0    → -5 per module
  - coupling_density > 0.5     → -10
  - coupling_density > 0.3     → -5
```

### 实现要点

- **双模式**: 优先调用 LightRAG 服务端 endpoint (O(1) 数据传输)，降级为客户端全量计算
- **`--module` 分治**: 传 `source_prefix` 参数给 LightRAG API，仅分析目标模块
- orphan 检测排除 `module` 类型（module 实体天然无调用关系）
- hub/god_function 排除标准库调用（`len`, `str`, `isinstance` 等）
- coupling_density = cross_module_relations / total_relations

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F1-S1 | 实现 `TopologyAnalyzer.analyze_from_data()` core 模块（纯函数，无 I/O） | 1d |
| F1-S2 | 实现 `topology` CLI 命令 + `--module` 参数 + 输出格式 | 0.5d |
| F1-S3 | 标准库实体过滤（排除 `len`, `str` 等噪音） | 0.5d |
| F1-S4 | `LightRAGClient` 新增 4 个方法 + `TopologyAnalyzer._analyze_server_side()` | 0.5d |
| F1-S5 | 单元测试（15+ tests，纯 mock） | 0.5d |

---

## Feature 2: `loomgraph check` — 索引新鲜度检查

### 命令接口

```bash
# 检查索引新鲜度
loomgraph check

# 指定项目路径（用于 source_id 验证）
loomgraph check --repo-path /path/to/repo

# 指定 workspace
loomgraph check -w my-project
```

### 输出格式

```json
{
  "success": true,
  "data": {
    "freshness": {
      "total_source_ids": 150,
      "valid": 116,
      "stale": 34,
      "freshness_ratio": 0.773
    },
    "stale_entries": [
      {
        "entity": "ErrorCode",
        "source_id": "cli/main.py:66-81",
        "reason": "file_restructured",
        "suggestion": "Run 'loomgraph update' or 'loomgraph index --clear .'"
      }
    ],
    "suggestion": "34 entities have stale source_ids. Run 'loomgraph index --clear .' to rebuild."
  }
}
```

### 实现要点

- 优先调用 `LightRAGClient.get_source_ids()` 获取去重路径列表（轻量，无需全量实体）
- 降级为 `get_all_entities()` → 提取 source_id 字段
- 提取文件路径部分（去除行号 `:10-20`），验证是否存在于磁盘
- 统计比率，给出刷新建议
- `--repo-path` 用于 source_id 的基准路径（默认 cwd）

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F2-S1 | 实现 `check` CLI 命令 + source_id 验证逻辑 | 0.5d |
| F2-S2 | 单元测试 | 0.5d |

---

## Feature 3: 增强 Skill A (debt-radar)

### 当前 Skill A 步骤

```
Step 1: codeindex tech-debt    → 文件级债务
Step 2: loomgraph deps         → 模块依赖
Step 3: loomgraph overview     → 模块概览
Step 4: loomgraph workspace    → 统计信息
Step 5: LLM 综合分析           → 报告
```

### 增强后 Skill A 步骤

```
Step 1: codeindex tech-debt    → 文件级债务        (不变)
Step 2: loomgraph deps         → 模块依赖          (不变)
Step 3: loomgraph overview     → 模块概览          (不变)
Step 4: loomgraph workspace    → 统计信息          (不变)
Step 5: loomgraph topology     → 图谱拓扑分析      (新增)
Step 6: loomgraph check        → 索引新鲜度        (新增)
Step 7: LLM 综合分析           → 增强版报告        (改进)
```

### LLM 分析维度扩展

**当前维度** (3 维):
1. 文件级债务 (codeindex)
2. 依赖耦合 (deps)
3. 职责清晰度 (overview)

**增强维度** (7 维):

| 维度 | 数据源 | 坏味道示例 |
|------|--------|-----------|
| 文件级债务 | codeindex tech-debt | God Class, 超大文件 |
| 依赖耦合 | loomgraph deps | 循环依赖, 高 fan-out |
| 职责清晰度 | loomgraph overview | 模块职责不清 |
| **拓扑健康度** | loomgraph topology | 孤岛实体, Hub 脆弱, God Function |
| **死代码率** | topology.orphans | 未被引用的实体占比 |
| **耦合密度** | topology.coupling | 跨模块关系 vs 模块内关系 |
| **索引新鲜度** | loomgraph check | 过时的 source_id |

### 增强版评分体系

**模块健康度打分 (0-100, 越高越差)**:

```
文件级债务 (来自 codeindex):
  - God Class:        +30
  - 超大文件:         +25
  - 高噪音比:         +15
  - 符号过载:         +10

依赖耦合 (来自 deps):
  - 循环依赖:         +25
  - fan_out > 5:      +15
  - fan_in > 8:       +10

拓扑问题 (来自 topology):          ← 新增
  - orphan_ratio > 15%: +20
  - hub entity (in >= 15): +15
  - god_function (out >= 20): +15
  - god_function (out >= 10): +10

索引新鲜度 (来自 check):           ← 新增
  - freshness < 80%:    +10
  - freshness < 50%:    +20
```

### 增强版报告模板

在现有报告基础上新增两个章节：

```markdown
## 图谱拓扑分析

### 拓扑健康分 (topology_score)

| 指标 | 值 | 评级 |
|------|-----|------|
| 拓扑健康分 | {score}/100 | {rating} |
| 孤岛实体占比 | {orphan_ratio}% | {status} |
| Hub 脆弱点 | {hub_count} 个 | {status} |
| 上帝函数 | {god_count} 个 | {status} |
| 耦合密度 | {coupling_density} | {status} |

### 孤岛实体 (潜在死代码)

> 以下实体在知识图谱中没有任何调用关系（0 callers + 0 callees），
> 可能是死代码、仅被测试引用、或解析遗漏。

| 实体 | 类型 | 文件 | 建议 |
|------|------|------|------|
| {entity} | {type} | {source_id} | {suggestion} |

### Hub 实体 (单点故障风险)

> 被大量其他实体依赖的实体。修改它们会产生广泛的涟漪效应。

| 实体 | 类型 | 被依赖数 | 主要调用者 | 风险等级 |
|------|------|----------|-----------|---------|

### 上帝函数 (职责过重)

> 调用大量其他实体的函数，可能承担了过多职责。

| 实体 | 类型 | 调用数 | 主要调用目标 | 建议 |
|------|------|--------|-------------|------|

## 索引新鲜度

| 指标 | 值 |
|------|-----|
| Source ID 总数 | {total} |
| 有效 | {valid} |
| 过时 | {stale} |
| 新鲜度 | {ratio}% |

> {freshness_advice}
```

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| F3-S1 | 更新 SKILL.md：新增 Step 5 (topology) + Step 6 (check) | 0.5d |
| F3-S2 | 扩展 LLM 分析维度和评分体系 | 0.5d |
| F3-S3 | 增强报告模板（拓扑 + 新鲜度章节） | 0.5d |

---

## 技术方案

### 规模化挑战

当前 `get_all_entities()` + `get_all_relations()` 全量下载模式在大项目上不可行：

| 项目规模 | 实体数 | 关系数 | 全量下载数据量 | 可接受？ |
|----------|--------|--------|--------------|:---:|
| LoomGraph (当前) | 586 | 952 | ~100KB | ✅ |
| 中型项目 (10 万行) | ~5K | ~15K | ~5MB | ✅ |
| 大型项目 (100 万行) | ~50K | ~200K | ~50MB | ⚠️ |
| Chrome 级 (3500 万行) | ~500K+ | ~2M+ | ~500MB+ | ❌ OOM |

**解法**: 把计算推到 LightRAG/PostgreSQL 侧，不下载原始数据。

```
当前:  CLI → GET /graph/entities/all → 500MB JSON → Python 计算 → 结果
优化:  CLI → GET /graph/orphans      → 5KB JSON   → 直接输出
            GET /graph/degree         → 10KB JSON
            GET /graph/stats          → 1KB JSON
```

### 并行开发: LightRAG 新增 4 个 endpoint

LightRAG 使用 Apache AGE (PostgreSQL 图扩展)，已有索引，新增 endpoint 复杂度低。

详见 LightRAG Issue: [dreamlx/LightRAG - Graph Analytics API](https://github.com/dreamlx/LightRAG)

| Endpoint | SQL 核心 | 数据量 | 复杂度 |
|----------|---------|--------|--------|
| `GET /graph/orphans` | NOT EXISTS × 2 | 仅孤岛实体 | 低 |
| `GET /graph/degree` | GROUP BY + HAVING | 仅超阈值实体 | 低 |
| `GET /graph/stats` | COUNT + 模块前缀提取 | 1 条记录 | 低 |
| `GET /graph/source_ids` | DISTINCT source_id | 去重路径列表 | 极低 |

**参数设计**:
- `source_prefix` — 模块级分治（如 `cli/` 只分析 CLI 模块）
- `exclude_types` — 排除类型（如 `module`）
- `min_degree` / `direction` — degree endpoint 的阈值和方向

### 新增模块

```
src/loomgraph/
├── core/
│   └── topology.py          # TopologyAnalyzer (新增)
├── cli/
│   ├── _analysis.py         # topology + check 命令 (扩展)
│   └── ...
```

### TopologyAnalyzer 双模式设计

```python
@dataclass
class TopologyResult:
    total_entities: int
    total_relations: int
    orphans: list[dict]        # 0 in + 0 out entities
    hubs: list[dict]           # high in-degree entities
    god_functions: list[dict]  # high out-degree entities
    placeholder_modules: list[dict]
    coupling: CouplingMetrics
    topology_score: int        # 0-100

class TopologyAnalyzer:
    def __init__(self, hub_threshold=5, god_threshold=5, stdlib_filter=True):
        ...

    async def analyze(self, client: LightRAGClient) -> TopologyResult:
        """Auto-select server-side or client-side computation."""
        try:
            return await self._analyze_server_side(client)
        except (LightRAGAPIError, KeyError):
            # Fallback for older LightRAG without graph analytics endpoints
            logger.info("Server-side topology not available, falling back to client-side")
            entities = await client.get_all_entities()
            relations = await client.get_all_relations()
            return self.analyze_from_data(entities, relations)

    async def _analyze_server_side(self, client):
        """4 parallel API calls, each returns small JSON. Scales to any project size."""
        orphans, hubs, gods, stats = await asyncio.gather(
            client.get_orphan_entities(exclude_types=["module"]),
            client.get_degree_distribution(direction="in", min_degree=self.hub_threshold),
            client.get_degree_distribution(direction="out", min_degree=self.god_threshold),
            client.get_graph_stats(),
        )
        return self._build_result(orphans, hubs, gods, stats)

    def analyze_from_data(self, entities, relations) -> TopologyResult:
        """Client-side computation from raw data. For testing and small projects."""
        ...
```

**关键设计**: `analyze_from_data()` 是纯函数（输入 entities/relations，输出 TopologyResult），便于单元测试无需 mock HTTP。

### LightRAGClient 新增方法

```python
class LightRAGClient:
    # 已有
    async def get_all_entities(self) -> list[dict]: ...
    async def get_all_relations(self) -> list[dict]: ...

    # 新增 (对接 LightRAG graph analytics endpoints)
    async def get_orphan_entities(self, exclude_types=None, source_prefix=None) -> list[dict]: ...
    async def get_degree_distribution(self, direction="in", min_degree=5, source_prefix=None) -> list[dict]: ...
    async def get_graph_stats(self, source_prefix=None) -> dict: ...
    async def get_source_ids(self) -> list[str]: ...
```

### topology 命令新增 --module 参数

```bash
loomgraph topology                    # 全局分析
loomgraph topology --module cli       # 只分析 cli 模块 (source_prefix 过滤)
loomgraph topology --module core      # 只分析 core 模块
```

`--module` 映射为 `source_prefix` 参数传递给 LightRAG API，实现模块级分治。

### 数据流

```
loomgraph topology (服务端模式, 默认)
  → LightRAGClient.get_orphan_entities()     ─┐
  → LightRAGClient.get_degree_distribution() ─┼─ 4 个并行 API 调用
  → LightRAGClient.get_degree_distribution() ─┤   每个返回 < 50KB
  → LightRAGClient.get_graph_stats()         ─┘
  → TopologyAnalyzer._build_result()
  → JSON output

loomgraph topology (降级模式, LightRAG 未升级时)
  → LightRAGClient.get_all_entities()
  → LightRAGClient.get_all_relations()
  → TopologyAnalyzer.analyze_from_data(entities, relations)
  → JSON output

loomgraph check
  → LightRAGClient.get_source_ids()   # 仅返回去重路径列表
  → 本地文件系统验证
  → JSON output

debt-radar Skill (增强版)
  → Step 1-4: (现有步骤)
  → Step 5: loomgraph topology (JSON)
  → Step 6: loomgraph check (JSON)
  → Step 7: LLM 综合分析 (7 维数据)
```

### 并行开发计划

```
LightRAG 仓库:                          LoomGraph 仓库:
──────────────                          ──────────────
Week 1:                                 Week 1:
  graph_routes.py:                        core/topology.py:
    GET /graph/orphans                      TopologyAnalyzer (analyze_from_data)
    GET /graph/degree                       纯函数，用 mock 数据测试
    GET /graph/stats                      cli/_analysis.py:
    GET /graph/source_ids                   topology + check 命令
  postgres_impl.py:                       tests/:
    4 条 SQL 查询                           单元测试 (20+ tests, 纯 mock)
  tests/:
    endpoint 测试

Week 2:                                 Week 2:
  └───── 集成测试 ─────┘                  LightRAGClient 新增 4 个方法
                                          TopologyAnalyzer._analyze_server_side()
                                          Skill A 增强
                                          dogfooding 验证
```

---

## 标准库实体过滤

orphan/hub/god 分析需要过滤标准库和内建函数，否则 `len`（25 callers）会被误报为 hub：

```python
STDLIB_ENTITIES = {
    # Python builtins
    "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "isinstance", "issubclass", "hasattr", "getattr", "setattr",
    "print", "range", "enumerate", "zip", "map", "filter",
    "super", "type", "object",
    # Common stdlib
    "logging", "asyncio", "json", "os", "sys", "pathlib",
    "asyncio.run", "json.dumps", "json.loads",
    # Common patterns
    "join", "append", "extend", "get", "items", "keys", "values",
    "strip", "split", "replace", "format", "encode", "decode",
}
```

同时，对 `*.get`、`*.append` 等通用方法调用（无法确定属于哪个类）标记为 `generic_method` 排除。

---

## 开发顺序

```
Feature 1 (topology)  ████████████████  核心：拓扑分析命令
Feature 2 (check)     ████████░░░░░░░░  新鲜度检查
Feature 3 (Skill A)   ████████████░░░░  Skill 增强
```

**建议顺序**: F1 → F2 → F3

F1 是核心工作（TopologyAnalyzer + CLI），F2 较轻量，F3 是 Skill 层集成（改 SKILL.md + 报告模板）。

---

## 验收标准

- [ ] `loomgraph topology` 返回 orphans / hubs / god_functions / coupling / topology_score
- [ ] `loomgraph topology --module cli` 模块级分治正常
- [ ] topology 分析排除标准库实体（`len`, `str` 等不计入 hub）
- [ ] topology_score 计算规则明确，可复现
- [ ] TopologyAnalyzer 双模式: 服务端优先，自动降级到客户端
- [ ] `loomgraph check` 验证 source_id 对应文件是否存在
- [ ] `loomgraph check` 对过时索引给出刷新建议
- [ ] LightRAG 4 个新 endpoint 可用 (`/graph/orphans`, `/graph/degree`, `/graph/stats`, `/graph/source_ids`)
- [ ] Skill A (debt-radar) 新增 Step 5 (topology) + Step 6 (check)
- [ ] Skill A 报告模板包含"图谱拓扑分析"和"索引新鲜度"章节
- [ ] LLM 分析评分体系从 3 维扩展到 7 维
- [ ] 现有 282+ 测试全部通过
- [ ] 新增 topology + check 单元测试（20+ tests）
- [ ] CLAUDE.md + CLI_DESIGN.md 已更新

---

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| orphan 误报 | 数据类/DTO 天然无调用关系，被标记为"死代码" | 按 type 分类（data_class / function / class），Skill 层 LLM 判断是否真正死代码 |
| hub 噪音 | 标准库函数 (`len`, `str`) 占据 hub 排行榜 | STDLIB_ENTITIES 白名单过滤 + `*.get` 等通用方法排除 |
| 全量数据拉取性能 | 大项目 get_all_entities + get_all_relations 可能慢/OOM | 双模式: 优先服务端计算 (4 个轻量 endpoint)，降级为客户端计算；`--module` 分治 |
| LightRAG 未升级 | 新 endpoint 不可用 | 自动降级到客户端全量计算 (中小项目仍可工作) |
| source_id 格式不统一 | `file.py:10-20` vs `module/file.py` | 提取文件路径部分时做 normalization |
| topology_score 评分权重 | 初始权重可能不合理 | dogfooding 调参，在报告中同时输出分项扣分明细 |

---

## 对 debt-radar 价值的核心提升

**改进前**: codeindex 全绿 → Skill A 报告 "项目健康，无技术债务" → 误导

**改进后**: codeindex 全绿 + topology 发现 46 个孤岛 + 72 个上帝函数 → Skill A 报告 "文件级健康，但图谱拓扑显示存在 X 个结构性问题" → 更准确的全景视图

> **一句话**: 让 Skill A 从 "文件医生" 升级为 "系统架构师"。
