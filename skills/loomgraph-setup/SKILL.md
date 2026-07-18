---
name: loomgraph-setup
description: Configure LoomGraph for the current project - install parser extras, delegate .codeindex.yaml generation to codeindex's own wizard
disable-model-invocation: true
argument-hint: "[--force]"
---

## LoomGraph 项目配置向导

在执行 `loomgraph index .` 之前，需要先配置 codeindex（loomgraph 的 AST 解析基础组件）。

> **核心原则：不手写 `.codeindex.yaml`**。codeindex 自己有配置向导（`codeindex init`），能按项目实际文件检测语言、框架、源码布局，生成 schema-correct 的配置。本 skill 只负责装 parser extras + **委托** codeindex 生成配置，不在 loomgraph 侧重造模板（#132：旧版手写模板在多模块 Java / 普通 PHP / 混合 JS-TS 等布局下静默索引 0 实体）。

---

### Step 0: 版本检查（用 pinned 环境，别走 PATH）

loomgraph 运行时用 `sys.executable -m codeindex.cli` 调 codeindex（与 pinned 依赖同 venv，不走 PATH——否则可能命中别的位置装的旧 codeindex，#76/#132 同类坑）。验证也必须走同一路径：

```bash
# loomgraph 版本
loomgraph version 2>/dev/null || echo '{"error": "loomgraph not installed"}'

# codeindex 版本 —— 用 loomgraph 自己的 venv python，不要裸跑 `codeindex --version`
python -m codeindex.cli --version 2>/dev/null || \
  python3 -m codeindex.cli --version 2>/dev/null || \
  echo '{"error": "codeindex not found in loomgraph venv"}'
```

如果未安装或需更新：

```bash
pipx install loomgraph          # 安装
pipx install --upgrade loomgraph  # 更新
```

> 没有 pipx？`python3 -m pip install --user pipx && python3 -m pipx ensurepath`

---

### Step 1: 安装语言 parser extras（loomgraph 侧）

Python 默认包含。其他语言需要对应 tree-sitter extra——**这一步是 loomgraph 的职责**（extras 是 loomgraph 声明的）：

| 检测到的语言 | 安装命令 |
|---|---|
| Python | 无需（默认） |
| Java | `pipx install --force loomgraph[java]` |
| TypeScript / TSX | `pipx install --force loomgraph[typescript]` |
| Swift | `pipx install --force loomgraph[swift]` |
| **JavaScript / JSX** | ⚠️ loomgraph 暂无 `[javascript]` extra。需手动 `pip install tree-sitter-javascript`（否则 JS 文件索引时被跳过 + 警告，但不会让整个索引失败） |
| Objective-C / Go / Rust | codeindex parser 支持，但 loomgraph 暂无 extra。同上手动装 `tree-sitter-<lang>` |

**语言检测交给 Step 2 的 codeindex wizard 做**（它会遍历文件判定，比看根目录一个文件准）。这里只需知道：装好对应 grammar 再进 Step 2。

> `--force` 让 pipx 在已装的 loomgraph 上重装带 extra。codeindex（parser engine）是 loomgraph 依赖，自动安装，无需用户直接操作。

---

### Step 2: 委托 codeindex 生成 `.codeindex.yaml`（核心）

在项目根目录跑 codeindex 自己的向导，**非交互模式**（适合 skill / 自动化）：

```bash
# 预览会改哪些文件（不实际写，GH #88）
python -m codeindex.cli init --dry-run

# 生成 .codeindex.yaml（--yes = 非交互默认；--force = 覆盖已存在的）
python -m codeindex.cli init --yes --force
```

codeindex wizard 会自动完成（loomgraph 旧 skill 手写模板搞不定的事）：
- `detect_languages` — 遍历文件判定语言（多语言项目自动 union，如 `languages: [javascript, typescript]`）
- `infer_include_patterns` — 按实际源码布局推断 include（多模块 Maven、普通 Composer 包 `lib/`、Python flat layout 都能正确处理，不会硬编码 `src/main/java/`）
- `infer_exclude_patterns` / `detect_frameworks` — 排除依赖目录、检测框架

