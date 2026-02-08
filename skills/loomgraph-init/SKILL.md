---
name: loomgraph-init
description: Add LoomGraph usage instructions to project CLAUDE.md
disable-model-invocation: true
---

## 配置项目使用 LoomGraph

在当前项目的 CLAUDE.md 中追加以下内容：

```markdown
## 代码搜索 (LoomGraph)

本项目已用 LoomGraph 索引，可使用以下命令：

- `loomgraph search "<查询>"` - 语义搜索代码
- `loomgraph graph "<类名.方法名>"` - 查询调用关系
- `loomgraph status` - 检查服务状态

如需重新索引：`loomgraph index .`
```

### 执行步骤

1. 检查当前目录是否有 CLAUDE.md
   - 如果不存在，创建新文件
   - 如果存在，检查是否已有 "代码搜索 (LoomGraph)" 部分

2. 如果已有 LoomGraph 配置，提示用户并跳过

3. 如果没有，追加上述内容到 CLAUDE.md 末尾

4. 提示用户执行 `loomgraph index .` 索引代码库
