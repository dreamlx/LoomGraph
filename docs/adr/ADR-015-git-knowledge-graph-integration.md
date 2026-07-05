# ADR-015: Git × 知识图谱时空融合架构

**状态**: Accepted
**日期**: 2026-03-06
**决策者**: AI Agent + User
**影响组件**: DebtAnalyzer, GitMetricsAnalyzer (new), CLI

> **编号说明（2026-07-05）**: 本决策最初被误编为 ADR-013（提交 8e03d39，2026-03-07），与
> EPIC-011 的「SQLite + sqlite-vec 替换 LightRAG」决策（提交 3658ac4，2026-06-25，同样占了
> ADR-013）发生编号碰撞。后者 supersede 了 ADR-001/002/010/011，被 `storage/*.py`、客户
> migration guide 与 ADR-014 广泛引用（~20 处），改号 blast radius 大；本决策仅在 4 个文档中
> 被引用，故改本决策为 **ADR-015** 以消歧。**决策日期不变（2026-03-06）**——因此 015 在时间上
> 早于 013/014，编号缺口反映的是碰撞修复，而非决策顺序。
>
> 另：本文档正文中「LightRAG 管图谱」的前提已被后来的 [ADR-013](ADR-013-sqlite-vec-replace-lightrag.md)
> 取代——图谱存储现为单文件 SQLite + sqlite-vec，GitMetrics × graph 的 Join 逻辑不变，只是落在
> SQLite store 上而非 LightRAG。

---

## 背景

### 问题

当前技术债务分析 (ADR-012) 仅提供**空间维度**（知识图谱拓扑），缺少**时间维度**（代码演化历史）：

1. **Hotspot 盲点**：无法识别"高频变更 + 高耦合"的系统脆弱点
2. **假阳性过多**：Orphan 实体可能是最近新增的代码（非死代码）
3. **缺少预警**：无法检测代码腐化趋势（复杂度随时间增长）
4. **团队风险盲区**：不知道总线因子（知识孤岛）

### E2E 试用反思发现

在 LoomGraph v0.9.0 自我分析中：
- 99 个 orphans → 实际只需关注长期未修改的（置信度高）
- 28 个 god functions → 无法区分"正在腐化"vs"稳定复杂"
- 无法回答："哪些模块最危险？"（需要 change_frequency × coupling）

---

## 决策

### 核心原则

**时空分离、后期融合**：Git 数据与知识图谱**独立存储**，在 `DebtAnalyzer` 层 Join。

### 架构选择

采用 **方案 B: 独立分析 + 后期 Join**（而非方案 A: 注入 LightRAG，或方案 C: 事件溯源）

**理由**：
1. **解耦**：Git 数据频繁变化（每次 commit），图谱相对稳定（增量更新）
2. **性能**：避免 LightRAG 存储膨胀（每个 entity +5 字段）
3. **灵活**：Git 分析是可选功能（`--with-git` flag）
4. **职责清晰**：LightRAG 管图谱，GitMetrics 管历史

### 数据流

```
┌─────────────┐     ┌──────────────┐
│ codeindex   │     │ git log      │
│ (AST 解析)   │     │ (历史提取)    │
└──────┬──────┘     └──────┬───────┘
       │                   │
       ↓                   ↓
┌─────────────┐     ┌──────────────┐
│ LightRAG    │     │ GitMetrics   │
│ (图谱存储)   │     │ (JSON 缓存)   │
└──────┬──────┘     └──────┬───────┘
       │                   │
       └────────┬──────────┘
                ↓
         ┌─────────────┐
         │ DebtAnalyzer│  ← Join 逻辑
         │ (多维评分)   │
         └─────────────┘
                ↓
         三维债务报告
    (quality + topology + git)
```

### 新增维度

| 维度 | 数据源 | 检测能力 |
|------|--------|----------|
| **Hotspot** | git change_frequency × graph in_degree | 高频变更 + 高耦合 = 脆弱点 |
| **置信度** | git last_modified_days | Orphan 是否真死代码 |
| **腐化趋势** | git 时间序列 + graph complexity | 复杂度增长预警 |
| **知识孤岛** | git shortlog + graph in_degree | 总线因子 = 1 的高风险模块 |
| **Bug 密度** | git log --grep="fix" / graph relations | 预测未来缺陷区 |

---

## 实施方案

