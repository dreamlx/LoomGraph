# LoomGraph 变更日志

> **给 Claude Code**: 阅读此文件了解版本变更。如果客户版本低于最新版本，建议更新。

---

## [Unreleased]

### 重构 — `/loomgraph-setup` 委托 codeindex 向导生成配置；新增 `loomgraph codeindex` 透传命令 (#132)
- 旧版 setup skill 用**手写静态模板**生成 `.codeindex.yaml`，且模板里有臆造的
  schema 键（`codeindex: 1` 应为 `version: 1`；不存在的 `symbols.project_symbols`）。
  在真实项目布局下会**静默索引 0 实体**：多模块 Maven（硬编码 `src/main/java/`）、
  普通 Composer PHP 包（假设 `app/`/`src/`）、混合 JS/TS（无模板）、非标准源码根目录。
  根因：skill 在重新发明 codeindex 自己的向导，且做得更差。
- 重构为**纯委托**：skill 跑 codeindex 自带的、适合自动化的向导（按项目实际文件检测
  语言/框架/源码布局）。删除全部四个静态模板 + flat-layout bash hack + 失效的 `scan --dry-run`
  验证。codeindex 是自己 schema 的权威源，loomgraph 不再手写。
- **新增 `loomgraph codeindex <args>` 透传 CLI 命令**：在 loomgraph 自己的 pinned venv 里跑
  codeindex（`sys.executable -m codeindex.cli`），与 loomgraph 内部已有的调用方式一致。
  skill 现在调 `loomgraph codeindex init` 而非走 PATH 的 `python`/`codeindex`（后者可能命中
  与 loomgraph 依赖版本不一致的 codeindex，#76 同类坑）。
- **codex review 加固（6 项全采纳）**：删除"go/rust 支持"的虚假宣称（codeindex parser 只支持
  python/php/java/ts/js/swift/objc）；警告 `codeindex init` 有副作用（注入 CLAUDE.md、把
  README_AI.md 加进 .gitignore）且 `--force` 会覆盖；烟测改为检查**覆盖完整性**而非只看
  `entities_created > 0`（monorepo 可能索引了错误子集仍计数 >0）；说明 wizard 的局限
  （1000 文件检测上限、固定 include 目录列表）；JS/ObjC grammar 用 `pipx runpip loomgraph
  install tree-sitter-<lang>` 注入 loomgraph venv（暂无一等 extra，#134）。
- **验证**：实测 `codeindex init --yes` → `loomgraph index .` 在 5 种布局（多模块 Java、
  普通 PHP、混合 JS/TS、Python flat、Python src）都产出 >0 实体。旧 skill 在前两种是 0。

### 修复 — 设了 `core.hooksPath` 的项目 hook 装了不生效 (#130)
- `loomgraph hooks install` 报 `success: true` 但 hook 从不触发——当项目设了
  自定义 `core.hooksPath`（husky、共享 hook、本仓库自己的 `.githooks/`）时。
  git 设了 hooksPath 后**只读该目录，完全忽略 `.git/hooks/`**，而
  `get_hooks_dir()` 硬编码了 `.git/hooks`，hook 落到了 git 永远不看的位置。
  修复：改用 `git rev-parse --git-path hooks` 定位 hooks 目录（尊重 hooksPath，
  未设时回退 `.git/hooks`）。与 #128 不同（#128 是装不上，#130 是装到死位置）。
- **更新指引**：升级后请重跑 `loomgraph hooks install --force`，hook 会装到
  git 实际读取的目录（husky 用户会进 `.husky/`，本仓库进 `.githooks/`）。

### 修复 — `loomgraph hooks install` 在 wheel/pipx 安装下失败 (#128)
- `loomgraph hooks install` 对所有 wheel/pipx 安装返回 `installed_count: 0`，
  模板 "not found"——"commit 即索引本轮变动"这个核心功能对所有正常安装路径失效。
  双重缺陷：(A) post-commit 模板从未打进 wheel；(B) 路径逻辑假设源码树布局
  （`Path(__file__).parent×4 / "scripts/hooks"`），只在 editable 安装下碰巧成立——
  这正是长期未被发现的原因（开发者用 editable dogfood，用户用 wheel 安装）。
  已将模板移入包内（`src/loomgraph/_hooks_templates/`）并用 `importlib.resources` 定位，
  editable/wheel/pipx 三种安装方式行为一致。
- 静默成功掩盖：`loomgraph hooks install` 即使全部 hook 失败仍返回 `success: true`。
  现在全部失败时报 `HOOK_INSTALL_FAILED` 错误，避免未来同类打包回归被吞掉。
- **更新指引**：升级后请重跑 `loomgraph hooks install --force` 重新生成 post-commit hook
  （旧版本虽报 `success`，但 hook 实际没装上）。

### 修复 — GitHub Action 集成不再因 `--lightrag-url` 报错 (#125)
- 可复用 workflow `incremental-update.yml` 仍调用 `loomgraph update --lightrag-url`，
  而该参数在 LightRAG 退役（v0.10-0.11）后已从 CLI 移除——任何引用该 workflow 的项目
  每次 push 都会报 "no such option"。已删除该参数及 `lightrag_endpoint` 输入；
  `embedding_endpoint` 改为可选（默认空 → 仅结构化索引，因为 GitHub-hosted runner
  无法访问本地 Ollama）。接入文档同步更新，移除 `LIGHTRAG_URL` secret。
- `loomgraph status --help` 的说明不再误标 "Jina Code V2"（Jina 已退役），改为
  "OpenAI-compatible embedding provider（默认本地 Ollama）"。

### 文档 — CLI 设计文档整篇对齐当前命令面 (#124)
- `docs/api/CLI_DESIGN.md` 的命令详情段（646 行）多处与实际 CLI 冲突：`update`
  被描述为全量重导（实际是 per-file warm-diff + content_hash 增量）、`status`
  示例里还有 PostgreSQL/Jina/LightRAG/docker（均已退役）、错误码表列了不存在的
  `LIGHTRAG_ERROR`。已整篇重写，每个参数表对照 `--help` 核实，并补齐
  `deps`/`debt`/`impact`/`overview`/`git-metrics`/`trends`/`workspace`/`hooks`/`mcp`
  等原本只在概览表里出现、没有详情段的命令。顶部声明本文为"写作时快照，以
  `--help` 为唯一权威"。
