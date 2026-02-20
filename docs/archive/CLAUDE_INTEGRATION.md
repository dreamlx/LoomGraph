# Claude Code 集成指南

本文档说明如何在用户项目中配置 Claude Code 使用 LoomGraph 进行代码搜索。

---

## 前置条件

1. LoomGraph 已安装（见 [README.md](../README.md)）
2. 用户项目已索引：`loomgraph index /path/to/project`
3. `loomgraph status` 显示服务正常

---

## 配置用户项目

在用户项目根目录的 `CLAUDE.md` 中添加以下内容：

### 基础配置（推荐）

```markdown
## 代码搜索 (LoomGraph)

本项目已用 LoomGraph 索引，可使用以下命令理解代码：

### 语义搜索
```bash
loomgraph search "<自然语言查询>"
```

示例：
- `loomgraph search "用户认证逻辑"`
- `loomgraph search "如何处理支付回调"`
- `loomgraph search "数据库连接池配置"`

### 调用关系查询
```bash
loomgraph graph "<类名.方法名>" --direction <callers|callees|both>
```

示例：
- `loomgraph graph "UserService.login" --direction callers` - 谁调用了这个方法
- `loomgraph graph "PaymentService.process" --direction callees` - 这个方法调用了谁

### 服务状态
```bash
loomgraph status
```
```

### 高级配置（可选）

如果希望 Claude 更主动地使用 LoomGraph：

```markdown
## 代码搜索 (LoomGraph)

**重要**: 在探索不熟悉的代码时，优先使用 LoomGraph 而非手动 grep/find。

### 使用场景

1. **理解代码结构**: 使用 `loomgraph search` 找到相关模块
2. **追踪调用链**: 使用 `loomgraph graph` 理解函数间关系
3. **定位功能实现**: 使用自然语言描述查找代码位置

### 命令参考

| 场景 | 命令 |
|------|------|
| 找认证相关代码 | `loomgraph search "authentication"` |
| 找谁调用了某函数 | `loomgraph graph "ClassName.method" --direction callers` |
| 找某函数调用了谁 | `loomgraph graph "ClassName.method" --direction callees` |
| 检查服务状态 | `loomgraph status` |

### 注意事项

- 搜索结果是 JSON 格式，包含 `response` 字段
- 如果索引过期，执行 `loomgraph index .` 重新索引
- 调用图查询依赖 codeindex 的 calls 输出（开发中）
```

---

## 使用示例

### 场景 1: 用户问 "认证是怎么实现的"

Claude 执行：
```bash
loomgraph search "用户认证实现"
```

输出示例：
```json
{
  "success": true,
  "data": {
    "query": "用户认证实现",
    "mode": "hybrid",
    "response": "用户认证主要在 AuthService 类中实现..."
  }
}
```

### 场景 2: 用户问 "谁调用了 login 方法"

Claude 执行：
```bash
loomgraph graph "AuthService.login" --direction callers
```

### 场景 3: 用户问 "支付流程是什么"

Claude 执行：
```bash
loomgraph search "支付流程 payment process"
```

---

## 故障排除

### 服务不可用

```bash
loomgraph status
```

如果显示 `connected: false`：
1. 检查网络白名单权限
2. 联系管理员确认服务状态

### 搜索结果不相关

可能原因：
1. 索引过期 → 重新索引：`loomgraph index .`
2. 查询太模糊 → 使用更具体的关键词
3. 代码刚添加 → 需要重新索引

### codeindex 未安装

```bash
pip install ai-codeindex
```

---

## 最佳实践

1. **索引粒度**: 索引整个项目根目录，而非子目录
2. **定期更新**: 代码大改后重新索引
3. **自然语言**: 搜索支持中英文自然语言描述
4. **组合使用**: 先 search 定位，再 graph 追踪调用链

---

## 相关文档

- [CLI_DESIGN.md](api/CLI_DESIGN.md) - CLI 命令详细说明
- [UPDATE_STRATEGY.md](architecture/UPDATE_STRATEGY.md) - 索引更新策略
