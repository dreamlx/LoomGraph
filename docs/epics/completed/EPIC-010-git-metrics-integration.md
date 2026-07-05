# EPIC-010: Git × 知识图谱时空融合

**状态**: Planning
**优先级**: High
**版本**: v0.10.0 - v0.11.0
**Epic Owner**: AI Agent
**ADR**: [ADR-015](../adr/ADR-015-git-knowledge-graph-integration.md)

---

## 概述

为技术债务分析引入**时间维度**（Git 历史），与现有**空间维度**（知识图谱）融合，实现：
1. **Hotspot 检测**：高频变更 × 高耦合 = 系统脆弱点
2. **置信度评估**：Orphan 是否真死代码（基于 last_modified_days）
3. **腐化预警**：复杂度增长趋势（代码正在恶化）
4. **团队风险**：知识孤岛（总线因子 = 1）

**核心价值**：
- **预防 > 治疗**：Hotspot 识别避免生产事故
- **精准 > 噪音**：假阳性从 99 → 3（置信度过滤）
- **趋势 > 快照**：预警窗口（趁未失控时重构）

---

## 背景与动机

### 问题

**E2E 试用反思**（LoomGraph v0.9.0 自我分析）发现：

1. **28 个 god functions**：无法区分"正在腐化"vs"稳定复杂"
   ```
   UserService.authenticate: 35 out-degree
   → 是长期复杂？还是最近 3 个月从 15 暴涨到 35？
   ```

2. **99 个 orphans**：假阳性过多（数据类、新代码）
   ```
   LegacyAnalyzer: 0 in-degree, 0 out-degree
   → 是死代码？还是新写的（还没被调用）？
   ```

3. **无法回答**："哪些模块最危险？"
   ```
   需要：change_frequency × coupling
   当前：只有 coupling（空间）
   ```

### 业界参考

**CodeScene**（Adam Tornhill）：
- 商业产品，核心算法 = git log × 代码复杂度
- 书籍：*Your Code as a Crime Scene*
- 核心理念：**Hotspot = 犯罪现场**（高频出事的地方）

**LoomGraph 优势**：
- 我们有**知识图谱**（比单纯复杂度更精准）
- 我们有 **LightRAG 向量检索**（可查询 "频繁变更的高耦合模块"）
- 我们可以做得**比 CodeScene 更好**！

---

## Feature 分解

### Feature 1: GitMetricsAnalyzer 基础模块（v0.10.0）

**目标**: 提取 Git 历史维度指标

**新增组件**:
- `src/loomgraph/core/git_metrics.py` — 主逻辑
- `src/loomgraph/core/git_parser.py` — git log 解析器
- `tests/unit/test_git_metrics.py` — 单元测试

**核心 API**:
```python
class GitMetricsAnalyzer:
    def analyze(self) -> GitMetricsResult:
        """提取 Git 维度指标."""
        return GitMetricsResult(
            file_metrics={...},  # 按 source_id 索引
            hotspots=[...],      # 高频变更文件
            bus_factor=[...],    # 知识孤岛
        )
```

**独立 CLI**（调试用）:
```bash
loomgraph git-metrics ./src --since="3 months" --output metrics.json
```

**数据结构**:
```python
@dataclass
class FileMetrics:
    change_frequency: int        # N 个月内提交次数
    last_modified_days: int      # 距今天数
    authors: list[str]           # 贡献者列表
    bug_fix_ratio: float         # bug fix / total commits
    lines_changed: int           # 总变更行数
```

**算法**:
1. **Hotspot Score** = change_freq × file_size / 1000
2. **Bus Factor** = 1 / (unique_contributors + 1)
3. **Bug Fix Ratio** = `git log --grep="fix|bug"` / total commits

**工作量**: 8 小时
- Git log 解析: 3h
- Hotspot / Bus Factor 算法: 3h
- 单元测试: 2h

**验收标准**:
- [ ] 支持 `--since` 参数（3 months / 6 months / 1 year）
- [ ] Hotspot 识别：change_freq > 20 的文件
- [ ] Bus Factor 识别：contributors = 1 的文件
- [ ] 性能：千级文件项目 <5 秒
- [ ] 测试覆盖：>85%

---

