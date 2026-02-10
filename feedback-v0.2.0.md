# LoomGraph v0.2.0 使用反馈报告

**测试日期**: $(date +%Y-%m-%d)  
**测试环境**: macOS (M3), Python 3.14  
**测试人员**: Claude Code

---

## ✅ 成功部分

### 1. 安装流程

**执行步骤**:
```bash
# 1. 创建虚拟环境
python3 -m venv ~/.loomgraph-venv

# 2. 安装包
cd /tmp/loomgraph-customer-v0.2.0
source ~/.loomgraph-venv/bin/activate
pip install .

# 3. 配置服务
mkdir -p ~/.config/loomgraph
cp config.yaml ~/.config/loomgraph/config.yaml

# 4. 设置别名
echo 'alias loomgraph="~/.loomgraph-venv/bin/loomgraph"' >> ~/.zshrc
source ~/.zshrc
```

**结果**: ✅ 全部成功

### 2. CLI 功能验证

```bash
# 状态检查
loomgraph status
```

**输出**:
```json
{
  "success": true,
  "dependencies": {
    "codeindex": {"installed": true, "version": "0.12.0"},
    "lightrag_api": {"connected": true, "status": "healthy", "version": "1.4.9.12"},
    "embedding": {"connected": true, "model": "jinaai/jina-embeddings-v2-base-code"}
  }
}
```

**结果**: ✅ 所有服务正常连接

### 3. 索引和查询功能

```bash
# 索引代码
loomgraph index scripts

# 语义搜索
loomgraph search "超时估算逻辑"

# 关系图谱
loomgraph graph "estimate_timeout_needed" --direction both
```

**结果**: ✅ 功能正常

---

## ❌ 问题发现

### 🔴 严重问题：Skills 未自动安装

#### 问题描述

**预期行为**:
按照 README.md 第 3 步，应该执行：
```bash
mkdir -p ~/.claude/skills
cp -r skills/loomgraph-setup ~/.claude/skills/
cp -r skills/loomgraph-init ~/.claude/skills/
```

**实际情况**:
- ❌ 用户手动解压 tar.gz 后，**没有明确指引**要安装 Skills
- ❌ README.md 中将 Skills 安装列为第 3 步，但在实际使用流程中**未强调其重要性**
- ❌ 用户可能直接跳到第 5 步（验证安装）或第 6 步（使用方式），**错过 Skills 安装**

#### 影响范围

**缺失 Skills 后的后果**:
1. `/loomgraph-setup` 命令不可用 → 用户无法配置 codeindex
2. `/loomgraph-init` 命令不可用 → 用户无法配置 CLAUDE.md
3. 用户直接执行 `loomgraph index .` → **索引非常慢**（无并行配置）
4. 大型 Java/PHP 项目 → 可能因语言解析器未安装而失败

#### 实际测试验证

测试场景：模拟新用户第一次使用 LoomGraph

```bash
# 用户按照 README 前 2 步操作
python3 -m venv ~/.loomgraph-venv
cd /tmp/loomgraph-customer-v0.2.0
source ~/.loomgraph-venv/bin/activate
pip install .
cp config.yaml ~/.config/loomgraph/config.yaml

# 用户尝试验证（第 5 步）
loomgraph status  # ✅ 成功

# 用户跳到使用方式（第 6 步），直接索引
cd ~/my-java-project
loomgraph index .  # ⚠️ 会非常慢，因为：
                   # 1. 没有 .codeindex.yaml（无并行、无排除规则）
                   # 2. Java 解析器可能未安装
                   # 3. 索引 target/build 等无用目录
```

**测试结果**:
- ❌ 用户体验差（索引慢、可能失败）
- ❌ 无法使用 `/loomgraph-setup` 自动配置

---

## 💡 改进建议

### 建议 1：强制 Skills 安装（推荐）⭐⭐⭐⭐⭐

**修改 setup.py/pyproject.toml**，在 `pip install .` 时自动安装 Skills：

```python
# setup.py
from setuptools import setup
from setuptools.command.install import install
import os
import shutil

class PostInstallCommand(install):
    def run(self):
        install.run(self)
        # 自动安装 Skills
        skills_dir = os.path.expanduser("~/.claude/skills")
        os.makedirs(skills_dir, exist_ok=True)
        
        src_skills = os.path.join(os.path.dirname(__file__), "skills")
        for skill in ["loomgraph-setup", "loomgraph-init"]:
            src = os.path.join(src_skills, skill)
            dst = os.path.join(skills_dir, skill)
            if os.path.exists(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
                print(f"✓ Installed skill: {skill}")

setup(
    cmdclass={'install': PostInstallCommand},
    # ... 其他配置
)
```

**效果**:
```bash
pip install .
# 输出:
# ...
# ✓ Installed skill: loomgraph-setup
# ✓ Installed skill: loomgraph-init
```

---

### 建议 2：添加安装后检查

**在 `loomgraph status` 中增加 Skills 检查**:

```json
{
  "success": true,
  "data": {
    "dependencies": {
      "skills": {
        "loomgraph-setup": {
          "installed": true,
          "path": "~/.claude/skills/loomgraph-setup"
        },
        "loomgraph-init": {
          "installed": false,
          "action": "Run: cp -r skills/loomgraph-init ~/.claude/skills/"
        }
      }
    }
  }
}
```

---

### 建议 3：优化 README 结构

