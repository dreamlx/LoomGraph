# EPIC-007: 研发熵减 Skills — Claude Code 技能交付

**状态**: ✅ 已完成（Skill A/B/C SKILL.md 全部交付）
**优先级**: P1
**预估**: 8-12 天
**ADR**: [ADR-009](../adr/ADR-009-workspace-as-knowledge-snapshot.md)
**前置依赖**:
- EPIC-004 (deps/overview) → Skill A 基础
- EPIC-005 (workspace 管理) → Skill A 增强 + Skill B/C 前提
- EPIC-006 (跨 workspace 对比) → Skill B/C 基础

---

## 背景

LoomGraph 定位为 AI Agent 的能力层（CLI + JSON），最终价值通过 Claude Code Skills 交付给客户。

当前已有 2 个 Skills：
- `loomgraph-setup` — 项目配置向导
- `loomgraph-init` — CLAUDE.md 注入

研发熵减解决方案需要 3 个新 Skills，编排 LoomGraph CLI + codeindex + git + LLM 来解决企业客户痛点。

## 定位：三层架构中的 Skill 层

```
Skill 层 (Claude Code Skills)              ← 本 EPIC
    ├── Skill A: loomgraph-debt-radar      编排 codeindex + LoomGraph
    ├── Skill B: loomgraph-sync-advisor    编排 LoomGraph + git + LLM
    └── Skill C: loomgraph-evolution       编排 LoomGraph + LLM

LoomGraph 能力层 (CLI)                      ← EPIC-004/005/006
    ├── deps, overview                      单 workspace 查询
    ├── workspace list/info/delete          workspace 管理
    ├── compare, similar                    跨 workspace 对比
    └── impact, search, graph              已有命令

基础设施层
    ├── codeindex (AST 解析, tech-debt)
    ├── LightRAG (图谱存储, 向量检索)
    └── LLM (Claude/GLM, 语义推理)
```

**核心原则**：
- Skill 是编排者，不做数据计算
- LoomGraph CLI 提供结构化 JSON 数据
- Skill 负责流程控制 + LLM 推理 + 报告生成
- 每个 Skill 是一个 SKILL.md 文件，随 wheel 分发，`loomgraph install-skills` 安装

---

## Skill A: `loomgraph-debt-radar` — 债务雷达

### 定位

> 一键生成项目技术债务审计报告，结合代码静态分析和知识图谱结构洞察。

### 解决的客户痛点

| 痛点 | 当前状态 | Skill A 解决方式 |
|------|----------|------------------|
| "这个项目技术债务有多严重？" | 靠人工 review | 自动化报告 |
| "哪些模块最该重构？" | 主观判断 | 数据驱动排序 |
| "重构风险有多大？" | 不确定 | 依赖图 + 影响分析 |

### 输入/输出

```
输入: 项目目录 (已索引到 LoomGraph)
输出: 《技术债务审计报告》(Markdown)
```

### 工作流

```
Step 1: codeindex tech-debt ./src --format json
        → 文件级问题 (God Class, 超大文件, 高噪音比)

Step 2: loomgraph deps --depth 2
        → 模块级依赖图 (循环依赖, 高耦合模块)

Step 3: loomgraph overview
        → 模块功能概览 (识别职责不清的模块)

Step 4: LLM 综合分析
        → 汇总 Step 1-3 的数据
        → 生成优先级排序 + 重构建议
        → 输出 Markdown 报告
```

### SKILL.md 调用的 LoomGraph 命令

| 命令 | 用途 | 依赖 EPIC |
|------|------|-----------|
| `loomgraph deps` | 模块依赖图 | EPIC-004 |
| `loomgraph overview` | 模块概览 | EPIC-004 |
| `loomgraph workspace info` | workspace 统计 | EPIC-005 |
| `codeindex tech-debt` | 文件级债务 | codeindex 已有 |

### 报告模板

```markdown
# 技术债务审计报告 — {project}

## 概要
- 债务等级: {level} (1-5)
- 高风险模块: {count}
- 建议优先处理: {top_module}

## 模块健康度排名
| 排名 | 模块 | 债务分 | 主要问题 | 建议 |
|------|------|--------|----------|------|
| 1 | src/auth | 85 | God Class + 循环依赖 | 拆分 + 解耦 |
| 2 | src/gateway | 62 | 高耦合 | 引入接口层 |

## 依赖结构问题
- 循环依赖: auth ↔ gateway
- 高扇出: common (被 12 个模块依赖)

## 重构优先级建议
1. **紧急**: AuthService 拆分 (影响范围可控)
2. **重要**: 解耦 gateway → auth 单向依赖
3. **改善**: common 模块分层
```

### Stories

| Story | 描述 | 预估 | 状态 |
|-------|------|------|------|
| A-S1 | 编写 SKILL.md 工作流 | 1d | ✅ |
| A-S2 | 设计报告模板 + LLM prompt | 1d | ✅ |
| A-S3 | 端到端验证 (用客户项目) | 0.5d | 📋 |

