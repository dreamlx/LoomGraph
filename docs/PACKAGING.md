# LoomGraph 打包与部署指南

## 概述

LoomGraph 提供两条发布通道：

> **首次 clone 后必跑**: `./scripts/install-hooks.sh` —— 装本地 git
> pre-push hook，会在 tag push 之前自动校验 tag 名 vs pyproject.toml
> 版本，杜绝 v0.12.0 release 那次的 tag-on-wrong-commit 事故。CI 端
> 的 `version-check` job 是兜底，本地 hook 失败更快、错误信息更详细。


| 通道 | 适用场景 | 客户体验 |
|------|----------|----------|
| **在线** | 可访问 GitHub 的客户 | `pip install git+https://...` 一行安装 |
| **离线** | 内网客户 | tarball 内含 wheel，`pip install ./xxx.whl` |

客户配置 (`config.yaml`) 始终手动交付，不打入包内。

## 快速开始（使用 Makefile）

项目提供了统一的 `Makefile` 来简化常用操作。**推荐使用 make 命令**而非直接调用脚本。

### 查看所有可用命令

```bash
make help
```

### 常用命令速查

| 命令 | 说明 |
|------|------|
| `make release VERSION=0.9.0` | 🚀 **完整发布流程**（bump → test → lint → commit → tag → push） |
| `make delivery-summary` | 📋 生成客户交付总结 |
| `make token-list` | 🔑 查看所有客户 Token 状态 |
| `make token-check` | ⏰ 检查即将过期的 Token |
| `make test` | ✅ 运行所有测试 |
| `make lint` | 🔍 代码检查 |
| `make package-all` | 📦 打包所有客户（离线包） |

### 典型工作流示例

**场景 1: 发布新版本**
```bash
# 一键发布（推荐）
make release VERSION=0.9.0

# 等待 GitHub Actions 完成后
make delivery-summary

# 将交付总结发送给客户
cat /tmp/customer_delivery_summary.txt
```

**场景 2: 检查 Token 状态**
```bash
# 查看所有 Token
make token-list

# 检查即将过期的 Token
make token-check

# 验证单个 Token
make token-verify CUSTOMER=customer TOKEN=github_pat_...
```

**场景 3: 开发调试**
```bash
# 运行测试
make test

# 修复 lint 问题
make lint-fix

# 清理临时文件
make clean
```

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

**推荐方式（使用 Makefile）**:

```bash
# 一键发布（自动执行 bump → test → lint → commit → tag → push）
make release VERSION=0.9.0

# 等待 GitHub Actions 完成（~1 分钟），然后生成交付总结
make delivery-summary

# 查看交付总结并发送给客户
cat /tmp/customer_delivery_summary.txt
```

**手动方式（直接调用脚本）**:

```bash
# 1. Bump version（自动更新 pyproject.toml, customers/VERSION, CHANGELOG.md）
python scripts/bump_version.py 0.9.0

# 2. Commit + tag
git add pyproject.toml customers/VERSION CHANGELOG.md
git commit -m "chore: bump version to 0.9.0"
git tag v0.9.0

# 3. Push（触发 CI: test → build → GitHub Release）
git push origin develop --tags

# 4. 生成交付总结（发布成功后）
python scripts/generate_delivery_summary.py

# 5. 通知客户升级
cat /tmp/customer_delivery_summary.txt
# 复制对应客户的命令发送，或直接发送 customers/{customer}/INSTALL.md
```

### 客户 Token 管理

**重要**: GitHub Token 管理是企业项目的安全核心，详见专门文档：

📖 **[TOKEN_MANAGEMENT.md](guides/TOKEN_MANAGEMENT.md)**（完整指南）

**快速要点**：
- ✅ 使用 **Fine-grained Personal Access Token**（推荐，仓库级权限）
- ✅ 每个客户使用**独立 token**（方便单独撤销）
- ✅ 设置**过期时间**（90 天，提前 30 天预警）
- ✅ 最小权限原则：仅 `Contents: Read-only`
- ✅ 在 `customers.yaml` 中记录元数据（名称、创建日期、过期日期）
- ✅ 使用密码管理器（1Password / Bitwarden）存储实际 token
- ✅ 通过加密渠道交付（ProtonMail / 企业微信密聊）

**管理工具**：
```bash
# 检查即将过期的 token
python scripts/manage_tokens.py --check-expiry

# 生成安装命令
python scripts/manage_tokens.py --generate-install customer --version v0.9.0

# 列出所有客户 token 状态
python scripts/manage_tokens.py --list

# 验证 token 是否有效
python scripts/manage_tokens.py --verify customer --token github_pat_xxxxx
```

### CI 工作流

| Workflow | 触发条件 | 步骤 |
|----------|----------|------|
| `test.yml` | PR to develop/main | lint → unit tests |
| `release.yml` | tag push `v*` | lint → test → build wheel → GitHub Release |

### 交付总结生成器

每次 release 发布后，使用 `generate_delivery_summary.py` 生成格式化的客户交付总结：

```bash
# 生成当前版本的交付总结（自动读取 pyproject.toml）
python scripts/generate_delivery_summary.py

# 生成指定版本的交付总结
python scripts/generate_delivery_summary.py --version v0.9.0

# 自定义输出路径
python scripts/generate_delivery_summary.py --output ~/Desktop/delivery.txt

# 直接打印到终端
python scripts/generate_delivery_summary.py --print
```

**生成内容包括**：
- ✅ 每个客户的 pip/pipx 安装命令（含 Token）
- ✅ 服务配置信息（LightRAG URL、语言）
- ✅ Token 过期日期及剩余天数
- ✅ 从 CHANGELOG.md 自动提取的版本亮点
- ✅ 交付方式建议（企业微信/加密邮件）
- ✅ 快速访问链接（GitHub Release、文档）

**输出示例**：
```
═══════════════════════════════════════════════════════════════
  LoomGraph v0.9.0 客户交付包 - 就绪
═══════════════════════════════════════════════════════════════

📦 3 个客户安装包已准备完毕，每个包含：
   ✅ INSTALL.md - 完整安装说明（含 Token）
   ✅ config.yaml - 服务配置文件

───────────────────────────────────────────────────────────────
1️⃣  智采云链（customer）
───────────────────────────────────────────────────────────────

📋 安装命令（复制发送给客户）:
export LOOMGRAPH_TOKEN="github_pat_..."
pip install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/..."
...
```

**使用场景**：
1. **发布后通知客户**：生成总结，复制对应客户的命令发送
2. **批量交付**：一次性生成所有客户的安装信息
3. **版本追溯**：指定旧版本重新生成交付文档

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
