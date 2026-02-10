# LoomGraph 变更日志

> **给 Claude Code**: 阅读此文件了解版本变更。如果客户版本低于最新版本，建议更新。

---

## [0.2.4] - 2025-02-10

### 新增
- Workspace 自动检测 - 从当前目录名自动识别 workspace，无需硬编码

### 改进
- `--workspace/-w` 参数现在可选，默认使用当前目录名
- 简化客户 CLAUDE.md 配置，无需指定 workspace 名称

### 更新方式
```bash
cd /path/to/loomgraph-package
source ~/.loomgraph-venv/bin/activate
pip install .
```

---

## [0.2.3] - 2025-02-10

### 新增
- `--workspace/-w` 选项 - 多项目 workspace 隔离支持
- README 知识图谱更新策略指南（给 AI Agent）

### 改进
- 模板化打包系统，单一 README 模板维护所有客户

### 更新方式
```bash
cd /path/to/loomgraph-package
source ~/.loomgraph-venv/bin/activate
pip install .
```

---

## [0.2.1] - 2025-02-10

### 新增
- `loomgraph index --clear` - Cold Rebuild，清空后重建索引
- `loomgraph update` - Warm Update，仅索引 git 变更文件
- `loomgraph version` - 显示当前版本

### 改进
- 使用 LightRAG `insert_custom_kg` API 批量注入，性能提升 5x
- 支持 `--since` 参数指定 git 比较基准

### 技术变更
- 依赖 codeindex v0.11.0+（需要 `codeindex parse` 命令）

### 更新方式
```bash
cd /path/to/loomgraph-package
source ~/.loomgraph-venv/bin/activate
pip install .
```

---

## [0.2.0] - 2025-02-09

### 新增
- `loomgraph index <path>` - 索引代码库到 LightRAG
- `loomgraph search "<query>"` - 语义搜索代码
- `loomgraph graph "<entity>"` - 查询调用关系
- `loomgraph status` - 检查服务连接状态

### Skills
- `/loomgraph-setup` - 配置 codeindex 和语言解析器
- `/loomgraph-init` - 初始化项目 CLAUDE.md

### 依赖
- LightRAG API: http://internal.example.invalid:3001 (customer) / :3020 (customer)
- codeindex v0.9.0+

---

## 版本对比

| 版本 | 主要功能 | 必须更新？ |
|------|----------|-----------|
| 0.2.4 | Workspace 自动检测 | 推荐 - 简化配置 |
| 0.2.3 | Workspace 隔离 + 更新策略 | 多项目用户必须 |
| 0.2.1 | Warm/Cold Update | 推荐 - 增量索引更快 |
| 0.2.0 | 基础索引和搜索 | 基线版本 |

---

## 检查当前版本

```bash
loomgraph version
# 或
~/.loomgraph-venv/bin/loomgraph version
```

如果命令不存在，说明版本 < 0.2.1，需要更新。
