---
name: loomgraph-sync-advisor
description: Analyze upstream changes and generate merge advice with Git-history-aware conflict prediction (v2)
disable-model-invocation: true
argument-hint: "--ws1 <upstream> --ws2 <downstream>"
---

> ⚠️ **DEPRECATED in v0.12.1 — will be REMOVED in v0.13.0**
>
> Superseded by the MCP tool **`loomgraph_sync_advice`** in
> `loomgraph>=0.12.1`. Same compose + 3-dim debt + per-entity impact
> workflow, one parallel MCP call.
>
> **Migrate**: configure MCP once
> (`loomgraph mcp install-config --path ~/.claude/mcp.json`), then ask
> Claude *"sync advice from proj:main to proj:feature-branch"*. Skill
> remains functional in v0.12.x for backward compat.

## 智能同步顾问 v2

上游发了补丁，自动分析对下游分支的影响，给出合并建议和冲突预测。

**v2 新特性** (基于 EPIC-010):
- ✨ Git 历史质量分析（hotspots、knowledge silos、bug magnets）
- ✨ 三维健康评分（quality + topology + git）
- ✨ 质量趋势对比（可选，需 ≥3 历史快照）
- ✨ Git 维度加权的冲突风险评分

**前置条件**:
- 上游和下游分支都已索引到各自的 workspace（`loomgraph index <path> -w <name>`）
- 使用 `loomgraph workspace list` 确认 workspace 存在
- 推荐：项目是 Git 仓库（v2 Git 分析功能需要）

**参数**:
- `--ws1` — 上游 workspace 名称（基准）
- `--ws2` — 下游 workspace 名称（待同步目标）
- 如果用户提供了多个下游，对每个下游分别执行 Step 1-5，最后统一生成报告

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

### Step 2.5: Git 历史质量分析 ✨ v2 新增

**目的**: 识别上游变更中的技术债务热点，为冲突预测提供历史维度数据。

#### 2.5.1 提取变更模块列表

从 `COMPARE_DATA` 中提取上游变更涉及的文件路径（`only_in_ws1` 和 `relation_changes` 中的 `source_id`），按目录聚合成模块列表。

**模块提取规则**:
- 取路径前 2 层目录，如 `src/core/config.py` → `src/core`
- 去重，得到模块列表如 `["src/core", "src/api", "tests/unit"]`

#### 2.5.2 上游质量分析

对每个变更模块，运行 Git 历史质量分析：

```bash
loomgraph debt --with-git -m {module_path} -w {upstream_ws}
```

**关键指标**（保存为 `GIT_QUALITY_DATA`）:
- **Hotspots**: 文件的 `change_frequency`（变更次数）和 `hotspot_score`
  - `hotspot_score >= 60` = 高风险脆弱点
- **Knowledge Silos**: 文件的 `bus_factor`
  - `bus_factor == 1` = 单点故障风险（只有一个主要贡献者）
- **Bug Magnets**: 文件的 `bug_ratio`（Bug fix 占比）
  - `bug_ratio >= 30%` = 质量脆弱点
- **Module Health**: 模块的三维健康分（`overall_health_score`）
  - `< 60` = 差, `60-75` = 中等, `> 75` = 良好

#### 2.5.3 下游对应模块健康分（可选）

如果下游也包含相同模块，运行：

```bash
loomgraph debt --with-git -m {module_path} -w {downstream_ws}
```

对比上下游的模块健康分，识别**质量分歧**：
- 上游健康分下降 + 下游保持/上升 → 警告"上游引入技术债务"
- 上游健康分上升 + 下游保持/下降 → 建议"优先同步，提升下游质量"

#### 2.5.4 优雅降级

**如果项目不是 Git 仓库**:
- Step 2.5 自动跳过
- 在报告中注明"Git 历史分析不可用（非 Git 仓库）"
- 冲突预测仅基于结构分析（Step 1-2）

