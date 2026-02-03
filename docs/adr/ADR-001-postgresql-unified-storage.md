# ADR-001: 使用 PostgreSQL 统一存储

**状态**: ✅ 已批准
**日期**: 2025-02-03
**决策者**: DreamLinx

---

## 上下文

LoomGraph 需要存储三类数据：
1. **向量数据**: 代码块的 embedding（768 维，Jina Code V2）
2. **图数据**: 代码实体之间的关系（调用、继承、导入等）
3. **元数据**: 文件路径、代码内容、时间戳等

常见的技术选型方案：

| 方案 | 向量存储 | 图存储 | 元数据 |
|------|----------|--------|--------|
| A | Milvus | Neo4j | PostgreSQL |
| B | pgvector | Neo4j | PostgreSQL |
| C | pgvector | PostgreSQL | PostgreSQL |

## 决策

**选择方案 C: 使用 PostgreSQL + pgvector 作为统一存储**

## 理由

### 选择 pgvector 而非 Milvus

1. **运维简化**: 减少一个组件，降低部署复杂度
2. **事务一致性**: 向量和元数据可在同一事务中更新
3. **性能足够**: 对于百万级向量，pgvector 性能可接受
   - IVFFlat 索引：~10ms 查询延迟 (Top-100, 1M vectors)
   - HNSW 索引：~5ms 查询延迟（内存占用更高）
4. **成熟稳定**: pgvector 已被广泛使用，社区活跃

### 选择 PostgreSQL 表而非 Neo4j

1. **查询需求简单**: 主要是 1-2 跳关系查询，SQL 足够表达
2. **避免 N+1 查询**: 使用 CTE 可高效实现多跳遍历
3. **统一技术栈**: 减少团队学习成本
4. **事务保证**: 图更新与实体更新原子性

### 不选择的原因

- **Milvus**: 引入额外运维负担，向量规模（百万级）未达到必须使用的程度
- **Neo4j**: 增加部署复杂度，简单图查询 SQL 可满足

## 后果

### 正面

- 单一数据库，简化运维和部署
- 统一的事务模型
- 更简单的备份和恢复策略

### 负面

- 向量检索性能上限受限于 pgvector
- 复杂图查询（5+ 跳）性能可能不如专用图数据库
- 单点故障风险（需要配置高可用）

### 风险缓解

- **向量规模增长**: 如超过 1000 万向量，可迁移到 Milvus
- **图查询复杂化**: 如需要复杂图算法，可引入 Neo4j
- **高可用**: 使用 PostgreSQL 主从复制或 Patroni

## 验证计划

在 Sprint 1 结束时验证：

1. 向量搜索延迟 < 50ms (Top-100, 10K vectors)
2. 2-hop 图查询延迟 < 200ms
3. 批量插入吞吐量 > 1000 records/s

## 参考

- [pgvector Performance Benchmarks](https://github.com/pgvector/pgvector#performance)
- [LightRAG Storage Options](https://github.com/HKUDS/LightRAG)
- [PostgreSQL Recursive CTE](https://www.postgresql.org/docs/current/queries-with.html)
