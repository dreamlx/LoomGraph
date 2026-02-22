# LoomGraph 客户快速上手指南

## 方案概述

**目标**：客户在 Claude Code 中执行一个 Skill 命令，自动完成所有配置和初始化。

## 一键启动流程

### 场景 1：首次安装（新客户）

**客户收到 demo 包后的操作**：

```bash
# 1. 解压 demo 包
tar xzf loomgraph-demo-{customer}-v{version}.tar.gz
cd loomgraph-demo-{customer}-v{version}

# 2. 运行快速启动脚本
./quickstart.sh
```

**quickstart.sh 自动完成**：
1. ✅ 检查系统依赖（Python 3.11+）
2. ✅ 创建虚拟环境（`~/.loomgraph-venv`）
3. ✅ 安装 codeindex + LoomGraph（从 wheel）
4. ✅ 安装 Claude Code Skills（`loomgraph install-skills`）
5. ✅ 配置服务连接（从 demo 包内置的 `config.yaml`）
6. ✅ 验证安装成功（`loomgraph status`）
7. ✅ 输出下一步指引

**脚本执行完成后，在 Claude Code 中执行**：

```
/loomgraph-setup
```

**Skill 自动完成**：
1. ✅ 检测项目语言（Java/PHP/Python）
2. ✅ 安装对应的 tree-sitter 解析器
3. ✅ 生成 `.codeindex.yaml` 配置文件
4. ✅ 验证配置正确性

**然后执行**：

```
/loomgraph-init
```

**Skill 自动完成**：
1. ✅ 在项目 CLAUDE.md 中添加使用说明
2. ✅ 提示执行 `loomgraph index .` 开始索引

**最后，Claude Code 自动执行索引**：

```bash
loomgraph index .
```

**完成！客户可以开始使用**：

```
/mo:arch "show me the authentication flow"
loomgraph find "UserService"
loomgraph query "how does payment processing work"
```

---

### 场景 2：版本升级（已有客户）

**客户收到升级包后的操作**：

```bash
# 1. 解压升级包
tar xzf loomgraph-upgrade-{customer}-v{new_version}.tar.gz
cd loomgraph-upgrade-{customer}-v{new_version}

# 2. 运行升级脚本
./upgrade.sh
```

**upgrade.sh 自动完成**：
1. ✅ 检查当前版本（`loomgraph version`）
2. ✅ 备份当前配置（`~/.config/loomgraph/config.yaml`）
3. ✅ 激活虚拟环境
4. ✅ 升级 codeindex + LoomGraph（`pip install --upgrade ./loomgraph-*.whl`）
5. ✅ 重新安装 Skills（`loomgraph install-skills`）
6. ✅ 恢复配置文件（merge 新旧配置）
7. ✅ 检查是否需要重建索引（版本兼容性判断）
8. ✅ 输出升级报告

**在 Claude Code 中验证升级**：

```bash
# 检查新版本
loomgraph version

# 检查新功能（如果有）
loomgraph --help | grep "New"

# 测试查询功能
loomgraph status
loomgraph find "SomeClass"
```

**如果需要重建索引**（大版本升级）：

```bash
# Cold Rebuild（清空重建）
loomgraph index --clear .
```

**升级完成！新功能自动可用**。

---

## Demo 包结构

### 首次安装包（loomgraph-demo-{customer}-v{version}.tar.gz）

```
loomgraph-demo-zcyl-v0.6.0/
├── README.md                              # 快速上手指南
├── CHANGELOG.md                           # 客户可见变更日志
├── quickstart.sh                          # 🔑 一键启动脚本
├── config.yaml                            # 🔑 客户专用配置（预配置 LightRAG URL）
├── codeindex-*.whl                        # codeindex wheel
├── loomgraph-*.whl                        # LoomGraph wheel
├── requirements.txt                       # 依赖列表（仅供参考）
└── scripts/
    ├── check_deps.sh                      # 依赖检查脚本
    └── verify_install.sh                  # 安装验证脚本
```

