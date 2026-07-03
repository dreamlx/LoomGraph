# LoomGraph - {{customer_name}}专用版

> **给 Claude Code / Codex**: 请按顺序执行下面的 Checklist，每完成一项就打勾 `[x]`。
> **所有步骤都必须完成**，跳过任何一步都会导致功能异常。

---

## 功能与前置条件

> **重要**: 不同功能需要不同的前置条件。安装后请对照此表确认哪些功能可用。

| 功能 | 命令 | 前置条件 | 说明 |
|------|------|---------|------|
| 结构化搜索 | `loomgraph find` | codeindex + LightRAG | 按名称/类型搜索实体 |
| 语义搜索 | `loomgraph search` | **embedding.enabled + provider** | 按语义/意图搜索实体（向量检索，非名称匹配） |
| 调用关系图 | `loomgraph graph` | codeindex 需提取 call relations | 查询 callers/callees |
| 语义问答 | `loomgraph query` | **LightRAG 需配置 LLM** | 自然语言提问（需 LLM 推理） |
| 拓扑分析 | `loomgraph topology` | codeindex + LightRAG | 检测孤立实体、God 函数等 |
| 索引新鲜度 | `loomgraph check` | 已索引 + 本地文件 | 对比图谱 vs 磁盘文件 |
| 变更影响 | `loomgraph impact` | 已索引 + Git 仓库 | 分析代码变更影响范围 |
| 技术债务 | `loomgraph debt` | codeindex 静态分析数据 | 多维度债务评分 |
| Git 度量 | `loomgraph git-metrics` | Git 仓库 | 热点/总线因子/缺陷率 |
| 向量补齐 | `loomgraph embed-backfill` | 已索引 + embedding.enabled + provider | 为无向量的 workspace（如 import-export 导入）补向量，使其可被 `search` 命中；不触发全量重建，幂等 |

### 常见问题速查

| 现象 | 原因 | 解决方案 |
|------|------|---------|
| `query` 返回错误或空 | LightRAG 服务端未配置 LLM | 联系技术团队配置 LLM endpoint |
| `graph` 返回空关系 | codeindex 未提取该语言的 call relations | 确认 codeindex 版本 ≥ 0.20.0 + 语言解析器已安装 |
| `find` 正常但 `graph` 空 | 只有 entity 数据，缺少 relation 数据 | 重新索引: `loomgraph index --clear .` |
| `search` 报 `EMBEDDING_NOT_INDEXED` 或返回空 | workspace 无向量（embedding 未启用 / import-export 导入） | `loomgraph embed-backfill -w <ws>` 补向量；或 `loomgraph index .`（需 `LOOMGRAPH_EMBEDDING__ENABLED=true`） |
| 索引很慢 | 未配置 `.codeindex.yaml` | 先执行 `/loomgraph-setup` 再索引 |

---

## 安装 Checklist

### 1. 创建虚拟环境

- [ ] 创建虚拟环境
```bash
python3 -m venv ~/.loomgraph-venv
```

### 2. 安装 LoomGraph

选择**在线安装**或**离线安装**其中一种方式：

#### 方式 A: 在线安装（推荐）

- [ ] 一行命令安装
```bash
source ~/.loomgraph-venv/bin/activate
pip install "loomgraph @ git+https://TOKEN@github.com/dreamlx/LoomGraph.git@v{{version}}"
```

> TOKEN 由 LoomGraph 技术团队提供。

#### 方式 B: 离线安装（内网环境）

- [ ] 从 tarball 安装 wheel
```bash
source ~/.loomgraph-venv/bin/activate
# 先安装 codeindex（必须依赖）
pip install ./ai_codeindex-*.whl
# 再安装 LoomGraph
pip install ./loomgraph-*.whl
```

> 如果 wheel 文件不存在，可以从源码安装：`pip install .`

### 3. 配置服务连接

- [ ] 复制配置文件（由技术团队提供）
```bash
mkdir -p ~/.config/loomgraph
cp config.yaml ~/.config/loomgraph/config.yaml
```

或交互式生成：
```bash
loomgraph setup-config --lightrag-url {{lightrag_url}}
```

- [ ] 验证配置
```bash
cat ~/.config/loomgraph/config.yaml
# 应包含:
# lightrag:
#   api_url: "{{lightrag_url}}"
# embedding:
#   base_url: "http://internal.example.invalid:3002"
```

### 4. 安装 Skills（必须！）

> **警告**：跳过此步骤会导致：
> - 无法使用 `/loomgraph-setup` 和 `/loomgraph-init` 命令
> - {{language_hint}} 项目可能索引失败（语言解析器未安装）

- [ ] 一键安装 Skills
```bash
loomgraph install-skills
```

### 5. 安装语言解析器

- [ ] 安装对应语言的解析器
```bash
source ~/.loomgraph-venv/bin/activate
pip install {{language_parser}}
```

### 6. 添加 Shell 别名

- [ ] 添加别名（可选但推荐）
```bash
echo 'alias loomgraph="~/.loomgraph-venv/bin/loomgraph"' >> ~/.zshrc
source ~/.zshrc
```

### 7. 验证安装

