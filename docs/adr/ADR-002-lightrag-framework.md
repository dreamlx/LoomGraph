# ADR-002: 选择 LightRAG 作为图谱构建框架

**状态**: ❌ Superseded by [ADR-013](ADR-013-sqlite-vec-replace-lightrag.md) (2026-06-25)
**日期**: 2025-02-03
**决策者**: DreamLinx

> **v0.10.0 update**: 一年实践后发现 LightRAG 是 layer 错配（它的
> LLM 实体抽取在代码 AST 层是多此一举）。LightRAG 客户端 + 适配器
> + 配置全部移除，存储/查询归 SQLite + sqlite-vec。详见 ADR-013。

---

## 上下文

LoomGraph 需要一个 RAG 框架来实现：
1. 从代码中提取实体和关系
2. 构建知识图谱
3. 提供混合检索能力（关键词 + 语义 + 图谱）

可选方案：

| 方案 | 框架 | 特点 |
|------|------|------|
| A | Microsoft GraphRAG | 功能完整，社区大，但速度慢 |
| B | LightRAG | 轻量级，速度快，易定制 |
| C | 自研 | 完全控制，但开发成本高 |

## 决策

**选择方案 B: 使用 LightRAG 框架，并在入口处进行 AST 预处理**

## 理由

### LightRAG vs Microsoft GraphRAG

| 维度 | LightRAG | Microsoft GraphRAG |
|------|----------|-------------------|
| 构建速度 | ~100x 更快 | 慢（大量 LLM 调用） |
| 内存占用 | 低 | 高 |
| 可定制性 | 高（易替换组件） | 中 |
| 检索模式 | 4 种（naive/local/global/hybrid） | 2 种 |
| 文档质量 | 中 | 高 |

### 关键考量

1. **增量更新**: LightRAG 的追加式设计适合代码频繁变更场景
2. **H200 利用率**: LightRAG 可配置批量处理，充分利用 GPU 吞吐量
3. **自定义 Embedding**: 轻松替换为 Jina Code V2
4. **自定义 LLM**: 轻松对接本地 vLLM 服务

### 为什么不自研

- LightRAG 已解决图谱构建的核心复杂性
- 团队资源有限，应聚焦代码领域定制
- 快速验证 MVP 比完美架构更重要

## 实施策略

### AST Pre-Chunking (关键定制点)

LightRAG 默认按 token 数切分，会破坏代码逻辑边界。必须在 `rag.insert()` 之前进行 AST 预处理：

```
源代码 → Tree-sitter AST 解析 → 提取函数/类块 → LightRAG.insert()
```

### 自定义组件注入

```python
rag = LightRAG(
    working_dir="./index",
    llm_model_func=h200_llm_func,      # 本地 vLLM
    embedding_func=jina_embedding_func  # Jina Code V2
)
```

### 存储后端适配

LightRAG 默认使用 JSON/LevelDB。需要定制以支持 PostgreSQL：
- **Phase 1**: 使用默认存储，快速验证
- **Phase 2**: 实现 `PostgresKVStorage` 和 `PostgresGraphStorage`

## 后果

### 正面

- 快速启动，2 周内可有可用原型
- 混合检索能力开箱即用
- 社区活跃，问题容易解决

### 负面

- 需要 Fork/定制以支持 PostgreSQL 存储
- 增量更新需要额外处理（旧节点清理）
- 文档不如 GraphRAG 完善

### 风险缓解

- **存储定制**: 先用默认存储验证流程，后期逐步迁移
- **增量更新**: 小规模项目可接受全量重建；大规模需定制清理逻辑

## 后续行动

1. ✅ 在 Epic 1 中集成 LightRAG 基础功能
2. 📋 在 Epic 2 中实现 PostgreSQL 存储适配
3. 📋 验证增量更新策略

## 参考

- [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
- [LightRAG Paper](https://arxiv.org/abs/2410.05779)
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