### 升级包（loomgraph-upgrade-{customer}-v{new_version}.tar.gz）

```
loomgraph-upgrade-zcyl-v0.7.0/
├── README.md                              # 升级说明
├── CHANGELOG.md                           # 本版本变更
├── UPGRADE_NOTES.md                       # 🔑 升级注意事项
├── upgrade.sh                             # 🔑 一键升级脚本
├── config.yaml.new                        # 新版配置模板（如有变更）
├── codeindex-*.whl                        # 新版 codeindex wheel
├── loomgraph-*.whl                        # 新版 LoomGraph wheel
└── scripts/
    ├── version_check.sh                   # 版本兼容性检查
    └── migrate_config.sh                  # 配置迁移脚本
```

---

## 核心脚本实现

### quickstart.sh（首次安装）

```bash
#!/bin/bash
# LoomGraph 一键快速启动脚本

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}🚀 LoomGraph 快速启动${NC}\n"

# Step 1: 检查系统依赖
echo -e "${CYAN}[1/7] 检查系统依赖${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 未找到 Python 3，请先安装 Python 3.11+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓ Python ${PYTHON_VERSION}${NC}"

# Step 2: 创建虚拟环境
echo -e "\n${CYAN}[2/7] 创建虚拟环境${NC}"
VENV_PATH="$HOME/.loomgraph-venv"

if [ -d "$VENV_PATH" ]; then
    echo -e "${YELLOW}⚠ 虚拟环境已存在，跳过创建${NC}"
else
    python3 -m venv "$VENV_PATH"
    echo -e "${GREEN}✓ 虚拟环境已创建：${VENV_PATH}${NC}"
fi

# Step 3: 激活虚拟环境
source "$VENV_PATH/bin/activate"

# Step 4: 安装 wheel 包
echo -e "\n${CYAN}[3/7] 安装 codeindex + LoomGraph${NC}"
pip install --quiet --upgrade pip
pip install ./codeindex-*.whl
pip install ./loomgraph-*.whl
echo -e "${GREEN}✓ 安装完成${NC}"

# Step 5: 安装 Claude Code Skills
echo -e "\n${CYAN}[4/7] 安装 Claude Code Skills${NC}"
loomgraph install-skills
echo -e "${GREEN}✓ Skills 已安装${NC}"

# Step 6: 配置服务连接
echo -e "\n${CYAN}[5/7] 配置服务连接${NC}"
mkdir -p "$HOME/.config/loomgraph"
cp config.yaml "$HOME/.config/loomgraph/config.yaml"
echo -e "${GREEN}✓ 配置已写入：~/.config/loomgraph/config.yaml${NC}"

# Step 7: 验证安装
echo -e "\n${CYAN}[6/7] 验证安装${NC}"
loomgraph version
loomgraph status

# Step 8: 输出下一步指引
echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ 安装完成！${NC}\n"
echo -e "${CYAN}下一步操作（在 Claude Code 中执行）：${NC}\n"
echo -e "1️⃣  进入你的项目目录："
echo -e "   ${YELLOW}cd /path/to/your/project${NC}\n"
echo -e "2️⃣  配置项目（检测语言、生成配置）："
echo -e "   ${YELLOW}/loomgraph-setup${NC}\n"
echo -e "3️⃣  添加使用说明到 CLAUDE.md："
echo -e "   ${YELLOW}/loomgraph-init${NC}\n"
echo -e "4️⃣  索引代码库："
echo -e "   ${YELLOW}loomgraph index .${NC}\n"
echo -e "5️⃣  开始使用："
echo -e "   ${YELLOW}/mo:arch \"show me the architecture\"${NC}"
echo -e "   ${YELLOW}loomgraph find \"YourClassName\"${NC}\n"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
```

### upgrade.sh（版本升级）

