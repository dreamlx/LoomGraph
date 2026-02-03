# Epic 001: 存储层初始化

**状态**: 📋 待开发
**优先级**: P0 - 基础设施
**预估规模**: M (5-8 Story Points)

---

## 目标

建立 LoomGraph 的数据持久化基础设施，支持向量存储和图谱数据存储。

## 业务价值

- 为后续索引和检索功能提供数据存储能力
- 统一使用 PostgreSQL 简化运维复杂度
- 支持向量相似度检索（pgvector）

## 范围

### 包含 (In Scope)

- PostgreSQL + pgvector 数据库 schema 设计
- Repository 模式实现（代码块、实体、关系）
- 数据库连接池管理
- 基本的 CRUD 操作
- 向量相似度查询

### 不包含 (Out of Scope)

- 高级图查询（多跳遍历）- 留到 Epic 003
- 缓存层 - 后续优化
- 数据迁移工具

---

## 用户故事

### Story 1.1.1: 数据库 Schema 设计

```
作为一名开发者
我想要一个设计良好的数据库 schema
以便存储代码块、实体和关系数据
```

**验收标准**:
- [ ] 设计 `code_chunks` 表，包含文件路径、内容、hash、embedding
- [ ] 设计 `entities` 表，包含实体名称、类型、描述
- [ ] 设计 `relationships` 表，包含源、目标、关系类型
- [ ] 创建必要的索引（向量索引、查询索引）
- [ ] 编写 SQL migration 脚本

**技术任务**:
- [ ] T1.1.1.1: 编写 `migrations/001_initial_schema.sql`
- [ ] T1.1.1.2: 配置 pgvector 扩展
- [ ] T1.1.1.3: 创建向量索引（IVFFlat）

---

### Story 1.1.2: 数据库连接管理

```
作为一名开发者
我想要可靠的数据库连接池
以便高效地执行数据库操作
```

**验收标准**:
- [ ] 使用 asyncpg 实现异步连接池
- [ ] 支持从环境变量读取连接配置
- [ ] 实现连接健康检查
- [ ] 支持优雅关闭

**技术任务**:
- [ ] T1.1.2.1: 实现 `DatabaseConfig` 配置类
- [ ] T1.1.2.2: 实现 `DatabasePool` 连接池管理
- [ ] T1.1.2.3: 编写连接池单元测试

---

### Story 1.1.3: ChunkRepository 实现

```
作为一名开发者
我想要操作代码块的 Repository
以便保存和查询代码块数据
```

**验收标准**:
- [ ] 实现 `save()` - 保存单个代码块
- [ ] 实现 `save_batch()` - 批量保存代码块
- [ ] 实现 `find_by_hash()` - 按内容 hash 查找（去重）
- [ ] 实现 `search_by_vector()` - 向量相似度搜索
- [ ] 实现 `delete_by_file()` - 按文件路径删除（增量更新）

**技术任务**:
- [ ] T1.1.3.1: 定义 `CodeChunk` 数据模型
- [ ] T1.1.3.2: 实现 `PostgresChunkRepository`
- [ ] T1.1.3.3: 编写单元测试（mock DB）
- [ ] T1.1.3.4: 编写集成测试（testcontainers）

---

### Story 1.1.4: EntityRepository 实现

```
作为一名开发者
我想要操作实体的 Repository
以便保存和查询代码实体数据
```

**验收标准**:
- [ ] 实现 `save_batch()` - 批量保存实体
- [ ] 实现 `find_by_name()` - 按名称查找实体
- [ ] 实现 `find_by_chunk()` - 按代码块 ID 查找实体

**技术任务**:
- [ ] T1.1.4.1: 定义 `Entity` 数据模型
- [ ] T1.1.4.2: 实现 `PostgresEntityRepository`
- [ ] T1.1.4.3: 编写测试

---

### Story 1.1.5: RelationshipRepository 实现

```
作为一名开发者
我想要操作关系的 Repository
以便保存和查询实体之间的关系
```

**验收标准**:
- [ ] 实现 `save_batch()` - 批量保存关系
- [ ] 实现 `find_callers()` - 查找调用者（1 跳）
- [ ] 实现 `find_callees()` - 查找被调用者（1 跳）

**技术任务**:
- [ ] T1.1.5.1: 定义 `Relationship` 数据模型
- [ ] T1.1.5.2: 实现 `PostgresRelationshipRepository`
- [ ] T1.1.5.3: 编写测试

---

## 技术设计

### 目录结构

```
src/loomgraph/storage/
├── __init__.py
├── config.py          # DatabaseConfig
├── pool.py            # DatabasePool
├── models.py          # CodeChunk, Entity, Relationship
├── repositories/
│   ├── __init__.py
│   ├── base.py        # 抽象基类
│   ├── chunk.py       # ChunkRepository
│   ├── entity.py      # EntityRepository
│   └── relationship.py # RelationshipRepository
└── migrations/
    └── 001_initial_schema.sql
```

### 依赖

- `asyncpg`: PostgreSQL 异步驱动
- `pgvector`: 向量扩展 Python 绑定
- `pydantic`: 数据模型验证

---

## 测试计划

| 测试类型 | 覆盖范围 | 工具 |
|----------|----------|------|
| 单元测试 | Repository 逻辑 | pytest + mock |
| 集成测试 | 真实 DB 操作 | pytest + testcontainers |

### 关键测试用例

1. **向量搜索准确性**: 插入已知向量，验证 Top-K 返回正确
2. **去重逻辑**: 相同 content_hash 不重复插入
3. **批量操作性能**: 1000 条记录批量插入 < 1s
4. **连接池恢复**: 模拟连接断开后自动重连

---

## 依赖与风险

### 前置依赖

- Docker 环境可用（运行 PostgreSQL）
- pgvector 扩展安装

### 风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| pgvector 索引性能不足 | 低 | 中 | 后续可切换 HNSW 索引 |
| asyncpg 与 pgvector 兼容性问题 | 低 | 高 | 提前验证，必要时用 psycopg3 |

---

## 完成定义 (Definition of Done)

- [ ] 所有 Story 的验收标准满足
- [ ] 单元测试覆盖率 ≥ 90%
- [ ] 集成测试通过
- [ ] 代码通过 ruff + mypy 检查
- [ ] 文档更新（API 文档 + CHANGELOG）
- [ ] PR Review 通过并合并到 develop
