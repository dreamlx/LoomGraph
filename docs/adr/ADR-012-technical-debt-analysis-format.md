# ADR-012: 技术债务分析标准化格式

**状态**: 已批准
**日期**: 2026-03-05
**决策者**: LoomGraph 架构团队
**相关 ADR**: ADR-009（Workspace 即知识快照）, ADR-011（AI 迭代策略）

---

## 背景与问题

### 当前技术债务分析现状

LoomGraph 在 EPIC-009 中实现了基础的拓扑债务分析（`topology` 命令），但存在以下问题：

1. **缺乏标准化格式**
   - 当前输出：简单 JSON 对象，无固定 Schema
   - 人类可读性差：缺少 Markdown 报告格式
   - 不支持趋势分析：无时间维度数据

2. **评分维度单一**
   - 当前只有 `topology_score`（0-100）
   - 无法体现多维度质量：可维护性、可测试性、影响半径、耦合度

3. **决策支持不足**
   - 缺乏明确的债务优先级分级（P0/P1/P2）
   - 无重构建议生成机制
   - 无工作量预估（ROI 评估）

4. **职责边界模糊**
   - codeindex（静态分析）vs LoomGraph（图谱分析）职责不清
   - 重复功能可能出现在两个仓库

### 启发案例

参考真实测试重构分析案例（2026-03-05），其核心方法论包括：

**1. 多维度评分矩阵**
```
Confidence（置信度）+ Speed（速度）+ Isolation（隔离性）= 总分
决策规则：≥13分保留、8-12分重构、<8分删除
```

**2. 分层分析**
```
测试金字塔：E2E(10%) / Integration(20%) / Unit(70%)
架构分层：Application(薄) / Domain(核心) / Infra(隔离)
```

**3. 标准化报告格式**
```markdown
## 债务评分矩阵
| 模块 | 可维护性 | 可测试性 | 影响半径 | 耦合度 | 总分 | 处理 |
| UserService | 3 | 2 | 1 | 2 | 8/40 | ❌ 重写 |
```

---

## 决策

**LoomGraph 采用标准化技术债务分析格式，包含以下核心要素**：

### 1. 多维度评分体系

**四维质量评分**（每项 0-10 分，总分 40）：

| 维度 | 计算依据 | 责任方 |
|------|---------|--------|
| **Maintainability**（可维护性） | 文件大小、命名规范、注释覆盖率 | codeindex |
| **Testability**（可测试性） | 依赖注入、职责单一性、低耦合 | LoomGraph |
| **Impact**（影响半径） | 入度/出度、变更传播范围 | LoomGraph |
| **Coupling**（耦合度） | 依赖数量、循环依赖检测 | LoomGraph |

**决策规则**：
- **≥35 分**：✅ 核心资产，优先维护
- **25-34 分**：🔨 重构候选
- **<25 分**：❌ 重写/淘汰候选

### 2. 标准化输出格式

**三种格式支持**：

#### 格式 A：JSON（机器可读，CI/CD 集成）

```json
{
  "timestamp": "2024-03-05T10:30:00Z",
  "project": "my-project:main",
  "overall_health": {
    "total_score": 73,
    "breakdown": {
      "topology": 85,
      "quality": 68,
      "test_coverage": 70,
      "maintainability": 65
    }
  },
  "issues": [
    {
      "severity": "P0",
      "category": "god_class",
      "entity": "UserService",
      "location": "src/services/UserService.ts",
      "metrics": {
        "methods": 150,
        "lines": 2500,
        "maintainability_score": 3,
        "testability_score": 2,
        "impact_radius_score": 1,
        "coupling_score": 2,
        "total_score": 8
      },
      "suggestion": "拆分为 UserAuth + UserProfile + UserSettings",
      "estimated_effort_days": "3-5"
    }
  ],
  "trends": {
    "3_months_debt_increase": "+15%",
    "3_months_debt_repayment": "-8%"
  }
}
```

**JSON Schema 路径**：`docs/schemas/debt-report-v1.schema.json`

#### 格式 B：Markdown（人类可读，文档化）

```markdown
# 技术债务分析报告
**项目**: my-project:main
**生成时间**: 2024-03-05 10:30:00

## 📊 整体健康度评分
| 维度 | 得分 | 状态 |
|------|------|------|
| **总分** | **73/100** | 🟡 中等 |
| 拓扑健康度 | 85/100 | 🟢 良好 |

## 🔴 严重问题（P0）
### 1. 上帝类：UserService
- **质量评分**: 8/40
- **建议**: 拆分为 3 个服务

## 📈 趋势分析
- 新增债务: +15% (近 3 个月)
```

**Template 路径**：`docs/templates/debt-report.md.template`

#### 格式 C：Console（命令行简洁版）

