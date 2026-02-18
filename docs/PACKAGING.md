# LoomGraph 打包与部署指南

## 概述

LoomGraph 提供两条发布通道：

| 通道 | 适用场景 | 客户体验 |
|------|----------|----------|
| **在线** | 可访问 GitHub 的客户 | `pip install git+https://...` 一行安装 |
| **离线** | 内网客户 | tarball 内含 wheel，`pip install ./xxx.whl` |

客户配置 (`config.yaml`) 始终手动交付，不打入包内。

## 目录结构

```
customers/
├── README.template.md      # 公开模板（GitHub）
├── CHANGELOG.md            # 公开变更日志（GitHub）
├── VERSION                 # 公开版本号（GitHub）
├── customers.yaml.example  # 公开配置示例（GitHub）
├── customers.yaml          # 客户注册表（本地私有）
├── customer/
│   └── config.yaml         # 客户配置（本地私有）
└── customer/
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
customer:
  name: "智采云链"
  lightrag_url: "http://x.x.x.x:3020"
  language_hint: "Java"
  language_parser: "ai-codeindex[java]"
  exclude_dirs: "target/, build/"

customer:
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

## 在线发布流程

### 标准发布步骤

```bash
# 1. Bump version（自动更新 pyproject.toml, customers/VERSION, CHANGELOG.md）
python scripts/bump_version.py 0.2.5

# 2. Commit + tag
git add pyproject.toml customers/VERSION CHANGELOG.md
git commit -m "chore: bump version to 0.2.5"
git tag v0.2.5

# 3. Push（触发 CI: test → build → GitHub Release）
git push origin develop --tags

# 4. 通知客户升级
#    pip install --upgrade "loomgraph @ git+https://TOKEN@github.com/dreamlx/LoomGraph.git@v0.2.5"
```

### 客户 Token 管理

- 创建 GitHub Personal Access Token (PAT)，仅限 `contents:read` 权限
- 每个客户使用独立 token，方便单独撤销
- Token 通过安全渠道（加密邮件/即时通讯）交付

### CI 工作流

| Workflow | 触发条件 | 步骤 |
|----------|----------|------|
| `test.yml` | PR to develop/main | lint → unit tests |
| `release.yml` | tag push `v*` | lint → test → build wheel → GitHub Release |

## 离线发布流程

### 打包命令

```bash
# 激活虚拟环境
source .venv/bin/activate

# 列出所有客户
python scripts/package.py --list

# 打包单个客户（自动构建 wheel）
python scripts/package.py --customer customer

# 打包所有客户
python scripts/package.py --all

# 同步版本号
python scripts/package.py --sync-version
```

### 离线包内容

```
loomgraph-customer-v0.2.5/
├── README.md                              # 从模板生成的安装指南
├── CHANGELOG.md                           # 客户可见变更日志
├── loomgraph-0.2.5-py3-none-any.whl       # 预构建 wheel（首选安装方式）
├── pyproject.toml                         # 备用（可从源码安装）
├── LICENSE
└── src/                                   # 源码备用
```

> **注意**: config.yaml 不再打入包内，由技术团队手动交付。

### 离线安装流程

```bash
# 解压
tar xzf loomgraph-customer-v0.2.5.tar.gz
cd loomgraph-customer-v0.2.5

# 创建虚拟环境
python3 -m venv ~/.loomgraph-venv
source ~/.loomgraph-venv/bin/activate

# 安装 wheel（比 pip install . 更快）
pip install ./loomgraph-*.whl

# 安装 Skills
loomgraph install-skills

# 配置（config.yaml 由技术团队提供）
mkdir -p ~/.config/loomgraph
cp /path/to/config.yaml ~/.config/loomgraph/config.yaml

# 验证
loomgraph status
```

## CHANGELOG 维护策略

项目维护**两份 CHANGELOG**，面向不同读者：

| | `CHANGELOG.md`（根目录） | `customers/CHANGELOG.md` |
|---|---|---|
| **读者** | 开发者、AI Agent | 客户侧 Claude Code |
| **内容** | 全部变更（含 refactor、fix、docs） | 仅用户可感知的功能变更 |
| **格式** | [Keep a Changelog](https://keepachangelog.com) 英文 | 中文，含「更新方式」和「版本对比表」 |
| **更新时机** | 开发中随手更新 `[Unreleased]` | 打包发布时从根 CHANGELOG 挑选 |

### 日常开发

开发中向根 `CHANGELOG.md` 的 `[Unreleased]` 区追加条目：

```markdown
## [Unreleased]

### Added
- New feature description

### Fixed
- Bug fix description
```

### 发布时

1. `[Unreleased]` → `[0.x.x] - YYYY-MM-DD`
2. 从中挑选**客户可见项**写入 `customers/CHANGELOG.md`
3. 添加新的空 `[Unreleased]` 区

### 哪些写入客户 CHANGELOG？

| 变更类型 | 根 CHANGELOG | 客户 CHANGELOG |
|----------|:---:|:---:|
| 新 CLI 命令 / 选项 | ✅ | ✅ |
| 行为变更 / Breaking Change | ✅ | ✅ |
| 性能提升（用户可感知） | ✅ | ✅ |
| 内部重构 | ✅ | ❌ |
| 测试改进 | ✅ | ❌ |
| 文档 / ADR | ✅ | ❌ |
| Bug 修复（内部） | ✅ | ❌ |

## 模板变量

README.template.md 中使用 `{{变量名}}` 占位符：

| 变量 | 来源 | 说明 |
|------|------|------|
| `{{customer_name}}` | customers.yaml | 客户名称 |
| `{{lightrag_url}}` | customers.yaml | LightRAG API 地址 |
| `{{language_hint}}` | customers.yaml | 主要语言 (Java/PHP/Python) |
| `{{language_parser}}` | customers.yaml | codeindex 解析器 |
| `{{exclude_dirs}}` | customers.yaml | 排除目录 |
| `{{version}}` | pyproject.toml | 当前版本号 |

## 安全注意事项

以下文件包含敏感信息，已加入 .gitignore：

- `customers/customers.yaml` - 客户列表和内部 URL
- `customers/*/config.yaml` - 客户服务配置
- `customers/*/` - 客户目录

**切勿将这些文件提交到 GitHub！**
