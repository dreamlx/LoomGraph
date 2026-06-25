# ADR-011: AI Iteration Strategy - External vs Internal

**Status**: ⚠️ Superseded by [ADR-013](ADR-013-sqlite-vec-replace-lightrag.md) (2026-06-25)
**Date**: 2026-02-24
**Deciders**: Core Team
**Related**: ADR-010 (Search Architecture), EPIC-008 (Search Refactoring)

> **v0.10.0 update**: This ADR assumed `loomgraph query` would be the
> central AI iteration surface. v0.10.0 removed `query` because
> Claude Code / Codex / Cursor now handle natural-language code Q&A
> better than a LightRAG-backed RAG. The iteration strategy is now:
> external agents drive iteration; LoomGraph supplies deterministic
> structural primitives (`find` / `graph` / `topology`). See ADR-013.

## Context

### Background

在代码智能工具领域，存在两种"AI 自动迭代"的设计模式：

1. **内部迭代**（Manon 模式）：工具内部通过后端 LLM 自动进行多轮查询，直到判断信息完整
2. **外部迭代**（LoomGraph + Claude 模式）：工具提供高质量的单次查询，由 Claude 判断是否需要继续

### The Problem

LoomGraph 面临设计选择：
- 是否应该像 Manon 一样，在工具内部实现"智能迭代"？
- 还是应该专注于提供高质量的"原子能力"，让 Claude 来做迭代判断？

### Manon `deep_query` 分析

通过对 Manon 项目（MatrixOneGraph 知识图谱）的源码分析，发现其"AI 自动迭代"的实际实现：

```python
# Manon 后端伪代码（从源码和文档推断）
async def deep_query_backend(question: str, max_rounds: int):
    """
    服务端 LLM 驱动的迭代查询
    """
    rounds = []
    context = ""
    covered = []

    # Round 1: 初始向量检索
    result = await vector_search(question, top_k=10)
    context += result

    for round_num in range(2, max_rounds + 1):
        # 🔥 关键：LLM 判断是否需要补充
        analysis = await llm_analyze_coverage(
            question=question,
            current_context=context,
            covered=covered
        )
        # Prompt (推测):
        # "问题: {question}
        #  当前上下文: {context}
        #  分析: 是否完整？缺什么？"

        # 如果完整，停止
        if analysis["completeness"] > 0.9:
            break

        # Round 2+: 补充查询
        for entity in analysis["missing_entities"]:
            补充 = await graph_search(entity, depth=2)
            context += 补充

        rounds.append(round_num)

    # 最终生成答案
    return await llm_generate(question, context)
```

**关键发现**：

1. **80% 固定流程 + 20% LLM 判断**：
   - 预设的多步骤流程（vector → graph → 补充）
   - LLM 负责判断"缺什么"和生成答案
   - 不是真正的"智能 Agent 自动拆分任务"

2. **性能数据**（Manon 官方评估）：
   - 成功率：80% (4/5，1 个超时)
   - 平均轮次：2.25 轮
   - Token 消耗：~8K/查询
   - 延迟：60-90 秒
   - 调用次数：1 次 MCP 调用（vs Native 17.6 次）

3. **成本结构**：
   - 后端 LLM 调用：2-3 次（每轮判断 + 最终生成）
   - 使用 reasoning model（如 DeepSeek-R1）
   - Claude 调用：1 次（用户交互）
   - **总成本 = 后端 LLM + Claude**

4. **失败模式**：
   - 20% 超时率（reasoning model token 超限）
   - 降级到单轮搜索
   - 黑盒不可调试

### LoomGraph `query` 分析

当前实现：

```python
# LoomGraph CLI
async def _async_query(question: str, mode: str):
    """单轮 RAG 查询"""
    # 1. 向量检索
    # 2. 图谱扩展
    # 3. LLM 生成答案
    data = await client.query(query=question, mode=mode)
    return data["response"]
```

**特点**：
- 单次查询，快速返回（5-10 秒）
- 依赖 Claude 判断是否继续
- 透明、可控、可调试

### 对比矩阵

| 维度 | Manon `deep_query` | LoomGraph `query` + Claude |
|------|-------------------|---------------------------|
| **迭代控制** | 后端 LLM（自动） | Claude（手动） |
| **调用次数** | 1 次 MCP | 2-3 次 CLI |
| **LLM 成本** | 后端 2-3 次 + Claude 1 次 | Claude 2-3 次 |
| **Token 消耗** | ~8K | ~4-6K |
| **延迟** | 60-90 秒 | 10-15 秒 |
| **成功率** | 80% | ~95% |
| **可调试性** | ❌ 黑盒 | ✅ 透明 |
| **可控性** | ❌ 不可控 | ✅ 灵活调整 |
| **成本** | 高（双重 LLM） | 低（仅 Claude） |

## Decision

**LoomGraph 采用"外部迭代"策略**，即：

1. **专注于提供高质量的单次查询能力**
2. **把迭代控制权交给 Claude**（更强大的 AI）
3. **不在工具内部实现黑盒的"自动迭代"**