### Feature 2: DebtAnalyzer 三维评分集成（v0.10.0）

**目标**: 将 Git 维度融入技术债务分析

**修改组件**:
- `src/loomgraph/core/debt_analyzer.py` — Join 逻辑
- `src/loomgraph/cli/_debt.py` — CLI 参数

**新增 CLI 参数**:
```bash
loomgraph debt \
  --codeindex-data debt.json \
  --with-git \                # 启用 Git 分析（默认关闭）
  --git-since "3 months"      # 时间窗口
```

**新增 Issue 类别**:
1. **`critical_hotspot`** (P0)
   ```json
   {
     "severity": "P0",
     "category": "critical_hotspot",
     "entity": "UserService.authenticate",
     "metrics": {
       "change_frequency": 50,
       "in_degree": 120,
       "hotspot_score": 95
     },
     "suggestion": "⚠️ Critical hotspot: 50 changes + 120 callers = refactor ASAP"
   }
   ```

2. **`knowledge_silo`** (P1)
   ```json
   {
     "severity": "P1",
     "category": "knowledge_silo",
     "entity": "CriticalModule",
     "metrics": {
       "owner": "alice",
       "contributors": 1,
       "in_degree": 80
     },
     "suggestion": "Only alice knows this code. Add documentation."
   }
   ```

**增强现有 Issue**:
- `orphan_entity`: 添加 `confidence` 字段
  ```json
  {
    "category": "orphan_entity",
    "entity": "LegacyAnalyzer",
    "confidence": "high",  // ← 新增（基于 last_modified_days）
    "metrics": {
      "last_modified_days": 400
    }
  }
  ```

- `god_function`: 添加 `is_hotspot` 标记
  ```json
  {
    "category": "god_function",
    "entity": "process_data",
    "is_hotspot": true,  // ← 新增（change_freq > 10）
    "severity": "P0"     // ← 升级（原 P1 → P0）
  }
  ```

**三维评分**:
```python
total_score = (quality_score + topology_score + git_score) // 3

# 示例：
# quality: 50 (codeindex)
# topology: 65 (graph)
# git: 20 (发现严重 hotspot)
# → total: (50 + 65 + 20) // 3 = 45
```

**工作量**: 6 小时
- DebtAnalyzer Join 逻辑: 3h
- 置信度 / Hotspot 计算: 2h
- 集成测试: 1h

**验收标准**:
- [ ] `--with-git` 参数工作正常
- [ ] 新增 2 个 Issue 类别（hotspot, silo）
- [ ] Orphan 置信度正确（high/medium/low）
- [ ] God function hotspot 标记正确
- [ ] 三维评分准确
- [ ] 测试覆盖：>85%

---

### Feature 3: 代码腐化趋势分析（v0.11.0）

**目标**: 检测复杂度随时间增长（预警窗口）

**新增组件**:
- `src/loomgraph/core/trends.py` — 趋势分析器
- `src/loomgraph/cli/_trends.py` — CLI 命令

**历史数据存储**:
```
~/.loomgraph/metrics-history/
├── 2026-01-01.json
├── 2026-02-01.json
├── 2026-03-01.json
└── latest.json -> 2026-03-01.json
```

**新增 CLI**:
```bash
loomgraph trends --entity "UserService" --months 6
```

**输出示例**:
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

**检测算法**:
```python
def detect_code_rot(timeline: dict) -> str:
    """线性回归检测腐化趋势."""
    values = [v["out_degree"] for v in timeline.values()]
    slope = linear_regression(values)

    if slope > 5:      # 每月增长 >5 out-degree
        return "rotting"
    elif slope > 2:
        return "degrading"
    else:
        return "stable"
```

**新增 Issue 类别**:
```json
{
  "severity": "P1",
  "category": "code_rot",
  "entity": "UserService.authenticate",
  "trend": "rotting",
  "metrics": {
    "slope": 6.7,
    "6_months_ago": 15,
    "current": 35,
    "growth": "+133%"
  },
  "suggestion": "Code is rotting (+133% in 6 months). Refactor before it's too late."
}
```

**工作量**: 10 小时
- 历史数据存储逻辑: 4h
- 线性回归算法: 3h
- ASCII 图表可视化: 3h