```bash
#!/bin/bash
# LoomGraph 一键升级脚本

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}🔄 LoomGraph 版本升级${NC}\n"

VENV_PATH="$HOME/.loomgraph-venv"

# Step 1: 检查当前版本
echo -e "${CYAN}[1/6] 检查当前版本${NC}"
if [ ! -f "$VENV_PATH/bin/loomgraph" ]; then
    echo -e "${RED}❌ LoomGraph 未安装，请使用 quickstart.sh 首次安装${NC}"
    exit 1
fi

source "$VENV_PATH/bin/activate"
CURRENT_VERSION=$(loomgraph version | jq -r '.version' 2>/dev/null || echo "unknown")
echo -e "${YELLOW}当前版本：${CURRENT_VERSION}${NC}"

# 读取新版本号
NEW_VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
echo -e "${YELLOW}升级到：${NEW_VERSION}${NC}"

# Step 2: 备份配置
echo -e "\n${CYAN}[2/6] 备份当前配置${NC}"
CONFIG_PATH="$HOME/.config/loomgraph/config.yaml"
if [ -f "$CONFIG_PATH" ]; then
    cp "$CONFIG_PATH" "$CONFIG_PATH.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${GREEN}✓ 配置已备份${NC}"
else
    echo -e "${YELLOW}⚠ 未找到配置文件${NC}"
fi

# Step 3: 升级包
echo -e "\n${CYAN}[3/6] 升级 codeindex + LoomGraph${NC}"
pip install --quiet --upgrade ./codeindex-*.whl
pip install --quiet --upgrade ./loomgraph-*.whl
echo -e "${GREEN}✓ 升级完成${NC}"

# Step 4: 重新安装 Skills
echo -e "\n${CYAN}[4/6] 重新安装 Skills${NC}"
loomgraph install-skills
echo -e "${GREEN}✓ Skills 已更新${NC}"

# Step 5: 配置迁移（如果需要）
echo -e "\n${CYAN}[5/6] 检查配置兼容性${NC}"
if [ -f "config.yaml.new" ]; then
    echo -e "${YELLOW}⚠ 检测到配置格式变更${NC}"
    echo -e "${YELLOW}请手动检查并更新：~/.config/loomgraph/config.yaml${NC}"
    echo -e "${YELLOW}参考新模板：$(pwd)/config.yaml.new${NC}"
else
    echo -e "${GREEN}✓ 配置兼容，无需迁移${NC}"
fi

# Step 6: 验证升级
echo -e "\n${CYAN}[6/6] 验证升级${NC}"
loomgraph version
loomgraph status

# 检查是否需要重建索引
echo -e "\n${CYAN}检查索引兼容性${NC}"
if [ -f "UPGRADE_NOTES.md" ]; then
    if grep -q "需要重建索引" UPGRADE_NOTES.md; then
        echo -e "${YELLOW}⚠ 此版本需要重建索引${NC}"
        echo -e "${YELLOW}请在项目目录中执行：loomgraph index --clear .${NC}"
    else
        echo -e "${GREEN}✓ 无需重建索引，增量更新即可${NC}"
    fi
fi

# 输出升级报告
echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ 升级完成！${NC}\n"
echo -e "${CYAN}版本变化：${NC}"
echo -e "  ${CURRENT_VERSION} → ${NEW_VERSION}\n"
echo -e "${CYAN}新功能（如有）：${NC}"
cat CHANGELOG.md | sed -n '/^## \[.*\]/,/^## \[/p' | head -20
echo -e "\n${CYAN}下一步（可选）：${NC}"
echo -e "  • 查看完整变更：${YELLOW}cat CHANGELOG.md${NC}"
echo -e "  • 重建索引（如需要）：${YELLOW}cd /path/to/project && loomgraph index --clear .${NC}"
echo -e "  • 测试新功能：${YELLOW}loomgraph --help${NC}\n"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
```

---

## Claude Code 感知机制

### 初始化场景

```
客户解压 demo 包 → 运行 quickstart.sh →
├─ 安装 codeindex + LoomGraph
├─ 安装 Claude Code Skills
└─ 配置服务连接

Claude Code 中执行 /loomgraph-setup →
├─ 检测项目语言
├─ 安装解析器
└─ 生成 .codeindex.yaml

Claude Code 中执行 /loomgraph-init →
└─ 在 CLAUDE.md 添加使用说明

Claude Code 自动执行 loomgraph index . →
└─ 构建知识图谱

✅ 完成！Claude Code 可以通过 /mo:arch 查询
```