### Phase 1: GitMetricsAnalyzer 基础模块（v0.10.0）

**新增文件**：
```
src/loomgraph/core/
├── git_metrics.py        # GitMetricsAnalyzer 主逻辑
└── git_parser.py         # git log 解析器（复用 git.py）

tests/unit/
└── test_git_metrics.py
```

**核心 API**：
```python
class GitMetricsAnalyzer:
    def __init__(self, repo_path: Path, since: str = "3 months"):
        pass

    def analyze(self) -> GitMetricsResult:
        """提取 Git 维度指标."""
        return GitMetricsResult(
            file_metrics={
                "src/auth/user_service.py:45-78": FileMetrics(
                    change_frequency=12,
                    last_modified_days=5,
                    authors=["alice", "bob"],
                    bug_fix_ratio=0.33,
                )
            },
            hotspots=[
                Hotspot(file="user_service.py", change_freq=50, lines=500)
            ],
            bus_factor=[
                BusFactor(file="critical.py", owner="alice", contributors=1)
            ]
        )
```

**独立 CLI**（调试用）：
```bash
loomgraph git-metrics ./src --since="3 months" --output metrics.json
```

### Phase 2: DebtAnalyzer 集成（v0.10.0）

**修改文件**：
- `src/loomgraph/core/debt_analyzer.py`
- `src/loomgraph/cli/_debt.py`

**新增参数**：
```bash
loomgraph debt \
  --codeindex-data debt.json \
  --with-git \                # 启用 Git 分析
  --git-since "3 months"      # 时间窗口
```

**Join 逻辑**：
```python
class DebtAnalyzer:
    async def analyze(
        self,
        codeindex_data: dict | None = None,
        module: str | None = None,
        with_git: bool = False,  # 新参数
        git_since: str = "3 months",
    ) -> dict:
        # 现有逻辑
        topology_score = await self._analyze_topology_issues(module)
        quality_score = self._analyze_quality_issues(codeindex_data)

        # 新增 Git 维度
        git_score = 100
        if with_git:
            git_analyzer = GitMetricsAnalyzer(Path.cwd(), since=git_since)
            git_metrics = git_analyzer.analyze()

            # 1. 生成 Git-based issues (hotspot, silo)
            git_score = self._analyze_git_issues(git_metrics)

            # 2. 增强现有 issues（添加置信度）
            self._enrich_with_git_metrics(git_metrics)

        # 三维评分
        total_score = (quality_score + topology_score + git_score) // 3

        return {
            "overall_health": {
                "total_score": total_score,
                "breakdown": {
                    "quality": quality_score,
                    "topology": topology_score,
                    "git": git_score,  # 新增
                }
            },
            "issues": self.issues,
        }
```

**新增 Issue 类别**：
- `critical_hotspot` (P0)
- `knowledge_silo` (P1)
- `code_rot` (P1) — 代码腐化趋势

**增强现有 Issue**：
- `orphan_entity`: 添加 `confidence` 字段（high/medium/low）
- `god_function`: 添加 `is_hotspot` 标记

### Phase 3: 趋势分析（v0.11.0）

**历史数据存储**：
```
~/.loomgraph/metrics-history/
├── 2026-01-01.json
├── 2026-02-01.json
├── 2026-03-01.json
└── latest.json -> 2026-03-01.json
```

**新增 CLI**：
```bash
loomgraph trends --entity "UserService" --months 6
```

**输出**：
```
UserService.authenticate
├─ 2025-10: out_degree=15
├─ 2025-11: out_degree=18
├─ 2025-12: out_degree=22
├─ 2026-01: out_degree=28
├─ 2026-02: out_degree=32
└─ 2026-03: out_degree=35  ⚠️ Trend: +133% in 6 months (rotting)

Recommendation: Refactor NOW (still salvageable)
```

---

## 数据结构设计

### GitMetricsResult