```
📊 LoomGraph 技术债务报告
────────────────────────────────────────

总体健康度: 73/100 🟡

🔴 严重问题 (2)
  1. UserService - 上帝类 (8/40)
  2. Order ↔ Payment - 循环依赖

📈 趋势: 债务净增长 +7%
```

### 3. 职责边界划分

| 功能 | codeindex | LoomGraph | 数据流 |
|------|-----------|-----------|--------|
| 文件大小统计 | ✅ 主责 | ❌ | → |
| 超长函数检测 | ✅ 主责 | ❌ | → |
| Mock 使用统计 | ✅ 主责 | ❌ | → |
| 跳过的测试识别 | ✅ 主责 | ❌ | → |
| 圈复杂度/认知复杂度 | ✅ 主责 | ❌ | → |
| **可维护性评分** | ✅ 计算 | 🔄 集成 | codeindex → LoomGraph |
| 孤儿实体检测 | ❌ | ✅ 主责 | |
| 循环依赖检测 | ❌ | ✅ 主责 | |
| 架构分层违规 | ❌ | ✅ 主责 | |
| 变更影响分析 | ❌ | ✅ 主责 | |
| **可测试性评分** | 🔄 辅助数据 | ✅ 计算 | codeindex → LoomGraph |
| **影响半径评分** | ❌ | ✅ 计算 | |
| **耦合度评分** | ❌ | ✅ 计算 | |
| **生成最终报告** | ❌ | ✅ 主责 | |

**数据流**：
```
codeindex scan --debt-analysis
  ↓ (JSON 输出)
loomgraph debt --codeindex-data <file>
  ↓ (合并图谱数据)
最终报告（JSON/Markdown/Console）
```

### 4. 新命令设计

#### LoomGraph 侧

```bash
# 完整分析（默认）
loomgraph debt

# 指定模块
loomgraph debt --module src/services

# 输出格式
loomgraph debt --format json|markdown|console

# 导入 codeindex 数据
loomgraph debt --codeindex-data codeindex-output.json

# 趋势分析（需要 git）
loomgraph debt --trend 3m

# 设置评分阈值
loomgraph debt --threshold 30  # <30 分标记为 P0

# 生成重构计划
loomgraph debt --action-plan
```

#### codeindex 侧

```bash
# 新增子命令
codeindex debt-scan ./src --format json

# 输出示例
{
  "giant_files": [
    {"path": "UserService.ts", "lines": 2500, "score": 3}
  ],
  "giant_functions": [
    {"path": "processOrder", "lines": 150, "complexity": 25}
  ],
  "test_smells": [
    {"path": "BLE.test.ts", "type": "giant_test", "lines": 1625}
  ],
  "maintainability_scores": {
    "UserService.ts": 3,
    "OrderService.ts": 7
  }
}
```

---

## 理由

### 为什么需要多维度评分？

**反例：单一 topology_score 的局限**

假设两个类都是 `topology_score = 60`：

| 类 | Lines | Methods | 入度 | 出度 | 问题 |
|-----|-------|---------|------|------|------|
| ClassA | 200 | 10 | 2 | 3 | 正常类 |
| ClassB | 2500 | 150 | 47 | 23 | 上帝类 |

单一分数无法区分两者，但多维度评分可以：

| 类 | 可维护性 | 可测试性 | 影响半径 | 耦合度 | 总分 | 决策 |
|-----|---------|---------|---------|--------|------|------|
| ClassA | 8 | 9 | 8 | 8 | 33/40 | ✅ 保留 |
| ClassB | 2 | 3 | 1 | 2 | 8/40 | ❌ 重写 |

### 为什么需要标准化格式？

**1. CI/CD 集成**
```yaml
# GitHub Actions 集成
- name: Debt Analysis
  run: loomgraph debt --format json > debt.json
- name: Check Threshold
  run: |
    SCORE=$(jq '.overall_health.total_score' debt.json)
    if [ $SCORE -lt 70 ]; then exit 1; fi
```

**2. 趋势追踪**
```bash
# 存储历史报告
git add reports/debt-2024-03-05.json
git commit -m "chore: debt report"

# 对比趋势
loomgraph debt-trend --compare reports/debt-2024-02-05.json
```

**3. AI Agent 友好**
```python
# Claude Code Skills 可解析
report = json.load("debt.json")
p0_issues = [i for i in report["issues"] if i["severity"] == "P0"]
# 自动生成重构 PR
```

### 为什么职责边界清晰？

**避免重复开发**：
- codeindex 已有复杂度计算能力（tree-sitter AST）
- LoomGraph 专注图谱分析（调用关系、影响范围）
- 明确数据流向：codeindex → LoomGraph，单向依赖

**独立演化**：
- codeindex 可独立升级复杂度算法（如迁移到 Ruff）
- LoomGraph 可独立优化图谱查询性能

