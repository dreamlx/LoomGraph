# 客户打包部署指南

本文档记录 LoomGraph 客户分发的完整流程和经验教训。

---

## 客户信息

| 客户 | 代号 | LightRAG 端口 | 代码语言 |
|------|------|--------------|----------|
| 拼便宜 | pinbianyi | 3010 | PHP |
| 智采云链 | zcyl | 3020 | Java |

共享服务：
- Embedding (TEI): `http://117.131.45.179:3002`
- LLM: `http://117.131.45.179:3000`

---

## 打包流程

### 1. 更新版本号

```bash
# pyproject.toml 和 src/loomgraph/__init__.py
version = "x.y.z"
__version__ = "x.y.z"
```

### 2. 生成客户包

```bash
# 打包指定客户
python3 scripts/package.py --customer zcyl

# 打包所有客户
python3 scripts/package.py --all

# 列出可用客户
python3 scripts/package.py --list
```

### 3. 输出内容

```
dist/loomgraph-{customer}-v{version}.tar.gz

解压后：
loomgraph-{customer}-v{version}/
├── README.md                    # 客户专属安装指南
├── src/loomgraph/               # 源码
├── pyproject.toml               # 安装配置
├── config.yaml                  # 客户专属 LightRAG URL
└── skills/
    └── loomgraph-init/
        └── SKILL.md             # 全局 skill
```

---

## 客户安装流程

### 预期流程（由客户 Claude Code 执行）

**安装阶段（一次性）：**
```
1. 创建虚拟环境 ~/.loomgraph-venv
2. 安装 loomgraph + 依赖
3. 复制配置到 ~/.config/loomgraph/
4. 安装 skills 到 ~/.claude/skills/（loomgraph-setup + loomgraph-init）
5. 添加 shell 别名
6. 验证 loomgraph status
```

**项目初始化（每个项目）：**
```
1. /loomgraph-setup  - 配置 codeindex（检测语言、安装解析器、生成 .codeindex.yaml）
2. /loomgraph-init   - 配置项目 CLAUDE.md
3. loomgraph index . - 索引代码
```

### 关键学到的经验

#### 经验 1: 虚拟环境是必须的

**问题**：macOS 默认 Python 禁止全局安装 (PEP 668)

**解决**：README 直接给出完整的虚拟环境创建命令，而不是 `pip install .`

```bash
# 正确的方式
python3 -m venv ~/.loomgraph-venv
source ~/.loomgraph-venv/bin/activate
pip install .

# 错误的方式（会失败）
pip install .
uv pip install .
```

#### 经验 2: Shell 别名很有用

Claude Code 在实际安装中自己添加了 shell 别名，这是个好实践：

```bash
echo 'alias loomgraph="~/.loomgraph-venv/bin/loomgraph"' >> ~/.zshrc
```

这样用户不需要每次激活虚拟环境就能使用 loomgraph。

#### 经验 3: Claude Code 足够智能

不需要 `install.sh` 脚本。Claude Code 能够：
- 识别 PEP 668 错误并创建虚拟环境
- 自动添加 shell 别名
- 处理各种环境问题

只需要 README 提供清晰的步骤说明。

#### 经验 4: Checklist 格式更有效

**问题**：普通 README 步骤容易被跳过，用户直接跳到"使用方式"

**解决**：使用 Checklist 格式 `- [ ]`，并在开头添加指引：
```markdown
> **给 Claude Code**: 请按顺序执行下面的 Checklist，每完成一项就打勾 `[x]`。
> **所有步骤都必须完成**，跳过任何一步都会导致功能异常。
```

**效果**：
- Claude Code 明确知道需要逐项完成
- 可以在 CLAUDE.md 中记录安装状态
- 故障排除时可以追溯漏了哪一步

#### 经验 5: 安装状态需要持久化

**问题**：Claude Code 不会自动记住安装过程

**解决**：在 README 末尾要求 Claude Code 更新项目 CLAUDE.md：
```markdown
## LoomGraph 安装状态

- [x] LoomGraph v0.2.0 已安装
- [x] Skills 已配置: /loomgraph-setup, /loomgraph-init
- [x] 服务连接正常: http://117.131.45.179:3020
```

#### 经验 6: 配置优先级

```
当前目录 .loomgraph.yaml  >  ~/.config/loomgraph/config.yaml
```

客户项目中通常没有 `.loomgraph.yaml`，所以全局配置会生效。

---

## 客户 README 模板

### 关键内容

1. **明确的虚拟环境创建步骤**
2. **Shell 别名设置**
3. **服务连接验证**
4. **常见问题解答**

### 模板位置

- `customers/{customer}/README.md`

---

## 验证清单

发给客户前的验证步骤：

### 功能验证

```bash
# 在无 .loomgraph.yaml 的目录中测试
cd /tmp

# 1. 状态检查
loomgraph status
# 确认 lightrag_url 是正确的客户端口

# 2. 索引测试
loomgraph index /path/to/test/project

# 3. 搜索测试
loomgraph search "某个功能"

# 4. 调用图测试（如果有数据）
loomgraph graph "SomeClass.method"
```

### 配置验证

```bash
# 确认配置文件内容正确
cat ~/.config/loomgraph/config.yaml

# 确认 skill 已安装
ls ~/.claude/skills/loomgraph-init/
```

---

## 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| 单文件索引 | ISSUE-001 | CLI 不支持，Core 层已支持 |
| 索引 warning | ISSUE-002 | 预期行为，在 README 说明 |
| 实体缺少代码内容 | Task #2 | 待实现 |

---

## 版本历史

| 版本 | 日期 | 客户 | 说明 |
|------|------|------|------|
| v0.1.0 | 2025-02-?? | pinbianyi | 首次发布 |
| v0.2.0 | 2025-02-08 | zcyl | 优化安装流程 |
| v0.2.1 | 2025-02-08 | all | README Checklist 格式优化 |

---

## 文件结构

```
customers/
├── pinbianyi/
│   ├── config.yaml      # api_url: :3010
│   └── README.md
└── zcyl/
    ├── config.yaml      # api_url: :3020
    └── README.md

skills/
├── loomgraph-setup/     # 项目配置向导（v0.3.0+）
│   └── SKILL.md
└── loomgraph-init/      # 项目 CLAUDE.md 配置
    └── SKILL.md

scripts/
└── package.py
```

---

## Skills 说明

### /loomgraph-setup（v0.3.0+）

**用途**：在索引前配置 codeindex

**解决问题**：
- 大型项目索引慢（没有并行、没有排除规则）
- 语言解析器未安装（Java 需要 `ai-codeindex[java]`）

**流程**：
1. 检测项目语言
2. 安装对应 tree-sitter 解析器
3. 生成 `.codeindex.yaml` 配置

### /loomgraph-init

**用途**：在项目 CLAUDE.md 添加使用说明

**流程**：追加 LoomGraph 命令参考到 CLAUDE.md

---

## 添加新客户

1. 创建目录 `customers/{new_customer}/`
2. 创建 `config.yaml`（修改 api_url 端口）
3. 创建 `README.md`（修改客户名和端口）
4. 在 H200 上部署新的 LightRAG 实例
5. 运行 `python3 scripts/package.py --customer {new_customer}`
