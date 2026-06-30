---
name: loomgraph-debt-radar
description: Generate a comprehensive technical debt audit report combining static analysis, knowledge graph topology, Git history metrics, and trend prediction
disable-model-invocation: true
argument-hint: "[source-path]"
---

> ⚠️ **DEPRECATED in v0.12.1 — will be REMOVED in v0.13.0**
>
> Superseded by the MCP tool **`loomgraph_debt_audit`** in `loomgraph>=0.12.1`.
> The MCP tool runs all dimensions in parallel (~10× faster), guarantees
> consistent dimension coverage, and lets the agent compose the narrative.
>
> **Migrate**: configure `~/.claude/mcp.json` once
> (`loomgraph mcp install-config --path ~/.claude/mcp.json`), then ask
> Claude *"audit this codebase's technical debt"* — no `/loomgraph-debt-radar`
> invocation needed. Skill remains functional in v0.12.x for backward compat.

## 技术债务审计报告生成（v3 - 十维度全面分析）

一键生成项目技术债务审计报告，结合 codeindex 静态分析、LoomGraph 知识图谱拓扑分析、Git 历史度量和代码腐化趋势预测。

**版本**: v3.0 (EPIC-010 增强 - 新增 Git × 时间维度)

**前置条件**:
- 项目已执行 `loomgraph index .` 完成索引
- Git 仓库（用于历史度量分析）

**参数**: `source-path` — 要分析的源码目录，默认 `./src`

---

### 前置检查

验证必要工具可用：

```bash
codeindex --version 2>/dev/null || echo '{"error": "codeindex not found", "suggestion": "pip install ai-codeindex"}'
```

```bash
~/.loomgraph-venv/bin/loomgraph version 2>/dev/null || loomgraph version 2>/dev/null || echo '{"error": "loomgraph not found"}'
```

```bash
git --version 2>/dev/null || echo '{"warning": "git not found", "impact": "Git metrics and trend analysis will be skipped"}'
```

如果 codeindex 或 loomgraph 不可用，提示用户安装后重试，中止流程。
如果 git 不可用，仅警告（Git 度量和趋势分析将跳过）。

---

### Step 1: 三维度债务分析（整合 Git 历史）

**新增（v3）**: 使用 `loomgraph debt --with-git` 一次性获取三维度评分（质量 + 拓扑 + Git）。

```bash
# 先运行 codeindex 生成静态分析数据
codeindex tech-debt {source-path} --format json --recursive > /tmp/debt_raw.json 2>/dev/null

# 调用 loomgraph debt 整合三维度（如果 Git 可用）
if git rev-parse --git-dir >/dev/null 2>&1; then
  loomgraph debt --codeindex-data /tmp/debt_raw.json --with-git --git-since "3 months"
else
  # 降级：仅静态 + 拓扑分析
  loomgraph debt --codeindex-data /tmp/debt_raw.json
fi
```

**解读指引**:
- `overall_health`: 整体健康分（0-100，越高越健康）
  - 有 Git: `(quality + topology + git) / 3`
  - 无 Git: `(quality + topology) / 2`
- `issues`: 债务问题列表，**新增 3 大类**（v3）:
  - `critical_hotspot` — 高频变更 + 高耦合（系统脆弱点）
  - `knowledge_silo` — 总线因子 = 1（知识孤岛）
  - `defect_magnet` — Bug fix ratio > 30%（缺陷磁铁）
- `severity`: critical > warning > info

将完整 JSON 结果保存为变量 `DEBT_DATA`，后续步骤使用。

---

### Step 2: 模块依赖图

获取模块间依赖关系，识别耦合问题：

```bash
loomgraph deps --depth 2
```

**解读指引**:
- 关注 `fan_in` 高的模块 → 被大量依赖，修改风险高
- 关注 `fan_out` 高的模块 → 依赖过多，职责可能不清
- 关注双向依赖 → 循环依赖，必须解耦

将完整 JSON 结果保存为变量 `DEPS_DATA`，后续步骤使用。

