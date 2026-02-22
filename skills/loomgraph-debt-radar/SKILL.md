---
name: loomgraph-debt-radar
description: Generate a technical debt audit report combining static analysis, knowledge graph topology, and index freshness
disable-model-invocation: true
argument-hint: "[source-path]"
---

## 技术债务审计报告生成

一键生成项目技术债务审计报告，结合 codeindex 静态分析、LoomGraph 知识图谱拓扑分析和索引新鲜度检查。

**前置条件**: 项目已执行 `loomgraph index .` 完成索引。

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

如果任一工具不可用，提示用户安装后重试，中止流程。

---

### Step 1: 文件级债务分析

使用 codeindex 扫描文件级技术债务（God Class、超大文件、高噪音比等）：

```bash
codeindex tech-debt {source-path} --format json --recursive 2>/dev/null
```

**解读指引**:
- `severity: critical` → 必须处理的重大问题（超大文件 >5000 行、God Class >50 方法）
- `severity: warning` → 需要关注的问题（符号过载 >100、高噪音比 >50%）
- `severity: info` → 改善建议

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

### Step 7: LLM 综合分析

将 Step 1-6 收集的所有数据汇总，生成技术债务审计报告。

**分析维度** (7 维):

| 维度 | 数据源 | 坏味道示例 |
|------|--------|-----------|
| 文件级债务 | DEBT_DATA (Step 1) | God Class, 超大文件, 高噪音比 |
| 依赖耦合 | DEPS_DATA (Step 2) | 循环依赖, 高 fan-out |
| 职责清晰度 | OVERVIEW_DATA (Step 3) | 模块职责不清 |
| 拓扑健康度 | TOPOLOGY_DATA (Step 5) | 孤岛实体, Hub 脆弱, God Function |
| 死代码率 | TOPOLOGY_DATA.orphans (Step 5) | 未被引用的实体占比 |
| 耦合密度 | TOPOLOGY_DATA.coupling (Step 5) | 跨模块关系 vs 模块内关系 |
| 索引新鲜度 | CHECK_DATA (Step 6) | 过时的 source_id |

**分析要求**:

1. **债务等级评定** (1-5):
   - 1 = 健康：无 critical 问题，warning < 3，topology_score >= 80
   - 2 = 轻度：无 critical，warning 3-5，topology_score >= 60
   - 3 = 中度：critical 1-2 或 warning > 5 或 topology_score < 60
   - 4 = 重度：critical 3-5 或存在循环依赖 或 orphan_ratio > 20%
   - 5 = 严重：critical > 5 或多处循环依赖 + God Class + topology_score < 40

2. **模块健康度排名**: 综合以下维度打分 (0-100，越高越差)：
   - 文件级债务（来自 Step 1）: God Class +30, 超大文件 +25, 高噪音比 +15, 符号过载 +10
   - 依赖耦合（来自 Step 2）: 循环依赖 +25, fan_out > 5 +15, fan_in > 8 +10
   - 职责清晰度（来自 Step 3）: 根据模块描述主观评估
   - 拓扑问题（来自 Step 5）: orphan_ratio > 15% +20, hub(in>=15) +15, god_function(out>=20) +15, god_function(out>=10) +10
   - 索引新鲜度（来自 Step 6）: freshness < 80% +10, freshness < 50% +20

3. **重构优先级**: 综合风险和收益排序：
   - **紧急**: 影响范围可控但问题严重（可立即执行）
   - **重要**: 问题严重但影响范围大（需规划）
   - **改善**: 非紧急但有长期收益

**输出报告格式**:

```markdown
# 技术债务审计报告 — {project_name}

> 生成时间: {date}
> 分析范围: {source-path}
> 工具版本: codeindex {version} + loomgraph {version}

## 概要

| 指标 | 值 |
|------|-----|
| 债务等级 | {level}/5 |
| 拓扑健康分 | {topology_score}/100 |
| 索引新鲜度 | {freshness_ratio}% |
| 高风险模块数 | {count} |
| Critical 问题数 | {critical_count} |
| Warning 问题数 | {warning_count} |
| 建议优先处理 | {top_module} |

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

## 重构优先级建议

### 紧急 (可立即执行)
1. **{action}**: {reason} — 影响范围: {scope}

### 重要 (需规划)
1. **{action}**: {reason} — 影响范围: {scope}

### 改善 (长期收益)
1. **{action}**: {reason} — 影响范围: {scope}
```

---

## 注意事项

1. **未索引项目**: 如果 `loomgraph deps` 或 `loomgraph overview` 返回错误，提示用户先执行 `loomgraph index .`
2. **codeindex 未配置**: 如果 `codeindex tech-debt` 失败，提示用户先执行 `/loomgraph-setup` 配置项目
3. **空结果处理**: 如果某个步骤返回空数据，在报告中注明"无数据"而非省略该章节
4. **大型项目**: tech-debt 递归扫描可能耗时较长，提前告知用户
5. **拓扑分析降级**: 如果 `loomgraph topology` 失败（LightRAG 未连接），在报告中注明"图谱拓扑数据不可用"
6. **新鲜度检查**: `loomgraph check` 依赖当前工作目录，确保在项目根目录执行