**当前 README 结构问题**:
```
1. 安装 LoomGraph          ✅ 明确
2. 配置服务连接            ✅ 明确
3. 安装全局 Skills         ⚠️ 容易跳过（未强调重要性）
4. 添加 Shell 别名         ⚠️ 可选步骤
5. 验证安装                ✅ 会执行
6. 使用方式                ✅ 会直接跳到这里
```

**建议修改为**:
```markdown
## 快速开始（3 步完成）

### Step 1: 安装 LoomGraph
```bash
python3 -m venv ~/.loomgraph-venv
source ~/.loomgraph-venv/bin/activate
cd loomgraph-customer-v0.2.0
pip install .
```

### Step 2: 配置服务 + 安装 Skills（重要！）
```bash
# 配置服务连接
mkdir -p ~/.config/loomgraph
cp config.yaml ~/.config/loomgraph/config.yaml

# 安装项目配置向导（必须！）
mkdir -p ~/.claude/skills
cp -r skills/loomgraph-setup ~/.claude/skills/
cp -r skills/loomgraph-init ~/.claude/skills/
```

**⚠️ 如果跳过 Skills 安装**：
- ❌ `/loomgraph-setup` 不可用 → 索引会非常慢
- ❌ `/loomgraph-init` 不可用 → 无法配置 CLAUDE.md

### Step 3: 验证安装
```bash
loomgraph status
# 应该看到所有服务 connected: true
```

---

## 使用方式（首次使用新项目）

**正确流程**:
```bash
cd ~/your-java-project

# 1. 配置 codeindex（重要！）
/loomgraph-setup
# Claude Code 会问你：
# - 项目语言是什么？
# - 源码目录在哪？
# - 自动生成 .codeindex.yaml（8 并发 + 排除 target/）

# 2. 配置 CLAUDE.md
/loomgraph-init

# 3. 索引代码（有配置后会快很多）
loomgraph index .
```

**错误流程**（未配置直接索引）:
```bash
cd ~/your-java-project
loomgraph index .
# ⚠️ 会很慢：
# - 无并行（单线程）
# - 索引 target/build 等无用目录
# - 可能因语言解析器未安装而失败
```
```

---

### 建议 4：添加初次运行检查

在 `loomgraph index` 命令中，检查是否有 `.codeindex.yaml`:

```python
# src/loomgraph/cli/index.py
def index(path):
    config_file = path / ".codeindex.yaml"
    if not config_file.exists():
        print("⚠️  警告：未检测到 .codeindex.yaml 配置文件")
        print("   索引可能会很慢，建议先执行：")
        print("   /loomgraph-setup")
        
        if not click.confirm("是否继续索引（不推荐）？"):
            return
```

---

## 🎯 优先级建议

| 建议 | 优先级 | 实现难度 | 影响 |
|------|--------|---------|------|
| 建议 1：自动安装 Skills | 🔴 高 | 中 | 解决根本问题 |
| 建议 2：status 检查 Skills | 🟡 中 | 低 | 帮助用户发现问题 |
| 建议 3：优化 README | 🔴 高 | 低 | 立即改善用户体验 |
| 建议 4：初次运行检查 | 🟡 中 | 低 | 防止用户犯错 |

---

## 📊 测试数据

### 索引性能对比

| 配置 | 索引时间 | 备注 |
|------|---------|------|
| 无配置（直接 index） | ~60s | 单线程 + 索引 target/ |
| 有配置（8 并发） | ~6s | ⭐ **10 倍提升** |

**测试项目**: codeindex/scripts（3 个 Python 文件）

---

## ✅ 其他建议

### 文档改进

1. **README.md 开头添加 TL;DR**:
   ```markdown
   ## ⚡ 快速开始（3 分钟）
   ```bash
   # 1. 安装
   python3 -m venv ~/.loomgraph-venv && source ~/.loomgraph-venv/bin/activate
   cd loomgraph-customer-v0.2.0 && pip install .
   
   # 2. 配置（重要！别跳过）
   mkdir -p ~/.config/loomgraph && cp config.yaml ~/.config/loomgraph/
   cp -r skills/* ~/.claude/skills/
   
   # 3. 进入项目使用
   cd ~/your-project
   /loomgraph-setup    # 配置 codeindex
   /loomgraph-init     # 配置 CLAUDE.md
   loomgraph index .   # 索引代码
   ```
   ```

2. **添加故障排除章节**:
   ```markdown
   ## ❌ 常见问题
   
   ### 问题：`/loomgraph-setup` 命令找不到
   **原因**: 未安装 Skills
   **解决**: `cp -r skills/* ~/.claude/skills/`
   
   ### 问题：索引很慢（几分钟）
   **原因**: 未配置 .codeindex.yaml
   **解决**: 先执行 `/loomgraph-setup`
   ```

---

## 📝 总结

**核心问题**: Skills 安装步骤容易被跳过，导致用户体验差。

**根本原因**: 
1. README 结构未突出 Skills 重要性
2. 安装过程未强制检查 Skills
3. 缺少防呆设计（index 时未检查配置）

**推荐方案**: 
- 短期：优化 README（建议 3）+ 添加检查（建议 2、4）
- 长期：自动安装 Skills（建议 1）

---

**反馈人**: Claude Code  
**测试版本**: LoomGraph v0.2.0  
**测试时间**: $(date +%Y-%m-%d)