---

## 替代方案

### 方案 A：全部在 LoomGraph 中实现（已拒绝）

**优点**：
- 单一入口，用户体验统一

**缺点**：
- ❌ 重复 codeindex 已有能力（复杂度计算）
- ❌ LoomGraph 需要依赖 tree-sitter（违反架构分层）
- ❌ codeindex 无法独立提供债务分析（耦合性强）

### 方案 B：全部在 codeindex 中实现（已拒绝）

**优点**：
- codeindex 本身已有 `tech-debt` 命令基础

**缺点**：
- ❌ codeindex 无法获取图谱关系（无调用图、无依赖传播）
- ❌ 无法实现影响半径评分、循环依赖检测
- ❌ 违反三仓库架构（codeindex 职责是解析，不是分析）

### 方案 C：标准化格式 + 明确职责边界（已选择）

**优点**：
- ✅ 符合三仓库架构（codeindex 解析 → LoomGraph 映射调度）
- ✅ 数据流单向清晰（codeindex → LoomGraph）
- ✅ 两个工具可独立演化
- ✅ 支持 CI/CD 集成、趋势追踪、AI Agent 解析

---

## 实现路线图

### Phase 1：定义标准（1 天）

**LoomGraph 侧**：
- [ ] 创建 `docs/guides/DEBT_REPORT_FORMAT.md` 规范文档
- [ ] 创建 `docs/schemas/debt-report-v1.schema.json`（JSON Schema）
- [ ] 创建 `docs/templates/debt-report.md.template`（Markdown 模板）

**codeindex 侧**：
- [ ] 文档：`docs/api/DEBT_SCAN_OUTPUT.md`（输出格式规范）

### Phase 2：codeindex 实现（2-3 天）

**新增 `debt-scan` 子命令**：
```bash
codeindex debt-scan ./src --format json > codeindex-debt.json
```

**输出内容**：
- 文件大小统计（>1000 行标记为 giant_file）
- 超长函数检测（>100 行或圈复杂度 >15）
- 测试 Smells（`it.skip`、超大测试文件）
- Mock 使用统计
- 可维护性评分（0-10）

**集成点**：
- 修改 `codeindex/src/codeindex/tech_debt.py`（复用现有逻辑）
- 新增 `codeindex/src/codeindex/debt_scanner.py`

### Phase 3：LoomGraph 实现（3-5 天）

**新增 `debt` 命令**：
```bash
loomgraph debt --format markdown > report.md
```

**核心模块**：
- `src/loomgraph/core/debt_analyzer.py`（债务分析器）
- `src/loomgraph/cli/_debt.py`（CLI 命令）

**数据流**：
```python
class DebtAnalyzer:
    async def analyze(self, codeindex_data: dict | None = None):
        # Step 1: 获取 codeindex 数据（可选）
        maintainability = codeindex_data or self._estimate_maintainability()

        # Step 2: 获取图谱数据
        topology = await self.topology_analyzer.analyze()
        deps = await self.deps_analyzer.analyze()

        # Step 3: 计算四维评分
        scores = {
            "maintainability": maintainability,
            "testability": self._calc_testability(topology, deps),
            "impact": self._calc_impact(topology),
            "coupling": self._calc_coupling(deps)
        }

        # Step 4: 生成报告
        return self._generate_report(scores)
```

### Phase 4：集成与测试（2 天）

**单元测试**：
- `tests/unit/test_debt_analyzer.py`（LoomGraph）
- `tests/unit/test_debt_scanner.py`（codeindex）

**集成测试**：
```bash
# E2E 流程
cd /path/to/project
codeindex debt-scan ./src --format json > /tmp/codeindex.json
loomgraph debt --codeindex-data /tmp/codeindex.json --format markdown
```

**性能基准**：
- 目标：1000 个文件项目 < 30 秒
- codeindex 扫描：< 10 秒
- LoomGraph 分析：< 20 秒

### Phase 5：文档与发布（1 天）

**用户文档**：
- 更新 `CLAUDE.md`（新增 `loomgraph debt` 命令）
- 更新 `README.md`（技术债务分析特性）

**CHANGELOG**：
- LoomGraph v0.9.0：新增 `debt` 命令（ADR-012）
- codeindex v0.12.0：新增 `debt-scan` 子命令

---

## 影响与风险

### 正面影响

1. **量化决策**：从"感觉这段代码不好"到"评分 8/40，建议重写"
2. **CI/CD 集成**：自动债务检测，阻止低质量代码合并
3. **趋势可见**：每周生成报告，追踪债务演化
4. **AI Agent 友好**：标准化 JSON 格式，Claude Code Skills 可直接解析

