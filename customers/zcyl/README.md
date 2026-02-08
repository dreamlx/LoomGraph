# LoomGraph - 智采云链专用版

> **Note**: 以下步骤由 Claude Code 读取后自动执行。

---

## 1. 安装 LoomGraph

创建专用虚拟环境并安装：

```bash
python3 -m venv ~/.loomgraph-venv
source ~/.loomgraph-venv/bin/activate
pip install .
```

这会自动安装 `ai-codeindex` 依赖。

---

## 2. 配置服务连接

```bash
mkdir -p ~/.config/loomgraph
cp config.yaml ~/.config/loomgraph/config.yaml
```

---

## 3. 安装全局 Skill

```bash
mkdir -p ~/.claude/skills
cp -r skills/loomgraph-init ~/.claude/skills/
```

这会添加 `/loomgraph-init` 斜杠命令，用于初始化新项目。

---

## 4. 添加 Shell 别名（推荐）

```bash
echo 'alias loomgraph="~/.loomgraph-venv/bin/loomgraph"' >> ~/.zshrc
source ~/.zshrc
```

这样不需要每次激活虚拟环境就能使用 loomgraph。

---

## 5. 验证安装

```bash
loomgraph status
# 或者（如果没有设置别名）
~/.loomgraph-venv/bin/loomgraph status
```

**预期输出**：
- `lightrag_api.connected: true`
- `lightrag_api.url: http://117.131.45.179:3020`

**如果失败**：
- `codeindex installed: false` → 重新执行安装步骤
- `lightrag connected: false` → 检查网络白名单权限

---

## 使用方式

### 初始化新项目

进入你的代码项目目录，执行：

```
/loomgraph-init
```

这会在项目 CLAUDE.md 中添加 LoomGraph 使用说明。

然后索引代码：

```bash
loomgraph index .
```

### 日常使用

```bash
# 语义搜索代码
loomgraph search "用户认证逻辑"

# 查询调用关系
loomgraph graph "UserService.login" --direction callers

# 检查服务状态
loomgraph status
```

---

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `loomgraph status` | 检查服务状态 |
| `loomgraph index <path>` | 索引代码库 |
| `loomgraph search "<query>"` | 语义搜索 |
| `loomgraph graph "<entity>"` | 查询调用关系 |

---

## 故障排除

### 索引时出现大量 warning

这是正常现象。跨文件依赖（如标准库、外部包）会产生 "Target entity does not exist" 警告，不影响使用。

### 搜索结果不相关

1. 确认已执行 `loomgraph index .`
2. 代码变更后需重新索引

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
