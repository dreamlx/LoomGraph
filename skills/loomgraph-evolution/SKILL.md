---
name: loomgraph-evolution
description: Track code evolution across branches/versions, quantify fork divergence, and suggest convergence strategies
disable-model-invocation: true
argument-hint: "--entity <name> [--workspaces ws1,ws2,ws3]"
---

## 代码演化观察

追踪代码实体在多个分支/版本间的分叉轨迹，量化维护代价，给出收敛建议。

**前置条件**:
- 多个版本/分支已索引到各自的 workspace（`loomgraph index <path> -w <name>`）
- 至少需要 2 个 workspace 才能进行演化分析

**参数**:
- `--entity` — 要追踪的实体名称（如 `AuthService`）
- `--workspaces` — 逗号分隔的 workspace 列表（可选，默认查询所有 workspace）

---

### 前置检查

验证工具可用并确认 workspace 存在：

```bash
~/.loomgraph-venv/bin/loomgraph version 2>/dev/null || loomgraph version 2>/dev/null || echo '{"error": "loomgraph not found"}'
```

```bash
loomgraph workspace list
```

如果指定了 `--workspaces`，检查每个 workspace 是否存在。
如果未指定，从 workspace 列表中自动使用全部可用 workspace。
如果可用 workspace 少于 2 个，提示用户至少需要索引 2 个版本/分支：

```
演化分析需要至少 2 个 workspace。请索引多个版本：
  git checkout v1.0 && loomgraph index . -w project:v1.0
  git checkout v2.0 && loomgraph index . -w project:v2.0
```

---

### Step 1: 跨 Workspace 相似实体搜索

在所有目标 workspace 中查找与指定实体匹配的实体：

```bash
loomgraph similar --entity "{entity_name}" --workspaces "{ws1,ws2,ws3}"
```

**解读指引**:
- `match_type: exact` → 同名实体，高置信度匹配
- `match_type: fuzzy` → 近似名称（如重命名、版本后缀），需关注
- `relations_count` → 反映该实体在各 workspace 中的连接密度
- 无匹配 → 该实体可能是某个版本新增的，不需要演化分析

将完整 JSON 结果保存为变量 `SIMILAR_DATA`，后续步骤使用。

如果无任何匹配（matches 为空），输出"在指定 workspace 中未找到相似实体"并结束。
如果仅在 1 个 workspace 中找到，输出"该实体仅存在于 {ws} 中，无法进行跨版本对比"并结束。

---

### Step 2: 逐对结构对比

对 Step 1 中匹配到的 workspace 进行两两对比（按 workspace 名称排序，相邻对比），分析实体关系的演化轨迹：

对每一对相邻 workspace (ws_n, ws_n+1) 执行：

```bash
loomgraph compare --ws1 {ws_n} --ws2 {ws_n+1}
```

**解读指引**:
- 关注 `relation_changes` 中包含目标实体的条目
- `added` 关系 → 该版本新增的依赖或调用
- `removed` 关系 → 该版本移除的依赖或调用
- 关系数量变化趋势 → 反映复杂度增长/收敛

将每对对比结果保存为变量 `COMPARE_DATA_{n}_{n+1}`。

---

### Step 3: 各版本实体详情

对 Step 1 中每个匹配到的实体，获取其在对应 workspace 的调用关系详情：

```bash
loomgraph graph "{matched_entity_name}" -w {workspace}
```

**解读指引**:
- 对比不同版本中同一实体的调用者和被调用者
- 调用者增加 → 该实体变得更核心
- 被调用者增加 → 该实体职责扩展
- fuzzy 匹配的实体要对比其调用图结构相似度

将结果保存为变量 `GRAPH_DATA_{ws}`。

---

### Step 4: LLM 演化分析

将 Step 1-3 收集的所有数据汇总，生成演化分析报告。

**分析要求**:

1. **演化轨迹识别**:
   - 按 workspace 顺序（通常代表时间/版本递进），描述实体的变化历程
   - 标注关键转折点（如重命名、大量关系变化、模块迁移）