- [ ] 检查服务状态
```bash
loomgraph status
# 或: ~/.loomgraph-venv/bin/loomgraph status
```

**预期输出**：
- `lightrag_api.connected: true`
- `lightrag_api.url: {{lightrag_url}}`

**如果失败**：
- `codeindex installed: false` → 重新执行步骤 5
- `lightrag connected: false` → 检查网络白名单权限

### 8. 安装后自检（防呆！）

> **给 AI Agent**: 安装完成后，请执行以下诊断命令确认所有功能正常。

- [ ] 运行完整自检
```bash
# 1. 确认版本
loomgraph version
# 预期: {{version}}

# 2. 确认服务连接
loomgraph status
# 预期: lightrag connected: true, codeindex installed: true

# 3. 确认 codeindex 可用
codeindex --version
# 预期: 版本号 ≥ 0.20.0

# 4. 确认语言解析器
codeindex parse --help
# 预期: 无报错
```

- [ ] 记录自检结果
```
codeindex 版本: ___
loomgraph 版本: ___
LightRAG 连接: ✅/❌
语言解析器: ✅/❌
```

---

## 安装完成确认

当所有步骤都打勾后，请在项目 CLAUDE.md 中添加：

```markdown
## LoomGraph 安装状态

- [x] LoomGraph v{{version}} 已安装
- [x] Skills 已配置: /loomgraph-setup, /loomgraph-init
- [x] 服务连接正常: {{lightrag_url}}
- [x] 语言解析器: {{language_parser}}

### 功能可用性
- [x] find (结构化搜索)
- [x] graph (调用关系) — 需索引后验证
- [ ] query (语义问答) — 需 LLM 配置，当前可能不可用
- [x] topology (拓扑分析)
- [x] debt (技术债务)
```

---

## 如何更新

> **给 Claude Code**: 当收到更新通知时，执行以下步骤。

### 在线更新

```bash
source ~/.loomgraph-venv/bin/activate
pip install --upgrade "loomgraph @ git+https://TOKEN@github.com/dreamlx/LoomGraph.git@vNEW_VERSION"
loomgraph install-skills
loomgraph version
```

### 离线更新

```bash
source ~/.loomgraph-venv/bin/activate
pip install ./ai_codeindex-*.whl  # 如果有新版
pip install ./loomgraph-*-py3-none-any.whl
loomgraph install-skills
loomgraph version
```

---

## 使用方式

### 初始化新项目（首次使用）

进入代码项目目录，按顺序执行：

#### Step 1: 配置 codeindex（必须先执行！）

```
/loomgraph-setup
```

这会引导你：
1. 检测项目语言（Java/PHP/Python/TypeScript）
2. 安装对应的语言解析器
3. 生成 `.codeindex.yaml` 配置文件（设置并行、排除构建目录等）

**为什么需要这一步？**
- 大型项目不配置会非常慢（单线程 vs 8 并发 = 10 倍差距）
- 需要安装对应语言的 tree-sitter 解析器
- 排除 `{{exclude_dirs}}` 等无用目录

#### Step 2: 配置项目 CLAUDE.md

```
/loomgraph-init
```

这会在项目 CLAUDE.md 中添加 LoomGraph 使用说明。

#### Step 3: 索引代码

```bash
loomgraph index .
```

**注意**：首次索引大型项目可能需要几分钟，请耐心等待。

#### Step 4: 验证索引结果

```bash
# 确认实体已入库
loomgraph find "Service" --limit 5

# 确认关系已入库（如果为空，见「功能与前置条件」表格）
loomgraph graph "YourMainClass" --direction callees
```

### 日常使用

```bash
# 结构化搜索（按名称查找实体）
loomgraph find "UserService"
loomgraph find "UserService" --with-relations  # 带调用关系

# 语义问答（需 LLM 支持，如不可用见前置条件表）
loomgraph query "用户认证逻辑是怎么工作的？"

# 调用关系查询
loomgraph graph "UserService.login" --direction callers

# 增量更新（git 变更后）
loomgraph update

# 检查服务状态
loomgraph status
```

### 知识图谱更新策略

> **给 Claude Code**: 请根据以下规则维护知识图谱的时效性。
>
> ⚠️ **#66 Breaking**: `index`/`update` 已迁到 `codeindex graph-export` 契约（module-qualified 实体 id，修复跨模块同名冲突）。**从旧版本升级后，必须执行一次 `loomgraph index --clear .`** 重建 workspace（旧简单名 key 数据会保留冲突）。`update` 现为 whole-tree re-export（不再 per-file 增量；大仓库建议 hook 用 `LOOMGRAPH_HOOK_MODE=async`）。

#### 何时执行 Update（whole-tree re-export + upsert）

| 场景 | 命令 |
|------|------|
| 完成代码修改并 commit 后 | `loomgraph update` |
| 搜索前发现索引可能过期 | `loomgraph update` |

> `update` 现在每次全量 re-export 整棵树（`--since`/`--files` 已废弃但保留兼容，会被忽略并打印提示）。upsert 保证新增/修改收敛、不丢数据；**删除**的符号不会自动清理（upsert 只覆盖同 id、不删除），搜索结果与代码不符时用 `loomgraph index --clear .` 重建。