---

## Skill B: `loomgraph-sync-advisor` — 智能同步顾问

### 定位

> 上游发了补丁，自动分析对下游分支的影响，给出合并建议和冲突预测。

### 解决的客户痛点

| 痛点 | 当前状态 | Skill B 解决方式 |
|------|----------|------------------|
| "上游修了 Bug，下游 3 个分支怎么同步？" | 人工检查每个分支 | 自动分析 + 建议 |
| "合并会冲突吗？冲突点在哪？" | 试 merge 才知道 | 预测 + 定位 |
| "哪个分支最紧急？" | 凭经验判断 | 影响范围排序 |

### 输入/输出

```
输入: 上游 workspace + 下游 workspace(s)
输出: 《同步建议报告》(Markdown) + 可选自动 PR
```

### 工作流

```
Step 1: loomgraph compare --ws1 {upstream} --ws2 {downstream}
        → 实体/关系 diff (新增/删除/变更)

Step 2: loomgraph impact --file {changed_files}
        → 变更影响范围 (直接/间接调用者)

Step 3: git diff {upstream_branch}..{downstream_branch}
        → 代码级差异

Step 4: LLM 综合分析
        → 冲突预测 (结构 diff + 代码 diff 交叉分析)
        → 合并策略建议
        → 优先级排序 (按影响范围)
        → 输出报告
```

### SKILL.md 调用的 LoomGraph 命令

| 命令 | 用途 | 依赖 EPIC |
|------|------|-----------|
| `loomgraph compare` | 跨 workspace 结构 diff | EPIC-006 |
| `loomgraph impact` | 变更影响分析 | 已有 |
| `loomgraph workspace list` | 发现可用 workspace | EPIC-005 |
| `git diff` | 代码级差异 | git |

### 报告模板

```markdown
# 同步建议报告

## 上游变更摘要
- 来源: {upstream_ws}
- 变更实体: {entity_count}
- 新增关系: {new_relations}

## 下游影响分析

### {downstream_ws_1}
- 影响等级: 高
- 受影响实体: AuthService, UserValidator
- 预测冲突: 2 处 (src/auth/validator.py:45-60)
- 建议: 手动合并，保留下游自定义参数

### {downstream_ws_2}
- 影响等级: 低
- 受影响实体: 无直接冲突
- 建议: 可自动合并

## 建议操作顺序
1. 先同步 downstream_2 (低风险，快速完成)
2. 再处理 downstream_1 (需 review)
```

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| B-S1 | 编写 SKILL.md 工作流 | 1.5d | ✅ |
| B-S2 | 设计报告模板 + LLM prompt | 1d | ✅ |
| B-S3 | 多分支场景验证 | 1d | 📋 |

---

## Skill C: `loomgraph-evolution` — 演化观察

### 定位

> 追踪代码在多个分支/版本间的分叉轨迹，量化维护代价，给出收敛建议。

### 解决的客户痛点

| 痛点 | 当前状态 | Skill C 解决方式 |
|------|----------|------------------|
| "这段逻辑在 3 个分支都改了，维护代价多大？" | 不可见 | 量化分叉代价 |
| "要不要把这个功能抽成公共模块？" | 主观判断 | 数据驱动建议 |
| "代码分叉的趋势是收敛还是发散？" | 没有追踪 | 趋势分析 |

### 输入/输出

```
输入: 实体名 + 多个 workspace (版本/分支快照)
输出: 《演化分析报告》(Markdown)
```

### 工作流

```
Step 1: loomgraph similar --entity {name} --workspaces {ws1,ws2,ws3}
        → 跨 workspace 相似实体匹配

Step 2: 对每组匹配实体:
        loomgraph compare --ws1 {ws_a} --ws2 {ws_b}
        → 实体关系 diff

Step 3: LLM 演化分析
        → 分叉点识别
        → 分叉代价估算 (维护 N 份 vs 抽象成公共)
        → 趋势判断 (收敛/发散/稳定)
        → 收敛建议
        → 输出报告
```

### SKILL.md 调用的 LoomGraph 命令

| 命令 | 用途 | 依赖 EPIC |
|------|------|-----------|
| `loomgraph similar` | 跨 workspace 相似检测 | EPIC-006 |
| `loomgraph compare` | 结构 diff | EPIC-006 |
| `loomgraph workspace list` | 发现版本快照 | EPIC-005 |

### 报告模板

