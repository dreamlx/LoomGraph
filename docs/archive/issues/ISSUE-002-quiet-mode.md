# ISSUE-002: 添加 --quiet 选项抑制索引 warning

**类型**: enhancement
**优先级**: P2
**状态**: Open
**创建日期**: 2025-02-08

---

## 背景

索引时会输出大量跨文件依赖的 warning（如 "Target entity does not exist"），可能让客户困惑。

## 现状

```bash
loomgraph index .
# 输出大量 warning 到 stderr
Failed to inject import xxx: Target entity 'xxx' does not exist
Failed to inject call xxx->yyy: Target entity 'yyy' does not exist
...
```

## 期望

```bash
# 默认行为：只显示关键信息
loomgraph index .

# 详细模式：显示所有 warning
loomgraph index . --verbose

# 安静模式：只显示最终 JSON
loomgraph index . --quiet
```

## 临时方案

在客户 README 中说明这是预期行为：

> 索引时出现大量 warning 是正常现象。跨文件依赖（如标准库、外部包）会产生 "Target entity does not exist" 警告，不影响使用。

## 相关代码

- `src/loomgraph/core/injector.py` - warning 输出位置
- `src/loomgraph/cli/main.py` - CLI 参数
