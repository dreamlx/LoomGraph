# EPIC-002: Git 集成 Skills - 代码演化洞察

**版本**: 0.1.0
**创建日期**: 2025-02-06
**状态**: 📝 需求分析中
**优先级**: P0-P3

---

## 1. 背景与动机

### 1.1 业务背景

参考《研发熵减解决方案》，企业面临的核心痛点：

| 研发抱怨 | 根本原因 |
|----------|----------|
| "改一行不知道影响什么" | 信息黑洞：依赖关系不可见 |
| "Bug 修了又出现" | 没有机制追踪相似代码 |
| "Fork 太多，合并地狱" | 分叉代价不可见 |
| "新人上手慢" | 架构知识在人脑里，不在代码里 |

### 1.2 LoomGraph 定位

> **AI 观察者 + 建议者**：让代码演化的代价可见，人做决定

```
代码仓库 (主线 + N 分支)
         ↓
    LoomGraph Skills
         ↓
代码演化洞察报告 + 操作建议
```

### 1.3 当前能力

| 命令 | 能力 | 状态 |
|------|------|------|
| `loomgraph search` | 语义搜索代码 | ✅ 已实现 |
| `loomgraph graph` | 调用关系查询 | ✅ 已实现 |
| `loomgraph index` | 代码索引 | ✅ 已实现 |
| `loomgraph status` | 服务状态 | ✅ 已实现 |

**缺失**：与 git 的深度集成

---

## 2. 目标 Skills

### 2.1 Skills 总览

```
LoomGraph Git Integration Skills
├── P0: /loomgraph-impact     变更影响分析
├── P1: /loomgraph-sync       智能同步助手
├── P2: /loomgraph-similar    跨分支相似检测
└── P3: /loomgraph-evolution  演化追踪
```

### 2.2 优先级矩阵

| 优先级 | Skill | 价值 | 复杂度 | 依赖 |
|--------|-------|------|--------|------|
| **P0** | impact | 最直接，"改了影响谁" | 低 | git diff + graph |
| **P1** | sync | Skill B 核心场景 | 中 | impact + LLM |
| **P2** | similar | Skill C 核心场景 | 中 | 多分支索引 |
| **P3** | evolution | 完整演化追踪 | 高 | similar + git log |

---

## 3. P0: `/loomgraph-impact` - 变更影响分析

### 3.1 用户故事

```gherkin
Feature: 变更影响分析
  As a 开发者
  I want to 知道我的代码变更会影响哪些模块
  So that 我可以评估风险并通知相关人员

  Scenario: 分析单个 commit 的影响
    Given 我刚提交了一个 commit
    When 我执行 `loomgraph impact HEAD`
    Then 我看到被修改函数的调用者列表
    And 我看到受影响的模块清单
    And 我看到风险等级评估

  Scenario: 分析未提交变更的影响
    Given 我有未提交的代码修改
    When 我执行 `loomgraph impact --staged`
    Then 我看到暂存区变更的影响分析

  Scenario: 分析两个分支的差异影响
    Given 我在 feature 分支
    When 我执行 `loomgraph impact main..HEAD`
    Then 我看到整个分支相对于 main 的影响分析
```

### 3.2 CLI 设计

```bash
# 分析最近一次 commit
loomgraph impact HEAD

# 分析指定 commit
loomgraph impact abc1234

# 分析暂存区变更
loomgraph impact --staged

# 分析两个分支差异
loomgraph impact main..feature

# 分析指定文件的变更影响
loomgraph impact --file src/auth/login.py
```

### 3.3 输出格式 (JSON)

```json
{
  "success": true,
  "data": {
    "commit": "abc1234",
    "changed_symbols": [
      {
        "name": "UserService.login",
        "file": "src/auth/service.py",
        "change_type": "modified",
        "lines_changed": 15
      }
    ],
    "impact_analysis": {
      "direct_callers": [
        {
          "name": "AuthController.handle_login",
          "file": "src/api/auth.py",
          "line": 45
        }
      ],
      "indirect_callers": [
        {
          "name": "APIRouter.dispatch",
          "file": "src/api/router.py",
          "depth": 2
        }
      ],
      "affected_modules": ["auth", "api"],
      "affected_tests": ["tests/unit/test_auth.py"]
    },
    "risk_assessment": {
      "level": "medium",
      "reason": "修改了被 5 个地方调用的核心认证函数",
      "suggestions": [
        "建议运行 auth 模块的测试",
        "建议通知 @auth-team 进行 review"
      ]
    }
  }
}
```

### 3.4 技术实现

```
输入: git commit / git diff
         ↓
Step 1: 解析变更文件和符号 (git diff --name-only + codeindex)
         ↓
Step 2: 查询知识图谱 (loomgraph graph --direction callers)
         ↓
Step 3: 计算影响范围 (递归查找调用者)
         ↓
Step 4: 风险评估 (LLM 或规则)
         ↓
输出: 影响分析报告 (JSON)
```

### 3.5 依赖

- `git diff` - 获取变更列表
- `codeindex` - 解析变更的符号
- `loomgraph graph` - 查询调用关系
- (可选) LLM - 生成风险评估建议

---

## 4. P1: `/loomgraph-sync` - 智能同步助手

### 4.1 用户故事

