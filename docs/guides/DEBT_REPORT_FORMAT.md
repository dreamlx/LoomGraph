# 技术债务报告格式规范

**版本**: 1.0
**日期**: 2026-03-05
**相关**: [ADR-012: 技术债务分析标准化格式](../adr/ADR-012-technical-debt-analysis-format.md)

---

## 概述

本文档定义 LoomGraph 技术债务分析系统的标准输出格式，包括：

- **JSON 格式**（机器可读）：用于 CI/CD 集成、趋势追踪、AI Agent 解析
- **Markdown 格式**（人类可读）：用于文档化、知识沉淀、团队评审
- **Console 格式**（命令行简洁版）：用于日常开发快速反馈

---

## JSON 格式（v1.0）

### Schema 定义

完整 JSON Schema 见 [`../schemas/debt-report-v1.schema.json`](../schemas/debt-report-v1.schema.json)

### 顶层结构

```json
{
  "schema_version": "1.0",
  "timestamp": "2024-03-05T10:30:00Z",
  "project": "my-project:main",
  "generator": {
    "tool": "loomgraph",
    "version": "0.9.0",
    "command": "loomgraph debt --module src"
  },
  "overall_health": { ... },
  "issues": [ ... ],
  "trends": { ... },
  "recommendations": [ ... ]
}
```

### 字段说明

#### `overall_health` 对象

整体健康度评分（0-100）。

```json
{
  "total_score": 73,
  "grade": "C",           // A(≥90), B(80-89), C(70-79), D(60-69), F(<60)
  "breakdown": {
    "topology": 85,       // 拓扑健康度（来自 topology 命令）
    "quality": 68,        // 代码质量（多维度评分平均）
    "test_coverage": 70,  // 测试覆盖率（如果可用）
    "maintainability": 65 // 可维护性（来自 codeindex）
  },
  "summary": {
    "total_entities": 833,
    "p0_issues": 2,       // 严重问题数
    "p1_issues": 5,       // 中等问题数
    "p2_issues": 12       // 轻微问题数
  }
}
```

#### `issues` 数组

具体债务问题列表。

```json
{
  "id": "debt-001",
  "severity": "P0",                 // P0(严重) | P1(中等) | P2(轻微)
  "category": "god_class",          // 问题类型（见下表）
  "entity": "UserService",
  "entity_type": "class",           // class | function | module
  "location": {
    "file": "src/services/UserService.ts",
    "start_line": 1,
    "end_line": 2500
  },
  "metrics": {
    "lines": 2500,
    "methods": 150,
    "maintainability_score": 3,     // 0-10
    "testability_score": 2,         // 0-10
    "impact_radius_score": 1,       // 0-10
    "coupling_score": 2,            // 0-10
    "total_score": 8                // 0-40
  },
  "details": {
    "in_degree": 47,                // 被依赖次数
    "out_degree": 23,               // 依赖数量
    "dependencies": [...]           // 依赖列表（可选）
  },
  "suggestion": "拆分为 UserAuth + UserProfile + UserSettings",
  "estimated_effort": {
    "days": "3-5",
    "complexity": "high"            // low | medium | high
  },
  "references": [
    "src/services/UserService.test.ts",
    "src/controllers/UserController.ts"
  ]
}
```

**问题类型（`category`）**：

| Category | 说明 | 检测依据 |
|----------|------|---------|
| `god_class` | 上帝类 | methods >50 或 lines >2000 |
| `god_function` | 上帝函数 | lines >100 或 complexity >20 |
| `orphan_entity` | 孤儿实体 | in_degree = 0 且非入口点 |
| `hub_fragility` | Hub 脆弱性 | in_degree >30 或 out_degree >20 |
| `circular_dependency` | 循环依赖 | 检测到环形依赖链 |
| `architecture_violation` | 架构违规 | Infra → Domain 反向依赖 |
| `test_smell` | 测试 Smells | it.skip、超大测试文件、Mock 过度 |
| `high_coupling` | 高耦合 | coupling_score <3 |
| `low_maintainability` | 低可维护性 | maintainability_score <3 |