**验收标准**:
- [ ] 历史数据自动保存（每次 `loomgraph debt` 运行）
- [ ] 支持 6 个月回溯
- [ ] 腐化检测准确（slope > 5 = rotting）
- [ ] ASCII 图表清晰
- [ ] 测试覆盖：>80%

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| **Git 解析** | `git log --format=...` | 标准 git 命令 |
| **数据缓存** | JSON 文件 | `~/.loomgraph/cache/git-metrics.json` |
| **历史存储** | JSON 文件 | `~/.loomgraph/metrics-history/` |
| **趋势算法** | NumPy / 自实现 | 线性回归（最小二乘法） |
| **图表** | ASCII Art | 轻量级可视化 |

**依赖变更**:
```toml
# pyproject.toml
[project.optional-dependencies]
trends = ["numpy>=1.24"]  # 可选依赖（仅 Feature 3）
```

---

## 数据流

### Feature 1-2 数据流（v0.10）

```
1. Git Log 提取
   └─> git log --since="3 months" --format="%H|%an|%at|%s"
   └─> 解析为 FileMetrics

2. 缓存存储
   └─> ~/.loomgraph/cache/git-metrics.json
   └─> TTL: 1 天

3. DebtAnalyzer Join
   └─> LightRAG entities + Git metrics
   └─> 按 source_id 匹配
   └─> 生成增强的 debt report
```

### Feature 3 数据流（v0.11）

```
1. 债务分析运行（每月）
   └─> loomgraph debt --with-git
   └─> 生成 report

2. 历史快照保存
   └─> ~/.loomgraph/metrics-history/2026-03-01.json
   └─> {entity_name: {out_degree, in_degree, ...}}

3. 趋势分析
   └─> loomgraph trends --entity "X"
   └─> 读取 6 个月历史数据
   └─> 线性回归 → 趋势判定
```

---

## 成功指标

### Feature 1（GitMetricsAnalyzer）

- [ ] **准确性**: Hotspot 识别 5-10 个真正高风险代码
- [ ] **性能**: Git 分析 <5 秒（千级文件项目）
- [ ] **覆盖**: 测试覆盖 >85%

### Feature 2（DebtAnalyzer 集成）

- [ ] **假阳性削减**: Orphan 假阳性从 99 → 3（置信度过滤）
- [ ] **风险识别**: Hotspot 检测精准（P0 优先级）
- [ ] **用户体验**: `--with-git` 参数直观易用

### Feature 3（趋势分析）

- [ ] **腐化检测**: 识别 3-5 个腐化趋势实体
- [ ] **预警价值**: 提前 1-2 个月发出重构建议
- [ ] **可视化**: ASCII 图表清晰易读

### 整体（EPIC 级别）

- [ ] **E2E 验证**: 在 LoomGraph 自身上验证（15 → 70 分提升）
- [ ] **文档完整**: ADR + Epic + README 更新
- [ ] **向后兼容**: 不破坏现有 `loomgraph debt` 命令

---

## Timeline

```
v0.10.0 (2 weeks)
├─ Week 1: Feature 1 (GitMetricsAnalyzer)
│  ├─ Day 1-2: git log 解析器
│  ├─ Day 3-4: Hotspot / Bus Factor 算法
│  └─ Day 5: 单元测试
│
└─ Week 2: Feature 2 (DebtAnalyzer 集成)
   ├─ Day 1-2: Join 逻辑
   ├─ Day 3: 置信度 / Hotspot 增强
   ├─ Day 4: 集成测试
   └─ Day 5: 文档 + E2E 验证

v0.11.0 (1 week)
└─ Feature 3: 趋势分析
   ├─ Day 1-2: 历史数据存储
   ├─ Day 3-4: 线性回归 + ASCII 图表
   └─ Day 5: 测试 + 文档
```

**关键里程碑**:
- v0.10.0-alpha: Feature 1 完成（独立 CLI 可用）
- v0.10.0-beta: Feature 2 完成（三维评分）
- v0.10.0: 正式发布（包含 Hotspot + 置信度）
- v0.11.0: 趋势分析发布

---

## 依赖关系

### 内部依赖

- ✅ **ADR-012**（技术债务分析框架）— 已完成
- ✅ **EPIC-009**（拓扑债务分析）— 已完成
- 🔄 **core/git.py** — 现有 Git 工具函数（复用）

