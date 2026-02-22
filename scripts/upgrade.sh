#!/bin/bash
# LoomGraph 一键升级脚本
# 用于客户升级包的版本更新

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

# 获取当前版本
CURRENT_VERSION=$(loomgraph version 2>/dev/null | jq -r '.version' 2>/dev/null || echo "unknown")
echo -e "${YELLOW}当前版本：${CURRENT_VERSION}${NC}"

# 读取新版本号
NEW_VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
echo -e "${YELLOW}升级到：${NEW_VERSION}${NC}"

# 版本比较
if [ "$CURRENT_VERSION" = "$NEW_VERSION" ]; then
    echo -e "${YELLOW}⚠ 已是最新版本，无需升级${NC}"
    echo -e "${CYAN}是否强制重新安装？(y/N)${NC}"
    read -r FORCE_INSTALL
    if [ "$FORCE_INSTALL" != "y" ] && [ "$FORCE_INSTALL" != "Y" ]; then
        exit 0
    fi
fi

# Step 2: 备份配置
echo -e "\n${CYAN}[2/6] 备份当前配置${NC}"
CONFIG_PATH="$HOME/.config/loomgraph/config.yaml"
BACKUP_SUFFIX=$(date +%Y%m%d_%H%M%S)

if [ -f "$CONFIG_PATH" ]; then
    cp "$CONFIG_PATH" "$CONFIG_PATH.backup.$BACKUP_SUFFIX"
    echo -e "${GREEN}✓ 配置已备份：${CONFIG_PATH}.backup.${BACKUP_SUFFIX}${NC}"
else
    echo -e "${YELLOW}⚠ 未找到配置文件${NC}"
fi

# Step 3: 升级包
echo -e "\n${CYAN}[3/6] 升级 codeindex + LoomGraph${NC}"

# 查找 wheel 文件
CODEINDEX_WHL=$(ls codeindex-*.whl 2>/dev/null | head -1)
LOOMGRAPH_WHL=$(ls loomgraph-*.whl 2>/dev/null | head -1)

if [ -z "$CODEINDEX_WHL" ] || [ -z "$LOOMGRAPH_WHL" ]; then
    echo -e "${RED}❌ 未找到 wheel 文件${NC}"
    exit 1
fi

pip install --quiet --upgrade "./$CODEINDEX_WHL"
pip install --quiet --upgrade "./$LOOMGRAPH_WHL"
echo -e "${GREEN}✓ 升级完成${NC}"

# Step 4: 重新安装 Skills
echo -e "\n${CYAN}[4/6] 重新安装 Skills${NC}"
loomgraph install-skills
echo -e "${GREEN}✓ Skills 已更新${NC}"

# Step 5: 配置迁移（如果需要）
echo -e "\n${CYAN}[5/6] 检查配置兼容性${NC}"
if [ -f "config.yaml.new" ]; then
    echo -e "${YELLOW}⚠ 检测到配置格式变更${NC}"
    echo -e "${YELLOW}新配置模板：$(pwd)/config.yaml.new${NC}"
    echo -e "${YELLOW}当前配置：${CONFIG_PATH}${NC}"
    echo -e "\n${CYAN}需要手动检查并更新配置文件${NC}"
    echo -e "${CYAN}备份文件：${CONFIG_PATH}.backup.${BACKUP_SUFFIX}${NC}"

    # 显示差异（如果可能）
    if command -v diff &> /dev/null; then
        echo -e "\n${YELLOW}配置差异：${NC}"
        diff "$CONFIG_PATH" "config.yaml.new" || true
    fi
else
    echo -e "${GREEN}✓ 配置兼容，无需迁移${NC}"
fi

# Step 6: 验证升级
echo -e "\n${CYAN}[6/6] 验证升级${NC}"
echo -e "${YELLOW}新版本信息：${NC}"
loomgraph version

echo -e "\n${YELLOW}服务状态：${NC}"
loomgraph status

# 检查是否需要重建索引
echo -e "\n${CYAN}检查索引兼容性${NC}"
NEED_REBUILD=false

if [ -f "UPGRADE_NOTES.md" ]; then
    if grep -qi "需要重建索引\|rebuild.*index\|breaking.*change" UPGRADE_NOTES.md; then
        NEED_REBUILD=true
        echo -e "${YELLOW}⚠ 此版本需要重建索引${NC}"
        echo -e "${YELLOW}原因：数据格式变更或重大更新${NC}"
        echo -e "\n${YELLOW}请在项目目录中执行：${NC}"
        echo -e "   ${RED}loomgraph index --clear .${NC}\n"
    else
        echo -e "${GREEN}✓ 无需重建索引，增量更新即可${NC}"
    fi
else
    echo -e "${GREEN}✓ 无需重建索引${NC}"
fi

# 输出升级报告
echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ 升级完成！${NC}\n"
echo -e "${CYAN}版本变化：${NC}"
echo -e "  ${CURRENT_VERSION} → ${NEW_VERSION}\n"

if [ -f "CHANGELOG.md" ]; then
    echo -e "${CYAN}本版本变更（摘要）：${NC}"
    # 提取最新版本的变更（第一个版本段落）
    awk '/^## \[.*\]/{p++} p==1' CHANGELOG.md | head -30
fi

echo -e "\n${CYAN}下一步（可选）：${NC}"
echo -e "  • 查看完整变更：${YELLOW}cat CHANGELOG.md${NC}"
if [ "$NEED_REBUILD" = true ]; then
    echo -e "  • ${RED}重建索引（必需）${NC}：${YELLOW}cd /path/to/project && loomgraph index --clear .${NC}"
fi
echo -e "  • 测试新功能：${YELLOW}loomgraph --help${NC}"
echo -e "  • ${RED}重启 Claude Code${NC} 以加载新版 Skills\n"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