#### `trends` 对象（可选）

时间趋势分析，需要历史数据。

```json
{
  "period": "3_months",
  "debt_increase": "+15%",
  "debt_repayment": "-8%",
  "net_change": "+7%",
  "hotspots": [
    {
      "module": "services",
      "change": "+22%"
    }
  ],
  "comparison": {
    "previous_report": "reports/debt-2024-02-05.json",
    "score_delta": -3,          // 总分变化
    "new_issues": 5,
    "resolved_issues": 2
  }
}
```

#### `recommendations` 数组

重构建议优先级列表。

```json
{
  "priority": 1,                    // 1(最高) → N(最低)
  "action": "refactor",             // refactor | rewrite | delete | isolate
  "target": "UserService",
  "description": "拆分为 3 个独立服务",
  "estimated_effort_days": "3-5",
  "expected_roi": "high",           // high | medium | low
  "blockers": [],                   // 阻塞因素（如依赖未解耦）
  "steps": [
    "1. 创建 UserAuthService 接口",
    "2. 迁移认证相关方法（30 个）",
    "3. 更新 47 处调用点"
  ]
}
```

---

## Markdown 格式

### 模板路径

[`../templates/debt-report.md.template`](../templates/debt-report.md.template)

### 结构示例

```markdown
# 技术债务分析报告

**项目**: my-project:main
**生成时间**: 2024-03-05 10:30:00
**LoomGraph 版本**: 0.9.0

---

## 📊 整体健康度评分

| 维度 | 得分 | 状态 |
|------|------|------|
| **总分** | **73/100** | 🟡 C 级 |
| 拓扑健康度 | 85/100 | 🟢 良好 |
| 代码质量 | 68/100 | 🟡 中等 |
| 测试覆盖 | 70/100 | 🟡 中等 |
| 可维护性 | 65/100 | 🟡 中等 |

**问题统计**:
- 🔴 严重问题 (P0): 2
- 🟡 中等问题 (P1): 5
- 🟢 轻微问题 (P2): 12

---

## 🔴 严重问题（P0）

### 1. 上帝类：UserService

**位置**: `src/services/UserService.ts` (Lines 1-2500)

**质量评分**: 8/40（低于阈值 25）

| 评分维度 | 得分 | 说明 |
|---------|------|------|
| 可维护性 | 3/10 | 文件过大（2500 行），难以理解 |
| 可测试性 | 2/10 | 职责过多，Mock 复杂度高 |
| 影响半径 | 1/10 | 被 47 个模块依赖，变更风险极高 |
| 耦合度 | 2/10 | 直接依赖 23 个类，高耦合 |

**指标**:
- 方法数：150
- 代码行数：2500
- 被依赖次数：47
- 依赖数量：23

**建议**:

拆分策略：

```
UserService (2500行)
  ↓
├─ UserAuthService (800行)      # 认证/授权
├─ UserProfileService (600行)   # 个人信息管理
└─ UserSettingsService (500行)  # 偏好设置
```

**预估工作量**: 3-5 天（高复杂度）

**影响范围**:
- 需要更新 47 处调用点
- 涉及文件：
  - `src/services/UserService.test.ts`
  - `src/controllers/UserController.ts`
  - ...（完整列表见附录）

---

## 🟡 中等问题（P1）

### 2. 循环依赖：OrderService ↔ PaymentService

**影响模块**: 2 个
**调用链长度**: 3 层

**依赖链**:
```
OrderService → PaymentService → OrderValidator → OrderService
```

**建议**: 引入 `IPaymentGateway` 接口解耦

**预估工作量**: 1-2 天（中等复杂度）

---

## 📈 趋势分析

**时间范围**: 近 3 个月（2024-01-05 ~ 2024-03-05）

```
债务演化:
  ┌────────────────────────────────┐
  │ 新增债务: +15% ⚠️              │
  │ 债务偿还: -8%                  │
  │ 净增长: +7%                    │
  └────────────────────────────────┘
