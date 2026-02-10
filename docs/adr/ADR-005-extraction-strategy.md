# ADR-005: 实体/关系提取策略 - AST 优先 + LLM 可选增强

**状态**: ✅ 已批准
**日期**: 2025-02-03
**决策者**: DreamLinx

---

## 上下文

LoomGraph 需要从代码中提取：
1. **实体 (Entity)**: 函数、类、方法、变量
2. **关系 (Relationship)**: 调用、继承、导入、使用

有两种提取方式：
- **AST 静态分析**: tree-sitter 解析，100% 准确，快速
- **LLM 语义提取**: 大模型推理，可理解语义，但可能幻觉

## 决策

**采用混合策略：AST 优先提取 + LLM 可选增强**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         提取策略分层                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Layer 1: codeindex AST (必须，MVP 范围)                                │
│  ├── Chunking: AST 感知切分，保证代码逻辑完整                           │
│  ├── 实体提取: Symbol (函数、类、方法) - 100% 准确                      │
│  └── 关系提取: Call, Inheritance, Import - 100% 准确                    │
│                                                                         │
│  Layer 2: LightRAG LLM (可选，MVP 后)                                   │
│  ├── 语义描述: "这是认证模块的核心服务"                                 │
│  ├── 架构模式识别: "使用了 Repository 模式"                             │
│  └── 代码质量分析: "存在潜在的安全风险"                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 理由

### 为什么 AST 优先？

| 维度 | AST (codeindex) | LLM (LightRAG) |
|------|-----------------|----------------|
| **准确性** | 100% 确定性 | ~85% (可能幻觉) |
| **速度** | 毫秒级 | 秒级 |
| **成本** | CPU, 几乎免费 | GPU, 消耗 H200 算力 |
| **可复现** | 相同输入=相同输出 | 可能略有差异 |

### 为什么需要 AST 感知 Chunking？

```python
# 200 行的函数
def process_authentication(user, password):
    # ... 100 行 ...
    if validate(password):    # ← LightRAG 默认可能在这里切断
        # ... 100 行 ...
```

- **LightRAG 默认 (按 token)**: 函数被切成 2 块，语义丢失
- **codeindex AST**: 完整函数作为 1 块，Jina 能理解完整语义

### 为什么 LLM 增强是可选的？

| 查询类型 | AST 关系足够？ | 需要 LLM？ |
|---------|---------------|-----------|
| "谁调用了 login" | ✅ | 不需要 |
| "修改 X 影响哪些模块" | ✅ | 不需要 |
| "处理认证的代码在哪" | ❌ | **需要** |
| "有安全风险的代码" | ❌ | **需要** |

**结论**: MVP 阶段的核心场景（调用链、依赖分析）AST 关系已足够。

## 实施

### MVP 阶段配置

```yaml
# loomgraph.yaml
indexing:
  # Layer 1: AST 提取 (始终启用)
  ast_extraction:
    enabled: true
    chunking: "ast"  # 按函数/类边界切分
    extract_calls: true
    extract_inheritance: true

  # Layer 2: LLM 语义增强 (MVP 默认关闭)
  semantic_enhancement:
    enabled: false  # MVP 阶段关闭
    # 后续版本可启用:
    # enabled: true
    # features:
    #   - description_generation
    #   - pattern_recognition
    #   - quality_analysis
```

### 数据流 (MVP)

```
源代码
   │
   ▼
codeindex.parse_file()
   │
   ├── Symbol: UserService.login (method)
   ├── Call: login → db.query
   └── Inheritance: UserService → BaseService
   │
   ▼
Jina Code V2 向量化
   │
   ▼
LightRAG.add_entity() / add_relationship()
   │
   ▼
PostgreSQL 存储
   │
   ▼
混合检索 (Keyword + Semantic + Graph)
```

### 数据流 (语义增强启用时)

```
... 同上 ...
   │
   ▼
PostgreSQL 存储
   │
   ├── [可选] LLM 语义增强
   │   ├── 生成实体描述
   │   └── 识别架构模式
   │
   ▼
混合检索 (含语义描述)
```

## 后果

### 正面

- MVP 开发速度快（无需等待 LLM 提取逻辑）
- 索引速度快 100x+（纯 AST）
- 结果 100% 可靠（无幻觉风险）
- H200 算力可专注于向量化和查询

### 负面

- MVP 阶段不支持语义化查询（"认证代码在哪"）
- 需要在 codeindex 中为每种语言实现 Call/Inheritance 提取

### 缓解措施

- 语义增强作为 v0.2.0 功能规划
- 向量检索可部分弥补语义理解能力

## 路线图

| 版本 | 功能 | semantic_enhancement |
|------|------|---------------------|
| v0.1.0 (MVP) | AST 关系 + 向量检索 | `false` |
| v0.2.0 | 语义描述生成 | `true` (可选) |
| v0.3.0 | 架构模式识别 | `true` (可选) |