---

### Step 2.5: Git 历史度量（新增 v3）

**新增（v3）**: 分析 Git 历史，识别热点文件、知识孤岛和缺陷磁铁。

```bash
# 仅在 Git 仓库中执行
if git rev-parse --git-dir >/dev/null 2>&1; then
  loomgraph git-metrics . --since "3 months"
else
  echo '{"warning": "Not a git repository", "git_metrics": null}'
fi
```

**解读指引**:
- `hotspots`: 热点文件列表（按 hotspot_score 排序）
  - `hotspot_score` = change_frequency × log10(churn + 1) × 10
  - Score > 80: 高风险区域，优先重构
- `bus_factor`: 知识孤岛列表
  - `risk_level: critical`: 只有 1 人维护（100% 提交）
  - `risk_level: high`: 2 人维护但主要贡献者 > 70%
- `summary.total_commits`: 分析的总提交数
- `summary.hotspots`: 热点文件数量

将完整 JSON 结果保存为变量 `GIT_METRICS_DATA`，后续步骤使用。

**注意**: 如果非 Git 仓库，`GIT_METRICS_DATA` 为 null，后续分析跳过 Git 维度。

---

### Step 3: 模块概览

获取项目模块功能概览，理解各模块职责：

```bash
loomgraph overview --no-summary
```

**解读指引**:
- 结合 Step 1 的文件级问题，判断模块整体健康度
- 识别职责不清或过于庞大的模块

将完整 JSON 结果保存为变量 `OVERVIEW_DATA`，后续步骤使用。

---

### Step 4: Workspace 统计

获取当前索引的 workspace 统计信息：

```bash
loomgraph workspace info
```

**解读指引**:
- `entity_count` 和 `relation_count` 反映项目规模
- 结合 Step 1 的债务密度，评估整体债务占比

将完整 JSON 结果保存为变量 `WORKSPACE_DATA`，后续步骤使用。

---

### Step 5: 图谱拓扑分析

分析知识图谱拓扑结构，检测结构级代码坏味道：

```bash
loomgraph topology
```

**解读指引**:
- `topology_score` → 拓扑健康分 (0-100，越高越健康)
- `orphans` → 孤岛实体（0 callers + 0 callees），可能是死代码或解析遗漏
- `hubs` → Hub 脆弱点（高 in-degree），修改会产生广泛涟漪
- `god_functions` → 上帝函数（高 out-degree），职责过重
- `placeholder_modules` → 占位模块（仅含 __init__）
- `coupling.density` → 耦合密度（跨模块关系占比）

将完整 JSON 结果保存为变量 `TOPOLOGY_DATA`，后续步骤使用。

---

### Step 6: 索引新鲜度检查

验证知识图谱中的 source_id 是否仍然指向存在的文件：

```bash
loomgraph check
```

**解读指引**:
- `freshness_ratio` → 新鲜度比率 (1.0 = 全部有效)
- `stale_entries` → 过时条目（文件已删除或重构导致路径变更）
- 新鲜度 < 80% 时建议执行 `loomgraph index --clear .` 重建索引

将完整 JSON 结果保存为变量 `CHECK_DATA`，后续步骤使用。

---

### Step 7: 代码腐化趋势分析（新增 v3 - 可选）

**新增（v3）**: 检测关键文件的复杂度随时间增长趋势。

**前提条件**: 需要至少 3 次历史快照（通过多次运行 `loomgraph debt` 积累）。

```bash
# 尝试分析 Step 2.5 中识别的热点文件的趋势
if [ -n "$GIT_METRICS_DATA" ]; then
  # 获取 top 3 热点文件
  HOTSPOT_FILES=$(echo "$GIT_METRICS_DATA" | jq -r '.hotspots[:3][].file')

  for file in $HOTSPOT_FILES; do
    # 尝试分析趋势（如果快照不足会返回错误，忽略即可）
    loomgraph trends --entity "$file" --metric complexity --months 6 2>/dev/null || echo "{\"entity\": \"$file\", \"error\": \"insufficient snapshots\"}"
  done
fi
```