```

**热点模块**（债务增长最快）:

1. **services/** (+22%)
   - UserService 持续膨胀
   - 新增 NotificationService（未解耦）

2. **utils/** (+18%)
   - StringUtils 变成上帝类

3. **models/** (+12%)
   - 贫血模型问题加剧

---

## 🎯 重构建议优先级

| 优先级 | 模块 | 操作 | 预估工作量 | ROI | 阻塞因素 |
|--------|------|------|-----------|-----|---------|
| P0-1 | UserService | 拆分 | 3-5 天 | 高 | - |
| P1-1 | Order ↔ Payment | 解耦 | 1-2 天 | 中 | - |
| P1-2 | StringUtils | 重构 | 0.5 天 | 低 | - |
| P2-1 | NotificationService | 模块化 | 1 天 | 中 | UserService 重构 |

---

## 📋 附录

### A1: 完整问题列表

（所有 P0/P1/P2 问题的详细表格）

### A2: 依赖关系图

（循环依赖、架构违规的可视化图表）

### A3: 历史对比

（与上一次报告的 Diff）
```

---

## Console 格式

### 输出示例

```
📊 LoomGraph 技术债务报告
────────────────────────────────────────

项目: my-project:main
时间: 2024-03-05 10:30:00

整体健康度: 73/100 🟡 C 级
  拓扑: 85  质量: 68  测试: 70  维护: 65

🔴 严重问题 (2)
  1. UserService - 上帝类 (8/40)
     位置: src/services/UserService.ts
     → 拆分为 3 个服务 (预计 3-5 天)

  2. Order ↔ Payment - 循环依赖
     → 引入接口解耦 (预计 1-2 天)

🟡 中等问题 (5)
  3. StringUtils - 超长类 (18/40)
  4. HardwareBLE.test.ts - 超大测试 (1625 行)
  5. ...

📈 趋势
  ✗ 债务净增长: +7% (近 3 个月)
  ⚠  热点模块: services/ (+22%)

💡 下一步行动
  运行: loomgraph refactor-plan UserService
  查看: loomgraph debt --format markdown > report.md

────────────────────────────────────────
完整报告: /tmp/loomgraph-debt-report.json
```

### 格式规范

**颜色编码**（如果终端支持）：

- 🟢 绿色：良好（≥80）
- 🟡 黄色：中等（60-79）
- 🔴 红色：差（<60）

**严重性图标**：

- 🔴 `P0`（严重）
- 🟡 `P1`（中等）
- 🟢 `P2`（轻微）

**进度指示器**（长时间操作）：

```
分析拓扑结构... ████████████████████ 100%
计算质量评分... ████████████░░░░░░░░  60%
```

---

## 数据契约（codeindex ↔ LoomGraph）

### 职责分离原则

**codeindex**（原始数据采集器）:
- ✅ 提供：测量值（lines, line_number, severity）
- ❌ 不提供：推断值（complexity）、聚合值（详细 breakdown）

**LoomGraph**（分析引擎）:
- ✅ 接收：codeindex 原始数据
- ✅ 计算：complexity 估算、breakdown 聚合、多维度评分

---

### codeindex 输出格式（v0.22.0 实际格式）

codeindex 通过 `tech-debt` 命令（`debt-scan` 为别名）输出 JSON 数据。

**实际输出示例**：