```markdown
# 演化分析报告 — {entity_name}

## 分布概况
| Workspace | 实体 | 匹配类型 | 关系数 |
|-----------|------|----------|--------|
| customer-backend:v1.0 | AuthService | exact | 12 |
| customer-backend:v2.0 | AuthService | exact | 18 |
| customer-backend:v3.0 | AuthValidator | fuzzy (0.85) | 22 |

## 演化轨迹
- v1.0 → v2.0: 新增 6 个 CALLS 关系 (功能扩展)
- v2.0 → v3.0: 重命名 AuthService → AuthValidator，新增 4 关系

## 分叉代价分析
- 当前维护 3 份相似实现
- 预估额外维护成本: 每次上游变更需同步 3 处
- 如果抽象为公共模块: 一次性成本 X，长期节省 Y

## 建议
- **推荐**: 将 v1/v2/v3 的 Auth* 抽象为公共模块
- **理由**: 3 个版本的核心逻辑相似度 > 80%
- **风险**: 各版本有定制参数，需保留扩展点
```

### Stories

| Story | 描述 | 预估 |
|-------|------|------|
| C-S1 | 编写 SKILL.md 工作流 | 1.5d | ✅ |
| C-S2 | 设计报告模板 + LLM prompt | 1.5d | ✅ |
| C-S3 | 多版本快照场景验证 | 1d | 📋 |

---

## 交付形态

### 文件结构

```
skills/
├── loomgraph-setup/SKILL.md          # 已有: 项目配置
├── loomgraph-init/SKILL.md           # 已有: CLAUDE.md 注入
├── loomgraph-debt-radar/SKILL.md     # Skill A: 债务雷达
├── loomgraph-sync-advisor/SKILL.md   # Skill B: 智能同步
└── loomgraph-evolution/SKILL.md      # Skill C: 演化观察
```

### 分发方式

与现有 Skills 一致：
1. 打包进 wheel (`loomgraph/_skills/`)
2. 客户执行 `loomgraph install-skills` 安装到 `~/.claude/skills/`
3. Claude Code 自动发现 SKILL.md

### Skill 特性

| 属性 | Skill A | Skill B | Skill C |
|------|---------|---------|---------|
| 名称 | loomgraph-debt-radar | loomgraph-sync-advisor | loomgraph-evolution |
| 触发方式 | `/loomgraph-debt-radar` | `/loomgraph-sync-advisor` | `/loomgraph-evolution` |
| 需要 LLM | 是 (报告生成) | 是 (冲突分析) | 是 (趋势分析) |
| disable-model-invocation | false | false | false |
| 前置条件 | 项目已索引 | 多 workspace 已索引 | 多版本 workspace 已索引 |

---

## 与 EPIC-002 的关系

EPIC-002 定义了 4 个 CLI 命令（impact/sync/similar/evolution）。经过架构重新思考（ADR-009），职责分工明确为：

| EPIC-002 原规划 | 演变 | 归属 |
|----------------|------|------|
| `/loomgraph-impact` (P0) | `loomgraph impact` CLI 命令 | ✅ 已完成 |
| `/loomgraph-sync` (P1) | 拆分: CLI `compare` → EPIC-006, Skill → 本 EPIC Skill B | 重新规划 |
| `/loomgraph-similar` (P2) | 拆分: CLI `similar` → EPIC-006, Skill → 本 EPIC Skill C | 重新规划 |
| `/loomgraph-evolution` (P3) | 合并到 Skill C | 重新规划 |
| (无) | 新增 Skill A 债务雷达 | 本 EPIC |

**关键变化**: CLI 能力与 Skill 编排分离，CLI 提供 JSON 数据，Skill 负责 LLM 推理 + 报告生成。

---

## 开发顺序

```
Phase 1: LoomGraph 能力层 (当前)
├── EPIC-004: deps + overview           → Skill A 可用
├── EPIC-005: workspace list/info/delete → Skill B/C 前提
└── EPIC-006: compare + similar         → Skill B/C 可用

Phase 2: Skill 层 (能力层完成后)
├── Skill A: debt-radar                 → 最先开发，依赖最少
├── Skill B: sync-advisor               → 第二，依赖 compare
└── Skill C: evolution                  → 最后，依赖 similar + compare
```

**原则**: 先完成能力层，确保 CLI 输出稳定可靠后，再开发 Skill 层。

---

## 验收标准

- [x] 3 个 SKILL.md 随 wheel 分发，`install-skills` 可安装
- [x] Skill A: SKILL.md 工作流 + 报告模板已编写
- [ ] Skill A: 用客户项目生成完整的债务审计报告
- [x] Skill B: SKILL.md 工作流 + 报告模板已编写
- [ ] Skill B: 用两个分支 workspace 生成同步建议报告
- [x] Skill C: SKILL.md 工作流 + 报告模板已编写
- [ ] Skill C: 用多版本 workspace 生成演化分析报告
- [ ] 每个 Skill 的 LLM prompt 经过调优，报告质量稳定

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 报告质量不稳定 | 客户体验差 | Prompt 工程 + few-shot 示例 |
| Skill 工作流太长，容易中断 | 用户放弃 | 分步输出中间结果 |
| 客户 LLM 可能不是 Claude | Prompt 兼容性 | 测试 GLM-4 兼容性 |
