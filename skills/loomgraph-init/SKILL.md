---
name: loomgraph-init
description: Add LoomGraph usage instructions to project CLAUDE.md
disable-model-invocation: true
---

## 配置项目使用 LoomGraph

此 skill 将在当前项目的 CLAUDE.md 中追加 LoomGraph 使用说明。

### 要追加的内容

```markdown
## 代码智能 (LoomGraph)

本项目已用 LoomGraph 索引，可使用以下命令：

- `loomgraph find "<实体名>"` - 结构化实体发现（类、函数、模块）
- `loomgraph find "<实体名>" --with-relations` - 实体 + 调用关系一次返回
- `loomgraph graph "<实体名>"` - 精确关系遍历（callers/callees）
- `loomgraph deps` - 模块依赖分析
- `loomgraph overview` - 项目模块概览
- `loomgraph workspace info` - 查看索引统计
- `loomgraph status` - 检查服务状态

如需重新索引：`loomgraph index .`
```

### 执行步骤

1. **检查 CLAUDE.md 是否存在**
   ```bash
   ls CLAUDE.md
   ```
   - 如果不存在，创建新文件
   - 如果存在，继续下一步

2. **检查是否已有 LoomGraph 配置**
   ```bash
   grep -q "代码搜索 (LoomGraph)" CLAUDE.md
   ```
   - 如果已存在，提示："LoomGraph 配置已存在，跳过"
   - 如果不存在，继续下一步

3. **追加内容到 CLAUDE.md**
   - 在文件末尾添加上述 markdown 内容
   - 确保前面有空行分隔

4. **确认完成**
   - 输出："✅ 已在 CLAUDE.md 添加 LoomGraph 使用说明"
   - 提示：接下来执行 `loomgraph index .` 索引代码库

### 为什么需要这一步？

- **持久化记忆**：让 Claude Code 在后续会话中知道项目已配置 LoomGraph
- **命令参考**：提供快速可用的命令说明
- **避免重复配置**：下次进入项目不需要重新配置
