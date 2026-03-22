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

# 查找 wheel 文件（codeindex 包名为 ai_codeindex）
CODEINDEX_WHL=$(ls ai_codeindex-*.whl 2>/dev/null | head -1)
LOOMGRAPH_WHL=$(ls loomgraph-*.whl 2>/dev/null | head -1)

if [ -z "$LOOMGRAPH_WHL" ]; then
    echo -e "${RED}❌ 未找到 loomgraph wheel 文件${NC}"
    exit 1
fi

if [ -n "$CODEINDEX_WHL" ]; then
    pip install "./$CODEINDEX_WHL"
    echo -e "${GREEN}✓ codeindex 已安装${NC}"
else
    echo -e "${YELLOW}⚠ 未找到 codeindex wheel，尝试在线安装${NC}"
    pip install ai-codeindex
fi

pip install "./$LOOMGRAPH_WHL"
echo -e "${GREEN}✓ LoomGraph 已安装${NC}"

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

# Step 8: 安装后自检
echo -e "\n${CYAN}[7/7] 安装后自检${NC}"

DIAG_PASS=0
DIAG_WARN=0

# 检查 codeindex
if command -v codeindex &> /dev/null; then
    CODEINDEX_VER=$(codeindex --version 2>/dev/null || echo "unknown")
    echo -e "${GREEN}✓ codeindex: ${CODEINDEX_VER}${NC}"
    DIAG_PASS=$((DIAG_PASS + 1))
else
    echo -e "${RED}✗ codeindex: 未安装${NC}"
    DIAG_WARN=$((DIAG_WARN + 1))
fi

# 检查 LightRAG 连接
LIGHTRAG_URL=$(grep -oP 'api_url:\s*"\K[^"]+' "$HOME/.config/loomgraph/config.yaml" 2>/dev/null || echo "")
if [ -n "$LIGHTRAG_URL" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${LIGHTRAG_URL}/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ LightRAG: 连接正常 (${LIGHTRAG_URL})${NC}"
        DIAG_PASS=$((DIAG_PASS + 1))
    else
        echo -e "${YELLOW}⚠ LightRAG: 连接异常 (HTTP ${HTTP_CODE})${NC}"
        DIAG_WARN=$((DIAG_WARN + 1))
    fi
else
    echo -e "${YELLOW}⚠ LightRAG: 未在配置中找到 api_url${NC}"
    DIAG_WARN=$((DIAG_WARN + 1))
fi

# 功能可用性总结
echo -e "\n${CYAN}功能可用性：${NC}"
echo -e "  ${GREEN}✓${NC} find  (结构化搜索)    — 索引后可用"
echo -e "  ${GREEN}✓${NC} graph (调用关系)      — 索引后可用（需 codeindex 提取 relations）"
echo -e "  ${YELLOW}?${NC} query (语义问答)      — 需 LightRAG 服务端配置 LLM"
echo -e "  ${GREEN}✓${NC} topology (拓扑分析)   — 索引后可用"
echo -e "  ${GREEN}✓${NC} debt  (技术债务)      — 需 codeindex 静态分析数据"

if [ "$DIAG_WARN" -gt 0 ]; then
    echo -e "\n${YELLOW}⚠ 有 ${DIAG_WARN} 项需要关注，请查看上方警告${NC}"
fi

# Step 9: 输出下一步指引
echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ 安装完成！${NC}\n"
echo -e "${CYAN}下一步操作：${NC}\n"
echo -e "1. 进入你的项目目录："
echo -e "   ${YELLOW}cd /path/to/your/project${NC}\n"
echo -e "2. 配置项目（检测语言、生成配置）："
echo -e "   ${YELLOW}/loomgraph-setup${NC}  (Claude Code Skill)"
echo -e "   或手动: ${YELLOW}codeindex init && codeindex scan-all${NC}\n"
echo -e "3. 索引代码库到知识图谱："
echo -e "   ${YELLOW}loomgraph index .${NC}\n"
echo -e "4. 验证索引结果："
echo -e "   ${YELLOW}loomgraph find \"YourClassName\"${NC}"
echo -e "   ${YELLOW}loomgraph graph \"YourClassName\" --direction callees${NC}\n"
echo -e "${CYAN}提示：${NC}"
echo -e "   查看帮助：${YELLOW}loomgraph --help${NC}"
echo -e "   查看状态：${YELLOW}loomgraph status${NC}"
echo -e "   完整文档：${YELLOW}cat README.md${NC}"
echo -e "   query 不可用？查看 README.md「功能与前置条件」表\n"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