2. **分叉类型判断**:
   - **功能扩展**: 关系只增不减，实体名不变 → 正常演化
   - **重构/重命名**: 出现 fuzzy 匹配，旧名消失新名出现 → 跟踪重命名
   - **功能分叉**: 多个 workspace 中同名实体的关系图差异大 → 各自定制
   - **功能退化**: 关系减少，调用者变少 → 可能被废弃

3. **维护代价量化**:
   - 分叉份数 × 平均关系差异 = 同步负担指数
   - 如果 N 个 workspace 维护了 N 个版本，每次上游变更需同步 N 处
   - 估算：抽象为公共模块的一次性成本 vs 持续同步的长期成本

4. **收敛建议**:
   - **合并**: 多个版本核心逻辑一致，差异仅在配置/参数 → 抽象为公共模块 + 参数化
   - **保留分叉**: 各版本逻辑差异过大 → 保持独立，但建议统一接口
   - **废弃**: 某些版本的实体已不再使用 → 清理废弃版本

**输出报告格式**:

```markdown
# 演化分析报告 — {entity_name}

> 生成时间: {date}
> 分析范围: {workspace_count} 个 workspace
> 工具版本: loomgraph {version}

## 概要

| 指标 | 值 |
|------|-----|
| 追踪实体 | {entity_name} |
| 覆盖版本数 | {workspace_count} |
| 精确匹配 | {exact_count} 个 workspace |
| 模糊匹配 | {fuzzy_count} 个 workspace |
| 分叉类型 | {fork_type} |
| 同步负担指数 | {burden_index} |

## 分布概况

| Workspace | 实体名 | 匹配类型 | 关系数 | 备注 |
|-----------|--------|----------|--------|------|
| {ws} | {entity} | {exact/fuzzy} | {count} | {note} |

## 演化轨迹

### {ws_1} → {ws_2}
- 变化: {description}
- 新增关系: {added_relations}
- 移除关系: {removed_relations}
- 判断: {功能扩展/重构/分叉}

### {ws_2} → {ws_3}
- 变化: {description}
- 新增关系: {added_relations}
- 移除关系: {removed_relations}
- 判断: {功能扩展/重构/分叉}

## 各版本调用图对比

### {ws_1}: {entity_name}
- 调用者 ({n}): {caller_1}, {caller_2}, ...
- 被调用 ({n}): {callee_1}, {callee_2}, ...

### {ws_2}: {entity_name}
- 调用者 ({n}): {caller_1}, {caller_2}, ...
- 被调用 ({n}): {callee_1}, {callee_2}, ...

## 分叉代价分析

- **当前状态**: {n} 个版本维护了 {n} 份{相似/不同}实现
- **同步负担**: 每次上游变更需同步 {n} 处，平均差异 {avg_diff} 个关系
- **如果抽象为公共模块**:
  - 一次性成本: 需统一 {diff_count} 处差异
  - 长期收益: 每次变更仅需修改 1 处
- **如果保持分叉**:
  - 每次迭代成本: 同步 {n} 处 × {avg_time}
  - 风险: 版本间差异可能持续扩大

## 建议

### 推荐策略: {合并/保留分叉/废弃}

**理由**: {reasoning}

**操作建议**:
1. {step_1}
2. {step_2}
3. {step_3}

### 注意事项
- {note_1}
- {note_2}
```

---

## 注意事项

1. **Workspace 命名约定**: 建议使用 `project:version` 格式（如 `myapp:v1.0`），方便按版本排序
2. **对比顺序**: 按 workspace 名称字母序排列，相邻两两对比。如果 workspace 名称包含版本号，会自然按版本顺序排列
3. **大量 workspace**: 如果 workspace 超过 5 个，similar 查询可能较慢，建议用 `--workspaces` 指定关键版本
4. **fuzzy 匹配确认**: 对于 fuzzy 匹配的实体，在报告中标注置信度，提醒用户确认是否为同一实体
5. **空结果**: 如果某个步骤返回空数据，在报告中注明而非省略该章节
