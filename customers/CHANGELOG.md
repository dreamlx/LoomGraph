# LoomGraph 变更日志

> **给 Claude Code**: 阅读此文件了解版本变更。如果客户版本低于最新版本，建议更新。

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
- LightRAG API: http://117.131.45.179:3001 (pinbianyi) / :3020 (zcyl)
- codeindex v0.9.0+

---

## 版本对比

| 版本 | 主要功能 | 必须更新？ |
|------|----------|-----------|
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
