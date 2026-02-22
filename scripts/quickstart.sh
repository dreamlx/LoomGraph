#!/bin/bash
# LoomGraph 一键快速启动脚本
# 用于客户 demo 包的首次安装

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
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    echo -e "${RED}❌ Python 版本过低（${PYTHON_VERSION}），需要 3.11+${NC}"
    exit 1
fi

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

# 查找 wheel 文件
CODEINDEX_WHL=$(ls codeindex-*.whl 2>/dev/null | head -1)
LOOMGRAPH_WHL=$(ls loomgraph-*.whl 2>/dev/null | head -1)

if [ -z "$CODEINDEX_WHL" ] || [ -z "$LOOMGRAPH_WHL" ]; then
    echo -e "${RED}❌ 未找到 wheel 文件${NC}"
    exit 1
fi

pip install "./$CODEINDEX_WHL"
pip install "./$LOOMGRAPH_WHL"
echo -e "${GREEN}✓ 安装完成${NC}"

# Step 5: 安装 Claude Code Skills
echo -e "\n${CYAN}[4/7] 安装 Claude Code Skills${NC}"
loomgraph install-skills
echo -e "${GREEN}✓ Skills 已安装${NC}"

# Step 6: 配置服务连接
echo -e "\n${CYAN}[5/7] 配置服务连接${NC}"
mkdir -p "$HOME/.config/loomgraph"

if [ -f "config.yaml" ]; then
    cp config.yaml "$HOME/.config/loomgraph/config.yaml"
    echo -e "${GREEN}✓ 配置已写入：~/.config/loomgraph/config.yaml${NC}"
else
    echo -e "${YELLOW}⚠ 未找到 config.yaml，请手动配置${NC}"
fi

# Step 7: 验证安装
echo -e "\n${CYAN}[6/7] 验证安装${NC}"
echo -e "${YELLOW}版本信息：${NC}"
loomgraph version

echo -e "\n${YELLOW}服务状态：${NC}"
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
echo -e "${CYAN}💡 提示：${NC}"
echo -e "   • 查看帮助：${YELLOW}loomgraph --help${NC}"
echo -e "   • 查看状态：${YELLOW}loomgraph status${NC}"
echo -e "   • 安装完整文档：${YELLOW}cat README.md${NC}\n"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
