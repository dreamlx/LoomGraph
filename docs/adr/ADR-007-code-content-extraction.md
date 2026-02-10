# ADR-007: 代码内容提取策略 - LoomGraph 按需读取

**状态**: ✅ 已批准
**日期**: 2025-02-10
**决策者**: DreamLinx

---

## 上下文

当前实体注入到 LightRAG 时，只包含元信息（签名、docstring、位置），**不包含实际代码内容**：

```python
# 原始代码
def login(self, username: str, password: str) -> bool:
    """Authenticate user."""
    user = self.db.find_user(username)    # ← 未保存
    return check_password(user, password)  # ← 未保存
```

**当前保存的 description**：
```
def login(...) -> bool | Authenticate user. | Python | src/auth.py:12-25
```

**缺少的内容**：函数体（实现细节）

### 影响

1. **语义搜索不精确**：搜索 "如何查找用户" 无法匹配到 `find_user` 调用
2. **Embedding 不完整**：LightRAG 只能基于签名生成向量，不了解实现细节

### 需要决策

代码内容应该由谁提取？

| 方案 | 描述 |
|------|------|
| A | codeindex 输出 `body` 字段 |
| B | LoomGraph 根据位置信息自己读取源文件 |

---

## 决策

**选择方案 B：LoomGraph 按需读取源文件提取代码内容。**

codeindex 只负责结构化解析，不输出代码内容。

---

## 理由

### 1. 职责分离

| 组件 | 职责 | 输出 |
|------|------|------|
| **codeindex** | AST 结构解析 | 符号 + 位置 + 关系（轻量） |
| **LoomGraph** | 内容提取 + 注入 | 按需读取源文件，拼装完整内容 |

### 2. codeindex 保持轻量

如果 codeindex 输出 body：
- 输出会膨胀 **10-100 倍**
- 一个 10MB 的解析结果可能变成 100MB+
- 违背 "结构化索引" 的设计初衷

### 3. 位置信息已足够定位

codeindex 已输出：
```json
{
  "name": "login",
  "line_start": 12,
  "line_end": 25,
  "file_path": "src/auth.py"
}
```

LoomGraph 可以直接读取 `src/auth.py` 第 12-25 行。

### 4. 按需提取更灵活

- 不是所有场景都需要完整代码
- 可以根据符号大小决定是否包含 body
- 可以截断过长的代码（如 >500 行的函数）

---

## 实施

### LoomGraph 代码提取逻辑

```python
# loomgraph/core/content.py

def extract_symbol_body(
    file_path: str,
    line_start: int,
    line_end: int,
    max_lines: int = 100,
) -> str:
    """从源文件提取代码内容。

    Args:
        file_path: 源文件路径
        line_start: 起始行号
        line_end: 结束行号
        max_lines: 最大行数限制（防止巨型函数）

    Returns:
        代码内容字符串
    """
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # 提取指定范围
    start_idx = max(0, line_start - 1)
    end_idx = min(len(lines), line_end)

    # 截断过长内容
    if end_idx - start_idx > max_lines:
        end_idx = start_idx + max_lines

    return ''.join(lines[start_idx:end_idx])
```

### 更新 mapper.py

```python
def map_symbol_to_entity(
    symbol: Symbol,
    file_path: str,
    language: str,
    include_body: bool = True,  # 新参数
) -> EntityData:
    """Map codeindex Symbol to LightRAG entity data."""

    description_parts = []

    # 签名
    if symbol.signature:
        description_parts.append(symbol.signature)

    # Docstring
    if symbol.docstring:
        description_parts.append(symbol.docstring)

    # 代码内容（新增）
    if include_body:
        body = extract_symbol_body(
            file_path,
            symbol.line_start,
            symbol.line_end,
            max_lines=100,
        )
        description_parts.append(f"```{language}\n{body}\n```")

    # 位置信息
    description_parts.append(f"{language.capitalize()} | {file_path}:{symbol.line_start}-{symbol.line_end}")

    entity_data = {
        "entity_type": symbol.kind,
        "description": "\n\n".join(description_parts),
        "source_id": f"{file_path}:{symbol.line_start}-{symbol.line_end}",
        "file_path": file_path,
    }

    return EntityData(entity_name=symbol.name, entity_data=entity_data)
```

### 输出示例

**注入到 LightRAG 的 description**：
```
def login(self, username: str, password: str) -> bool

Authenticate user with credentials.

```python
def login(self, username: str, password: str) -> bool:
    """Authenticate user with credentials."""
    user = self.db.find_user(username)
    return check_password(user, password)
```

Python | src/auth/service.py:12-25
```

---

## 边界条件

### 大型函数处理

| 函数行数 | 处理方式 |
|---------|---------|
| ≤ 100 行 | 完整包含 |
| 100-500 行 | 截断 + 提示 "... (truncated)" |
| > 500 行 | 只包含签名，不含 body |

### 二进制/不可读文件

- 检测文件编码，跳过二进制文件
- 处理 UTF-8/GBK 等常见编码

### 文件不存在

- 仓库更新后文件可能已删除
- 优雅降级：只使用签名，不报错

---

## 后果

### 正面

- codeindex 保持轻量，输出可控
- LoomGraph 可按需决定是否包含代码
- 语义搜索更精确（包含实现细节）
- 灵活处理大型函数

### 负面

- LoomGraph 索引时需要访问源文件（不能只用 codeindex JSON）
- 如果文件已删除/移动，无法提取内容

### 缓解

- Warm Update 时源文件肯定存在
- Cold Rebuild 时遍历的就是当前文件

---

## 验收标准

- [ ] 索引后，实体 description 包含代码内容
- [ ] 搜索 "find_user" 能匹配到调用该函数的代码
- [ ] 大型函数（>100 行）正确截断
- [ ] 文件不存在时优雅降级

---

## 相关文档

- [DATA_CONTRACT.md](../api/DATA_CONTRACT.md) - 数据映射规范
- [ADR-005: AST 优先策略](ADR-005-extraction-strategy.md) - codeindex 定位