- **EPIC-003（增量更新策略）已归档** —— 核心目标已达成（warm-diff、content_hash
  增量、post-commit hook、MCP refresh）。`docs/epics/active/` 现已空。
- ⚠️ **GitHub Action 集成暂不可用**：底层 reusable workflow 仍调用已移除的
  `--lightrag-url` 参数。`docs/guides/github-action-integration.md` 已加显著警告，
  待 #125 修复 workflow 后恢复。

### 文档 — README 新增 `workspace` 概念说明
- `workspace` 是贯穿全工具的核心概念（存储路径、查询目标、分支隔离、
  自动降级），但 README 一直"用而不定义"。新加 "Workspaces" 小节：什么是
  workspace（一个被索引的代码库快照，`~/.loomgraph/<ws>.db`）、命名规则
  （`<仓目录>:<分支>`，全小写）、分支隔离语义、`--workspace` 覆盖、
  `workspace list/info/delete`，以及空 workspace 自动降级到 `main → develop → master`。
  新人跑完 `loomgraph index .` 后能立刻回答"它建了哪个 workspace、叫什么、
  分支切换怎么办"。

### 修复 — `refresh`/`update` 在 0 实体时不再静默清空数据 (#120)
- #118 修了 `index` 的 0 实体静默问题，但 `update` 和 `refresh`（含 MCP
  `loomgraph_refresh`）这两个同样调 `run_graph_export` 的入口没对齐：
  - **`loomgraph_refresh(force_full=True)`** 在配置错误的仓库（0 实体）上
    会先清空整个 workspace 再插入空图 —— **静默数据丢失**。
  - **`loomgraph update`** 会走到增量 GC，把变更文件里原本存在的符号当
    "已删除"清掉。
- 现在两者在 0 实体导出时**硬停**（`mode: zero_entity_skipped` + `warning`
  带出 codeindex 的真实根因），不再触碰 store。`index` 保持原行为（空仓
  合法 0 是允许的）。
- 同时修复 `loomgraph impact` 的 PATH bypass：原本裸调 `codeindex parse`
  走 PATH，可能命中旧版 pipx codeindex 绕过 pinned 依赖；现改为
  `sys.executable -m codeindex.cli parse`（与 #76 同类）。

## [0.16.1] - 2026-07-14

### 修复 — Swift 项目不再静默索引为 0 实体 (#118)
- 全新安装后对纯 Swift 仓库跑 `loomgraph index` 会得到 **0 实体** + 一句
  含糊警告。根因：loomgraph 没声明 `[swift]` extra，新用户 venv 没有
  `tree-sitter-swift`，而诊断链又丢了 codeindex 的 `Parser library not
  installed` 报错。
- **新增 `loomgraph[swift]` extra**：`pipx install loomgraph[swift]` 即可装
  上 Swift 解析器（与 `[java]` / `[typescript]` 对齐）。
- **0 实体诊断改进**：现在会直接点名缺失的语言 + 给出"装 extra + 配
  `languages`"的可执行指引，PHP/Java/TS/Swift 等都覆盖。Python 项目不受
  影响（双保险：硬依赖 + 默认 `languages: ["python"]`）。

## [0.16.0] - 2026-07-13

### 变更 — 移除企业私有分发遗留（仅仓库内部清理）
- LoomGraph 自 v0.16 起只走公开 PyPI（`pipx install loomgraph`），企业
  私有分发框架（GitHub PAT 管理、客户专属 INSTALL.md、离线 tarball 打包、
  交付总结生成器）已删除。**对公开用户无影响**——安装/升级命令不变。
  仓库内 `docs/PACKAGING.md` 重写为当前 `release.yml` CI 流程，Makefile
  清掉 11 个死 target。

## [0.15.5] - 2026-07-12

### 修复 — TS 项目 `@/` 路径别名现在正常解析（an internal TS monorepo 假孤儿节点消除）
- **背景**：用 `@/components/ui/button` 这类 `tsconfig.json` `paths` 别名
  的 TypeScript 仓库，之前 `loomgraph topology` 会把一批**实际被引用的**
  组件（`Button`、`Checkbox`、`Dialog`、`appRoutes`、`zhCN`、
  `TenantProvider` 等）误报为「孤儿节点」，因为这些 `@/` 导入边在
  codeindex 侧全部 unresolved。根因是 codeindex #139（0.33.2）只修了
  `src/*` 形式的别名目标，没修 `./src/*` 形式（Vite / Next.js / TS 官方
  示例的默认写法）—— `_dot` 把 `./src/*` 错误转成 `..src.*`，匹配不上
  `src.*` 模块名。codeindex #144（0.33.3）修好了这个归一化。
- **实测**（an internal TS monorepo，630 实体）：`@/` 别名导入边解析率 **0/381 (0%) →
  840/868 (96%)**；`topology` 孤儿节点 **235 → 208**（消除 27 个假孤儿，
  0 个新增）。剩余 4% 是指向 `include: [src/]` 扫描范围外模块的 `@/` 导入
  （如 `@/mocks/...`），属正常 unresolved，不是 bug。
- **更新指引**：TypeScript 项目升级后请执行一次 `loomgraph index --clear .`
  重建，让 `topology` 清掉旧的假孤儿节点。非 TS 项目无影响。

## [0.15.4] - 2026-07-11

### 变更 — 安装流程迁公开 PyPI + setup-config 废弃 (#114)
- **安装方式**：从 `~/.loomgraph-venv` + GitHub TOKEN 私有分发，统一改为
  `pipx install loomgraph`（公开 PyPI）。无需 TOKEN、无需远程 LightRAG 服务。
  Java/TypeScript 项目用 `pipx install --force loomgraph[java]` /
  `loomgraph[typescript]` 装语言解析器。
