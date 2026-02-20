---
name: loomgraph-sync-advisor
description: Analyze upstream changes and generate merge advice for downstream branches with conflict prediction
disable-model-invocation: true
argument-hint: "--ws1 <upstream> --ws2 <downstream>"
---

## 智能同步顾问

上游发了补丁，自动分析对下游分支的影响，给出合并建议和冲突预测。

**前置条件**:
- 上游和下游分支都已索引到各自的 workspace（`loomgraph index <path> -w <name>`）
- 使用 `loomgraph workspace list` 确认 workspace 存在

**参数**:
- `--ws1` — 上游 workspace 名称（基准）
- `--ws2` — 下游 workspace 名称（待同步目标）
- 如果用户提供了多个下游，对每个下游分别执行 Step 1-3，最后统一生成报告

---

### 前置检查

验证工具可用并确认 workspace 存在：

```bash
~/.loomgraph-venv/bin/loomgraph version 2>/dev/null || loomgraph version 2>/dev/null || echo '{"error": "loomgraph not found"}'
```

```bash
loomgraph workspace list
```

检查用户指定的 `--ws1` 和 `--ws2` 是否都在 workspace 列表中。如果不存在，提示用户先执行索引：

```
该 workspace 不存在。请先索引对应分支：
  git checkout <branch>
  loomgraph index . -w <workspace-name>
```

---

### Step 1: 跨 Workspace 结构对比

对比上游和下游 workspace 的实体/关系差异：

```bash
loomgraph compare --ws1 {upstream_ws} --ws2 {downstream_ws}
```

**解读指引**:
- `only_in_ws1` → 上游有但下游没有的实体（上游新增，需要同步）
- `only_in_ws2` → 下游独有的实体（下游定制，合并时需保留）
- `relation_changes` → 共有实体的调用关系变化（重点关注，可能引发冲突）
- `summary.relations_diff == 0 && summary.only_in_ws1 == 0` → 无需同步

将完整 JSON 结果保存为变量 `COMPARE_DATA`，后续步骤使用。

如果对比结果显示无差异（`only_in_ws1 == 0` 且 `relations_diff == 0`），直接输出"上游和下游结构一致，无需同步"并结束。

---

### Step 2: 变更影响分析

对上游新增/变更的关键实体，分析其在下游的影响范围：

从 `COMPARE_DATA` 中提取 `relation_changes` 里变化最大的实体（按 `|ws1_count - ws2_count|` 排序，取 top 5），以及 `only_in_ws1` 中的关键实体。

对每个重点实体，查询其在下游 workspace 的调用关系：

```bash
loomgraph graph "{entity_name}" -w {downstream_ws}
```

**解读指引**:
- 如果该实体在下游有大量调用者 → 高影响，合并需谨慎
- 如果该实体在下游不存在 → 纯新增，合并风险低
- 如果调用关系差异大 → 可能有逻辑冲突

将分析结果保存为变量 `IMPACT_DATA`。

---

### Step 3: 代码级差异（可选）

如果上游和下游对应 git 分支可达，获取代码级差异来补充结构差异：

```bash
git diff --stat {upstream_branch}..{downstream_branch} 2>/dev/null
```

如果 git diff 不可用（比如是不同项目而非不同分支），跳过此步骤，在报告中注明"代码级差异不可用（跨项目对比）"。

将结果保存为变量 `GIT_DIFF_DATA`（可能为空）。

---

### Step 4: LLM 综合分析

将 Step 1-3 收集的所有数据汇总，生成同步建议报告。

**分析要求**:

1. **影响等级评定**:
   - **高**: `relation_changes` 中有 >3 个实体变化，或 `only_in_ws1` 中有核心模块实体
   - **中**: `relation_changes` 中有 1-3 个实体变化
   - **低**: 仅有 `only_in_ws1` 新增实体，无关系变化

2. **冲突预测**: 交叉分析结构 diff 和代码 diff：
   - 同一实体在两个 workspace 的关系都发生了变化 → 高冲突风险
   - 上游新增实体依赖下游已修改的实体 → 中冲突风险
   - 上游新增独立实体 → 低冲突风险

3. **合并策略建议**:
   - **自动合并**: 低风险变更，无结构冲突
   - **手动审查**: 中风险变更，需 review 关键文件
   - **分步合并**: 高风险变更，建议按模块分批合并

4. **如果有多个下游**，按影响等级排序，建议从低风险下游开始同步。

**输出报告格式**:

```markdown
# 同步建议报告

> 生成时间: {date}
> 上游: {upstream_ws}
> 下游: {downstream_ws}
> 工具版本: loomgraph {version}

## 概要

| 指标 | 值 |
|------|-----|
| 影响等级 | {高/中/低} |
| 上游新增实体 | {only_in_ws1_count} |
| 下游独有实体 | {only_in_ws2_count} |
| 共有实体 | {in_both_count} |
| 关系变化实体 | {relations_diff_count} |
| 预测冲突数 | {conflict_count} |

## 上游变更摘要

### 新增实体
| 实体名 | 类型 | 来源文件 | 下游影响 |
|--------|------|----------|----------|
| {name} | {type} | {source_id} | {impact_note} |

### 关系变化
| 实体 | 上游关系数 | 下游关系数 | 新增关系 | 移除关系 | 风险 |
|------|-----------|-----------|----------|----------|------|
| {entity} | {ws1_count} | {ws2_count} | {added} | {removed} | {risk} |

## 冲突预测

### 高风险
- **{entity}** ({file}): {conflict_reason}
  - 建议: {action}

### 中风险
- **{entity}**: {reason}
  - 建议: {action}

## 下游独有实体（需保留）

以下实体是下游定制开发的，合并时需确保不被覆盖：

| 实体名 | 类型 | 来源文件 |
|--------|------|----------|
| {name} | {type} | {source_id} |

## 合并建议

### 推荐策略: {自动合并/手动审查/分步合并}

**操作步骤**:
1. {step_1}
2. {step_2}
3. {step_3}

### 注意事项
- {note_1}
- {note_2}
```

---

## 多下游场景

如果用户提供了多个下游 workspace（逗号分隔），对每个下游分别执行上述流程，最后生成一份汇总报告：

```markdown
## 多分支同步概况

| 下游分支 | 影响等级 | 冲突数 | 建议策略 | 优先级 |
|----------|----------|--------|----------|--------|
| {downstream_1} | 高 | 3 | 分步合并 | 2 |
| {downstream_2} | 低 | 0 | 自动合并 | 1 |

**建议操作顺序**: 先同步 {low_risk}（低风险，快速完成），再处理 {high_risk}（需 review）。
```

---

## 注意事项

1. **未索引 workspace**: 如果 compare 返回错误，提示用户先索引对应分支
2. **空 workspace**: 如果某个 workspace 实体数为 0，提示可能未完成索引
3. **跨项目对比**: 如果 ws1 和 ws2 是不同项目（非同源分支），在报告开头注明"跨项目对比模式"，冲突预测仅基于结构分析
4. **大型项目**: compare 可能耗时较长，对实体数 >1000 的 workspace 提前告知用户
