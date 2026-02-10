# DISCUSSION-001: 客户专属安装包设计

**状态**: 已确认
**创建日期**: 2025-02-08
**参与者**: DreamLinx, Claude

---

## 背景

LoomGraph 作为私有项目，需要分发给多个客户。目前已有两个客户：

| 客户 | LightRAG 端口 | URL |
|------|--------------|-----|
| 拼便宜 | 3010 | http://internal.example.invalid:3010 |
| 智采云链 | 3020 | http://internal.example.invalid:3020 |

每个客户的 Claude Code 需要能够自动完成安装和配置。

---

## 确认的 User Story

### 角色

| 角色 | 说明 |
|------|------|
| 我们 | LoomGraph 开发者，打包分发 |
| 客户 Claude Code | 读取文档，自动执行安装配置 |
| 客户（人） | 在自己项目中使用 LoomGraph |

### 阶段 1: 我们打包分发（一次）

```bash
python scripts/package.py --customer customer
# → dist/loomgraph-customer-v0.1.0.tar.gz
```

包内容：
```
loomgraph-customer-v0.1.0/
├── README.md                    # 安装指南（Claude 读这个）
├── src/loomgraph/               # 源码
├── pyproject.toml               # 安装配置
├── config.yaml                  # 客户专属 LightRAG URL
└── skills/
    └── loomgraph-init/
        └── SKILL.md             # 全局 skill
```

### 阶段 2: 客户首次安装（一次性）

客户解压后，Claude Code 读取 README.md 自动执行：

```bash
# 1. 安装 loomgraph
pip install .

# 2. 复制客户专属配置
mkdir -p ~/.config/loomgraph
cp config.yaml ~/.config/loomgraph/config.yaml

# 3. 安装全局 skill
cp -r skills/loomgraph-init ~/.claude/skills/

# 4. 验证
loomgraph status
```

### 阶段 3: 客户在新项目中初始化（每项目一次）

```bash
cd /path/to/customer/project
/loomgraph-init      # 配置项目 CLAUDE.md
loomgraph index .    # 索引代码库
```

### 阶段 4: 日常使用

```bash
loomgraph search "用户认证逻辑"
loomgraph graph "AuthService.login" --direction callers
```

### 流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                        我们（开发者）                            │
│  python scripts/package.py --customer customer                      │
│  → 生成 loomgraph-customer-v0.1.0.tar.gz → 发送给客户                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 客户首次安装（Claude Code 执行）                  │
│  1. pip install .                                               │
│  2. cp config.yaml ~/.config/loomgraph/                         │
│  3. cp -r skills/loomgraph-init ~/.claude/skills/               │
│  4. loomgraph status ✓                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 客户新项目初始化（每项目一次）                    │
│  /loomgraph-init    → 配置项目 CLAUDE.md                        │
│  loomgraph index .  → 索引代码库                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        日常使用                                  │
│  loomgraph search "xxx"     → 语义搜索                          │
│  loomgraph graph "A.b"      → 调用关系                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 问题分析

### 模拟用户流程发现的问题

| # | 问题 | 验证结果 | 状态 |
|---|------|----------|------|
| 1 | `pip install .` 在 macOS 失败 (PEP 668) | 需要 uv 或虚拟环境 | 待讨论 |
| 2 | 默认 LightRAG URL 是 `:3001` | 需要客户专属配置 | 待解决 |
| 3 | 客户 Claude 不知道包解压位置 | 需要 README 说明 | 待解决 |
| 4 | 索引时大量 warning 输出 | 跨文件依赖，预期行为 | 仅需文档说明 |
| 5 | 不支持单文件索引 | codeindex 已支持 parse，CLI 未暴露 | 非 P0 |

---

## 问题 1 讨论：安装方式

### 现状
- README 写的是 `pip install .`
- macOS 默认 Python 禁止全局安装
- 项目用 `uv` 管理，没有 pip

### 用户观点
> 安装脚本 install.sh: 兼容 pip/uv，处理虚拟环境 这个问题，你能解决，就是说明其他客户的 claude code 也能解决

### 结论
**不需要 install.sh**。Claude Code 有足够智能处理安装问题：
- 遇到 PEP 668 错误 → 知道用 `uv` 或创建虚拟环境
- 遇到 pip 不存在 → 知道用 `python -m pip` 或 `uv pip`

只需 README 提供清晰的安装说明和故障排除指南。

---

## 问题 2 解决方案：客户专属配置

### 方案 A: 预配置 config.yaml

在包中包含客户专属配置文件：

```
loomgraph-customer/
├── README.md
├── loomgraph-*.whl
└── config.yaml  # 预配置 LightRAG URL
```

**config.yaml (智采云链版)**:
```yaml
lightrag:
  api_url: "http://internal.example.invalid:3020"

embedding:
  base_url: "http://internal.example.invalid:3002"
```

README 说明：
```bash
# 安装包
pip install ./loomgraph-*.whl

# 复制配置
mkdir -p ~/.config/loomgraph
cp config.yaml ~/.config/loomgraph/config.yaml

# 验证
loomgraph status
```

### 方案 B: 环境变量

README 说明设置环境变量：
```bash
export LOOMGRAPH_LIGHTRAG__API_URL="http://internal.example.invalid:3020"
```

**优点**: 无需额外文件
**缺点**: 每次需要设置

### 推荐: 方案 A

---

## 问题 3 解决方案：客户 README

客户收到的 README 需要明确说明：