```json
{
  "timestamp": "2026-03-06T15:32:14.368787Z",
  // ❌ 无 target_path 字段（调用上下文，LoomGraph 自己记录）
  "summary": {
    "total_files": 97,
    "giant_files": 0,
    "giant_functions": 3,
    "test_smells": 64,
    "avg_maintainability": 9.9
  },
  "giant_files": [
    {
      "path": "src/services/UserService.ts",
      "lines": 2500,
      "severity": "critical"
    }
  ],
  "giant_functions": [
    {
      "path": "tests/test_symbol_overload.py",
      "function_name": "test_noise_breakdown_categorization",
      "lines": 92
      // ❌ 无 complexity 字段（LoomGraph 基于 lines 估算）
    }
  ],
  "test_smells": [
    {
      "path": "tests/test_windows_path_optimization.py",
      "type": "skipped_test",
      "details": "Skipped test detected: @pytest.mark.skip at line 120",
      "line_number": 120,
      "metric_value": null
      // ✅ 使用 line_number（行号），不是 lines（行数）
    }
  ],
  "maintainability_scores": [
    {
      "path": "tests/test_cli_scan_defaults_bdd.py",
      "score": 9.5,
      "breakdown": {
        "quality_score_based": 9.5
        // ❌ 简化 breakdown（详细聚合在 LoomGraph）
      }
    }
  ],
  "file_reports": [...]  // 完整原始数据（供 LoomGraph 聚合）
}
```

**LoomGraph 集成方式**：

```bash
# Step 1: codeindex 扫描
codeindex tech-debt ./src --format json > /tmp/codeindex-debt.json

# Step 2: LoomGraph 分析（自动合并 codeindex 数据）
loomgraph debt --codeindex-data /tmp/codeindex-debt.json --format markdown
```

**数据映射规则**：

| codeindex 字段 | LoomGraph 处理 | 说明 |
|---------------|---------------|------|
| `timestamp` | 直接使用 | ISO 8601 时间戳 |
| `summary.*` | 直接使用 | 汇总统计 |
| `giant_files[].lines` | 直接使用 | 文件行数 |
| `giant_functions[].lines` | → 估算 `complexity` | `complexity ≈ lines // 10` |
| `test_smells[].line_number` | 直接使用 | 跳过测试的行号 |
| `maintainability_scores[].score` | 直接使用或调整 | 0-10 分 |
| `maintainability_scores[].breakdown` | 忽略，从 `file_reports` 聚合 | 详细分解由 LoomGraph 计算 |
| `file_reports` | 聚合详细 `breakdown` | 完整问题列表 |

---

## 版本历史

### v1.0（2026-03-05）

**初始版本**：
- 定义 JSON/Markdown/Console 三种格式
- 四维评分体系（可维护性、可测试性、影响半径、耦合度）
- 趋势分析结构（可选）
- codeindex 数据契约

### 未来版本（规划）

**v1.1（预计 2026-04-01）**：
- 新增 `test_coverage` 字段（从测试覆盖率工具导入）
- 新增 `security_issues` 字段（安全 Smells）
- 支持多语言项目（当前主要针对 TypeScript/Python）

**v2.0（预计 2026-06-01）**：
- 引入 AI 生成重构建议（调用 Claude API）
- 支持自定义评分权重（用户可配置）
- 支持 HTML 交互式报告

---

## 附录

### A1: JSON Schema 完整定义

见 [`../schemas/debt-report-v1.schema.json`](../schemas/debt-report-v1.schema.json)

### A2: Markdown 模板

见 [`../templates/debt-report.md.template`](../templates/debt-report.md.template)

### A3: 示例报告

- **JSON 示例**: [`examples/debt-report-example.json`](../../tests/fixtures/debt-report-example.json)
- **Markdown 示例**: [`examples/debt-report-example.md`](../../tests/fixtures/debt-report-example.md)

### A4: 相关文档

- **ADR-012**: [技术债务分析标准化格式](../adr/ADR-012-technical-debt-analysis-format.md)
- **LoomGraph Issue #21**: [EPIC-010: Technical Debt Analysis](https://github.com/dreamlx/LoomGraph/issues/21)
- **codeindex Issue #24**: [debt-scan 命令](https://github.com/dreamlx/codeindex/issues/24)
