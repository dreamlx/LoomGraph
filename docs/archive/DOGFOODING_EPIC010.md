# EPIC-010 Dogfooding 总结

**日期**: 2026-03-07
**测试人员**: Claude Sonnet 4.5
**测试对象**: EPIC-010 Feature 3 (代码腐化趋势分析)
**测试环境**: LoomGraph 项目本身（自举测试）

## 测试场景

### 场景 1: 真实项目数据（同天多次快照）

- **操作**: 运行 `loomgraph debt --with-git` 6 次（14 分钟内）
- **数据**: 6 个快照，all on 2026-03-07
- **命令**: `loomgraph trends -e "project" -m "total_score" --months 1`

### 场景 2: 模拟 30 天历史数据

- **操作**: 创建 10 个跨 30 天的快照（3 天间隔）
- **数据**: total_score 从 50 → 77（线性增长）
- **命令**: `loomgraph trends -e "test-project" -m "total_score" --months 2`

### 场景 3: 数据不足场景

- **操作**: 查询不存在的实体
- **命令**: `loomgraph trends -e "nonexistent" -m "total_score" --months 2`

## 发现的问题

### 🔴 Critical: 时区不匹配

**问题**:
```python
TypeError: can't compare offset-naive and offset-aware datetimes
```

**根因**:
- `cutoff = datetime.now()`（naive）
- `timestamp = datetime.fromisoformat(data["timestamp"])`（aware，从 JSON 加载）

**修复**:
```python
# Before
cutoff = datetime.now() - timedelta(days=30 * months)

# After
from datetime import UTC
cutoff = datetime.now(UTC) - timedelta(days=30 * months)
```

**影响范围**:
- `load_snapshots()`
- `cleanup_old_snapshots()`

### 🟡 Medium: 错误的 ErrorCode

**问题**:
```python
AttributeError: type object 'ErrorCode' has no attribute 'OPERATION_FAILED'
```

**根因**:
- `ErrorCode.OPERATION_FAILED` 不存在于 `_common.py`
- 可用的错误码: `INVALID_INPUT`, `LIGHTRAG_ERROR`, `FILE_NOT_FOUND`, etc.

**修复**:
```python
# Before
except Exception as e:
    output_error(code=ErrorCode.OPERATION_FAILED, ...)

# After
except Exception as e:
    output_error(code=ErrorCode.LIGHTRAG_ERROR, ...)
```

### 🟡 Medium: 斜率单位误导

**问题**:
```
Slope: +1.00/month, R²: 1.000
```
- 显示为 "/month"，但实际是 "/day"
- 用户误解：以为每月增长 1 分，实际是每天增长 1 分（每月 30 分）

**修复**:
```python
# 显示双单位
slope_per_month = regression.slope * 30
lines.append(f"Slope: {slope_per_month:+.2f}/month ({regression.slope:+.3f}/day), R²: ...")
```

**效果**:
```
Slope: +30.00/month (+1.000/day), R²: 1.000
```

### 🟢 Low: 同天数据 X 轴标签重复

**问题**:
```
       2026-03-07                                        2026-03-07
```
- 所有快照在同一天，X 轴标签重复且无意义

**修复**:
```python
if first_ts.date() == last_ts.date():
    # 同天显示时间
    first_label = first_ts.strftime("%H:%M")
    last_label = last_ts.strftime("%H:%M")
else:
    # 不同天显示日期
    first_label = data_points[0].label
    last_label = data_points[-1].label
```

**效果**:
```
       03:17                                                  03:31
```

### 🟡 Medium: 测试用例时区问题

**问题**:
- 测试使用 naive datetime（`datetime.now()`）
- 与生产代码不一致（生产用 UTC aware）
- 没有覆盖时区边界情况

**修复**:
```python
# Before
base_time = datetime.now() - timedelta(days=150)

# After
from datetime import UTC
base_time = datetime.now(UTC) - timedelta(days=150)
```

**影响范围**:
- `sample_snapshots` fixture
- `sample_stable_snapshots` fixture
- 所有测试用例

## 修复验证

### ✅ 时区修复验证