**验证生成的配置**（确认 languages 和 include 合理）：

```bash
cat .codeindex.yaml
```

> **不要手动编辑 languages/include 除非确实需要**。codeindex 生成的就是它自己 schema 的权威形态（正确的 `version: 1` 顶层键、真实的 `indexing.symbols` 路径，不是旧 skill 臆造的 `codeindex:` / `symbols.project_symbols`）。

---

### Step 3: 烟测 —— 真实索引验证（唯一可信的检查）

生成配置后，唯一能确认"配置真的对"的办法是跑一次真实索引，确认产出 >0 实体（旧 skill 用 `codeindex scan --dry-run` 验证是**错的**——它需 `--ai` flag，且预览的是 AI prompt 不是 graph-export 文件集）：

```bash
loomgraph index .
```

确认输出里 `entities_created > 0`。

- **如果 `entities_created: 0` + warning "Parser library not installed for \<lang\>"**：回到 Step 1 装对应 grammar（codeindex 的诊断会直接告诉你装哪个 `tree-sitter-<lang>`，#118 诊断链）。
- **如果 `entities_created: 0` + warning "graph-export returned 0 entities"**：`.codeindex.yaml` 的 `languages`/`include` 与实际代码不匹配。重跑 Step 2 的 `codeindex init --yes --force`（让 wizard 重新检测），或检查 `include` 是否指向了真实存在源码的目录。
- **`entities_created > 0`**：配置正确，进 Step 4。

> 空仓库合法地索引为 0 实体（exit 0，不阻断），但你应该能区分"仓库真的没代码"和"配置错了"——后者一定伴随 codeindex 的 stderr warning。

---

### Step 4: 完成

配置 + 烟测通过后，提示用户：

1. 执行 `/loomgraph-init` 把 LoomGraph 用法写进项目 CLAUDE.md（Claude Code 用户）
2. 后续代码变动用 `loomgraph update`（增量）或装 git hook（`loomgraph hooks install`）自动更新

> 语义搜索（`loomgraph search`）默认关闭，需在 `.loomgraph.yaml` 配 `embedding.enabled: true` + provider（Ollama/OpenAI/Voyage）。结构化命令（`find`/`graph`/`topology`/`deps`）无需 embedding。

---

## 问答流程（仅当 codeindex wizard 检测结果明显不对时介入）

正常情况下 Step 2 的 `codeindex init --yes` 会自动检测，无需提问。**仅当生成配置与项目实际明显不符**（如烟测 0 实体且非 grammar 问题），才向用户确认：

1. 项目主要源码在哪个目录？（wizard 推断错了 include）
2. 是否有特殊的排除需求？（默认 exclude 不够）

修正后**直接编辑 `.codeindex.yaml` 的 `include`/`exclude`**，再重跑 Step 3 烟测。

---

## 注意事项

1. **绝不手写 languages/include 模板**。配置生成委托给 `codeindex init`，loomgraph 不维护语言模板（#132：手写模板永远跟不上新语言/新布局）。
2. **graph-export 只读 root 的 `.codeindex.yaml`**，不合并子模块配置。多模块项目用 `include: [.]`（wizard 默认）让整个仓库被扫，而不是每模块一份配置。
3. **首次索引慢**：正常现象，后续 `loomgraph update` 增量会快很多。
4. **零配置可用**：默认本地 SQLite，无需远程服务。`loomgraph setup-config`（生成 `.loomgraph.yaml`）已 deprecated，仅语义搜索需手写 config 时用。
5. **配置与 codeindex 版本**：`.codeindex.yaml` 的 schema 跟随已装的 codeindex 版本。loomgraph 在 `pyproject.toml` pin 了 `ai-codeindex>=0.33.3`，`pipx install loomgraph` 自动带上。