### 外部依赖

- **Git 版本**: >= 2.0（检测 `git --version`）
- **Python**: >= 3.11（现有要求）
- **NumPy** (可选): >= 1.24（仅 Feature 3 趋势分析）

### 阻塞风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Git 历史过大（>10w commits） | 中 | 性能 | 增量分析（只看 N 个月） |
| Monorepo 性能 | 低 | 性能 | 按 module 过滤 |
| NumPy 依赖冲突 | 低 | Feature 3 | 可选依赖 + 自实现 fallback |

---

## 测试策略

### 单元测试

```
tests/unit/
├── test_git_metrics.py       # Feature 1
│   ├── test_parse_git_log
│   ├── test_calculate_hotspot_score
│   ├── test_calculate_bus_factor
│   └── test_bug_fix_ratio
│
├── test_debt_analyzer.py     # Feature 2 (现有文件扩展)
│   ├── test_analyze_with_git
│   ├── test_enrich_orphan_confidence
│   └── test_enrich_god_hotspot
│
└── test_trends.py            # Feature 3
    ├── test_detect_code_rot
    ├── test_linear_regression
    └── test_ascii_chart
```

### 集成测试

```
tests/integration/
├── test_git_metrics_command.py
│   └── test_git_metrics_cli_output
│
└── test_debt_with_git.py
    ├── test_debt_with_git_flag
    ├── test_hotspot_detection
    └── test_confidence_filtering
```

### E2E 验证

```bash
# 1. 在 LoomGraph 自身上运行
cd /path/to/LoomGraph
codeindex tech-debt ./src > debt.json

# 2. 不带 Git（对比基准）
loomgraph debt --codeindex-data debt.json

# 3. 带 Git（验证增强）
loomgraph debt --codeindex-data debt.json --with-git

# 4. 验证改进
# - Hotspot 识别：5-10 个
# - Orphan 假阳性：99 → 3
# - 总分提升：15 → 45+
```

---

## 文档更新

### 需要更新的文档

1. **CLAUDE.md**
   - 新增 Git × 图谱集成说明
   - 更新 CLI 命令速查表

2. **docs/api/CLI_DESIGN.md**
   - 新增 `git-metrics` 命令
   - 更新 `debt` 命令参数
   - 新增 `trends` 命令（v0.11）

3. **README.md**
   - 更新特性列表
   - 新增使用示例

4. **CHANGELOG.md**
   - v0.10.0: Feature 1-2
   - v0.11.0: Feature 3

---

## 风险与缓解

### 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Git 解析错误（特殊字符） | 中 | 功能失效 | 健壮的解析器 + 错误处理 |
| 性能问题（大仓库） | 中 | 用户体验 | 缓存 + 增量分析 + 并行 |
| Hotspot 误报 | 中 | 假阳性 | 分层阈值 + 白名单 |

### 业务风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 用户困惑（三维评分） | 低 | 采用率 | `--with-git` 默认关闭 + 文档 |
| 非 git 项目不适用 | 低 | 兼容性 | 自动检测 + graceful fallback |

---

## 参考资料

### 书籍

- Adam Tornhill: *Your Code as a Crime Scene* (2015)
- Adam Tornhill: *Software Design X-Rays* (2018)

### 工具

- CodeScene: https://codescene.com
- git-quick-stats: https://github.com/arzzen/git-quick-stats

### 算法

- Hotspot Analysis: https://www.codescene.com/hubfs/web_docs/hotspot-analysis.pdf
- Linear Regression: https://en.wikipedia.org/wiki/Simple_linear_regression

---

## 状态跟踪

**EPIC 状态**: Planning → In Progress → Done

**Feature 状态**:
- [ ] Feature 1: GitMetricsAnalyzer (v0.10.0)
- [ ] Feature 2: DebtAnalyzer 集成 (v0.10.0)
- [ ] Feature 3: 趋势分析 (v0.11.0)

**GitHub Issue**: #TBD（待创建）
**GitHub Milestone**: v0.10.0, v0.11.0

---

**创建日期**: 2026-03-06
**最后更新**: 2026-03-06
**更新者**: AI Agent
