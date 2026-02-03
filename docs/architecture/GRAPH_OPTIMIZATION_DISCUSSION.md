# 图谱优化讨论：codeindex Parser vs LightRAG 提取

**状态**: 🔄 讨论中
**日期**: 2025-02-03

---

## 核心问题

codeindex 的 `parser.py` 当前能提取 **实体 (Entity)**，但图谱构建还需要 **关系 (Relationship)**。

```
┌─────────────────────────────────────────────────────────────────┐
│              codeindex parser.py 当前输出                        │
├─────────────────────────────────────────────────────────────────┤
│  Symbol:                                                        │
│    - name: "UserService.login"                                  │
│    - kind: "method"                                             │
│    - signature: "def login(username, password)"                 │
│    - docstring: "用户登录验证"                                   │
│    - line_start: 42                                             │
│    - line_end: 58                                               │
│                                                                 │
│  Import:                                                        │
│    - module: "hashlib"                                          │
│    - names: ["sha256"]                                          │
│    - is_from: True                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 缺失什么？
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              图谱需要的关系 (Relationship)                       │
├─────────────────────────────────────────────────────────────────┤
│  调用关系 (CALLS):                                              │
│    - UserService.login → hashlib.sha256                         │
│    - UserService.login → Database.query                         │
│                                                                 │
│  继承关系 (INHERITS):                                           │
│    - UserService → BaseService                                  │
│                                                                 │
│  导入关系 (IMPORTS):                                            │
│    - user_service.py → hashlib                                  │
│    - user_service.py → database                                 │
│                                                                 │
│  使用关系 (USES):                                               │
│    - UserService.login → self.db_connection                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 两种提取关系的方式

### 方式 A: AST 静态分析 (确定性)

在 codeindex parser 中深入分析 AST，提取调用关系。

```python
# 伪代码：提取函数调用
def extract_calls(function_node, source_bytes) -> list[Call]:
    calls = []
    for node in traverse(function_node):
        if node.type == "call":
            callee = get_callee_name(node)
            calls.append(Call(caller=function_name, callee=callee))
    return calls
```

**优点**:
- 100% 准确（基于 AST）
- 无 LLM 成本
- 速度快

**缺点**:
- 只能提取显式调用（无法识别动态调用如 `getattr(obj, method_name)()`）
- 跨文件引用需要符号表解析（复杂）
- 无法理解"语义关系"（如"这个函数处理用户认证"）

### 方式 B: LLM 语义提取 (LightRAG 默认)

让 LLM 阅读代码，提取实体和关系。

```python
# LightRAG 默认行为
prompt = """
Analyze this code and extract:
1. Entities (functions, classes, variables)
2. Relationships (calls, inherits, uses)

Code:
{code_chunk}
"""
```

**优点**:
- 能理解语义（"这是一个认证模块"）
- 能识别隐式关系
- 能处理注释和文档

**缺点**:
- LLM 可能产生幻觉（编造不存在的关系）
- 消耗大量 GPU 算力
- 结果不完全可复现

### 方式 C: 混合策略 (推荐)

```
┌────────────────────────────────────────────────────────────────┐
│                      混合提取流程                               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  源代码                                                        │
│     │                                                          │
│     ▼                                                          │
│  ┌──────────────────────────────────────┐                      │
│  │ codeindex parser (AST)               │                      │
│  │ - 提取 Symbol (实体)                  │                      │
│  │ - 提取 Import (导入关系) ✓            │                      │
│  │ - 提取 Call (调用关系) ← 新增         │                      │
│  │ - 提取 Inheritance (继承关系) ← 新增  │                      │
│  └──────────────────────────────────────┘                      │
│     │                                                          │
│     │ 确定性关系 (高置信度)                                     │
│     ▼                                                          │
│  ┌──────────────────────────────────────┐                      │
│  │ LightRAG LLM (语义)                  │                      │
│  │ - 补充语义描述                        │                      │
│  │ - 识别高层抽象关系                    │                      │
│  │ - 生成实体摘要                        │                      │
│  └──────────────────────────────────────┘                      │
│     │                                                          │
│     │ 语义关系 (需验证)                                         │
│     ▼                                                          │
│  合并图谱                                                       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 具体实施：codeindex 扩展

### 新增数据模型