**解读指引**:
- `trend_direction`:
  - `increasing`: 复杂度上升（代码正在腐化）
  - `stable`: 保持稳定
  - `decreasing`: 复杂度下降（重构改善）
- `slope`: 每月变化率（正值 = 上升，负值 = 下降）
- `forecast`: 预测下个月的复杂度
- `alert`: 自动预警（月增长率 >15% 时触发）
- `chart`: ASCII 趋势图

将所有趋势分析结果合并为变量 `TRENDS_DATA`（JSON 数组）。

**注意**: 如果快照不足（< 3 次），趋势分析会返回错误，这是正常的。报告中注明"需积累历史数据"。

---

### Step 8: LLM 综合分析

将 Step 1-7 收集的所有数据汇总，生成技术债务审计报告。

**分析维度** (7 → 10 维，v3 新增 3 维):

| 维度 | 数据源 | 坏味道示例 | v3 新增 |
|------|--------|-----------|---------|
| 文件级债务 | DEBT_DATA (Step 1) | God Class, 超大文件, 高噪音比 | — |
| 依赖耦合 | DEPS_DATA (Step 2) | 循环依赖, 高 fan-out | — |
| **热点检测** | GIT_METRICS_DATA (Step 2.5) | 高频变更文件 | ✨ v3 |
| **知识孤岛** | GIT_METRICS_DATA (Step 2.5) | Bus Factor = 1 | ✨ v3 |
| **缺陷磁铁** | GIT_METRICS_DATA (Step 2.5) | Bug fix ratio > 30% | ✨ v3 |
| 职责清晰度 | OVERVIEW_DATA (Step 3) | 模块职责不清 | — |
| 拓扑健康度 | TOPOLOGY_DATA (Step 5) | 孤岛实体, Hub 脆弱, God Function | — |
| 死代码率 | TOPOLOGY_DATA.orphans (Step 5) | 未被引用的实体占比 | — |
| 耦合密度 | TOPOLOGY_DATA.coupling (Step 5) | 跨模块关系 vs 模块内关系 | — |
| 索引新鲜度 | CHECK_DATA (Step 6) | 过时的 source_id | — |

**分析要求**:

1. **债务等级评定** (1-5，v3 更新规则):
   - 1 = 健康：无 critical 问题，warning < 3，topology_score >= 80，hotspot < 3
   - 2 = 轻度：无 critical，warning 3-5，topology_score >= 60，hotspot 3-5
   - 3 = 中度：critical 1-2 或 warning > 5 或 topology_score < 60 或 hotspot > 5
   - 4 = 重度：critical 3-5 或存在循环依赖 或 orphan_ratio > 20% 或存在 knowledge_silo (critical)
   - 5 = 严重：critical > 5 或多处循环依赖 + God Class + topology_score < 40 或 hotspot > 10 且存在 knowledge_silo

2. **模块健康度排名** (v3 更新，新增 Git 维度): 综合以下维度打分 (0-100，越高越差)：
   - 文件级债务（来自 Step 1）: God Class +30, 超大文件 +25, 高噪音比 +15, 符号过载 +10
   - 依赖耦合（来自 Step 2）: 循环依赖 +25, fan_out > 5 +15, fan_in > 8 +10
   - **Git 热点**（来自 Step 2.5，v3 新增）: hotspot_score > 80 +25, > 60 +15, > 40 +10
   - **知识孤岛**（来自 Step 2.5，v3 新增）: critical risk +20, high risk +10
   - **缺陷磁铁**（来自 Step 2.5，v3 新增）: bug_fix_ratio > 30% +15, > 20% +10
   - 职责清晰度（来自 Step 3）: 根据模块描述主观评估
   - 拓扑问题（来自 Step 5）: orphan_ratio > 15% +20, hub(in>=15) +15, god_function(out>=20) +15, god_function(out>=10) +10
   - 索引新鲜度（来自 Step 6）: freshness < 80% +10, freshness < 50% +20

