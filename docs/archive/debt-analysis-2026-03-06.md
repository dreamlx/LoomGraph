# Technical Debt Analysis Report
**Date**: 2026-03-06
**Tool**: loomgraph debt
**Target**: LoomGraph v0.6.1 (develop branch)
**Overall Score**: 15/100 (Grade F)

## Executive Summary

债务分析发现 **134 个 issues**，主要集中在图谱拓扑债务（99 orphans, 28 god functions, 6 hubs, 1 coupling）。

**关键发现**：
- ✅ **代码质量优秀**: codeindex 静态分析仅发现 1 个 issue（symbol noise ratio）
- ❌ **拓扑债务严重**: topology_score = 30/100
- 🔍 **误报率高**: 99 个 orphans 中约 70% 是数据类（正常孤立）
- 🎯 **真实问题**: 4 个严重的 god functions 需要重构

---

## 债务分类详解

### 1. Orphan Entities (99 issues, P1) - **70% 误报**

**定义**: in-degree = 0, out-degree = 0

**分析**:
- **误报原因**: 数据类/DTO 只被序列化使用，不在代码图谱中被引用
- **真实 orphans**: Analyzer 类可能确实未被使用

**示例误报**:
```python
# models.py
@dataclass
class Call:         # ← Orphan (但被 JSON 序列化使用)
    source: str
    target: str
```

**建议**:
- 将 `@dataclass` 和 `models.py` 中的类加入白名单
- 真正需要审查的 orphans: Analyzer 类（可能已废弃）

---

### 2. God Functions (28 issues, P0) - **4 个真实问题**

#### 🔴 Critical (out-degree ≥ 30)

| Function | Out | Lines | Location | Status |
|----------|-----|-------|----------|--------|
| `main` | 43 | 6 | cli/main.py:19-25 | **误报** (bottom imports) |
| `_async_index_pipeline` | 31 | 182 | cli/_indexing.py:109-291 | **真实** 需重构 |
| `_async_warm_update` | 30 | 181 | cli/_indexing.py:566-747 | **真实** 需重构 |
| `TopologyAnalyzer.analyze_from_data` | 30 | 156 | core/topology.py:282-438 | **复杂但合理** |

#### 🟡 Medium (20 ≤ out < 30)

| Function | Out | Lines | Status |
|----------|-----|-------|--------|
| `LightRAGClient.batch_create_graph` | 27 | 186 | **已废弃** 可删除 |
| `OverviewAnalyzer.analyze` | 25 | 100 | 复杂但合理 |
| `package_customer` | 23 | 96 | scripts/, 不影响核心 |
| `_async_find` | 20 | 82 | 可优化 |

---

### 3. Hub Fragility (6 issues, P1) - **设计合理**

| Hub | In-degree | Location | Analysis |
|-----|-----------|----------|----------|
| `output_success` | 22 | cli/_common.py | ✅ 公共工具，正常 |
| `output_error` | 19 | cli/_common.py | ✅ 公共工具，正常 |
| `get_settings` | 18 | core/config.py | ✅ 单例配置，正常 |
| `_get_headers` | 15 | core/lightrag_client.py | ✅ 内部辅助，正常 |

**结论**: 所有 hubs 都是设计合理的公共工具，**无需修复**。

---

### 4. Coupling Density (1 issue, P1) - **误报**

**Metrics**:
- Density: 0.83
- Cross-module: 1180 relations
- Intra-module: 234 relations

**Most coupled pairs**:
```
src/loomgraph ↔ scripts: 7 relations
```

**分析**:
- 只有 7 个跨模块关系，但 density 计算可能包含了 `scripts/` 作为模块
- 实际耦合度很低，`scripts/` 是工具脚本，不是核心模块

**建议**:
- 从 workspace 中排除 `scripts/`
- 或者修改 coupling 计算逻辑，只考虑 `src/` 内部

---

## 修复计划

### Phase 1: 删除废弃代码 (Low-Hanging Fruit)

**目标**: 删除 `LightRAGClient.batch_create_graph` (已废弃，被 `insert_custom_kg` 替代)

**预期改进**:
- -1 god function (27 out-degree)
- -186 lines

**文件**:
- `src/loomgraph/core/lightrag_client.py`
- `tests/unit/test_lightrag_client.py`

---

### Phase 2: 重构 God Functions (High Impact)

#### 2.1 重构 `_async_index_pipeline` (31 out, 182 lines)