#### 何时执行 Cold Rebuild（完全重建）

| 场景 | 命令 |
|------|------|
| 首次索引项目 | `loomgraph index .` |
| **从旧版本升级（#66）** | `loomgraph index --clear .` |
| 大规模重构后（文件移动/重命名） | `loomgraph index --clear .` |
| 搜索结果明显不准确 | `loomgraph index --clear .` |
| 项目结构变化（新增/删除大量文件） | `loomgraph index --clear .` |

#### 自动判断提示

1. **每次 `git commit` 后**：建议执行 `loomgraph update`（或 post-commit hook 自动跑）
2. **搜索结果与代码不符**：执行 `loomgraph index --clear .`
3. **不确定时**：执行 `loomgraph update`（安全，upsert 不丢数据）

---

## CLI 命令参考

### 核心命令

| 命令 | 说明 | 前置条件 |
|------|------|---------|
| `loomgraph status` | 检查服务状态 | 无 |
| `loomgraph version` | 显示当前版本 | 无 |
| `loomgraph index <path>` | 索引代码库（`codeindex graph-export` 契约，module-qualified 实体 id） | codeindex ≥ 0.28 |
| `loomgraph index --clear <path>` | Cold Rebuild（清空重建） | codeindex ≥ 0.28 |
| `loomgraph update` | Whole-tree re-export + upsert（不再 per-file 增量；`--since`/`--files` 已废弃但兼容） | codeindex ≥ 0.28 |

### 搜索命令

| 命令 | 说明 | 前置条件 |
|------|------|---------|
| `loomgraph find "<名称>"` | 结构化实体搜索（名字匹配） | 已索引 |
| `loomgraph find "<名称>" --with-relations` | 搜索 + 显示调用关系 | 已索引 + 关系数据 |
| `loomgraph query "<问题>"` | 语义知识问答 | 已索引 + **LLM 配置** |
| `loomgraph graph "<实体>"` | 调用关系图查询 | 已索引 + 关系数据 |

### 分析命令

| 命令 | 说明 | 前置条件 |
|------|------|---------|
| `loomgraph topology` | 图谱拓扑债务分析 | 已索引 |
| `loomgraph check` | 索引新鲜度检查 | 已索引 + 本地文件 |
| `loomgraph impact [TARGET]` | 变更影响分析 | 已索引 + Git |
| `loomgraph deps` | 模块依赖分析 | 已索引 |
| `loomgraph overview` | 项目模块概览 | 已索引 |

### Workspace 管理

| 命令 | 说明 |
|------|------|
| `loomgraph workspace list` | 列出所有 workspace |
| `loomgraph workspace info` | 查看当前 workspace 详情 |

### Skills（在 Claude Code 中执行）

| 命令 | 说明 |
|------|------|
| `/loomgraph-setup` | 配置 codeindex 和语言解析器 |
| `/loomgraph-init` | 初始化项目 CLAUDE.md |
| `/loomgraph-debt-radar` | 技术债务审计报告 |

---

## 故障排除

### `query` 命令返回错误

**原因**: LightRAG 服务端未配置 LLM（大语言模型）

**说明**: `query` 命令使用 RAG 管线，需要 LLM 对检索结果进行推理和总结。这是服务端配置，客户端无法自行解决。

**解决**: 联系技术团队确认 LightRAG 实例是否已配置 LLM endpoint。

**替代方案**: 使用 `loomgraph find` 进行结构化搜索（不需要 LLM）。

### `graph` 命令返回空关系

**原因**: codeindex 未成功提取该语言的 call relations

**排查步骤**:
```bash
# 1. 确认 codeindex 版本
codeindex --version  # 需要 ≥ 0.20.0

# 2. 确认语言解析器已安装
codeindex parse --list-parsers

# 3. 手动测试单文件解析
codeindex parse /path/to/sample/file.py | python3 -m json.tool
# 查看输出中是否有 "calls" 字段
```

**解决**: 如果 `codeindex parse` 的输出中没有 `calls` 字段，说明该语言的 call 提取尚未支持或版本过旧。

### `/loomgraph-setup` 命令找不到

**原因**: 未安装 Skills

**解决**:
```bash
loomgraph install-skills
```

### 索引很慢（几分钟）

**原因**: 未配置 `.codeindex.yaml`

**解决**: 先执行 `/loomgraph-setup`，再执行 `loomgraph index .`

### 索引时出现大量 warning

这是正常现象。跨文件依赖（如标准库、外部包）会产生 "Target entity does not exist" 警告，不影响使用。

### 命令找不到

如果 `loomgraph` 命令找不到：

```bash
# 方式 1: 使用完整路径
~/.loomgraph-venv/bin/loomgraph status

# 方式 2: 激活虚拟环境
source ~/.loomgraph-venv/bin/activate
loomgraph status

# 方式 3: 重新设置别名
echo 'alias loomgraph="~/.loomgraph-venv/bin/loomgraph"' >> ~/.zshrc
source ~/.zshrc
```

---

## 技术支持

如有问题，请联系 LoomGraph 技术团队。