- **`loomgraph setup-config` 废弃**：原命令生成 LightRAG config，与 v0.11+
  SQLite 默认矛盾。现改为输出 stderr 废弃警告 + 写 SQLite config stub。命令保留
  不 break 现有脚本，但日常无需运行（零配置默认可用）。
- **`/loomgraph-setup` Skill**：去掉 venv/LightRAG 依赖；新增 flat layout 检测
  （根目录 `*.py` 无 `src/` 时用 `include: ["."]`），修复此前 0 实体静默清空问题。
- **CLAUDE.md / README 模板**：对齐当前架构（SQLite + codeindex + MCP native），
  移除 LightRAG/Postgres/H200/`loomgraph query` 等过时内容。
- **⚠️ 安全**：历史交付文档曾含真实 GitHub PAT 明文，已脱敏；但 git 历史仍含明文，
  请到 github.com/settings/tokens 确认相关 token 已 revoke。

### 修复 — `graph <类>` 现在聚合方法的 callees (#105)
- 类实体本身不拥有传出边，调用都在它的方法上（`Class.method`），所以
  `graph SomeClass` 之前显示 0 个 callee，即使每个方法都在调东西。现在把
  方法的 callees 折叠进来，对类已有的直接边去重（如 REFERENCES）。callers
  不受影响（构造函数边通过 codeindex 落在类上）。loomgraph 自测：一个调用
  密集的类 callees 从 0 → 80。

### 修复 — `deps` 对单包仓库自动下钻模块深度 (#106)
- 源码只深一层（如全在 `src/pkg/` 下）的仓库，在 depth 1 时塌成单一模块，
  掩盖了真实的内部耦合。`DepsAnalyzer` 现在会扩展 depth 直到出现 ≥2 个真实
  模块，停在第一个多模块深度（不过度拆分）。`--depth` 现在指「起始深度」。
  loomgraph 自测：1 模块/0 依赖 → 7 模块/11 依赖。

### 修复 — `index`/`update` 不再静默成功掩盖少实体 (#108)
- 用默认 `languages:[python]` 索引非 Python 仓库时，codeindex 会抓到几个零
  散实体并在 stderr 写 WARNING；之前 loomgraph 在 exit 0 时丢弃 stderr，于是
  报 `success:1` 但实体近乎为零。现在 WARNING 被捕获并 echo 到 stderr + 写
  入 JSON 结果的 `warning` 字段。

### 变更 — pin `ai-codeindex>=0.33.1` (#107, #111)
- graph-export 现在遵守 `.codeindex.yaml` 的 `include:`（codeindex #137），
  所以当项目把索引范围限定到 `src/` 时，`loomgraph index .` 不再吃进
  `docs/`/`tests/`/`spikes/` —— 清掉了它们在 `topology` 里造成的假
  god/hub/orphan 节点（#107）。
- MCP server 与 debt 报告的版本号改为从 `loomgraph.__version__` 取
  （`importlib.metadata`），不再是滞后于已装包的硬编码常量（#111）。
- **更新指引**：升级后建议 `loomgraph index --clear .` 重建，让 `topology`
  清除旧的假 god/hub/orphan 节点。单点查询（`graph`/`find`/`deps`）行为
  改善但不依赖重建。

## [0.15.3] - 2026-07-08

### 修复 — `graph --depth` 现在做真 BFS，之前是 no-op (#103)
- `graph()` 收了 `--depth` 但调 `_async_graph_query` 时丢了，导致 depth
  1/2/3/5 返回完全相同结果（仅直接邻居）。`_async_graph_query` 现在建
  relation_type 过滤的 adjacency，对 callers/callees 做 `depth` 层 BFS
  （复用 `find --with-relations` 的 `_bfs_collect`）。depth=1 行为不变；
  depth>1 传递性扩展，去重。
- an internal TS monorepo 实测：`graph src.__tests__.db-seed.test. --callees --depth 1` →
  22，`--depth 2` → 23（经一跳 callee 到达 `JSON.stringify`）。
- **注意**：密集代码图（如 an internal TS monorepo 5794 relations）depth>2 可能返回大量
  节点，按需选 depth。

## [0.15.2] - 2026-07-08

### 修复 — ambiguous CALLS 边不再产生幽灵模块依赖 (#101)
- codeindex 把 dynamic-dispatch 调用（`db.exec`、`x.json()`）标为
  `resolution_qualifier=ambiguous`，并把所有同名方法塞进 `candidates`
  （如 4 个 `test.exec` 测试辅助）。`map_edge` 取 `candidates[0]`，导致
  `src/lib/api/queries.ts` 里每个 `db.exec` 都被 resolve 到
  `server.test.customers.test.exec` —— 系统性幽灵跨模块依赖，使 `deps` 和
  `topology` 在 TS 项目上不可信。
- `map_edge` 现在用 `dst_raw`（调用表达式）作 ambiguous 边的 `tgt_id`（同
  `unresolved`），`deps`/`topology` 自然 skip（无 entity 匹配调用表达式 id），
  candidates 保留在 `edge_data` 供 graph 调用方使用。
- an internal TS monorepo 实测：544 条 ambiguous 边修前 100% 幽灵（全撞真实 entity），修后
  0；`deps` 的 `→ server/test` 边从 ~20 降到 0。
- **更新指引**：TS 项目（或大量 `obj.method()` dynamic-dispatch 的代码库）
  升级后需 `loomgraph index --clear .` 重建，`deps`/`topology` 才清除假边。
  实体级（`graph`/`find`）不受影响，无需重建。

## [0.15.1] - 2026-07-08

