# LoomGraph 打包与部署指南

## 概述

LoomGraph 使用模板化打包系统，为每个客户生成定制的安装包。

## 目录结构

```
customers/
├── README.template.md      # 公开模板（GitHub）
├── CHANGELOG.md            # 公开变更日志（GitHub）
├── VERSION                 # 公开版本号（GitHub）
├── customers.yaml.example  # 公开配置示例（GitHub）
├── customers.yaml          # 客户注册表（本地私有）
├── zcyl/
│   └── config.yaml         # 客户配置（本地私有）
└── pinbianyi/
    └── config.yaml         # 客户配置（本地私有）
```

## 初始设置（新开发者）

```bash
# 1. 克隆仓库后，创建客户配置
cp customers/customers.yaml.example customers/customers.yaml

# 2. 编辑 customers.yaml 填写实际客户信息
vim customers/customers.yaml
```

### customers.yaml 示例

```yaml
zcyl:
  name: "智采云链"
  lightrag_url: "http://x.x.x.x:3020"
  language_hint: "Java"
  language_parser: "ai-codeindex[java]"
  exclude_dirs: "target/, build/"

pinbianyi:
  name: "拼便宜"
  lightrag_url: "http://x.x.x.x:3010"
  language_hint: "PHP"
  language_parser: "ai-codeindex[php]"
  exclude_dirs: "vendor/, cache/"
```

## 添加新客户

```bash
# 1. 在 customers.yaml 添加客户配置
vim customers/customers.yaml

# 2. 创建客户目录和服务配置
mkdir customers/newcustomer
cat > customers/newcustomer/config.yaml << 'EOF'
# LoomGraph 配置 - 新客户专用
# 复制到 ~/.config/loomgraph/config.yaml

lightrag:
  api_url: "http://your-server:3001"
  api_timeout: 30.0

embedding:
  base_url: "http://your-server:3002"
EOF

# 3. 验证
.venv/bin/python scripts/package.py --list
```

## 打包命令

```bash
# 激活虚拟环境
source .venv/bin/activate

# 列出所有客户
python scripts/package.py --list

# 打包单个客户
python scripts/package.py --customer zcyl

# 打包所有客户
python scripts/package.py --all

# 同步版本号（从 __init__.py 到 VERSION）
python scripts/package.py --sync-version
```

## 发布新版本流程

```bash
# 1. 更新版本号
vim src/loomgraph/__init__.py  # 修改 __version__

# 2. 同步 VERSION 文件
python scripts/package.py --sync-version

# 3. 更新 CHANGELOG
vim customers/CHANGELOG.md

# 4. 提交
git add -A
git commit -m "release: v0.x.x"
git tag v0.x.x

# 5. 打包所有客户
python scripts/package.py --all

# 6. 分发
# 将 dist/loomgraph-{customer}-v{version}.tar.gz 发送给客户
```

## 模板变量

README.template.md 中使用 `{{变量名}}` 占位符：

| 变量 | 来源 | 说明 |
|------|------|------|
| `{{customer_name}}` | customers.yaml | 客户名称 |
| `{{lightrag_url}}` | customers.yaml | LightRAG API 地址 |
| `{{language_hint}}` | customers.yaml | 主要语言 (Java/PHP/Python) |
| `{{language_parser}}` | customers.yaml | codeindex 解析器 |
| `{{exclude_dirs}}` | customers.yaml | 排除目录 |
| `{{version}}` | VERSION 文件 | 当前版本号 |

## 打包输出

```
dist/
├── loomgraph-zcyl-v0.2.1.tar.gz
└── loomgraph-pinbianyi-v0.2.1.tar.gz
```

每个包包含：
- `README.md` - 从模板生成的客户专用说明
- `CHANGELOG.md` - 变更日志
- `config.yaml` - 客户服务配置
- `src/` - 源代码
- `skills/` - Claude Code Skills
- `pyproject.toml` - 安装配置

## 安全注意事项

以下文件包含敏感信息，已加入 .gitignore：

- `customers/customers.yaml` - 客户列表和内部 URL
- `customers/*/config.yaml` - 客户服务配置
- `customers/*/` - 客户目录

**切勿将这些文件提交到 GitHub！**