3. **重构优先级** (v3 更新，新增热点+孤岛考量): 综合风险和收益排序：
   - **紧急**:
     - 高频热点 + God Class（易产生事故，可立即拆分）
     - 知识孤岛 + critical 级文件（单点故障风险）
   - **重要**:
     - 循环依赖（影响范围大，需规划）
     - Hub 脆弱点 + 高频变更（修改涟漪大）
   - **改善**:
     - 孤岛实体清理（长期收益）
     - 缺陷磁铁加测试（提升质量）

**输出报告格式**:

```markdown
# 技术债务审计报告 — {project_name}

> 生成时间: {date}
> 分析范围: {source-path}
> 工具版本: codeindex {version} + loomgraph {version}
> 分析维度: 10 维（v3 - 新增 Git 历史 + 趋势预测）

## 概要

| 指标 | 值 |
|------|-----|
| 债务等级 | {level}/5 |
| 整体健康分 | {overall_health}/100 |
| 拓扑健康分 | {topology_score}/100 |
| 索引新鲜度 | {freshness_ratio}% |
| 高风险模块数 | {count} |
| Critical 问题数 | {critical_count} |
| Warning 问题数 | {warning_count} |
| **热点文件数** (v3) | {hotspot_count} |
| **知识孤岛数** (v3) | {silo_count} |
| 建议优先处理 | {top_module} |

## Git 历史度量分析（v3 新增）

> 分析窗口: 最近 3 个月
> 总提交数: {total_commits}

### 热点文件 (Top 10)

> 高频变更 + 高代码量的文件，系统脆弱点。

| 排名 | 文件 | 变更次数 | 代码行数 | 热点分 | 风险等级 |
|------|------|---------|----------|--------|---------|
| 1 | {file} | {change_freq} | {lines} | {score}/100 | {risk} |
| ... | ... | ... | ... | ... | ... |

**建议**:
- Score > 80: 立即重构（拆分模块、提取helper）
- Score 60-80: 规划重构（下个迭代）
- Score 40-60: 监控（增加测试覆盖）

### 知识孤岛 (Bus Factor < 2)

> 只有 1-2 人维护的文件，单点故障风险。

| 文件 | 主要维护者 | 贡献者数 | 所有权占比 | 风险等级 |
|------|-----------|---------|-----------|---------|
| {file} | {owner} | {count} | {ratio}% | {risk_level} |
| ... | ... | ... | ... | ... |

**建议**:
- Critical (1 贡献者): 立即知识转移（结对编程、文档）
- High (2 贡献者, >70% 占比): 增加第三人参与

### 缺陷磁铁 (Bug Fix Ratio > 20%)

> Bug fix 占比高的文件，质量脆弱点。

| 文件 | 总提交数 | Bug Fix 数 | Bug Fix 占比 | 建议 |
|------|---------|-----------|-------------|------|
| {file} | {total} | {bug_count} | {ratio}% | {suggestion} |
| ... | ... | ... | ... | ... |

**建议**:
- Ratio > 30%: 增加单元测试 + 代码审查
- Ratio 20-30%: 重构复杂逻辑

## 文件级问题清单

按严重度排序，列出所有 codeindex tech-debt 检出的问题：

| 严重度 | 文件 | 问题类型 | 详情 | 建议 |
|--------|------|----------|------|------|
| ... | ... | ... | ... | ... |

## 图谱拓扑分析

### 拓扑健康分

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

## 代码腐化趋势预测（v3 新增 - 可选）

> **前提**: 需要至少 3 次历史快照（通过多次运行 `loomgraph debt` 积累）。
> **状态**: {trend_analysis_status}

{如果有足够快照}

### 热点文件趋势分析

| 文件 | 当前复杂度 | 趋势 | 月增长率 | 下月预测 | 预警 |
|------|-----------|------|---------|----------|------|
| {file} | {current} | {trend_direction} | {slope}/月 | {forecast} | {alert} |
| ... | ... | ... | ... | ... | ... |

**ASCII 趋势图示例**:
```
src/cli/_analysis.py - Complexity Trend

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

