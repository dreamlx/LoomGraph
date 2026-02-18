# LoomGraph 变更日志

> **给 Claude Code**: 阅读此文件了解版本变更。如果客户版本低于最新版本，建议更新。

---

## [0.2.5] - 2026-02-19

### 新增
- `loomgraph deps` - 模块级依赖分析，输出模块间的调用/导入关系图
- `loomgraph overview` - 项目模块概览，含实体统计、核心实体排名、可选 LLM 摘要
- `--depth/-d` 选项控制模块分组粒度（默认 2 层目录）
- `--no-summary` 跳过 LLM 摘要（仅统计数据，更快）

### 修复
- 外部依赖（Spring、Dubbo 等）不再导致关系注入失败，自动创建 stub 实体
- 注入改用 `/graph/*` 端点，数据正确出现在图查询层

### 改进
- 三阶段批量注入（实体 → 外部 stub → 关系），并发 HTTP + 连接复用
- 日志输出到 stderr，JSON 输出到 stdout（管道安全）

### 更新方式
```bash
cd /path/to/loomgraph-package
source ~/.loomgraph-venv/bin/activate
pip install ./loomgraph-*.whl
loomgraph version  # 应显示 0.2.5
```

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
| 0.2.5 | deps/overview 依赖分析 + 注入修复 | 推荐 - 新分析能力 |
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