**如果 `loomgraph debt --with-git` 失败**:
- 捕获错误，记录日志
- 降级为纯结构分析
- 在报告中注明"Git 历史数据缺失"

---

### Step 3: 代码级差异（可选）

如果上游和下游对应 git 分支可达，获取代码级差异来补充结构差异：

```bash
git diff --stat {upstream_branch}..{downstream_branch} 2>/dev/null
```

如果 git diff 不可用（比如是不同项目而非不同分支），跳过此步骤，在报告中注明"代码级差异不可用（跨项目对比）"。

将结果保存为变量 `GIT_DIFF_DATA`（可能为空）。

---

### Step 4: 冲突预测与风险评分 ✨ v2 增强

将 Step 1-3 收集的所有数据（结构 diff + 影响分析 + Git 历史 + 代码 diff）汇总，计算**加权风险评分**。

#### 4.1 基础风险评分（结构维度）

**影响等级评定**:
- **高**: `relation_changes` 中有 >3 个实体变化，或 `only_in_ws1` 中有核心模块实体
- **中**: `relation_changes` 中有 1-3 个实体变化
- **低**: 仅有 `only_in_ws1` 新增实体，无关系变化

基础风险分（0-100）:
```python
base_risk = min(100, relation_changes_count * 15 + only_in_ws1_count * 5)
```

#### 4.2 Git 维度权重加成 ✨ v2 新增

对每个变更文件/模块，根据 `GIT_QUALITY_DATA` 计算额外风险分：

| Git 特征 | 条件 | 风险加成 | 原因 |
|---------|------|---------|------|
| **Hotspot** | `hotspot_score >= 60` | +20 | 高频变更 + 高代码量 = 系统脆弱点 |
| **Knowledge Silo** | `bus_factor == 1` | +30 | 单点故障，合并需原作者 review |
| **Bug Magnet** | `bug_ratio >= 30%` | +25 | 历史 bug 多，新变更易引入缺陷 |
| **Quality Decline** | 健康分月降幅 > 5 | +15 | 质量趋势下降，需警惕 |
| **Dual Modification** | 上下游都改了同一文件 | +25 | 高冲突概率 |

**最终风险分**:
```python
final_risk = min(100, base_risk + git_bonus)
```

#### 4.3 冲突分级

| 风险分 | 等级 | 冲突预测 |
|--------|------|---------|
| 0-30 | 🟢 低风险 | 无结构冲突 + 无 Git 热点 |
| 31-60 | 🟡 中风险 | 有关系变化或轻微 Git 热点 |
| 61-100 | 🔴 高风险 | 多维度冲突（结构 + Git + 双向修改）|

#### 4.4 合并策略建议

| 风险等级 | 推荐策略 | 说明 |
|---------|---------|------|
| 🟢 低风险 | **自动合并** | 低风险变更，无结构冲突，可快速合并 |
| 🟡 中风险 | **手动审查** | 需 review 关键文件（hotspots、silos） |
| 🔴 高风险 | **分步合并** | 建议按模块分批合并 + 增加测试覆盖 |

#### 4.5 多下游排序优化 ✨ v2 增强

如果有多个下游分支，按**综合优先级**排序：

```python
priority_score = (100 - final_risk) * 0.6 + downstream_health * 0.4
```

**建议同步顺序**:
1. 高优先级（低风险 + 高下游健康分）→ 快速完成
2. 中优先级 → 需要 review
3. 低优先级（高风险 + 低下游健康分）→ 延后处理，先修复技术债务

---

### Step 5: 质量趋势对比 ✨ v2 新增（可选）

**前提条件**: 上游和下游都有 ≥3 个历史快照（通过 `loomgraph trends` 生成）

**执行命令**:

```bash
# 上游质量趋势
loomgraph trends quality -w {upstream_ws}

# 下游质量趋势
loomgraph trends quality -w {downstream_ws}
```

