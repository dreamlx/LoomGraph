# 图谱优化讨论：codeindex Parser vs LightRAG 提取

**状态**: ✅ 已决策
**日期**: 2025-02-03
**决策记录**: ADR-005, ADR-006

---

## 决策结果

经过讨论，采用 **方式 C: 混合策略（AST 优先）**，具体决策如下：

| 决策点 | 选择 | 说明 |
|--------|------|------|
| 关系提取 | codeindex AST | 100% 准确，无 LLM 成本 |
| LLM 语义增强 | MVP 禁用 | `semantic_enhancement.enabled = false` |
| 实体提取 | codeindex AST | Symbol, Call, Inheritance, Import |
| 存储 | LightRAG 内置 | 不自定义 schema |

**相关 ADR**:
- [ADR-005: AST 优先提取策略](../adr/ADR-005-extraction-strategy.md)
- [ADR-006: MVP 简化策略](../adr/ADR-006-mvp-simplification.md)

---

## 最终分工

```
┌─────────────────────────────────────────────────────────────────┐
│                        分工矩阵 (已确认)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  提取内容              │ codeindex (AST) │ LightRAG (LLM)       │
│  ─────────────────────┼─────────────────┼────────────────────── │
│  函数/类定义 (Symbol)  │      ✅          │                      │
│  导入关系 (Import)     │      ✅          │                      │
│  调用关系 (Call)       │      ✅          │                      │
│  继承关系 (Inheritance)│      ✅          │                      │
│  语义描述              │                 │   v0.2.0+ (可选)     │
│  高层架构模式          │                 │   v0.2.0+ (可选)     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 原始讨论记录

以下为原始讨论内容，保留作为决策背景参考。

### 核心问题

codeindex 的 `parser.py` 当前能提取 **实体 (Entity)**，但图谱构建还需要 **关系 (Relationship)**。

```
┌─────────────────────────────────────────────────────────────────┐
│              codeindex parser.py 输出                            │
├─────────────────────────────────────────────────────────────────┤
│  Symbol:                                                        │
│    - name: "UserService.login"                                  │
│    - kind: "method"                                             │
│    - signature: "def login(username, password)"                 │
│    - docstring: "用户登录验证"                                   │
│    - line_start: 42                                             │
│    - line_end: 58                                               │
│                                                                 │
│  Import:                                                        │
│    - module: "hashlib"                                          │
│    - names: ["sha256"]                                          │
│    - is_from: True                                              │
│                                                                 │
│  Call: (新增)                                                    │
│    - caller: "UserService.login"                                │
│    - callee: "hashlib.sha256"                                   │
│    - line: 45                                                   │
│                                                                 │
│  Inheritance: (新增)                                             │
│    - child: "UserService"                                       │
│    - parent: "BaseService"                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 讨论的三种方式

| 方式 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A: AST 静态分析** | codeindex 提取 | 100% 准确，无 LLM 成本，速度快 | 无法理解语义关系 |
| **B: LLM 语义提取** | LightRAG 默认 | 能理解语义，识别隐式关系 | 可能幻觉，消耗 GPU |
| **C: 混合策略** | AST + LLM | 兼顾准确性和语义理解 | 实现复杂 |

### 最终选择

**MVP 选择方式 A (AST 优先)**，原因：

1. H200 算力充足，全量重建可行
2. AST 关系 100% 准确，足以验证 MVP 价值
3. LLM 语义增强延后到 v0.2.0+

---

## 实现状态

| 组件 | 状态 | 说明 |
|------|------|------|
| codeindex Call 提取 | 待 codeindex 实现 | Python 优先 |
| codeindex Inheritance 提取 | 待 codeindex 实现 | Python 优先 |
| LoomGraph Mapper | ✅ 已实现 | `map_call_to_relation()` |
| LoomGraph Injector | ✅ 已实现 | `inject_parse_result()` |
| LightRAG 集成 | 🔲 待开始 | 使用 `acreate_entity/relation` API |
