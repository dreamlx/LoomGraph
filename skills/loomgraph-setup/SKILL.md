---
name: loomgraph-setup
description: Configure LoomGraph for the current project - install parser extras, delegate .codeindex.yaml generation to codeindex's own wizard (via loomgraph codeindex)
disable-model-invocation: true
argument-hint: "[--force]"
---

## LoomGraph 项目配置向导

在执行 `loomgraph index .` 之前，需要先配置 codeindex（loomgraph 的 AST 解析基础组件）。

> **核心原则：不手写 `.codeindex.yaml`**。codeindex 自己有配置向导（`codeindex init`），能按项目实际文件检测语言、框架、源码布局，生成 schema-correct 的配置。本 skill 只负责装 parser extras + **委托** codeindex 生成配置，不在 loomgraph 侧重造模板（#132：旧版手写模板在多模块 Java / 普通 PHP / 混合 JS-TS 等布局下静默索引 0 实体）。

> **所有 codeindex 调用走 `loomgraph codeindex <args>`**（passthrough，在 loomgraph 自己的 pinned venv 里跑 codeindex），不要用裸 `codeindex` 或 `python -m codeindex.cli`——后者走 PATH，可能命中与 loomgraph 依赖版本不一致的 codeindex（#76 PATH-bypass 同类坑）。

---

### Step 0: 版本检查

```bash
loomgraph version 2>/dev/null || echo '{"error": "loomgraph not installed"}'
loomgraph codeindex --version    # 走 loomgraph 的 pinned venv，不查 PATH
```

如果未安装或需更新：

```bash
pipx install loomgraph            # 安装
pipx install --upgrade loomgraph  # 更新
```

> 没有 pipx？`python3 -m pip install --user pipx && python3 -m pipx ensurepath`

---

### Step 1: 安装语言 parser extras（loomgraph 侧）

Python 默认包含。其他语言需要对应 tree-sitter grammar——**grammar 必须装进 loomgraph 的 venv**（否则索引时该语言文件被跳过 + 警告）。

codeindex 实际支持的 parser（`codeindex/parser.py` `FILE_EXTENSIONS`，权威）：**python / php / java / typescript(+tsx) / javascript(+jsx) / swift / objc**。**不支持 go / rust / c / cpp**（即使装了 grammar 也不会索引）。

| 检测到的语言 | 安装（装进 loomgraph venv） |
|---|---|
| Python | 无需（默认） |
| Java | `pipx install --force "loomgraph[java]"` |
| TypeScript / TSX | `pipx install --force "loomgraph[typescript]"` |
| Swift | `pipx install --force "loomgraph[swift]"` |
| JavaScript / JSX | `pipx install --force "loomgraph[javascript]"` |
| Objective-C | `pipx install --force "loomgraph[objc]"` |

> 语言检测交给 Step 2 的 codeindex wizard 做。这里只需知道：装好对应 grammar 再进 Step 2。
> **引号必要**：`[extra]` 会被 zsh/bash 当 glob（`no matches found`），务必用引号包住 `"loomgraph[javascript]"`。

---

### Step 2: 委托 codeindex 生成 `.codeindex.yaml`（核心）

在项目根目录跑 codeindex 自己的向导，**非交互模式**：

```bash
# 先预览会改哪些文件（不实际写，GH #88）
loomgraph codeindex init --dry-run
```

> ⚠️ **`codeindex init` 不只生成 `.codeindex.yaml`**——它还会注入/更新 `CLAUDE.md`、把 `README_AI.md` 加进 `.gitignore`（`cli_config.py` `_update_gitignore`）。`--dry-run` 会列出所有 target，先看清再决定。

```bash
# 生成 .codeindex.yaml（+ 上述副作用）
loomgraph codeindex init --yes
```

> **关于 `--force`**：仅在确认要覆盖已有 `.codeindex.yaml` 时加。不加 `--force` 时若配置已存在，codeindex 会跳过不覆盖（更安全）。本 skill 的 `[--force]` 参数仅在用户明确要求重置配置时透传。

codeindex wizard 会自动完成（loomgraph 旧 skill 手写模板搞不定的事）：
- `detect_languages` — 遍历文件判定语言（多语言自动 union，如 `languages: [javascript, typescript]`）
- `infer_include_patterns` — 按实际源码布局推断 include
- `infer_exclude_patterns` / `detect_frameworks`