**分析目标**:
- 对比上游和下游的**质量演化方向**
- 识别**质量分歧**：上游质量下降 vs 下游质量上升

**输出指标**（保存为 `TREND_DATA`）:
- `upstream_slope`: 上游质量月变化率（如 +2.5/month = 上升）
- `downstream_slope`: 下游质量月变化率
- `trend_direction`: `converging`（趋同）| `diverging`（分歧）

**风险判定**:

| 上游趋势 | 下游趋势 | 分歧风险 | 建议 |
|---------|---------|---------|------|
| ⬇️ 下降 | ⬆️ 上升 | 🔴 高 | 暂缓同步，先修复上游技术债务 |
| ⬇️ 下降 | ⬇️ 下降 | 🟡 中 | 同步前增加测试，避免质量雪崩 |
| ⬆️ 上升 | ⬇️ 下降 | 🟢 低 | 优先同步，提升下游质量 |
| ⬆️ 上升 | ⬆️ 上升 | 🟢 低 | 趋势一致，可放心同步 |

**优雅降级**:
- 如果历史快照 < 3，Step 5 自动跳过
- 在报告中注明"历史趋势分析不可用（需 ≥3 个快照）"

---

### Step 6: LLM 综合分析与报告生成

将 Step 1-5 收集的所有数据汇总，生成**同步建议报告**。

**输出报告格式**:

```markdown
# 同步建议报告 v2

> 生成时间: {date}
> 上游: {upstream_ws}
> 下游: {downstream_ws}
> 工具版本: loomgraph {version}
> 分析模式: Git 历史增强 ✨

## 📊 概要

| 指标 | 值 |
|------|-----|
| 影响等级 | {高/中/低} |
| 风险评分 | {final_risk}/100 |
| 上游健康分 | {upstream_health}/100 ({差/中等/良好}) |
| 下游健康分 | {downstream_health}/100 ({差/中等/良好}) |
| 质量分歧风险 | {有/无} ({converging/diverging}) |
| 上游新增实体 | {only_in_ws1_count} |
| 下游独有实体 | {only_in_ws2_count} |
| 共有实体 | {in_both_count} |
| 关系变化实体 | {relations_diff_count} |
| 预测冲突数 | {conflict_count} |

## 🔥 上游变更质量分析 ✨ v2 新增

### 高风险文件（需重点 review）

| 文件 | 变更频率 | Bus Factor | Bug 率 | Hotspot 分 | 健康分 | 风险原因 |
|------|---------|-----------|--------|-----------|--------|---------|
| src/auth/service.py | 30 次 | 1 | 40% | 85/100 | 45/100 | 🔥 Hotspot + 🏝️ 知识孤岛 + 🐛 缺陷磁铁 |
| src/core/config.py | 15 次 | 2 | 20% | 62/100 | 68/100 | 🔥 Hotspot |

**风险说明**:
- 🔥 **Hotspot**: 高频变更（>10 次），合并冲突概率高
- 🏝️ **Knowledge Silo**: Bus Factor=1，需原作者 review
- 🐛 **Bug Magnet**: 历史 bug fix 占比 >30%，质量脆弱

### 健康文件（可快速合并）

| 文件 | 变更频率 | 健康分 | 说明 |
|------|---------|--------|------|
| src/utils/helpers.py | 2 次 | 88/100 | 低频变更，质量稳定 |
| src/common/constants.py | 1 次 | 92/100 | 纯新增，无冲突 |

## 📈 上游变更摘要

### 新增实体
| 实体名 | 类型 | 来源文件 | 健康分 | 下游影响 |
|--------|------|----------|--------|----------|
| AuthService.validate_token | method | src/auth/service.py | 45/100 | 🔴 高（下游有 12 个调用点）|
| ConfigLoader.load | function | src/core/config.py | 68/100 | 🟡 中（下游无调用）|

### 关系变化
| 实体 | 上游关系数 | 下游关系数 | 新增关系 | 移除关系 | 风险 |
|------|-----------|-----------|----------|----------|------|
| AuthService | 15 | 8 | 7 | 0 | 🔴 高（依赖扩张）|
| ConfigLoader | 5 | 5 | 2 | 2 | 🟡 中（依赖重构）|

## ⚠️ 冲突预测与风险分析 ✨ v2 增强

### 🔴 高风险冲突（需分步合并）

#### 1. AuthService.validate_token (风险分: 85/100)
- **结构风险**: 上游新增 7 个调用关系，下游已有 8 个
- **Git 风险**: Hotspot (85/100) + Knowledge Silo (Bus Factor=1) + Bug Magnet (40%)
- **双向修改**: ✅ 上下游都修改了 `src/auth/service.py`
- **建议**:
  1. 先让原作者 @zhang.san review（Bus Factor=1）
  2. 增加单元测试覆盖（历史 bug 率高）
  3. 手动合并，避免覆盖下游逻辑

### 🟡 中风险冲突（需手动审查）

#### 2. ConfigLoader (风险分: 45/100)
- **结构风险**: 依赖关系重构（新增 2 个，移除 2 个）
- **Git 风险**: Hotspot (62/100)
- **建议**: Review 配置加载逻辑变更，确保下游配置兼容

### 🟢 低风险变更（可自动合并）

- `src/utils/helpers.py`: 纯新增工具函数，无依赖
- `src/common/constants.py`: 常量定义，无逻辑冲突

## 📉 质量趋势对比 ✨ v2 新增（可选）

**上游趋势**:
- 月变化率: -3.5/month（下降）
- 预测：如果不干预，3 个月后健康分降至 65/100

**下游趋势**:
- 月变化率: +2.0/month（上升）
- 预测：3 个月后健康分升至 88/100

**分歧风险**: 🔴 **高** - 上游质量下降，下游质量上升

**建议**: 暂缓同步高风险模块（AuthService），优先修复上游技术债务后再合并。

## 🎯 下游独有实体（需保留）

以下实体是下游定制开发的，合并时需确保不被覆盖：

| 实体名 | 类型 | 来源文件 | 说明 |
|--------|------|----------|------|
| CustomAuthPlugin | class | src/auth/plugins.py | 下游定制认证插件 |
| LocalConfig | class | src/core/local.py | 下游环境配置 |

## 🚀 合并建议

### 推荐策略: **分步合并**（高风险）

**优先级排序**:
1. 🟢 **第一批**: 健康文件（utils、constants）→ 快速合并，风险低
2. 🟡 **第二批**: 中风险模块（ConfigLoader）→ 需 review，但可并行
3. 🔴 **第三批**: 高风险模块（AuthService）→ 延后处理，先修复上游债务

**详细操作步骤**:

#### 第一批：低风险模块（预计 1 天）
```bash
# 1. 切换到下游分支
git checkout {downstream_branch}

# 2. 合并 utils 和 constants
git cherry-pick {upstream_commit_hash_utils}
git cherry-pick {upstream_commit_hash_constants}

# 3. 运行测试
pytest tests/unit/test_utils.py tests/unit/test_constants.py

# 4. 提交
git push
```

#### 第二批：中风险模块（预计 2-3 天）
```bash
# 1. Review ConfigLoader 变更
git diff {upstream_branch} -- src/core/config.py

# 2. 手动合并（保留下游定制）
# 编辑 src/core/config.py，合并逻辑

# 3. 增加集成测试
pytest tests/integration/test_config_loader.py

# 4. 本地验证配置加载
python -m src.core.config --verify
```

#### 第三批：高风险模块（预计 1 周，需上游协作）
```bash
# ⚠️ 暂缓同步，先修复上游技术债务

# 上游需要做的（@zhang.san）:
# 1. 降低 AuthService 的 Hotspot 分数（减少单文件修改频率）
# 2. 增加单元测试（目标：bug_ratio < 20%）
# 3. 知识转移（Bus Factor 提升至 ≥2）