### 升级场景

```
客户解压升级包 → 运行 upgrade.sh →
├─ 检查当前版本
├─ 备份配置
├─ 升级 wheels
└─ 重新安装 Skills

Claude Code 重启 →
├─ MCP Server 重新加载
├─ 自动注册新 Skills
└─ 使用新版本 loomgraph CLI

Claude Code 执行命令 →
├─ 新 Skills 自动可用（如 /mo:refactor）
├─ 旧 Skills 保持兼容
└─ 配置向后兼容（除非 Breaking Change）

✅ 升级完成！用户无需手动配置
```

---

## 打包流程（开发者）

### 生成 demo 包

```bash
# 在 LoomGraph 仓库中执行
cd /Users/dreamlinx/Projects/LoomGraph

# 打包单个客户的 demo 包
python scripts/package.py --customer zcyl --mode demo

# 打包升级包
python scripts/package.py --customer zcyl --mode upgrade

# 批量打包所有客户
python scripts/package.py --all --mode demo
```

### package.py 新增参数

```python
# scripts/package.py

@click.option('--mode', type=click.Choice(['demo', 'upgrade']), default='demo',
              help='Package mode: demo (first install) or upgrade')
```

**demo 模式**：
- 包含 quickstart.sh
- 包含预配置的 config.yaml
- README 为首次安装指南

**upgrade 模式**：
- 包含 upgrade.sh
- 包含 UPGRADE_NOTES.md
- 包含 config.yaml.new（如有变更）
- README 为升级指南

---

## 客户体验总结

### 首次安装（3 步完成）

| 步骤 | 命令 | 耗时 | 说明 |
|------|------|------|------|
| 1 | `./quickstart.sh` | 1-2 分钟 | 自动安装和配置 |
| 2 | `/loomgraph-setup` | 30 秒 | Claude Code 中执行 |
| 3 | `loomgraph index .` | 5-10 分钟 | 首次索引（取决于项目大小） |

### 版本升级（2 步完成）

| 步骤 | 命令 | 耗时 | 说明 |
|------|------|------|------|
| 1 | `./upgrade.sh` | 30 秒 | 自动升级 |
| 2 | 重启 Claude Code | 5 秒 | MCP Server 重新加载 |

### 关键优势

1. ✅ **零配置文件编辑**：config.yaml 预配置在 demo 包中
2. ✅ **零依赖安装**：wheel 包全部内置
3. ✅ **零手动命令**：脚本自动完成所有操作
4. ✅ **零学习成本**：Skills 提供交互式引导
5. ✅ **零升级成本**：一个脚本完成所有升级步骤

---

## FAQ

### Q1: 客户如何知道有新版本？

**A**: 两种方式：
1. **邮件通知**：发送升级包 + 变更摘要
2. **版本检查命令**：`loomgraph version --check-update`（未来功能）

### Q2: 升级后旧配置会丢失吗？

**A**: 不会。upgrade.sh 自动备份配置，并在升级后恢复。

### Q3: 如果 quickstart.sh 执行失败怎么办？

**A**: 脚本包含详细错误提示，常见问题：
- Python 版本不符合要求（需要 3.11+）
- 虚拟环境创建失败（检查磁盘空间）
- wheel 安装失败（检查网络连接，使用离线包）

### Q4: Claude Code 如何感知新安装的 Skills？

**A**: Skills 安装后自动注册到 `~/.claude/skills/` 目录，Claude Code 启动时自动加载。无需手动配置。

### Q5: 大版本升级一定要重建索引吗？

**A**: 不一定。只有数据格式变更时才需要。upgrade.sh 会自动检查 UPGRADE_NOTES.md 并提示用户。

---

**最后更新**：2026-02-22
**适用版本**：LoomGraph v0.6.0+
