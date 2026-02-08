# LoomGraph - 拼便宜专用版

> **Note**: 以下步骤由 Claude Code 读取后自动执行。

---

## 1. 安装 LoomGraph

在此目录下执行：

```bash
pip install .
```

如果遇到 PEP 668 错误（externally-managed-environment），使用以下方式之一：

```bash
# 方式 A: 使用 uv
uv pip install .

# 方式 B: 创建虚拟环境
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
cp -r skills/loomgraph-init ~/.claude/skills/
```

这会添加 `/loomgraph-init` 斜杠命令，用于初始化新项目。

---

## 4. 验证安装

```bash
loomgraph status
```

**预期输出**：
- `lightrag_api.connected: true`
- `lightrag_api.url: http://117.131.45.179:3010`

**如果失败**：
- `codeindex installed: false` → 执行 `pip install ai-codeindex`
- `lightrag connected: false` → 检查网络白名单权限

---

## 5. 使用方式

### 初始化新项目

进入你的代码项目目录，执行：

```
/loomgraph-init
```

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

---

## 技术支持

如有问题，请联系 LoomGraph 技术团队。