### 潜在风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|-------|------|---------|
| **评分算法争议** | 中 | 中 | 在文档中说明评分为"参考值"，非绝对标准 |
| **性能问题**（大项目） | 低 | 高 | 分阶段执行（先 codeindex，再 LoomGraph） |
| **两个仓库同步** | 中 | 中 | 定义清晰的数据契约（JSON Schema） |

---

## 度量与成功标准

### 发布后 1 个月

- [ ] **采用率**: ≥3 个客户项目使用 `loomgraph debt`
- [ ] **性能**: 1000 文件项目 < 30 秒
- [ ] **准确性**: 用户反馈 P0 问题准确率 ≥80%

### 发布后 3 个月

- [ ] **CI/CD 集成**: ≥1 个客户将 `loomgraph debt` 集成到 CI
- [ ] **趋势追踪**: 生成 ≥10 份历史对比报告
- [ ] **AI Agent 使用**: Claude Code Skills 中 ≥1 个技能调用 `debt` 命令

---

## 参考资料

1. **测试重构分析案例**（2026-03-05）：多维度评分矩阵、测试金字塔分析
2. **ADR-009**：Workspace 即知识快照（趋势分析基础）
3. **ADR-011**：AI 迭代策略（外部迭代，标准化输出重要性）
4. **EPIC-009**：拓扑债务分析（当前 `topology` 命令基础）
5. **Manon 评估报告**：多轮迭代与单轮查询对比（性能基准参考）

---

## 附录：评分算法细节

### A1: 可维护性评分（Maintainability）

**计算公式**（0-10 分）：

```python
def calc_maintainability(file_data: dict) -> int:
    """
    基于文件大小、命名规范、注释覆盖率计算可维护性

    输入：codeindex debt-scan 输出
    {
      "path": "UserService.ts",
      "lines": 2500,
      "comment_lines": 50,
      "naming_violations": 12
    }
    """
    score = 10  # 满分

    # 文件大小惩罚
    if file_data["lines"] > 2000:
        score -= 5
    elif file_data["lines"] > 1000:
        score -= 3
    elif file_data["lines"] > 500:
        score -= 1

    # 注释率加分
    comment_ratio = file_data["comment_lines"] / file_data["lines"]
    if comment_ratio < 0.05:  # <5% 注释
        score -= 2

    # 命名规范惩罚
    if file_data["naming_violations"] > 10:
        score -= 2

    return max(0, score)
```

### A2: 可测试性评分（Testability）

**计算公式**（0-10 分）：

```python
async def calc_testability(entity: str, topology: dict, deps: dict) -> int:
    """
    基于依赖注入、职责单一性、低耦合计算可测试性

    需要 LoomGraph 图谱数据
    """
    score = 10

    # 依赖数量惩罚
    deps_count = len(deps.get(entity, []))
    if deps_count > 20:
        score -= 4
    elif deps_count > 10:
        score -= 2

    # 方法数量惩罚（职责单一性）
    methods = topology.get("god_functions", [])
    if entity in [m["entity"] for m in methods]:
        score -= 3

    # 循环依赖惩罚
    if has_circular_dependency(entity, deps):
        score -= 3

    return max(0, score)
```

### A3: 影响半径评分（Impact Radius）

**计算公式**（0-10 分）：

```python
async def calc_impact(entity: str, topology: dict) -> int:
    """
    基于入度/出度、变更传播范围计算影响半径

    影响半径越小越好（分数越高）
    """
    degree_data = topology.get("degree_distribution", [])
    entity_degree = next(
        (d for d in degree_data if d["entity"] == entity),
        {"in_degree": 0, "out_degree": 0}
    )

    score = 10

    # 高入度惩罚（被很多模块依赖，变更风险大）
    if entity_degree["in_degree"] > 50:
        score -= 5
    elif entity_degree["in_degree"] > 20:
        score -= 3

    # 高出度惩罚（依赖很多模块，影响范围广）
    if entity_degree["out_degree"] > 30:
        score -= 3

    return max(0, score)
```

### A4: 耦合度评分（Coupling）

**计算公式**（0-10 分）：

```python
async def calc_coupling(entity: str, deps: dict) -> int:
    """
    基于依赖数量、跨模块依赖、循环依赖计算耦合度
    """
    score = 10

    # 直接依赖数量
    direct_deps = len(deps.get(entity, []))
    if direct_deps > 15:
        score -= 4
    elif direct_deps > 8:
        score -= 2

    # 跨模块依赖惩罚
    cross_module_deps = count_cross_module_deps(entity, deps)
    if cross_module_deps > 5:
        score -= 3

    # 循环依赖严重惩罚
    if has_circular_dependency(entity, deps):
        score -= 3

    return max(0, score)
```

---

**批准**: ✅
**下一步**: 创建 GitHub Issues（LoomGraph + codeindex）→ 实施 Phase 1