```python
@dataclass
class FileMetrics:
    """单文件的 Git 指标."""
    change_frequency: int        # N 个月内提交次数
    last_modified_days: int      # 距今天数
    authors: list[str]           # 贡献者列表
    bug_fix_ratio: float         # bug fix / total commits
    lines_changed: int           # 总变更行数
    created_at: datetime         # 首次创建时间

@dataclass
class Hotspot:
    """高频变更热点."""
    file: str
    change_freq: int
    lines: int
    hotspot_score: int  # 0-100

@dataclass
class BusFactor:
    """知识孤岛 / 总线因子."""
    file: str
    owner: str          # 主要维护者
    contributors: int   # 贡献者数量
    ownership_ratio: float  # 主要维护者占比

@dataclass
class GitMetricsResult:
    """Git 分析结果."""
    file_metrics: dict[str, FileMetrics]  # 按 source_id 索引
    hotspots: list[Hotspot]
    bus_factor: list[BusFactor]
    summary: dict[str, Any]
```

### 增强的 DebtIssue

```python
@dataclass
class DebtIssue:
    # 现有字段
    id: str
    severity: str
    category: str
    entity: str
    # ...

    # 新增字段（Git 维度）
    confidence: str | None = None        # high/medium/low (for orphans)
    is_hotspot: bool = False             # (for god functions)
    trend: str | None = None             # "increasing" / "stable" / "decreasing"
    git_metrics: dict[str, Any] | None = None  # 原始 git 数据
```

---

## 技术约束

### 1. Git 仓库必需

- 非 git 项目：Git 分析自动跳过（不报错）
- 检测逻辑：`git rev-parse --is-inside-work-tree`

### 2. 性能考虑

- **缓存机制**：Git metrics 缓存 1 天（避免重复解析）
- **增量分析**：只分析最近 N 个月（默认 3 个月）
- **并行处理**：git log 解析可并行（按文件）

### 3. 兼容性

- Git 版本要求：>= 2.0
- 支持所有 git 托管平台（GitHub, GitLab, Bitbucket）

---

## 替代方案及对比

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **A: 注入 LightRAG** | 统一查询，向量检索跨维度 | 存储膨胀，职责混乱，频繁更新 | ❌ 过度耦合 |
| **B: 独立分析 + Join** | 解耦，灵活，性能好 | 两次扫描，Join 在应用层 | ✅ **推荐** |
| **C: 事件溯源** | 任意时间窗口，实时更新 | 存储成本高，实现复杂 | ❌ 过度设计 |

---

## 风险评估

### 技术风险

1. **Git 历史过大**（数万 commits）
   - 缓解：增量分析（只看 N 个月）
   - 缓解：缓存机制（避免重复解析）

2. **Monorepo 性能**
   - 缓解：按 module 过滤（git log -- src/module/）
   - 缓解：并行处理

### 业务风险

1. **假阳性**（Hotspot 误报）
   - 缓解：分层阈值（不同目录不同标准）
   - 缓解：白名单机制

2. **用户困惑**（新维度复杂）
   - 缓解：`--with-git` 默认关闭（可选功能）
   - 缓解：文档 + 示例

---

## 成功指标

### Phase 1-2（v0.10）

- [ ] Hotspot 检测：识别 5-10 个真正高风险代码
- [ ] 假阳性削减：Orphan 假阳性从 99 → 3（置信度过滤）
- [ ] 性能：Git 分析 <5 秒（千级文件项目）
- [ ] 测试覆盖：>85%

### Phase 3（v0.11）

- [ ] 趋势分析：检测 3-5 个腐化趋势
- [ ] 历史数据：支持 6 个月回溯
- [ ] 可视化：ASCII 图表（趋势线）

---

## 参考

### 业界实践

- **CodeScene**: git × 复杂度商业化成功案例
- **SonarQube**: New Code Definition 基于 git
- **GitHub Advanced Security**: git blame 显示漏洞引入者

### 学术研究

- Adam Tornhill: *Your Code as a Crime Scene* (2015)
- Michele Lanza: *The Evolution Matrix* (2001)

### 算法

- Hotspot Score = change_frequency × (in_degree + out_degree) / 10
- Bus Factor = 1 / (unique_contributors + 1)
- Code Churn = lines_added + lines_deleted

---

## 决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-03-06 | 采用独立分析 + Join | 解耦、性能、灵活性平衡 |
| 2026-03-06 | Git 分析作为可选功能 | 避免强依赖，支持非 git 项目 |
| 2026-03-06 | 三维评分（quality + topology + git） | 全面评估技术债务 |
| 2026-03-06 | Phase 1-2 优先（v0.10） | 快速验证价值（Hotspot + 置信度） |

---

## 状态

**当前**: Accepted（2026-03-06）
**下一步**: 创建 EPIC-010 并开始实施