### 具体实施

#### 1. 增强单次查询能力

```bash
# 提供更丰富的单次查询选项
loomgraph find "LoginController" --with-relations --depth 2

# 一次查询返回:
# - 实体本身
# - 直接关系（callers + callees）
# - 间接关系（depth 2）
```

**目标**：减少 Claude 需要迭代的次数，从 3-5 次降到 1-2 次。

#### 2. 提供查询建议（未来）

```bash
loomgraph query "登录流程" --suggest-next

# 返回:
# Response: LoginController 处理登录请求...
#
# 💡 建议下一步查询:
#   1. loomgraph graph "AuthService" (被调用)
#   2. loomgraph find "TokenService" (依赖)
#   3. loomgraph query "Token 验证机制" (相关主题)
```

**目标**：引导 Claude 进行有效的迭代，但不强制执行。

#### 3. MCP Server 支持（ROADMAP）

```python
# Claude 通过 MCP 调用 LoomGraph
# 保持外部迭代的灵活性，但调用更方便

mcp_loomgraph_query("登录流程")
# Claude 判断：需要更多信息
mcp_loomgraph_graph("LoginController")
# Claude 判断：足够了，综合回答
```

**目标**：提供 MCP 协议的便利性，但保持外部迭代的透明性。

#### 4. Skill 层面的智能 Prompt

```markdown
# skills/loomgraph-query/skill.md

当用户问代码问题时:
1. 先用 loomgraph query 获取概览
2. 如果 Claude 判断信息不足，继续:
   - 用 loomgraph find 定位具体实体
   - 用 loomgraph graph 查看调用关系
3. 综合分析后回答
```

**目标**：通过 Skill 提供最佳实践，但不限制 Claude 的灵活性。

## Rationale

### Why External Iteration?

#### 1. **Claude 是更强大的迭代引擎**

| 能力 | Manon 后端 LLM | Claude Sonnet 4.5 |
|------|---------------|------------------|
| 模型能力 | Reasoning model | Frontier model |
| 上下文理解 | 受限（单一问题） | 完整（整个对话） |
| 灵活性 | 固定流程 | 动态调整 |
| 可解释性 | 黑盒 | 透明 |

**Claude 可以**：
- 理解用户的真实意图（不只是字面问题）
- 根据已有上下文智能判断
- 灵活调整查询策略
- 在多轮对话中保持连贯性

#### 2. **成本与性能优势**

**Manon 模式成本**：
```
用户问题
  → MCP 调用（1 次）
    → 后端 LLM 判断（2-3 次）
    → Claude 交互（1 次）
总成本 = 后端 LLM + Claude
总延迟 = 60-90 秒（串行）
```

**LoomGraph + Claude 成本**：
```
用户问题
  → Claude 查询 1（5 秒）
  → Claude 判断（0 成本）
  → Claude 查询 2（5 秒）
  → Claude 综合回答（5 秒）
总成本 = Claude 2-3 次
总延迟 = 10-15 秒（分步反馈）
```

**节省**：
- 成本：-40% ~ -60%（无后端 LLM）
- 延迟：-75% ~ -83%（10-15s vs 60-90s）
- 成功率：+15%（95% vs 80%）

#### 3. **透明性与可控性**

**Manon 黑盒问题**：
```bash
manon_deep_query("登录流程")
# 用户等待 60 秒...
# 不知道内部做了什么
# 如果超时，整个过程浪费
# 无法调整方向
```

**LoomGraph 透明性**：
```bash
# Claude 第 1 步
loomgraph query "登录流程"
# 用户看到: LoginController 的说明

# Claude 第 2 步（用户可见）
loomgraph graph "LoginController"
# 用户看到: 调用关系图

# 用户可以随时:
# - 提供额外信息
# - 调整查询方向
# - 中断不需要的探索
```

#### 4. **工程复杂度**

**内部迭代的复杂度**：
- 需要后端 LLM 推理引擎
- 需要设计判断 prompt
- 需要处理超时和降级
- 需要维护迭代状态
- 难以调试和优化

**外部迭代的简洁性**：
- LoomGraph 只提供"原子能力"
- Claude 负责组合和判断
- 每个命令独立、可测试
- 易于调试和优化

### Why Not Internal Iteration?

#### 1. **不是真正的智能 Agent**

Manon 的"自动迭代"本质：
- **80% 固定流程**：vector → graph → 补充
- **20% LLM 判断**：判断"缺什么"
- **类似于简化的 ReAct Agent**，但更受限

这不是"AI 自动拆分任务"，而是：
- 预设的查询策略
- LLM 辅助的补充逻辑

#### 2. **成本效益不合理**

为了减少用户 1-2 次命令调用：
- 增加 40-60% 成本（后端 LLM）
- 增加 4-6 倍延迟（60-90s vs 10-15s）
- 降低 15% 成功率（80% vs 95%）
- 牺牲透明性和可控性

**不值得**。

#### 3. **违背 Unix 哲学**

> "Do one thing and do it well"