### 修复 — git 分支名含斜杠不再导致索引失败 (#99)
- 分支名如 `codex/ui-grammar-filter-parity-us023` 会让 workspace 名含 `/`，
  文件系统将其当路径分隔符 —— DB 落到子目录且 0 行数据落库，`workspace
  list` 也发现不了（只扫顶层 `*.db`）。`_resolve_db_path` 现把 `/` 和 `\`
  净化为 `-`，DB 落顶层且 round-trip 自洽（index → 查询）。影响所有
  `feature/*` / `bugfix/*` / `codex/*` 分支（git 主流约定）；此前这个
  silent-fail 被误判为"TS CALLS 边 quality bug"。

### 修复 — `graph <简单名>` 现解析到存储的 FQN (#98)
- `loomgraph graph downstreamBlockers` 之前返回 `callers: [], source_id: ""`
  —— 遍历用 `==` 把裸名跟模块限定名比较，从不解析。`_async_graph_query`
  现把简单名解析到 FQN（精确匹配优先；否则唯一 dotted-suffix 匹配）。
  `graph downstreamBlockers` 现返回 2 个调用方（handler + test），与
  `find --with-relations` 和 Serena LSP 一致。根因在查询端，不在 ingest。

## [0.15.0] - 2026-07-07

### 新增 — debt/topology 的 `--scope` 路径过滤 (#61)
- `loomgraph debt --scope src/` 和 `loomgraph topology --scope src/` 按
  绝对路径前缀过滤 codeindex 静态层 + topology 层，docs/scripts/tests
  不再污染审计结果（orphans / god functions / 耦合）。`--module` 保留为
  弃用别名；scope 优先。

### 新增 — MCP debt / check / git_metrics 独立 primitive (#62)
- `loomgraph_debt` / `loomgraph_check` / `loomgraph_git_metrics` 作为独立
  只读 primitive 暴露（之前只能经 `loomgraph_debt_audit` composite 到达）。
  未加载 composite 的会话也能单调。

### 移除 — 弃用的 workflow skills (#64, ⚠️ breaking)
- 删除 `loomgraph-debt-radar` / `-evolution` / `-sync-advisor` 三个 skill
  （v0.12.1 已弃用，被 `loomgraph_debt_audit` / `evolution_track` /
  `sync_advice` MCP composite 替代）。`install-skills` 现只装 `init` +
  `setup`。
- **更新指引**: 原来用 `/loomgraph-debt-radar` 的，改用 MCP composite
  `loomgraph_debt_audit`（一次调用并行多维度），或独立的
  `loomgraph_debt` / `_check` / `_git_metrics` primitive。

### 修复
- `overall_health.summary.total_entities` 不再硬编码 0 (#60)。
- `SERVER_VERSION` 此前停滞在 0.13.0，现已跟版本号同步。

## [0.14.2] - 2026-07-06

### 修复 — `workspace delete` 现在真正删除 .db 文件（#95）

之前 `workspace delete` 只清表内数据、不删 `.db` 文件，被删的 workspace 会作为空壳一直留在 `workspace list` 里（list 按 `*.db` 枚举）；删一个不存在的工作区反而会创建空壳。现在直接 unlink `<name>.db` + sqlite `-wal`/`-shm`，不再 open store；对不存在的工作区是幂等 no-op。

### 新增 — `[typescript]` extra + `.ts`/`.tsx` 零实体提示（#96）

与 `[java]` 看齐：`pipx install loomgraph[typescript]` 自动拉 `tree-sitter-typescript`。纯 TS 仓之前 `loomgraph index` 出 0 实体 + 通用警告（不告诉怎么修）；现在检测到 `.ts`/`.tsx` 会提示 `pipx install loomgraph[typescript]` + 在 `.codeindex.yaml` 的 languages 加 `typescript`。

注意：仍需写 `.codeindex.yaml languages: [typescript]`（codeindex graph-export 无自动检测 / `--languages` flag），extra + 提示只是让这条路可被发现（与 Java 同契约）。

## [0.14.1] - 2026-07-06

### 修复 — `loomgraph index` 现在真正用 pin 的 codeindex（#76）

`run_graph_export` 之前用裸 `codeindex` 走 PATH 查找，PATH 上的老 codeindex（如 pipx 装的 0.29.0）会**静默覆盖** venv 里 pin 的 `ai-codeindex>=0.32.0`。**0.14.0 的依赖升级方向对但没生效**——`loomgraph index` 实际还在跑老 parser，Java 调用图一直是断的（边源端 0% 解析），尽管 fix 版 codeindex 早已装在 venv 里。

现在改用 `[sys.executable, "-m", "codeindex.cli", ...]` 调 codeindex——在 loomgraph 自己的 venv python 下跑，与 pin 的依赖同环境，不再依赖 PATH。spring-petclinic 实测：边源端解析 0%→65%、orphan 81%→50%、coupling 0.0→0.62。

- **升级**：`pip install --upgrade loomgraph`（拉到 0.14.1）。
- **Java 客户**：升级后 `loomgraph index --clear .` 重建一次 workspace（旧索引仍是断的）。
- 若 `which codeindex` 指向非 loomgraph venv 的位置（如 pipx），本版本起不再依赖它，可不动。

## [0.14.0] - 2026-07-06

### 重要 — Java 调用图现在连通了（#76）

升级依赖 `ai-codeindex` → 0.32.0，修复 Java parser caller 命名错配（之前每条 Java 边源端悬空，`graph` / `topology` / `coupling` 在 Java 项目全报空，Python 正常）。spring-petclinic 实测：`graph` 0→9 callees、orphan 81%→49%、coupling 0.0→0.62。

- **升级**：`pip install --upgrade loomgraph`（自动拉 ai-codeindex 0.32.0）。
- **Java 客户**：升级后 `loomgraph index --clear .` 重建一次 workspace（旧边是断的）。
- 剩余 49% orphan = 非 callable 实体（field）+ Spring 框架调度入口 / 真静态不可解析（反射 / 多态），属 #76 P2 topology 可解释性的下一步，不影响连通性。

### 新增 — Java 开箱体验（#93）

- **新增 `loomgraph[java]` 可选 extras**：Java 仓库装 Java grammar 用 `pipx install loomgraph[java]`；纯 Python 项目不装，保持轻量。之前纯 Java 仓库 `loomgraph index` 会静默返回 0 实体（codeindex 默认只解析 Python）。
- **`loomgraph index` 对 0 实体不再静默成功**：`codeindex graph-export` 返回 0 实体时，打 stderr 警告 + JSON 返回 `data.warning` 字段（agent 可见）。检测到仓库含 `.java` 文件会提示 `pipx install loomgraph[java]` 并在 `.codeindex.yaml` 的 `languages` 加 `java`；否则提示检查 languages 配置。**仍是 exit 0**（空仓合法地索引为 0，不阻断 CI）。

### 修复 — 误报 "unknown entity_type" 警告（#76）

- loomgraph reader 之前对 codeindex 导出的 `field` / `constructor` / `property` 等实体类型（不在旧的 `{class, function, method}` 白名单里）逐条打 "unknown entity_type" 警告——**实体其实一直正常存图，只是日志噪音**。已把白名单对齐 codeindex 实际导出的 12 种类型，Java/TS 项目索引日志不再被这类误报刷屏。

## [0.13.0] - 2026-07-06

### Added — symbol-level 增量 + 本地 Ollama 默认（#90）

- **`update` 大幅省 embedding 成本**：改 1 个函数，旧版重 embed 整个文件所有 entity（50 函数文件 → 50 次调用）；新版按 codeindex `content_hash` 只重 embed 真正改动的 1 个 symbol（~50× 缩减）。依赖 `ai-codeindex >= 0.31.0`（`content_hash` 字段）。
- **LLM 默认改为本地 Ollama**：旧默认 GLM/H200 远程，H200 已于 2026-07 退役；现默认本地 `gemma3:12b-it-qat`（`http://localhost:11434`）。embedding 默认仍是 Ollama（`nomic-embed-text`）。
  - **⚠️ 升级注意**：如果你在 `.loomgraph.yaml` 显式配了 `llm.provider: glm` + H200 endpoint，需改为本地 Ollama 或其它可用 endpoint（H200 不可达）。**默认值变了，但你显式写的配置不受影响**——只有用默认 LLM 的部署才会从 H200 切到 Ollama。
  - 第三方 OpenAI-compatible endpoint（OpenAI / Voyage / GLM / vLLM / OpenRouter）仍可配，不受影响。
- **embedding 健壮性**：provider 过载返回 200-OK-but-empty 向量时自动跳过，不再污染 search 结果。

### Added — MCP `refresh` 主动刷新 + 存储跨进程写安全

- **首个 MCP 写 tool** `loomgraph_refresh`：agent 编辑文件后（含未提交、含 untracked 新文件）可主动触发重新索引，不必等 commit。与 commit-hook `update`（已提交变更）互补 —— push（开发者 commit）/ pull（agent 按需）双模式。参数：`path`（限定文件/目录）、`force_full`（全量冷重建）。详见 ADR-014。
- **存储并发硬化**：SQLite 转 WAL 模式 + 5s `busy_timeout`，MCP server（长驻进程）与 git-hook `update`（子进程）可并发写同一 `.db` 不再 `database is locked`。`close` 时 `wal_checkpoint` 保证打包的 `.db` 自洽。所有写路径（`update`/`index`/`import-export`）受益。
- **打包注意**：WAL 模式会在 `.db` 旁产生 `-wal`/`-shm` 边车文件；进程正常退出（graceful close）会 checkpoint（边车清空/删除），正常分发不受影响。若手动复制 `.db`，请确认进程已退出。

### ⚠️ Breaking — graph-export 迁移（#66）

`loomgraph index` / `update` 改为消费 `codeindex graph-export` NDJSON 契约：实体用 module-qualified id，边带 `resolution_qualifier` + 跨文件 callee 解析。**修复跨模块同名函数冲突**（旧版本 9 个 `handle` 会合并成 1 个幻影 god_function，out_degree 34）。

- **必须重建 workspace**：旧版本用简单名 key 索引的 workspace，升级后需 `loomgraph index --clear .` 一次，否则同名符号仍冲突。
- **`update` 改为 whole-tree re-export**（不再是 per-file warm 增量）：大仓库每次 `update` 会变慢。post-commit hook 建议 `LOOMGRAPH_HOOK_MODE=async` 或 `disabled`。warm-incremental 将由 content_hash diff 恢复（跟进项）。
- **移除**：`codeindex scan`/`parse` legacy 路径、死表 `vec_code_snippets`（从未写入；`search` 只读 `vec_node_descriptions`）、内部 helper `collect_kg_data`/`build_chunks`/`create_external_stubs`。
- `deps` 模块依赖图暂失 IMPORTS 边（codeindex graph-export 待加 IMPORTS edge —— #66 Phase A 跟进）；CALLS 推导的模块依赖边仍可用。
- 依赖：`ai-codeindex >= 0.28.0`（`signature` 字段）。

### ⚠️ Breaking — 移除 legacy programmatic API + embed/inject CLI（#77 收尾）

旧 `codeindex scan` 路径的残留全部清除（graph-export 契约已是唯一入口）：

- **移除 CLI**：`loomgraph embed` / `loomgraph inject`（旧分步管线；且 `embed` 自 EPIC-012 Jina→Direct 迁移后 import 即崩，已 broken 多版本）。`loomgraph index` 一键完成解析+向量化+注入；只为已索引 workspace 补向量用 `loomgraph embed-backfill`。
- **移除 Python API**：`loomgraph.index_file` / `index_repository` / `scan_code_files` / `inject_parse_result` 及 `loomgraph.core.mapper` / `indexer` / `injector` / `adapter` 模块。这些只服务于已删的 scan 路径，零内部调用。`loomgraph.__init__` public surface 收敛到 `Settings` / `get_settings` / `__version__`。
- **移除 models**：`Symbol` / `Call` / `Inheritance` / `Import` / `ParseResult` / `InjectResult` / `IndexResult`（legacy codeindex input types）。保留 `EntityData` / `RelationData` + analysis metrics。
- **客户影响**：CLI 用户只用 `index` / `update` / `search` / `find`，不受影响；programmatic API 此前未出现在客户文档。

### 恢复 — `update` per-file warm-diff（路 B, #66 收尾）

`loomgraph update` 恢复 per-file 增量（#66 期间临时降级为 whole-tree）：

- **git 仓库**：whole-tree `graph-export` 后，按 `git diff --since` 筛变更文件 → 只 re-embed/re-inject 变更部分 + GC 已删除符号（`delete_by_source` 按 source-id prefix）。命中 re-embed 成本（codeindex#110 点名的真正开销；parse 本身 ms 级）。
- **非 git 仓库 / `--files`**：fallback whole-tree upsert（`clear=False`，删除符号不 GC，需 `index --clear` 重建）。
- `--since` 重新生效（默认 `HEAD~1`）；`--use-affected` / `--embedding-url` 保留兼容但 inert。
- **粒度**：文件级；symbol-span（codeindex `content_hash`, #110 门控项）为后续 follow-up。

### 新增 — 语义搜索补齐

- **`loomgraph search "<意图>"`** —— 语义向量搜索，按含义/意图查实体（区别于按名称的 `find`）。需 `embedding.enabled: true` + 配置 provider。
- **`loomgraph embed-backfill [-w <ws>]`** —— 为已索引但无向量的 workspace 补向量，**不触发全量重建**。关键场景：`import-export` 导入的 workspace 本身不带向量，跑一次 backfill 即可被 `search` 命中。幂等（已有向量则跳过）。

### 升级指引

1. `pip install --upgrade loomgraph`（同时确保 `ai-codeindex >= 0.28.0`）。
2. **重建 workspace**：`loomgraph index --clear .`（旧简单名 key 数据必须清掉重建，否则 #66 修复不生效）。
3. 已开启 embedding：`search` / `embed-backfill` 直接可用；import-export workspace 跑 `loomgraph embed-backfill -w <workspace>` 启用语义搜索。

---

## [0.11.0] - 2026-06-25 — Embedding 默认本地 (Breaking)

### ⚠️ 主要变化

LoomGraph 现在**完全可本地跑**——pipx 装完不主动连接任何远端服务。
embedding 服务从 H200 Jina 解耦,改用 OpenAI-compatible 协议,user
自配 provider。

#### 默认行为变化

- `embedding.enabled: false` (默认) → 不调用任何 embedding API,vec0 列空
- 想要语义向量搜索 → 设 `enabled: true` + 配 provider

#### 配置示例 (`.loomgraph.yaml`)

**最小化(完全本地,不需要任何服务):**
```yaml
storage:
  backend: sqlite
embedding:
  enabled: false
```

**配本地 Ollama:**
```bash
# 先装 Ollama: https://ollama.com
ollama pull nomic-embed-text
```
```yaml
embedding:
  enabled: true
  provider: ollama
  api_url: http://localhost:11434/v1
  model: nomic-embed-text
  dimension: 768
```

**配 OpenAI:**
```yaml
embedding:
  enabled: true
  provider: openai
  api_url: https://api.openai.com/v1
  api_key: sk-...
  model: text-embedding-3-small
  dimension: 1536
```

#### 升级步骤

```bash
pipx install --upgrade loomgraph
# 旧的 .loomgraph.yaml 中 embedding.base_url 改为 api_url
# 旧的 provider: jina 改为 provider: ollama (本地默认)
loomgraph index --clear .   # 仅当切换了 dimension 才需要
```

#### Dimension 切换提示

如果换了 embedding 模型导致维度变化 (e.g., 768 → 1536),启动时会报
`SqliteDimensionMismatch`,按提示跑 `loomgraph index --clear .` 即可。

---

## [0.10.0] - 2026-06-25 — **Breaking Change**

### ⚠️ 重大变更

**LightRAG 后端将被替换为本地 SQLite + sqlite-vec**（EPIC-011 / ADR-013）。

#### 客户影响
- v0.10.0 起 LightRAG 后端不再官方支持（Phase 5 完成后），客户需 `loomgraph index --clear .` 重建知识图谱（Cold Rebuild）。
- 部署门槛降低：不再需要 LightRAG API service，单文件 `~/.loomgraph/<workspace>.db` 替代。
- 已部署客户可 pin `loomgraph==0.9.x` 暂缓升级；v0.9.x 不再接受 backport。

#### `loomgraph query` 已移除
自然语言代码问答让位给通用 agent（Claude Code / Codex / Cursor）。LoomGraph 现聚焦：
- `loomgraph find "<名称>"` — 结构化实体搜索
- `loomgraph graph "<实体>"` — 调用关系遍历
- `loomgraph topology` / `debt` / `impact` — 图谱分析

### 新增（Phase 1-4 已完成）
- SQLite + sqlite-vec 后端（可显式 `storage.backend=sqlite` 切换；Phase 5 翻为 default）
- 多 LLM provider 支持（GLM-4.7 / OpenRouter / vLLM）通过 `llm.provider` 配置
- vec0 向量 KNN 搜索（768 维 Jina Code V2 embedding）
- 跨后端 diff / benchmark 脚本

### 升级路径预告
v0.10.0 完整发布时（Phase 5），客户操作：
```bash
pipx install --upgrade ai-codeindex loomgraph
loomgraph index --clear .   # Cold rebuild
loomgraph find "<某类名>"   # 验证
```

---

## [0.9.3] - 2026-03-22

### 🚀 大代码库索引优化

**核心改进**：解决大型代码库（>5000 实体）索引时的超时问题，提升索引稳定性和用户体验。

#### 修复

- **索引超时问题**：动态计算超时时间（根据实体数量自动调整），大代码库不再因固定超时而失败
- **超时错误提示**：现在会明确建议调大 `api_timeout` 配置

#### 改进

- **自动分批上传**：超过 5000 个实体时自动拆分为多次上传，每批独立完成，避免单次请求过大
- **索引进度显示**：现在会实时显示：
  - 文件收集进度（每 100 个文件更新一次）
  - 上传实体/关系/chunks 总数
  - 分批上传进度（Batch 1/3, 2/3...）

#### 升级方式

```bash
source ~/.loomgraph-venv/bin/activate
pip install --upgrade loomgraph
loomgraph version  # 应显示 0.9.3
```

---

## [0.9.2] - 2026-03-08

### 🎯 评分准确性大幅提升

**核心改进**：修复了技术债务评分系统中的公式失衡问题，显著提升分析准确性。

#### 修复

- **评分公式修正**：从单维度改为多维度加权评分
  - 修复前：Quality 97/100 + Maintainability 97/100 → 总分 50/100 (F) 的矛盾
  - 修复后：综合评分 = 代码质量(40%) + 可维护性(30%) + 拓扑健康(30%)
  - 准确性：从 ~60% 提升到 ~90%+

- **上帝函数误报优化**：智能区分「领域复杂度」和「技术债务」
  - Parser/Generator/CLI 等领域固有复杂度自动降级为 P1 (Warning)
  - 只有真正的业务逻辑过度复杂才标记为 P0 (Critical)
  - 示例：26 个 giant functions → 4 个 P0（需重构）+ 22 个 P1（领域正常）

#### 升级方式

```bash
source ~/.loomgraph-venv/bin/activate
pip install --upgrade loomgraph
loomgraph version  # 应显示 0.9.2
```

#### 使用示例

```bash
# 运行债务分析，查看改进后的评分
loomgraph debt --codeindex-data /tmp/debt-report.json

# 查看多维度评分明细
# breakdown: { quality: 84, maintainability: 97, topology: 75 }
```

---

## [0.9.0] - 2026-03-07

### 🎉 重大更新：技术债务预警系统

**核心价值**：将代码健康度从静态评估升级为动态趋势预测，像体检系统一样监控代码健康度变化，提前预警技术债务恶化。

#### 新增功能

**1. Git 历史度量分析**
- **热点检测**：基于变更频率 × 代码量，定位最容易出问题的文件
- **总线因子分析**：识别知识孤岛风险（如某文件只有 1 人维护）
- **缺陷率统计**：计算 bug fix 占比，识别质量脆弱点
- **命令**：`loomgraph git-metrics [path] --since "3 months"`

**2. 三维度债务评分**
- 在原有静态分析基础上，新增**代码历史维度**
- 综合评分 = (代码质量 + 拓扑健康 + Git 度量) / 3
- 自动识别 7 大类债务问题：
  - 超大文件（>5000 行）
  - 上帝类（>50 方法）
  - 高频热点（经常被改的文件）
  - 知识孤岛（只有 1-2 人维护）
  - 缺陷磁铁（bug fix 比例 >30%）
- **命令**：`loomgraph debt --with-git`

**3. 代码腐化趋势分析**
- **线性回归预测**：基于历史快照预测未来 1 个月的复杂度变化
- **自动快照保存**：每次运行 `loomgraph debt` 自动保存度量数据（存储在 `~/.loomgraph/metrics-history/`）
- **ASCII 趋势图**：可视化复杂度、耦合度等指标的演化趋势
- **自动预警**：当月增长率 >15% 时发出警报
- **命令**：`loomgraph trends --entity "src/auth/user.py" --metric complexity --months 6`

#### 升级方式

**已有客户**（收到 upgrade 包）：
```bash
tar xzf loomgraph-upgrade-{customer}-v0.9.0.tar.gz
cd loomgraph-upgrade-{customer}-v0.9.0
./upgrade.sh

# 重启 Claude Code 后新功能自动可用
```

**手动升级**（在线安装）：
```bash
source ~/.loomgraph-venv/bin/activate
pip install --upgrade loomgraph
loomgraph install-skills
loomgraph version  # 应显示 0.9.0
```

#### 使用示例

**场景 1：发现质量热点**
```bash
# 分析最近 3 个月的 Git 历史
loomgraph git-metrics . --since "3 months"

# 输出示例：
# 热点文件 TOP 3:
#   1. src/auth/user_service.py - 45 次提交，2300 行，热点分数 87/100
#   2. src/api/handlers.py - 38 次提交，1800 行，热点分数 76/100
#
# 总线因子风险:
#   src/core/config.py - 唯一维护者：张三（100% 提交），风险等级：critical
```

**场景 2：全面债务评估（推荐）**
```bash
# 启用 Git 维度分析（首次运行可能需要 2-3 秒解析 git log）
loomgraph debt --with-git

# 自动检测 7 大类问题，综合评分更准确
```

**场景 3：趋势预测（需要先积累历史数据）**
```bash
# Step 1: 多次运行 debt 命令积累快照（建议每周运行一次，持续 1-2 个月）
loomgraph debt --with-git

# Step 2: 分析趋势（需要至少 3 次快照）
loomgraph trends --entity "src/auth/user_service.py" --metric complexity --months 6

# 输出示例：
# Trend: INCREASING
# Slope: +3.00/month (+0.100/day), R²: 0.950
#
# ⚠️ Rapid complexity growth detected: +25.0% projected in next month.
# Current: 45, Forecast: 56. Consider refactoring to prevent further deterioration.
```

#### 性能优化

- Git 度量分析（3 个月历史）：**< 3 秒**（LoomGraph 项目，203 个文件，1387 次提交）
- 趋势分析（6 个月数据）：**< 1 秒**（10+ 快照）
- 启用 `--with-git` 对 `debt` 命令影响：**几乎无感知**（+0.5 秒）

#### 版本对比

| 功能 | v0.7.0 | v0.9.0 |
|------|--------|--------|
| 静态代码质量分析 | ✅ | ✅ |
| 拓扑健康度分析 | ✅ | ✅ |
| Git 历史度量 | ❌ | ✅ |
| 三维度综合评分 | ❌ | ✅ |
| 趋势预测 | ❌ | ✅ |
| 自动预警 | ❌ | ✅ |

#### 最佳实践

1. **首次使用**：先运行 `loomgraph git-metrics .` 了解代码库历史健康度
2. **定期监控**：每周运行一次 `loomgraph debt --with-git`（自动保存快照）
3. **趋势分析**：积累 3+ 次快照后，使用 `loomgraph trends` 观察演化趋势
4. **集成 CI**：在 CI 流程中运行，设置评分阈值（如 <60 分则构建失败）

---

## [0.7.0] - 2026-02-22

### 🎉 重大更新：自动化增量更新

**核心价值**：知识图谱自动与代码保持同步，零人工干预。

#### 新增功能

**1. GitHub Action 自动更新**（CI/CD 集成）
- 代码推送后自动更新知识图谱
- 智能检测变更（仅更新修改的文件）
- 适用场景：团队协作、自动化部署

**2. Git Post-commit Hook**（本地开发）
- 提交代码后自动更新
- 4 种模式可选：
  - `auto`（默认）：≤3 文件同步更新，>3 文件后台更新
  - `sync`：总是同步更新（适合调试）
  - `async`：总是后台更新（适合大改动）
  - `disabled`：关闭自动更新

**3. 一键安装/升级**
- `quickstart.sh`：新客户一键安装（包含全部依赖）
- `upgrade.sh`：老客户一键升级（自动备份配置）

**4. 搜索体系增强**
- `loomgraph find "<实体名>"` - 结构化实体发现，替代原 `search` 命令
- `loomgraph query "<问题>"` - 语义知识问答（例："认证流程怎么工作的？"）
- `loomgraph graph` 结果新增 `source_id` 字段（显示文件路径）

**5. 技术债务分析增强**
- `loomgraph topology` - 图谱拓扑分析（孤立实体、Hub 脆弱性、God 函数、耦合密度）
- `loomgraph check` - 索引新鲜度检查（验证图谱是否过期）
- `/loomgraph-debt-radar` Skill 升级到 7 维度分析

#### 升级方式

**首次安装客户**（收到 demo 包）：
```bash
tar xzf loomgraph-demo-{customer}-v0.8.0.tar.gz
cd loomgraph-demo-{customer}-v0.8.0
./quickstart.sh

# 然后在 Claude Code 中执行：
# /loomgraph-setup
# loomgraph index .
```

**已有客户**（收到 upgrade 包）：
```bash
tar xzf loomgraph-upgrade-{customer}-v0.8.0.tar.gz
cd loomgraph-upgrade-{customer}-v0.8.0
./upgrade.sh

# 重启 Claude Code 后新功能自动可用
```

**手动升级**（在线安装）：
```bash
source ~/.loomgraph-venv/bin/activate
pip install --upgrade loomgraph
loomgraph install-skills
loomgraph version  # 应显示 0.7.0
```

#### 使用示例

**安装 Git Hook（本地开发推荐）**：
```bash
loomgraph hooks install
# 之后每次 git commit 会自动更新知识图谱
```

**语义搜索**：
```bash
# 结构化搜索
loomgraph find "UserService" --with-relations

# 语义问答
loomgraph query "用户认证的流程是什么？"
```

**技术债务分析**：
```bash
# 拓扑分析
loomgraph topology

# 索引新鲜度检查
loomgraph check
```

#### 版本对比

| 功能 | v0.6.1 | v0.8.0 |
|------|--------|--------|
| 手动更新 | ✅ | ✅ |
| GitHub Action 自动更新 | ❌ | ✅ |
| Git Hook 自动更新 | ❌ | ✅ |
| 一键安装/升级 | ❌ | ✅ |
| 语义问答 | ❌ | ✅ |
| 拓扑分析 | ❌ | ✅ |

---

## [0.6.1] - 2026-02-21

### 改进
- 注入性能提升 636 倍：`loomgraph index` 和 `loomgraph update` 从 ~350 秒降至 <1 秒
- `loomgraph update` 现在是真正的增量更新（先删旧数据，再注入新数据），不再产生重复实体
- Cold Rebuild (`loomgraph index --clear`) 简化为单次清理操作

### 更新方式
```bash
source ~/.loomgraph-venv/bin/activate
pip install ./loomgraph-*.whl
loomgraph install-skills
loomgraph version  # 应显示 0.6.1
```

---

## [0.6.0] - 2026-02-20

### 新增
- `loomgraph workspace list` - 列出所有 workspace 及实体/关系数量
- `loomgraph workspace info [NAME]` - 查看 workspace 详情（默认自动检测当前目录）
- `loomgraph workspace delete NAME --yes` - 删除指定 workspace 及其全部数据
- `loomgraph compare --ws1 A --ws2 B` - 跨 workspace 结构对比（新增/删除实体、关系变化）
- `loomgraph similar -e "<entity>"` - 跨 workspace 相似实体检测（精确匹配 + 模糊匹配）
- `/loomgraph-debt-radar` Skill - 技术债务审计报告（需 Claude Code 执行）
- `/loomgraph-sync-advisor` Skill - 跨分支同步建议 + 冲突预测（需 Claude Code 执行）
- `/loomgraph-evolution` Skill - 代码演化趋势分析（需 Claude Code 执行）

### 使用示例
```bash
# Workspace 管理
loomgraph workspace list
loomgraph workspace info customer-backend

# 跨分支对比（需先为不同分支建立 workspace）
loomgraph compare --ws1 customer-backend-main --ws2 customer-backend-feature

# 查找相似实体
loomgraph similar -e "AuthService"

# Skills（在 Claude Code 中执行）
# /loomgraph-debt-radar
# /loomgraph-sync-advisor --ws1 main --ws2 feature-branch
# /loomgraph-evolution --entity AuthService
```

### 更新方式
```bash
cd /path/to/loomgraph-package
source ~/.loomgraph-venv/bin/activate
pip install ./loomgraph-*.whl
loomgraph install-skills  # 更新 Skills
loomgraph version  # 应显示 0.6.0
```

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
| 0.6.1 | 注入性能 636x 提升 + 真增量更新 | **推荐** - 索引速度大幅提升 |
| 0.6.0 | workspace 管理 + 跨 workspace 对比 + 3 个分析 Skills | **强烈推荐** - 全新分析能力 |
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
