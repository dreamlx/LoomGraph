---
name: loomgraph-init
description: Add LoomGraph's orient-first evidence policy to a project CLAUDE.md
disable-model-invocation: true
---

## 配置项目的 LoomGraph evidence policy

此 skill 只委托 `loomgraph init` 写入简短、跨宿主的项目策略。它不手工编辑
`CLAUDE.md`，也不把命令清单复制进项目说明。

### 执行步骤

1. 说明此操作会向当前项目的 `CLAUDE.md` 追加一段 policy；若该文件已有
   LoomGraph policy，CLI 会保持原文不变。
2. 在项目根目录执行：

   ```bash
   loomgraph init
   ```

3. 报告 CLI 返回的 `updated` 状态与目标路径。

### 边界

- 不要手工编辑 `CLAUDE.md`；`loomgraph init` 是唯一 policy writer。
- 不运行 `loomgraph index`，不创建 snapshot 或数据库，不配置 MCP，不调用
  provider 或 LLM。
- 该 policy 只说明何时考虑结构/时间证据：小型或局部任务仍以 native tools
  为默认；不确定的跨文件或时间任务先运行 `loomgraph orient`。