{如果快照不足}

> ℹ️ 趋势分析需要至少 3 次历史快照。请定期运行 `loomgraph debt` 积累数据（建议每周一次）。
> 已保存本次快照到 `~/.loomgraph/metrics-history/`。

## 索引新鲜度

| 指标 | 值 |
|------|-----|
| Source ID 总数 | {total} |
| 有效 | {valid} |
| 过时 | {stale} |
| 新鲜度 | {ratio}% |

> {freshness_advice}

## 模块健康度排名

| 排名 | 模块 | 债务分 | 主要问题 | 建议 |
|------|------|--------|----------|------|
| 1 | {module} | {score}/100 | {issues} | {suggestion} |
| ... | ... | ... | ... | ... |

## 依赖结构问题

### 循环依赖
- {module_a} <-> {module_b}: {description}

### 高耦合模块
- {module} (fan_in: {n}, 被 {n} 个模块依赖): {risk}

### 高扇出模块
- {module} (fan_out: {n}, 依赖 {n} 个模块): {risk}

## 重构优先级建议（v3 更新）

### 紧急 (可立即执行)
1. **{action}**: {reason} — 影响范围: {scope} — 风险: {risk}
   - 示例: 拆分热点文件 src/cli/_analysis.py (hotspot_score: 87, God Class: 52 methods)

### 重要 (需规划)
1. **{action}**: {reason} — 影响范围: {scope} — 风险: {risk}
   - 示例: 解耦循环依赖 core.injector <-> core.mapper

### 改善 (长期收益)
1. **{action}**: {reason} — 影响范围: {scope} — 风险: {risk}
   - 示例: 清理 46 个孤岛实体（确认死代码后删除）

## 下一步行动

1. **立即执行**（本周）:
   - [ ] 重构紧急优先级项（1-3 项）
   - [ ] 知识转移计划（knowledge_silo 文件）

2. **规划执行**（下个迭代）:
   - [ ] 解耦循环依赖
   - [ ] 重构 Hub 脆弱点

3. **持续改善**（长期）:
   - [ ] 每周运行 `loomgraph debt` 积累趋势数据
   - [ ] 定期清理孤岛实体
   - [ ] 增加缺陷磁铁的测试覆盖

---

**v3 更新摘要**:
- ✨ 新增 Git 历史度量分析（热点检测、知识孤岛、缺陷磁铁）
- ✨ 新增代码腐化趋势预测（线性回归 + 自动预警）
- ✨ 三维度债务评分（质量 + 拓扑 + Git）
- 📊 分析维度从 7 维升级到 10 维
- 🎯 重构优先级算法优化（新增热点+孤岛考量）
```

---

## 注意事项

1. **未索引项目**: 如果 `loomgraph deps` 或 `loomgraph overview` 返回错误，提示用户先执行 `loomgraph index .`
2. **codeindex 未配置**: 如果 `codeindex tech-debt` 失败，提示用户先执行 `/loomgraph-setup` 配置项目
3. **非 Git 仓库**: Git 度量和趋势分析将跳过，报告中注明"非 Git 仓库，Git 维度不可用"
4. **快照不足**: 趋势分析需要 ≥3 次快照，首次使用会提示"需积累历史数据"
5. **空结果处理**: 如果某个步骤返回空数据，在报告中注明"无数据"而非省略该章节
6. **大型项目**: tech-debt 递归扫描可能耗时较长，提前告知用户
7. **拓扑分析降级**: 如果 `loomgraph topology` 失败（LightRAG 未连接），在报告中注明"图谱拓扑数据不可用"
8. **新鲜度检查**: `loomgraph check` 依赖当前工作目录，确保在项目根目录执行
9. **Git 度量降级**: 如果 `loomgraph git-metrics` 失败，降级为传统分析（不影响其他维度）
10. **趋势分析降级**: 如果 `loomgraph trends` 返回错误（快照不足），优雅降级，仅在报告中提示积累数据
