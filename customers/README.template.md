# LoomGraph - {{customer_name}}专用版

> **给 Claude Code / Codex / Cursor**: 请按顺序执行下面的 Checklist，每完成一项就打勾 `[x]`。
> **所有步骤都必须完成**，跳过任何一步都会导致功能异常。

---

## 功能与前置条件

> **重要**: 不同功能需要不同的前置条件。安装后请对照此表确认哪些功能可用。

| 功能 | 命令 | 前置条件 | 说明 |
|------|------|---------|------|
| 结构化搜索 | `loomgraph find` | 已索引 | 按名称/类型搜索实体 |
| 语义搜索 | `loomgraph search` | **embedding.enabled + provider** | 按语义/意图搜索实体（向量检索，非名称匹配） |
| 调用关系图 | `loomgraph graph` | 已索引 + 关系数据 | 查询 callers/callees（`--include-unresolved` 看原始调用表达式） |
| 拓扑分析 | `loomgraph topology` | 已索引 | 检测孤立实体、God 函数等 |
| 索引新鲜度 | `loomgraph check` | 已索引 + 本地文件 | 对比图谱 vs 磁盘文件 |
| 变更影响 | `loomgraph impact` | 已索引 + Git 仓库 | 分析代码变更影响范围 |
| 技术债务 | `loomgraph debt` | codeindex 静态分析数据 | 多维度债务评分 |
| 模块依赖 | `loomgraph deps` | 已索引 | 跨模块依赖图 |
| Git 度量 | `loomgraph git-metrics` | Git 仓库 | 热点/总线因子/缺陷率 |
| 向量补齐 | `loomgraph embed-backfill` | 已索引 + embedding.enabled + provider | 为无向量的 workspace 补向量，使其可被 `search` 命中；幂等 |

### 常见问题速查

| 现象 | 原因 | 解决方案 |
|------|------|---------|
| `graph` 返回空关系 | codeindex 未提取该语言的 call relations | 确认 codeindex 版本 ≥ 0.33.0 + 语言解析器已安装 |
| `find` 正常但 `graph` 空 | 只有 entity 数据，缺少 relation 数据 | 重新索引: `loomgraph index --clear .` |
| `search` 报 `EMBEDDING_NOT_INDEXED` 或返回空 | workspace 无向量（embedding 未启用） | `loomgraph embed-backfill -w <ws>` 补向量；或在 `.loomgraph.yaml` 开 `embedding.enabled: true` 后 `loomgraph index .` |
| `graph` callees 含 `source_id=""` 的空记录 | 默认已过滤（#113）；`--include-unresolved` 才会显示低信任边 | 正常现象，真实 callees 已在默认输出里 |
| 索引很慢 | 未配置 `.codeindex.yaml` | 先执行 `/loomgraph-setup` 再索引 |

---

## 安装 Checklist

### 1. 安装 LoomGraph

- [ ] 一行命令安装（公开 PyPI）
```bash
pipx install loomgraph
```

> `pipx` 为 LoomGraph 创建隔离环境，`codeindex`（parser engine）作为依赖自动安装，无需单独操作。
> 没有 `pipx`？先装：`python3 -m pip install --user pipx && python3 -m pipx ensurepath`

### 2. （可选）安装语言解析器

{{language_hint}} 项目需要对应的 tree-sitter 解析器（{{language_hint}} 为 Python 时跳过此步，Python 解析器默认包含）：

- [ ] Java 项目
```bash
pipx install loomgraph[java]
```

- [ ] TypeScript 项目
```bash
pipx install loomgraph[typescript]
```

> 已用 `pipx install loomgraph` 装过？改用 `pipx install --force loomgraph[java]` 重装带 extra。

### 3. 配置（零配置默认可用）

LoomGraph 默认本地 SQLite、embedding 关闭，**无需任何配置即可使用结构化命令**（`find`/`graph`/`topology`/`deps`/`impact`）。

- [ ] （可选）启用语义搜索时，在项目根目录创建 `.loomgraph.yaml`：
```yaml
embedding:
  enabled: true
  provider: ollama              # ollama | openai | voyage | glm | custom
  api_url: http://localhost:11434/v1
  model: nomic-embed-text
  dimension: 768
```

