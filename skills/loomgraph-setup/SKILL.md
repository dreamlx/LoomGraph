---
name: loomgraph-setup
description: Configure LoomGraph for the current project - detect language, install parser, generate .codeindex.yaml
disable-model-invocation: true
argument-hint: "[--force]"
---

## LoomGraph 项目配置向导

在执行 `loomgraph index .` 之前，需要先配置 codeindex。此 skill 将引导你完成配置。

> v0.16+: LoomGraph 走公开 PyPI（`pipx install loomgraph`），codeindex 作为依赖自动安装，默认零配置（本地 SQLite，无远程服务）。本向导只需检测语言 + 生成 `.codeindex.yaml`。

### Step 0: 版本检查

**检查当前安装的 LoomGraph 版本：**
```bash
loomgraph version 2>/dev/null || echo '{"error": "loomgraph not installed"}'
```

**如果未安装或需要更新：**
```bash
# 安装（公开 PyPI）
pipx install loomgraph

# 更新
pipx install --upgrade loomgraph
```

> 没有 pipx？`python3 -m pip install --user pipx && python3 -m pipx ensurepath`

---

### Step 1: 检测项目语言

检查项目根目录，确定主要语言：

| 文件 | 语言 |
|------|------|
| `pom.xml` 或 `build.gradle` | Java |
| `composer.json` | PHP |
| `pyproject.toml` 或 `requirements.txt` | Python |
| `package.json` | JavaScript/TypeScript |

**执行检测：**
```bash
ls -la pom.xml build.gradle composer.json pyproject.toml requirements.txt package.json 2>/dev/null
```

### Step 2: 安装语言解析器（按需）

Python 项目跳过此步（解析器默认包含）。Java / TypeScript 需要对应 tree-sitter extra：

```bash
# Java 项目
pipx install --force loomgraph[java]

# TypeScript 项目
pipx install --force loomgraph[typescript]
```

> `--force` 让 pipx 在已装的 loomgraph 上重装带 extra。codeindex（parser engine）是 loomgraph 依赖，自动安装，无需用户直接操作。

**验证安装：**
```bash
codeindex --version
```

### Step 3: 确定源码目录

询问用户或检测项目结构：

**常见的源码目录：**
- Java Maven/Gradle: `src/main/java/`
- PHP Laravel: `app/`
- Python: `src/` 或项目名目录，或 flat layout（`main.py` 在根目录）

**执行检测：**
```bash
# 查看项目结构
ls -d */ 2>/dev/null | head -10
```

### Step 4: 生成 .codeindex.yaml

根据检测结果，在项目根目录创建 `.codeindex.yaml`。

> **flat layout 检测（#114 问题 3）**：Python 项目若根目录直接有 `*.py` 且无 `src/` 目录（如 `main.py` 在 repo root），必须用 `include: ["."]`。若误用 `include: [src/]` 或 `include: ["*.py"]`，`codeindex graph-export` 会返回 0 entities 导致索引静默清空。
>
> 检测方式：
> ```bash
> ls *.py 2>/dev/null && [ ! -d src ] && echo "FLAT LAYOUT: use include: [\".\"]"
> ```

**Java 项目模板：**
```yaml
codeindex: 1

include:
  - src/main/java/

exclude:
  - "**/target/**"
  - "**/build/**"
  - "**/.git/**"
  - "**/*.class"
  - "**/test/**"

languages:
  - java

parallel_workers: 8
batch_size: 50

symbols:
  project_symbols:
    enabled: false  # 大项目建议关闭
```

**PHP 项目模板：**
```yaml
codeindex: 1

include:
  - app/
  - src/

exclude:
  - "**/vendor/**"
  - "**/.git/**"
  - "**/storage/**"
  - "**/cache/**"

languages:
  - php

parallel_workers: 8
batch_size: 50
```

**Python 项目模板（src/ layout）：**
```yaml
codeindex: 1

include:
  - src/

exclude:
  - "**/__pycache__/**"
  - "**/.git/**"
  - "**/venv/**"
  - "**/.venv/**"
  - "**/test/**"
  - "**/tests/**"

languages:
  - python

parallel_workers: 8
batch_size: 50
```

**Python 项目模板（flat layout — 根目录有 `*.py`，无 `src/`）：**
```yaml
codeindex: 1

include:
  - "."

exclude:
  - "**/__pycache__/**"
  - "**/.git/**"
  - "**/venv/**"
  - "**/.venv/**"
  - "**/test/**"
  - "**/tests/**"

languages:
  - python

parallel_workers: 8
batch_size: 50
```

### Step 5: 验证配置

```bash
# 检查配置文件
cat .codeindex.yaml

# 预览扫描范围（不实际执行）
codeindex scan . --dry-run 2>&1 | head -20
```

### Step 6: 完成提示

配置完成后，提示用户：

1. 执行 `/loomgraph-init` 配置项目 CLAUDE.md（Claude Code 用户）
2. 执行 `loomgraph index .` 开始索引

> 语义搜索（`loomgraph search`）默认关闭，需在 `.loomgraph.yaml` 配 `embedding.enabled: true` + provider（Ollama/OpenAI/Voyage）。结构化命令（`find`/`graph`/`topology`）无需 embedding。

---

## 问答流程

如果无法自动检测，向用户提问：

**问题 1：项目主要语言是什么？**
- Java
- PHP
- Python
- TypeScript
- 多语言（请说明）

**问题 2：源码目录在哪里？**
- 默认检测到的目录
- 自定义路径
- flat layout（根目录 `*.py`）

**问题 3：是否有特殊的排除目录？**
- 使用默认排除规则
- 添加自定义排除规则

---

## 注意事项

1. **大型项目**：建议设置 `symbols.project_symbols.enabled: false`
2. **多模块项目**：每个模块可以有自己的 `.codeindex.yaml`
3. **首次索引慢**：正常现象，后续增量索引会快很多
4. **零配置可用**：默认本地 SQLite，无需 LightRAG/Postgres/远程服务（v0.11+ 起 LightRAG 已移除）。`loomgraph setup-config` 已 deprecated，仅在需要手写 config stub 时使用。