```gherkin
Feature: 智能同步助手
  As a 分支维护者
  I want to 知道上游补丁对我的分支的影响
  So that 我可以安全地同步上游变更

  Scenario: 分析上游补丁影响
    Given 上游发布了安全补丁
    When 我执行 `loomgraph sync upstream/main`
    Then 我看到补丁影响的文件
    And 我看到与我的分支的冲突预测
    And 我看到合并建议

  Scenario: 批量分析多个下游分支
    Given 我是主线维护者
    When 我执行 `loomgraph sync --downstream customer-*`
    Then 我看到每个下游分支的同步状态
    And 我可以一键生成 PR
```

### 4.2 CLI 设计

```bash
# 分析与上游的差异
loomgraph sync upstream/main

# 分析多个下游分支
loomgraph sync --downstream "customer-*"

# 预览合并冲突
loomgraph sync upstream/main --preview-conflicts

# 生成同步 PR
loomgraph sync upstream/main --create-pr
```

### 4.3 输出格式

```json
{
  "success": true,
  "data": {
    "upstream": "upstream/main",
    "downstream": "customer-a",
    "patch_info": {
      "commits": 3,
      "files_changed": 5,
      "description": "Security fix for auth module"
    },
    "conflict_analysis": {
      "can_auto_merge": false,
      "conflicts": [
        {
          "file": "src/auth/validator.py",
          "lines": "45-60",
          "reason": "上游改了签名，下游加了参数",
          "suggestion": "保留下游参数，合并上游逻辑"
        }
      ]
    },
    "action": {
      "recommended": "manual_merge",
      "pr_draft": "https://github.com/.../pull/new"
    }
  }
}
```

---

## 5. P2: `/loomgraph-similar` - 跨分支相似检测

### 5.1 用户故事

```gherkin
Feature: 跨分支相似代码检测
  As a 架构师
  I want to 发现多个分支中的相似实现
  So that 我可以考虑抽象为通用模块

  Scenario: 检测相似函数
    Given 多个分支都有认证逻辑
    When 我执行 `loomgraph similar "authenticate user"`
    Then 我看到各分支的相似实现
    And 我看到抽象建议
```

### 5.2 CLI 设计

```bash
# 按语义搜索相似代码
loomgraph similar "user authentication"

# 按函数名搜索
loomgraph similar --function "validate_password"

# 指定分支范围
loomgraph similar "auth logic" --branches "customer-*"
```

---

## 6. P3: `/loomgraph-evolution` - 演化追踪

### 6.1 用户故事

```gherkin
Feature: 代码演化追踪
  As a 技术负责人
  I want to 追踪模块的演化历史
  So that 我可以理解技术债务的来源和代价

  Scenario: 追踪模块演化
    Given auth 模块经历了多次分叉
    When 我执行 `loomgraph evolution src/auth`
    Then 我看到分叉时间线
    And 我看到每次分叉的代价估算
    And 我看到合并建议
```

### 6.2 CLI 设计

```bash
# 追踪模块演化
loomgraph evolution src/auth

# 生成演化报告
loomgraph evolution src/auth --report markdown

# 可视化分叉树
loomgraph evolution src/auth --visualize
```

---

## 7. 实现计划

### 7.1 Phase 1: P0 实现 (impact)

```
Week 1:
├── Day 1-2: TDD - 编写测试用例
├── Day 3-4: 实现 git diff 解析 + 符号提取
└── Day 5: 集成 loomgraph graph 查询

Week 2:
├── Day 1-2: 影响范围计算算法
├── Day 3: 风险评估规则
├── Day 4: CLI 集成
└── Day 5: 文档 + 验收
```

### 7.2 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Git 操作 | `subprocess` + `git` | 解析 diff/log |
| 符号解析 | `codeindex` | 提取变更的符号 |
| 图查询 | `LightRAG` | 调用关系查询 |
| 风险评估 | 规则 / LLM | 生成建议 |

### 7.3 测试策略

```
tests/
├── unit/
│   ├── test_git_parser.py      # git diff 解析
│   ├── test_impact_analyzer.py # 影响分析算法
│   └── test_risk_assessor.py   # 风险评估
├── integration/
│   └── test_impact_e2e.py      # 端到端测试
└── bdd/
    └── features/
        └── impact.feature      # BDD 场景
```

---

## 8. 验收标准

### 8.1 P0 验收标准

- [ ] `loomgraph impact HEAD` 返回正确的影响分析
- [ ] 支持 commit / staged / branch 三种模式
- [ ] JSON 输出符合设计规范
- [ ] 单元测试覆盖率 >= 90%
- [ ] 有 BDD 场景测试
- [ ] 文档完整

### 8.2 性能要求

| 指标 | 目标 |
|------|------|
| 单 commit 分析 | < 5s |
| 100 文件分支对比 | < 30s |

---

## 9. 相关文档

- [研发熵减解决方案](../../../OneDrive-Personal/Work/20_一行码云/30_Products/解决方案/研发熵减解决方案-mini草案.md)
- [CLI_DESIGN.md](../api/CLI_DESIGN.md)
- [SYSTEM_DESIGN.md](../architecture/SYSTEM_DESIGN.md)

---

## 10. 变更历史

| 日期 | 版本 | 变更 | 作者 |
|------|------|------|------|
| 2025-02-06 | 0.1.0 | 初始需求分析 | Claude + DreamLinx |