> 详细配置见 [README.md](https://github.com/dreamlx/LoomGraph#configuration)。

### 4. 安装 Skills（Claude Code 用户）

> 仅 Claude Code 需要。Cursor / Codex 用户通过 MCP 集成（见下）。

- [ ] 安装 Skills
```bash
loomgraph install-skills
```

### 5. 配置 MCP（Claude Code / Cursor）

- [ ] Claude Code
```bash
loomgraph mcp install-config --path ~/.claude/mcp.json
```

- [ ] Cursor：项目级 `.cursor/mcp.json`
```json
{
  "mcpServers": {
    "loomgraph": {
      "command": "loomgraph",
      "args": ["mcp", "serve", "--default-workspace", "{{customer_key}}:main"]
    }
  }
}
```

> 配置后重启 IDE，`loomgraph_find` / `loomgraph_graph` / `loomgraph_topology` 等作为原生工具出现。

### 6. 验证安装

- [ ] 自检
```bash
loomgraph version    # 预期: {{version}}
loomgraph status     # 预期: storage=sqlite, codeindex installed
codeindex --version  # 预期: ≥ 0.33.0
```

---

## 安装完成确认

当所有步骤都打勾后，在项目 CLAUDE.md / `.cursor/rules` 中添加：

```markdown
## LoomGraph 安装状态

- [x] LoomGraph v{{version}} 已安装（pipx）
- [x] MCP 已配置 / Skills 已安装
- [x] 语言解析器: {{language_hint}}

### 功能可用性
- [x] find (结构化搜索)
- [x] graph (调用关系)
- [x] topology (拓扑分析)
- [x] deps (模块依赖)
- [ ] search (语义搜索) — 需 embedding.enabled
```

---

## 如何更新

```bash
pipx install --upgrade loomgraph
loomgraph install-skills   # Claude Code 用户
loomgraph version
```

> `#66 Breaking`: 从旧版本（< 0.11）升级后，**必须执行一次 `loomgraph index --clear .`** 重建 workspace（旧简单名 key 数据会冲突）。

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
2. 生成 `.codeindex.yaml` 配置文件（设置并行、排除构建目录等；flat layout 自动用 `include: ["."]`）

#### Step 2: 配置项目 CLAUDE.md（Claude Code 用户）

```
/loomgraph-init
```

#### Step 3: 索引代码

```bash
loomgraph index .
```

#### Step 4: 验证索引结果

```bash
loomgraph find "Service" --limit 5
loomgraph graph "YourMainClass" --direction callees
```

### 日常使用

```bash
# 结构化搜索（按名称查找实体）
loomgraph find "UserService"
loomgraph find "UserService" --with-relations  # 带调用关系

# 语义搜索（需 embedding.enabled）
loomgraph search "user authentication logic"

# 调用关系查询
loomgraph graph "UserService.login" --direction callers

# 增量更新（git 变更后）
loomgraph update

# 检查状态
loomgraph status
```

### 知识图谱更新策略

> ⚠️ **#66 Breaking**: `index`/`update` 用 `codeindex graph-export` 契约（module-qualified 实体 id）。**从旧版本升级后，必须执行一次 `loomgraph index --clear .`** 重建 workspace。

#### 何时执行 Update（per-file warm-diff）

| 场景 | 命令 |
|------|------|
| 完成代码修改并 commit 后 | `loomgraph update` |
| 搜索前发现索引可能过期 | `loomgraph update` |

> git 仓库里 `update` 只 re-embed/re-inject `git diff` 出的变更文件，并 GC 已删除符号。非 git 仓库 fallback 到 whole-tree upsert（此路径删除符号不 GC，需 `loomgraph index --clear .` 重建）。

#### 何时执行 Cold Rebuild（完全重建）

| 场景 | 命令 |
|------|------|
| 首次索引项目 | `loomgraph index .` |
| **从旧版本升级（#66）** | `loomgraph index --clear .` |
| 大规模重构后（文件移动/重命名） | `loomgraph index --clear .` |
| 搜索结果明显不准确 | `loomgraph index --clear .` |

---

## CLI 命令参考

### 核心命令

| 命令 | 说明 | 前置条件 |
|------|------|---------|
| `loomgraph status` | 检查系统状态 | 无 |
| `loomgraph version` | 显示当前版本 | 无 |
| `loomgraph index <path>` | 索引代码库（module-qualified 实体 id） | codeindex ≥ 0.33 |
| `loomgraph index --clear <path>` | Cold Rebuild（清空重建） | codeindex ≥ 0.33 |
| `loomgraph update` | Per-file warm-diff（git diff → 只 re-embed 变更文件 + GC） | codeindex ≥ 0.33 |

### 搜索命令

| 命令 | 说明 | 前置条件 |
|------|------|---------|
| `loomgraph find "<名称>"` | 结构化实体搜索（名字匹配） | 已索引 |
| `loomgraph find "<名称>" --with-relations` | 搜索 + 显示调用关系 | 已索引 + 关系数据 |
| `loomgraph search "<意图>"` | 语义搜索（向量检索，按含义） | 已索引 + **embedding.enabled** |
| `loomgraph graph "<实体>"` | 调用关系图查询（`--include-unresolved` 看低信任边） | 已索引 + 关系数据 |

### 分析命令

| 命令 | 说明 | 前置条件 |
|------|------|---------|
| `loomgraph topology` | 图谱拓扑债务分析 | 已索引 |
| `loomgraph debt` | 多维度技术债务评分 | 已索引 |
| `loomgraph deps` | 模块依赖分析 | 已索引 |
| `loomgraph overview` | 项目模块概览 | 已索引 |
| `loomgraph check` | 索引新鲜度检查 | 已索引 + 本地文件 |
| `loomgraph impact [TARGET]` | 变更影响分析 | 已索引 + Git |
| `loomgraph git-metrics` | Git 热点/总线因子 | Git 仓库 |
| `loomgraph trends --entity X` | 代码复杂度趋势 | 已索引 |
| `loomgraph embed-backfill` | 为 workspace 补向量 | 已索引 + embedding.enabled |

### Workspace 管理

| 命令 | 说明 |
|------|------|
| `loomgraph workspace list` | 列出所有 workspace |
| `loomgraph workspace info` | 查看当前 workspace 详情 |
| `loomgraph workspace delete NAME --yes` | 删除指定 workspace |
| `loomgraph compare --ws1 A --ws2 B` | 跨 workspace 实体/关系 diff |
| `loomgraph similar -e "<entity>"` | 跨 workspace 相似实体检测 |

### Skills（在 Claude Code 中执行）

| 命令 | 说明 |
|------|------|
| `/loomgraph-setup` | 配置 codeindex + 生成 .codeindex.yaml |
| `/loomgraph-init` | 初始化项目 CLAUDE.md |

> 技术债务审计 / 跨分支同步 / 演化趋势用 MCP composite：`loomgraph_debt_audit` / `loomgraph_sync_advice` / `loomgraph_evolution_track`。

---

## 故障排除

### `graph` 命令返回空关系

**原因**: codeindex 未成功提取该语言的 call relations

**排查步骤**:
```bash
codeindex --version  # 需要 ≥ 0.33.0
codeindex parse /path/to/sample/file.py | python3 -m json.tool
# 查看输出中是否有 "calls" 字段
```

### `search` 报 `EMBEDDING_NOT_INDEXED`

**原因**: workspace 无向量（embedding 未启用）

**解决**: 在 `.loomgraph.yaml` 开 `embedding.enabled: true` + 配置 provider，然后 `loomgraph index .` 或 `loomgraph embed-backfill -w <ws>`。

### `/loomgraph-setup` 命令找不到

**原因**: 未安装 Skills（仅 Claude Code）

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

```bash
# pipx 安装的 loomgraph 在 ~/.local/bin，确保 PATH 包含它
echo $PATH | tr ':' '\n' | grep local/bin
# 没有则: pipx ensurepath && 重开终端
```

---

## 技术支持

如有问题，请联系 LoomGraph 技术团队。