```python
# codeindex/parser.py 扩展

@dataclass
class Call:
    """函数调用关系"""
    caller: str          # 调用者 (函数全名)
    callee: str          # 被调用者
    line: int            # 调用发生的行号
    is_method: bool      # 是否是方法调用 (obj.method)

@dataclass
class Inheritance:
    """继承关系"""
    child: str           # 子类
    parent: str          # 父类

@dataclass
class ParseResult:
    """扩展后的解析结果"""
    path: Path
    symbols: list[Symbol]
    imports: list[Import]
    calls: list[Call]           # 新增
    inheritances: list[Inheritance]  # 新增
    module_docstring: str
    namespace: str
    error: str | None
    file_lines: int
```

### Python 调用提取示例

```python
def _extract_calls(function_node, source_bytes: bytes, function_name: str) -> list[Call]:
    """提取函数内的所有调用"""
    calls = []

    def traverse(node):
        if node.type == "call":
            # 获取被调用者名称
            callee = _get_callee_name(node, source_bytes)
            if callee:
                calls.append(Call(
                    caller=function_name,
                    callee=callee,
                    line=node.start_point[0] + 1,
                    is_method="." in callee
                ))

        for child in node.children:
            traverse(child)

    traverse(function_node)
    return calls

def _get_callee_name(call_node, source_bytes: bytes) -> str:
    """从 call node 提取被调用函数名"""
    for child in call_node.children:
        if child.type == "identifier":
            return _get_node_text(child, source_bytes)
        elif child.type == "attribute":
            # obj.method() 形式
            return _get_node_text(child, source_bytes)
    return ""
```

### 继承关系提取

```python
def _extract_inheritance(class_node, source_bytes: bytes, class_name: str) -> list[Inheritance]:
    """提取类的继承关系"""
    inheritances = []

    for child in class_node.children:
        if child.type == "argument_list":
            # class Foo(Bar, Baz): ...
            for arg in child.children:
                if arg.type == "identifier":
                    parent = _get_node_text(arg, source_bytes)
                    inheritances.append(Inheritance(
                        child=class_name,
                        parent=parent
                    ))

    return inheritances
```

---

## LightRAG 的角色调整

如果 codeindex 已经提取了确定性关系，LightRAG 的 LLM 提取可以：

### 选项 1: 完全跳过 LLM 实体提取

```python
# 自定义 LightRAG 配置
rag = LightRAG(
    entity_extraction_enabled=False,  # 禁用 LLM 实体提取
    # 直接使用 codeindex 提取的实体和关系
)

# 手动注入实体和关系
for symbol in parse_result.symbols:
    rag.add_entity(symbol.name, symbol.kind, symbol.docstring)

for call in parse_result.calls:
    rag.add_relationship(call.caller, call.callee, "CALLS")
```

**效果**: 省去 80% 的 LLM 调用，大幅提速

### 选项 2: LLM 仅做语义增强

```python
# LLM 只生成摘要和高层描述
prompt = """
Given these code entities and their relationships:
{entities_and_relations}

Generate:
1. A brief description for each module
2. High-level architectural patterns observed
3. Potential code smells or improvements

Do NOT re-extract entities or relationships.
"""
```

**效果**: 保留 LLM 的语义理解能力，但避免重复工作

### 选项 3: LLM 验证 + 补充

```python
# LLM 验证 AST 提取的关系，并补充缺失的
prompt = """
I extracted these relationships from code AST:
{ast_relationships}

Please:
1. Verify if these relationships are correct
2. Add any relationships I might have missed
3. Describe the semantic meaning of key relationships
"""
```

---

## 建议的分工

```
┌─────────────────────────────────────────────────────────────────┐
│                        分工矩阵                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  提取内容              │ codeindex (AST) │ LightRAG (LLM)       │
│  ─────────────────────┼─────────────────┼────────────────────── │
│  函数/类定义           │      ✓          │                      │
│  导入关系              │      ✓          │                      │
│  调用关系              │      ✓          │       验证           │
│  继承关系              │      ✓          │                      │
│  语义描述              │                 │       ✓              │
│  高层架构模式          │                 │       ✓              │
│  代码质量分析          │     部分        │       ✓              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 待确认

1. **是否同意混合策略 (方式 C)**？
   - codeindex 扩展提取 Call 和 Inheritance
   - LightRAG LLM 仅做语义增强

2. **codeindex 扩展优先级**：
   - 先 Python 调用/继承提取
   - 后 PHP 调用/继承提取
   - 再 JS/TS/Go/Java

3. **LightRAG 定制方向**：
   - 选项 1: 完全跳过 LLM 实体提取
   - 选项 2: LLM 仅做语义增强 ← 推荐
   - 选项 3: LLM 验证 + 补充