LoomGraph 应该：
- ✅ 做好代码知识图谱构建
- ✅ 做好高质量的查询接口
- ❌ 不应该试图"替 Claude 思考"

让专业的 AI（Claude）做专业的事（迭代判断）。

## Consequences

### Positive

1. **成本降低**：无需后端 LLM，节省 40-60% 成本
2. **延迟降低**：分步反馈，体验更好（10-15s vs 60-90s）
3. **成功率提升**：单次查询很少超时，95% vs 80%
4. **可调试性**：每步透明，易于定位问题
5. **灵活性**：用户/Claude 可以随时调整方向
6. **工程简洁性**：专注于"原子能力"，降低复杂度
7. **可扩展性**：未来可以通过 MCP + Skill 优化，但保持核心简洁

### Negative

1. **需要 Skill 设计**：需要提供良好的 prompt/workflow 指导 Claude
2. **多次命令**：用户可能看到 2-3 次命令执行（但延迟更低）
3. **依赖 Claude**：假设 Claude 有足够能力做迭代判断（目前是合理的）

### Neutral

1. **与 Manon 差异化**：
   - Manon：黑盒自动化（适合懒惰用户）
   - LoomGraph：透明工具化（适合专业用户 + AI Agent）

## Alternatives Considered

### Alternative 1: 完全模仿 Manon

**方案**：在 LoomGraph 内部实现类似 `deep_query` 的后端迭代。

**优点**：
- 减少用户命令调用次数

**缺点**：
- 成本高（双重 LLM）
- 延迟高（60-90s）
- 黑盒不可控
- 工程复杂度高
- 20% 超时率

**拒绝理由**：成本效益不合理，违背工具设计哲学。

### Alternative 2: 混合模式

**方案**：提供可选的 `--auto-iterate` 标志。

```bash
# 默认：单次查询
loomgraph query "登录流程"

# 可选：自动迭代
loomgraph query "登录流程" --auto-iterate --max-rounds 3
```

**优点**：
- 灵活性：用户选择
- 向后兼容

**缺点**：
- 仍然有黑盒问题
- 增加维护负担
- 用户不知道何时使用

**拒绝理由**：增加复杂度，收益不明确。可能在未来重新考虑，但不作为 MVP。

### Alternative 3: 查询建议（选中的补充方案）

**方案**：单次查询返回时，提供"下一步建议"。

```bash
loomgraph query "登录流程" --suggest-next

# 返回:
# Response: ...
# 💡 建议下一步:
#   - loomgraph graph "LoginController"
#   - loomgraph find "AuthService"
```

**优点**：
- 引导 Claude 有效迭代
- 保持透明性
- 不增加黑盒复杂度

**接受理由**：作为未来增强，提升用户体验，但不改变核心策略。

## Implementation Plan

### Phase 1: 增强单次查询（v0.9.0）

- [ ] `find --with-relations --depth N`
- [ ] `query` 优化返回内容丰富度
- [ ] 性能测试：确保单次查询延迟 < 10s

### Phase 2: MCP Server（v1.0.0）

- [ ] 实现 LoomGraph MCP Server
- [ ] 提供 `mcp_loomgraph_*` 工具集
- [ ] 保持外部迭代的透明性

### Phase 3: 查询建议（v1.1.0）

- [ ] `--suggest-next` 选项
- [ ] 基于图谱结构的智能建议
- [ ] A/B 测试效果

### Phase 4: Skill 优化（持续）

- [ ] 编写 LoomGraph 最佳实践 Skill
- [ ] 提供典型查询工作流示例
- [ ] 收集用户反馈，持续优化

## References

1. **Manon 项目分析**
   - GitHub: https://github.com/brandonzyy/manon-server
   - 源码：`mcp/_tools.py` (manon_deep_query 实现)
   - 评估文档：`docs/manon-query-tools-evaluation-en.md`
   - 性能数据：1 次调用 vs 17.6 次（94% reduction），但成本高、延迟高、超时率 20%

2. **LoomGraph 现状**
   - `src/loomgraph/cli/_search.py`: `query` 命令实现
   - `src/loomgraph/core/lightrag_client.py`: LightRAG 客户端
   - 当前单次查询延迟：5-10 秒
   - 成功率：~95%

3. **相关 ADR**
   - ADR-010: Search Architecture Redesign（find/query/graph 三命令体系）
   - ADR-008: Bidirectional Orchestrator（LoomGraph 作为调度器，不是 All-in-One）
   - ADR-002: LightRAG Framework Selection（选择 LightRAG 作为图谱引擎）

## Status Notes

- **2026-02-24**: Initial decision after Manon vs LoomGraph analysis
- Decision drivers: Cost efficiency, transparency, engineering simplicity, Unix philosophy
- Next review: After Phase 1 implementation (v0.9.0)

---

**Conclusion**: LoomGraph 专注于提供高质量的"原子能力"，让 Claude 这个更强大的 AI 来做迭代判断。这是成本、性能、可控性的最佳平衡，也符合工具设计的 Unix 哲学。
