# ISSUE-001: CLI 支持单文件索引

**类型**: enhancement
**优先级**: P2
**状态**: Open
**创建日期**: 2025-02-08

---

## 背景

Core 层已有 `index_file()` 函数支持单文件索引，但 CLI 层未暴露此功能。

## 现状

- `loomgraph index /path/to/dir` ✅ 工作正常
- `loomgraph index /path/to/file.py` ❌ 报错 "Directory is a file"

## 原因

CLI 直接调用 `codeindex scan`（只支持目录），而未使用 `codeindex parse`（支持单文件）。

```python
# src/loomgraph/cli/main.py:265
result = subprocess.run(
    ["codeindex", "scan", str(repo), "--output", "json"],
    ...
)
```

## 期望

```bash
# 索引单文件
loomgraph index src/auth/service.py

# 输出
{
  "success": true,
  "data": {
    "files_scanned": 1,
    "entities_created": 5,
    ...
  }
}
```

## 实现方案

1. CLI 检测输入是文件还是目录
2. 文件 → 调用 `codeindex parse` + `index_file()`
3. 目录 → 调用 `codeindex scan` + `index_repository()`（现有逻辑）

## 相关代码

| 文件 | 行号 | 说明 |
|------|------|------|
| `src/loomgraph/core/indexer.py` | 229 | `index_file()` 函数已存在 |
| `src/loomgraph/cli/main.py` | 240 | CLI index 命令 |

## 依赖

- codeindex v0.12.0+ 的 `parse` 命令（已支持）

---

## 备注

非阻塞问题，主要用例是索引整个目录。待打包问题解决后处理。