# 下游准备（当前可做）:
# 1. 整理 AuthService 下游定制逻辑
# 2. 增加测试覆盖（为合并做准备）
# 3. 与上游对齐接口设计
```

### 注意事项
- ⚠️ **不要强制覆盖**下游独有实体（CustomAuthPlugin、LocalConfig）
- ⚠️ **Knowledge Silo 模块**需原作者参与 review（AuthService → @zhang.san）
- ⚠️ **Hotspot 文件**合并后需增加测试覆盖（防止回归）
- ⚠️ **质量分歧**模块暂缓同步，优先修复上游债务

## 🔍 深度分析建议

对于高风险模块，建议执行以下深度分析：

### 技术债务全面审计
```bash
/loomgraph-debt-radar src/auth -w {upstream_ws}
```
全面评估 AuthService 模块的技术债务（7 维度 + Git 历史）

### 代码演化趋势分析
```bash
/loomgraph-evolution --entity AuthService -w {upstream_ws}
```
查看 AuthService 的历史变更模式，识别不稳定原因

---

## 📋 多下游场景汇总

如果有多个下游分支，按优先级排序：

| 下游分支 | 风险评分 | 下游健康分 | 冲突数 | 建议策略 | 优先级 |
|----------|---------|-----------|--------|----------|--------|
| downstream-A | 25/100 | 85/100 | 0 | 自动合并 | 1 (优先) |
| downstream-B | 48/100 | 72/100 | 2 | 手动审查 | 2 |
| downstream-C | 85/100 | 55/100 | 5 | 分步合并 | 3 (延后) |

**建议操作顺序**:
1. 先同步 **downstream-A**（低风险 + 高健康分，快速完成）
2. 再处理 **downstream-B**（需 review，但可并行）
3. 最后处理 **downstream-C**（高风险 + 低健康分，先修复下游债务）

---

## 🔧 故障排查

### Git 历史分析失败
**症状**: "Git 历史数据缺失"
**可能原因**:
- 项目不是 Git 仓库
- Git 历史不足（commits < 10）
- `loomgraph debt --with-git` 命令失败

**解决方案**:
- 检查是否在 Git 仓库根目录运行
- 降级为纯结构分析（Step 1-2 仍可用）

### 趋势分析不可用
**症状**: "历史趋势分析不可用（需 ≥3 个快照）"
**可能原因**:
- 项目未定期运行 `loomgraph index` 建立快照
- 历史快照被清理

**解决方案**:
- 跳过 Step 5，仅使用当前快照分析
- 未来定期建立快照（建议：每周一次）

---

## 📚 补充说明

### v2 vs v1 对比

| 维度 | v1 | v2 |
|------|----|----|
| 结构分析 | ✅ compare + graph | ✅ 保留 |
| Git 历史 | ❌ 无 | ✅ hotspots/silos/bug magnets |
| 风险评分 | 简单计数 | ✅ 多维度加权（结构 + Git） |
| 质量趋势 | ❌ 无 | ✅ 月变化率预测 |
| 健康评分 | ❌ 无 | ✅ 三维评分（quality + topology + git） |
| 合并策略 | 人工判断 | ✅ 算法优先级排序 |

### 向后兼容性

- ✅ 非 Git 项目自动降级为 v1 模式（纯结构分析）
- ✅ 历史快照不足时自动跳过趋势分析
- ✅ Step 1-3 核心逻辑不变，v1 报告仍可生成
- ✅ 新增的 Git 维度作为增强层，不影响基础功能

### 性能考虑

- `loomgraph debt --with-git` 仅针对**变更模块**运行（而非全项目）
- 模块聚合逻辑减少 API 调用次数（按目录去重）
- 趋势分析为可选步骤，可按需开启

---

**Version**: v2 (EPIC-010 Enhanced)
**Last Updated**: 2026-03-07
```