> **wizard 的局限（不是万能，#132 codex review）**：
> - `detect_languages` 扫描有 1000 文件上限，只跳过固定一组目录（不应用生成 exclude）。大型/含大量生成代码的仓库可能误判语言。
> - `infer_include_patterns` 只认顶层 `src/lib/app/pkg/cmd/core/modules`，否则用 `.`（整个仓库）。
> - 因此 **Step 3 的完整性验证不可省**——wizard 可能漏掉部分源码根。

**验证生成的配置**：

```bash
cat .codeindex.yaml
```

> 不要手动改 `languages`/`include` 除非确实需要。codeindex 生成的是它自己 schema 的权威形态（正确的 `version: 1`，真实字段如 `indexing.symbols`，不是旧 skill 臆造的 `codeindex:` / `symbols.project_symbols`）。

---

### Step 3: 烟测 —— 完整性验证（关键，不能只看计数）

生成配置后跑真实索引。**但光看 `entities_created > 0` 不够**——它只证明"有文件被解析"，不证明"该索引的都索引了"（#132 codex review #2：monorepo 里 wizard 只 include 了 `src/`，Python 索引成功但漏了 `services/` 的 PHP，计数仍 >0）。

```bash
loomgraph index .
```

**验证两件事**：

1. **`entities_created > 0`**（必要条件）。若为 0：
   - warning "Parser library not installed for \<lang\>" → 回 Step 1 装对应 grammar（codeindex 诊断会直接说装哪个）。
   - warning "graph-export returned 0 entities" → `.codeindex.yaml` 的 `languages`/`include` 与实际代码不匹配。重跑 `loomgraph codeindex init --yes --force` 让 wizard 重新检测，或手动修正 `include` 指向真实源码目录。

2. **覆盖完整性**（充分条件）：确认项目的**主要源码目录**都出现在索引结果里。可抽查：
   ```bash
   loomgraph find "<某个已知实体名>"   # 应能找到
   ```
   或直接检查 codeindex 扫到了哪些文件：
   ```bash
   loomgraph codeindex list-dirs       # codeindex 实际会扫描的目录
   ```
   若某个预期源码目录不在内（wizard 的 include 推断漏了），手动在 `.codeindex.yaml` 的 `include:` 补上，重跑 `loomgraph index .`。

> 空仓库合法地索引为 0（exit 0），但你要能区分"仓库真没代码"和"配置错了"——后者一定伴随 codeindex stderr warning。

---

### Step 4: 完成

配置 + 烟测通过后，提示用户：

1. 执行 `/loomgraph-init` 把 LoomGraph 用法写进项目 CLAUDE.md（Claude Code 用户）
2. 后续代码变动用 `loomgraph update`（增量）或装 git hook（`loomgraph hooks install`）自动更新

> 语义搜索（`loomgraph search`）默认关闭，需在 `.loomgraph.yaml` 配 `embedding.enabled: true` + provider。结构化命令（`find`/`graph`/`topology`/`deps`）无需 embedding。

---

## 问答流程（仅当 wizard 检测结果明显不对时介入）

正常情况下 Step 2 的 `codeindex init --yes` 会自动检测，无需提问。**仅当烟测发现覆盖不完整**（某个预期源码目录没被索引）才向用户确认：

1. 漏掉的源码在哪个目录？（手动补进 `include:`）
2. 是否有特殊排除需求？

修正后直接编辑 `.codeindex.yaml` 的 `include`/`exclude`，重跑 Step 3 烟测。

---

## 注意事项

1. **绝不手写 languages/include 模板**。配置生成委托给 `loomgraph codeindex init`，loomgraph 不维护语言模板（#132：手写模板永远跟不上新语言/新布局）。
2. **graph-export 只读 root 的 `.codeindex.yaml`**，不合并子模块配置。多模块项目让 wizard 用 `include: [.]`（或手动设）扫整个仓库，而非每模块一份配置。
3. **`codeindex init` 有副作用**（注入 CLAUDE.md、改 .gitignore）——先 `--dry-run` 看清。
4. **首次索引慢**：正常现象，后续 `loomgraph update` 增量会快很多。
5. **零配置可用**：默认本地 SQLite，无需远程服务。`loomgraph setup-config`（生成 `.loomgraph.yaml`）已 deprecated，仅语义搜索需手写 config 时用。
6. **codeindex 支持的语言有限**：python/php/java/typescript/javascript/swift/objc。go/rust/c/cpp 不支持（parser 无 dispatch）。
