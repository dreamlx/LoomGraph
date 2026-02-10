---
name: loomgraph-setup
description: Configure LoomGraph for the current project - detect language, install parser, generate .codeindex.yaml
disable-model-invocation: true
argument-hint: "[--force]"
---

## LoomGraph 项目配置向导

在执行 `loomgraph index .` 之前，需要先配置 codeindex。此 skill 将引导你完成配置。

### Step 0: 版本检查

**检查当前安装的 LoomGraph 版本：**
```bash
~/.loomgraph-venv/bin/loomgraph version 2>/dev/null || echo '{"error": "loomgraph not installed or version < 0.2.1"}'
```

**查看最新版本和变更日志：**
- 最新版本文件：安装包目录下的 `customers/VERSION`
- 变更日志：安装包目录下的 `customers/CHANGELOG.md`

**版本对比：**
| 当前版本 | 最新版本 | 建议操作 |
|----------|----------|----------|
| < 0.2.1 | 0.2.1 | 需要更新（支持增量索引） |
| = 0.2.1 | 0.2.1 | 已是最新 |

**如需更新：**
```bash
cd /path/to/loomgraph-package  # 安装包所在目录
source ~/.loomgraph-venv/bin/activate
pip install .
```

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

### Step 2: 安装语言解析器

根据检测到的语言，安装对应的 tree-sitter 解析器：

```bash
# Java 项目
source ~/.loomgraph-venv/bin/activate
pip install ai-codeindex[java]

# PHP 项目
pip install ai-codeindex[php]

# Python 项目
pip install ai-codeindex[python]

# 多语言项目
pip install ai-codeindex[java,python]

# 所有语言
pip install ai-codeindex[all]
```

**验证安装：**
```bash
codeindex --version
```

### Step 3: 确定源码目录

询问用户或检测项目结构：

**常见的源码目录：**
- Java Maven/Gradle: `src/main/java/`
- PHP Laravel: `app/`
- Python: `src/` 或项目名目录

**执行检测：**
```bash
# 查看项目结构
ls -d */ 2>/dev/null | head -10
```

### Step 4: 生成 .codeindex.yaml

根据检测结果，在项目根目录创建 `.codeindex.yaml`：

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

**Python 项目模板：**
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

### Step 5: 验证配置

```bash
# 检查配置文件
cat .codeindex.yaml

# 预览扫描范围（不实际执行）
codeindex scan . --dry-run 2>&1 | head -20
```

### Step 6: 完成提示

配置完成后，提示用户：

1. 执行 `/loomgraph-init` 配置项目 CLAUDE.md
2. 执行 `loomgraph index .` 开始索引

---

## 问答流程

如果无法自动检测，向用户提问：

**问题 1：项目主要语言是什么？**
- Java
- PHP
- Python
- 多语言（请说明）

**问题 2：源码目录在哪里？**
- 默认检测到的目录
- 自定义路径

**问题 3：是否有特殊的排除目录？**
- 使用默认排除规则
- 添加自定义排除规则

---

## 注意事项

1. **大型项目**：建议设置 `symbols.project_symbols.enabled: false`
2. **多模块项目**：每个模块可以有自己的 `.codeindex.yaml`
3. **首次索引慢**：正常现象，后续增量索引会快很多