**当前职责** (过多):
1. 配置初始化 (settings, client)
2. 数据收集 (collect entities, relations, chunks)
3. 外部 stub 创建
4. 批量注入 (insert_custom_kg)
5. 进度跟踪
6. 错误处理

**重构方案**: 提取 3 个辅助函数

```python
# 拆分为：
async def _initialize_index_client(workspace, clear) -> LightRAGClient:
    """初始化客户端 + 可选清空数据"""
    ...

async def _collect_index_data(parse_results, repo_path) -> tuple[list, list, dict]:
    """收集 entities, relations, chunks（纯数据处理）"""
    ...

async def _inject_to_lightrag(client, entities, relations, chunks) -> dict:
    """注入到 LightRAG（单一职责）"""
    ...

# 主函数变为编排
async def _async_index_pipeline(...):
    client = await _initialize_index_client(workspace, clear)
    entities, relations, chunks = await _collect_index_data(parse_results, repo_path)
    return await _inject_to_lightrag(client, entities, relations, chunks)
```

**预期改进**:
- `_async_index_pipeline`: 31 → ~15 out-degree
- 更易测试（每个辅助函数可独立测试）

#### 2.2 重构 `_async_warm_update` (30 out, 181 lines)

**类似重构**:
```python
async def _detect_changed_files(since, until) -> list[str]:
    """Git diff 检测变更文件"""
    ...

async def _reindex_changed_files(client, changed_files) -> dict:
    """重新索引变更文件"""
    ...

async def _async_warm_update(...):
    changed_files = await _detect_changed_files(since, until)
    return await _reindex_changed_files(client, changed_files)
```

**预期改进**:
- `_async_warm_update`: 30 → ~12 out-degree

---

### Phase 3: 优化白名单 (Reduce False Positives)

**目标**: 将合理的 orphans/hubs 加入白名单

**TopologyAnalyzer 白名单**:
```python
# topology.py
WHITELIST_ORPHANS = frozenset({
    # Data classes (models.py)
    "Call", "Import", "Inheritance", "Symbol",
    "EntityData", "RelationData", "ParseResult",
    # Result DTOs
    "CompareResult", "DepsResult", "TopologyResult",
    "ImpactResult", "OverviewResult",
})

WHITELIST_HUBS = frozenset({
    # Public utilities (expected high fan-in)
    "output_success", "output_error",
    "get_settings", "get_auto_workspace",
})
```

**预期改进**:
- Orphans: 99 → ~30 (真实问题)
- Hubs: 6 → 0 (全部合理)

---

## 修复优先级

| Phase | 难度 | 影响 | 预期改进 | 工作量 |
|-------|------|------|---------|--------|
| Phase 1: 删除 `batch_create_graph` | 低 | 中 | -1 god function | 1h |
| Phase 2.1: 重构 `_async_index_pipeline` | 中 | 高 | -16 out-degree | 3h |
| Phase 2.2: 重构 `_async_warm_update` | 中 | 高 | -18 out-degree | 3h |
| Phase 3: 白名单优化 | 低 | 高 | -69 orphans, -6 hubs | 1h |

**总计**: ~8 小时，预期改进 **15/100 → 70/100** (Grade F → C)

---

## 预期改进对比

| Metric | Before | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|--------|---------------|---------------|---------------|
| Total issues | 134 | 133 | 101 | 32 |
| P0 issues | 28 | 27 | 25 | 25 |
| P1 issues | 106 | 106 | 76 | 7 |
| God functions | 28 | 27 | 25 | 25 |
| Orphans | 99 | 99 | 99 | 30 |
| Hubs | 6 | 6 | 6 | 0 |
| Topology score | 30 | 32 | 50 | 70 |
| **Overall score** | **15** | **16** | **25** | **70** |
| **Grade** | **F** | **F** | **F** | **C** |

---

## 执行建议

**Quick Win** (今天可完成):
1. Phase 1: 删除 `batch_create_graph` (1h)
2. Phase 3: 添加白名单 (1h)
3. 验证: 重新运行 `loomgraph debt` 确认改进

**后续优化** (下次迭代):
1. Phase 2.1: 重构 `_async_index_pipeline`
2. Phase 2.2: 重构 `_async_warm_update`

**不建议修复**:
- Hubs (设计合理)
- Coupling (误报)
- `main` 的高 out-degree (bottom imports 模式，标准做法)