```markdown
# LoomGraph - [客户名] 专用版

> 以下步骤由 Claude Code 读取后自动执行

## 1. 安装

在此目录下执行:
```bash
pip install ./loomgraph-*.whl
```

如果遇到 PEP 668 错误，使用 uv:
```bash
uv pip install ./loomgraph-*.whl
```

## 2. 配置

```bash
mkdir -p ~/.config/loomgraph
cp config.yaml ~/.config/loomgraph/config.yaml
```

## 3. 验证

```bash
loomgraph status
```

预期输出应显示连接到 http://internal.example.invalid:30XX

## 4. 索引你的代码库

```bash
cd /path/to/your/project
loomgraph index .
```
```

---

## 打包流程设计

### 目录结构

```
scripts/
└── package.py           # 打包脚本

customers/
├── customer/
│   ├── config.yaml      # 拼便宜配置
│   └── README.md        # 客户专属 README
└── customer/
    ├── config.yaml      # 智采云链配置
    └── README.md        # 客户专属 README

dist/                    # 打包输出 (gitignore)
├── loomgraph-customer-v0.1.0.tar.gz
└── loomgraph-customer-v0.1.0.tar.gz
```

### 打包命令

```bash
# 打包所有客户
python scripts/package.py --all

# 打包指定客户
python scripts/package.py --customer customer
```

### 输出内容

```
loomgraph-customer-v0.1.0/
├── README.md                # 客户专属 README
├── loomgraph-0.1.0-py3-none-any.whl
├── config.yaml              # 预配置的 LightRAG URL
└── CHANGELOG.md             # 版本更新说明
```

---

## 待确认事项

1. [ ] 客户 README 模板内容是否完善？
2. [ ] 配置文件路径 `~/.config/loomgraph/config.yaml` 是否合适？
3. [ ] 是否需要包含 CHANGELOG.md？
4. [ ] 打包格式：tar.gz 还是 zip？

---

## 新需求：全局 Skill 集成

### 用户观点

> 配置方式没有问题，我觉得就是解压项目源码，然后移动配置文件
> 倒是需要思考如何让客户的 claude code 根据文档自己创建全局 skill，方便他们对自己代码项目 init 然后执行理解 loomgraph

### 问题分析

当前流程：
```
客户 Claude 读 README → 安装 loomgraph → 索引项目 → 手动配置项目 CLAUDE.md
```

期望流程：
```
客户 Claude 读 README → 安装 loomgraph
                      → 创建全局 skill (~/.claude/CLAUDE.md)
                      → 之后任何项目都能 "loomgraph init" 自动配置
```

### 设计方案

#### 1. 全局 Skill 定义

在 `~/.claude/CLAUDE.md` 中添加 loomgraph 使用说明：

```markdown
## LoomGraph 代码智能工具

本机已安装 LoomGraph，可用于代码语义搜索和调用图查询。

### 初始化新项目

对于新项目，执行以下步骤：
1. 索引代码库：`loomgraph index .`
2. 在项目 CLAUDE.md 添加 LoomGraph 使用说明（见下文模板）

### 命令参考

| 命令 | 说明 |
|------|------|
| `loomgraph status` | 检查服务状态 |
| `loomgraph index .` | 索引当前目录 |
| `loomgraph search "<查询>"` | 语义搜索代码 |
| `loomgraph graph "<类.方法>"` | 查询调用关系 |

### 项目 CLAUDE.md 模板

在索引完成后，将以下内容添加到项目的 CLAUDE.md：

\`\`\`markdown
## 代码搜索 (LoomGraph)

本项目已用 LoomGraph 索引，可使用以下命令：

- `loomgraph search "<查询>"` - 语义搜索代码
- `loomgraph graph "<类名.方法名>"` - 查询调用关系
- `loomgraph status` - 检查服务状态
\`\`\`
```

#### 2. 安装后自动配置 Skill

README 中指导 Claude Code 完成 skill 配置：

```markdown
## 5. 配置全局 Skill

将 LoomGraph 添加到你的全局 Claude 配置：

```bash
cat >> ~/.claude/CLAUDE.md << 'EOF'

## LoomGraph 代码智能工具
...（skill 内容）
EOF
```

或者直接编辑 `~/.claude/CLAUDE.md` 添加上述内容。
```

#### 3. 项目 init 命令

是否需要 `loomgraph init` 命令来自动化项目配置？

```bash
loomgraph init
# 自动执行：
# 1. loomgraph index .
# 2. 在当前目录 CLAUDE.md 追加 loomgraph 使用说明
```

### 打包内容更新

```
loomgraph-customer/
├── README.md                    # 安装 + skill 配置指南
├── src/                         # 完整源码
├── config.yaml                  # 客户专属配置
├── SKILL_TEMPLATE.md            # 全局 skill 模板（供复制）
└── PROJECT_TEMPLATE.md          # 项目 CLAUDE.md 模板
```

### 待讨论

1. [ ] 是否需要 `loomgraph init` 命令？
2. [ ] skill 模板内容是否完善？
3. [ ] 如何处理已存在的 `~/.claude/CLAUDE.md`（追加 vs 提示用户）？

---

## 下一步

1. 确认 skill 集成方案
2. 创建 customers/ 目录结构（包含 SKILL_TEMPLATE.md）
3. 发源码包而非 whl（用户建议）
4. 测试完整流程：解压 → 安装 → 配置 skill → 项目 init