```bash
$ .venv/bin/loomgraph trends -e "project" -m "total_score" --months 1
# ✅ 成功运行，无 TypeError
```

### ✅ 错误处理验证

```bash
$ .venv/bin/loomgraph trends -e "nonexistent" -m "total_score" --months 2
{
  "error": {
    "code": "INVALID_INPUT",  # ✅ 正确的错误码
    "message": "Trend analysis requires at least 3 snapshots, got 0."
  }
}
```

### ✅ 斜率显示验证

```bash
$ .venv/bin/loomgraph trends -e "test-project" --months 2
Trend: INCREASING
Slope: +30.00/month (+1.000/day), R²: 1.000  # ✅ 双单位清晰
```

### ✅ 同天标签验证

```bash
$ .venv/bin/loomgraph trends -e "project" --months 1
...
       03:17                                                  03:31
# ✅ 显示时间而非重复日期
```

### ✅ 告警验证

```bash
$ .venv/bin/loomgraph trends -e "test-project" --months 2
{
  "alert": "⚠️ Rapid complexity growth detected: +39.0% projected in next month. Current: 77, Forecast: 107."
}
# ✅ 正确触发告警（slope = 1.0/day > 0.15/day 阈值）
```

### ✅ 测试覆盖验证

```bash
$ .venv/bin/pytest tests/unit/test_trends.py -v
============================= 13 passed in 0.14s =============================
# ✅ 所有测试通过

$ .venv/bin/ruff check src/loomgraph/core/trends.py tests/unit/test_trends.py
All checks passed!
# ✅ Lint 检查通过
```

## 改进统计

| 文件 | 修改行数 | 说明 |
|------|---------|------|
| `src/loomgraph/core/trends.py` | +15 / -10 | UTC 修复 + 标签改进 + 斜率显示 |
| `src/loomgraph/cli/_analysis.py` | +1 / -1 | ErrorCode 修复 |
| `tests/unit/test_trends.py` | +34 / -25 | UTC 测试 + 代码清理 |
| **总计** | **+50 / -36** | **净增 14 行** |

## 经验教训

### ✅ Dogfooding 价值

1. **发现真实问题**: 单元测试未覆盖的时区问题（所有测试用 naive datetime）
2. **用户体验改进**: 斜率单位误导和 X 轴标签问题只能在真实使用中发现
3. **边界情况**: 同天多次快照的场景在测试中未考虑

### ✅ 测试改进

1. **使用真实数据类型**: 测试应该用 UTC aware datetime，而非 naive
2. **覆盖边界情况**: 同天多次快照、数据不足、时区边界
3. **性能测试**: 验证 < 1 秒的性能要求（通过）

### ✅ 开发最佳实践

1. **先 dogfooding 后发布**: 在真实项目上测试，发现隐藏问题
2. **双单位显示**: 内部用精确单位（/day），外部显示友好单位（/month）
3. **时区一致性**: 全栈统一使用 UTC aware datetime

## 后续优化建议

### 🔄 低优先级改进

1. **Cleanup 函数改进**:
   - 当前：使用文件修改时间（`st_mtime`）判断
   - 问题：用户复制文件会改变修改时间
   - 建议：读取 JSON 中的 `timestamp` 字段判断

2. **多指标对比图表**:
   - 当前：单指标趋势
   - 建议：支持 `--metrics "complexity,coupling"` 多指标对比

3. **导出功能**:
   - 当前：仅 JSON 输出
   - 建议：支持 CSV/PNG 导出（使用 matplotlib）

### ✅ 不需要改进

1. **ASCII 图表**: 已经清晰，满足需求
2. **线性回归**: R² > 0.9 时很准确，复杂模型不必要
3. **快照存储**: JSON 文件足够简单可靠，无需数据库

## 结论

**Dogfooding 成功发现 5 个问题**，其中 1 个 Critical（阻塞使用），4 个 Medium/Low（影响体验）。

**修复效果**:
- ✅ 核心功能正常工作
- ✅ 错误处理完善
- ✅ 用户体验改进
- ✅ 测试覆盖增强

**发布状态**: ✅ 可以合并到 `main` 并发布 v0.9.0
