# GitHub Token 管理指南

## 概述

LoomGraph 作为企业私有项目，需要为每个在线客户创建独立的 GitHub Access Token，用于：
- 通过 pip 安装特定版本：`pip install "loomgraph @ git+https://TOKEN@github.com/...@v0.8.0"`
- 克隆仓库进行本地开发

## Token 类型选择

| 类型 | 适用场景 | 优势 | 劣势 |
|------|----------|------|------|
| **Fine-grained PAT** (推荐) | 企业客户 | 仓库级权限、可设置过期时间、可限制 IP | 需要 GitHub Pro |
| **Classic PAT** | 个人/小团队 | 简单易用 | 权限粒度粗、不支持 IP 限制 |
| **Deploy Keys** | CI/CD | 只读单仓库、无需用户账号 | 不支持 pip install |

**推荐使用 Fine-grained PAT**，本指南以此为准。

---

## 创建 Token（仓库所有者操作）

### Step 1: 访问 GitHub Settings

```
https://github.com/settings/tokens?type=beta
```

或手动导航：
```
GitHub 右上角头像 → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token
```

### Step 2: 填写 Token 信息

| 字段 | 填写内容 | 说明 |
|------|---------|------|
| **Token name** | `loomgraph-客户名-YYYYMMDD` | 如 `loomgraph-zcyl-20260224` |
| **Description** | `智采云链访问 LoomGraph 仓库` | 便于后续识别 |
| **Expiration** | `90 days`（或自定义） | 建议不超过 1 年 |
| **Resource owner** | `dreamlx`（你的账号） | 仓库所属组织 |
| **Repository access** | `Only select repositories` | 选择 `LoomGraph` |

### Step 3: 设置权限（最小权限原则）

**必需权限**：
- ✅ **Contents**: `Read-only`（读取代码）
- ✅ **Metadata**: `Read-only`（自动包含，读取仓库元数据）

**不需要的权限（全部不勾选）**：
- ❌ Issues
- ❌ Pull requests
- ❌ Workflows
- ❌ Secrets
- ❌ Administration

### Step 4: 可选 - IP 白名单（企业推荐）

如果客户有固定 IP：
```
Restrict to specific IP addresses:
- 203.0.113.0/24  (客户办公网段)
```

### Step 5: 生成并保存

1. 点击 **Generate token**
2. **立即复制 token**（格式：`github_pat_xxxxx...`，只显示一次！）
3. 保存到安全位置（见下文"Token 存储"）

---

## Token 分配与跟踪

### 在 customers.yaml 中记录

更新 `customers/customers.yaml`，添加 token 相关字段：

```yaml
zcyl:
  name: "智采云链"
  contact: "张三 <zhangsan@zcyl.com>"

  # GitHub Token 信息（敏感，不提交 Git）
  github_token_name: "loomgraph-zcyl-20260224"
  github_token_created: "2026-02-24"
  github_token_expires: "2026-05-25"
  github_token_last_4: "a1b2"  # token 最后 4 位，便于识别

  # 服务配置
  lightrag_url: "http://x.x.x.x:3020"
  language_hint: "Java"
  language_parser: "ai-codeindex[java]"
  exclude_dirs: "target/, build/"

pinbianyi:
  name: "拼便宜"
  contact: "李四 <lisi@pinbianyi.com>"

  github_token_name: "loomgraph-pinbianyi-20260224"
  github_token_created: "2026-02-24"
  github_token_expires: "2026-05-25"
  github_token_last_4: "c3d4"

  lightrag_url: "http://x.x.x.x:3010"
  language_hint: "PHP"
  language_parser: "ai-codeindex[php]"
  exclude_dirs: "vendor/, cache/"
```

**安全注意事项**：
- ✅ `customers.yaml` 已在 `.gitignore`，不会提交到 GitHub
- ✅ 不要将完整 token 写入配置文件
- ✅ 仅记录 token 名称和最后 4 位（用于在 GitHub 界面识别）

---

## Token 存储方案

### 方案 A: 密码管理器（推荐）

**推荐工具**：1Password / Bitwarden / LastPass

**存储结构**：
```
Vault: LoomGraph 客户 Tokens
├─ zcyl-token
│  ├─ Token: github_pat_xxxxxxxxxxxxx
│  ├─ 客户: 智采云链
│  ├─ 创建日期: 2026-02-24
│  ├─ 过期日期: 2026-05-25
│  └─ 用途: pip install
├─ pinbianyi-token
   └─ ...
```

### 方案 B: 本地加密文件

如果没有密码管理器，使用 GPG 加密：

```bash
# 创建 tokens 文件
cat > customers/tokens.txt << EOF
# LoomGraph 客户 GitHub Tokens
# 格式: 客户名|Token|创建日期|过期日期

zcyl|github_pat_xxxxx|2026-02-24|2026-05-25
pinbianyi|github_pat_yyyyy|2026-02-24|2026-05-25
EOF

# 加密（需要先配置 GPG key）
gpg -c customers/tokens.txt  # 输入密码
rm customers/tokens.txt       # 删除明文

# 解密查看
gpg -d customers/tokens.txt.gpg
```

**注意**：`customers/tokens.txt.gpg` 也需加入 `.gitignore`

---

## Token 交付流程

### Step 1: 生成安装命令

```bash
# 为客户生成个性化安装命令
TOKEN="github_pat_xxxxxxxxxxxxx"
VERSION="v0.8.0"

cat > install_command_zcyl.txt << EOF
# 智采云链 - LoomGraph 安装命令
# 有效期至: 2026-05-25
# 请妥善保管此 token，切勿分享给他人

pip install "loomgraph @ git+https://${TOKEN}@github.com/dreamlx/LoomGraph.git@${VERSION}"

# 或使用环境变量（推荐）
export LOOMGRAPH_TOKEN="${TOKEN}"
pip install "loomgraph @ git+https://\${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@${VERSION}"
EOF
```

### Step 2: 安全交付

**方式 1: 加密邮件**（推荐）
- 使用 ProtonMail / Tutanota 等端到端加密邮件
- 或使用 GPG 加密附件

**方式 2: 企业即时通讯**
- 企业微信/钉钉的"密聊"功能
- Telegram Secret Chat

**方式 3: 密码管理器共享**
- 1Password 的 Share Vault 功能
- Bitwarden Send（一次性链接）

**禁止方式**：
- ❌ 明文邮件
- ❌ 未加密的聊天记录截图
- ❌ Word/PDF 文档（容易泄漏）

---

## Token 生命周期管理

### 定期检查（每月 1 号）

运行管理脚本（见下文）：

```bash
python scripts/manage_tokens.py --check-expiry
```

输出示例：
```
🔍 检查 GitHub Tokens 过期情况...

⚠️  即将过期（30 天内）:
  - zcyl (loomgraph-zcyl-20260224): 25 天后过期
  - pinbianyi (loomgraph-pinbianyi-20260224): 25 天后过期

✅ 正常:
  - trial (loomgraph-trial-20260301): 65 天后过期

💡 建议: 为即将过期的客户创建新 token
```

### 续期流程

**提前 30 天**通知客户：

```
【LoomGraph Token 即将过期通知】

尊敬的智采云链技术团队：

您的 LoomGraph 访问 Token 将在 25 天后（2026-05-25）过期。
为避免影响正常使用，我们已为您生成新的 Token（有效期至 2026-08-25）。

新安装命令（已通过企业微信密聊发送）:
pip install "loomgraph @ git+https://NEW_TOKEN@github.com/...@v0.9.0"

操作建议：
1. 立即更新本地环境变量
2. 更新 CI/CD 配置中的 token
3. 旧 token 将在过期后自动失效

如有疑问，请联系技术支持。
```

### 撤销 Token

**场景**：
- 客户合同到期
- Token 泄漏/安全事件
- 员工离职

**操作步骤**：
1. 访问 https://github.com/settings/tokens?type=beta
2. 找到对应 token（通过名称 `loomgraph-客户名-日期`）
3. 点击 **Revoke** 按钮
4. 确认撤销

**通知客户**（如果是正常到期）：
```
【Token 已撤销通知】

您的 LoomGraph Token (loomgraph-zcyl-20260224) 已按计划撤销。
如需继续使用，请联系我们获取新 token。
```

---

## Token 管理脚本

创建 `scripts/manage_tokens.py` 辅助管理：

### 功能清单

- ✅ 检查即将过期的 token
- ✅ 生成安装命令
- ✅ 记录 token 创建历史
- ✅ 检测 GitHub API 中的 token 状态

### 使用示例

```bash
# 检查过期情况
python scripts/manage_tokens.py --check-expiry

# 为新客户生成安装命令
python scripts/manage_tokens.py --generate-install zcyl --version v0.8.0

# 列出所有客户 token 状态
python scripts/manage_tokens.py --list

# 验证 token 是否有效（通过 GitHub API）
python scripts/manage_tokens.py --verify zcyl
```

（脚本代码见下文）

---

## 客户使用指南

### 方式 1: 环境变量（推荐）

**优势**：token 不会出现在命令历史中

```bash
# 设置环境变量（添加到 ~/.bashrc 或 ~/.zshrc）
export LOOMGRAPH_TOKEN="github_pat_xxxxxxxxxxxxx"

# 安装
pip install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.8.0"

# 或在 CI/CD 中使用 secret
pip install "loomgraph @ git+https://${GITHUB_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.8.0"
```

### 方式 2: 直接在命令中使用

**注意**：token 会留在 shell 历史中，使用后建议清理 history

```bash
pip install "loomgraph @ git+https://github_pat_xxxxx@github.com/dreamlx/LoomGraph.git@v0.8.0"

# 清理历史（bash）
history -d $(history 1 | awk '{print $1}')

# 清理历史（zsh）
fc -W; fc -R
```

### 方式 3: pip.conf 配置文件

对于频繁安装的场景：

```bash
# ~/.config/pip/pip.conf
[global]
extra-index-url = https://github_pat_xxxxx@github.com/dreamlx/LoomGraph/releases
```

---

## 安全最佳实践

### ✅ DO（推荐做法）

1. **每客户独立 token**：便于单独撤销，不影响其他客户
2. **设置过期时间**：最长不超过 1 年，常规客户 90 天
3. **最小权限原则**：只给 `Contents: Read-only`
4. **IP 白名单**：如果客户有固定 IP，务必配置
5. **定期审计**：每月检查一次 token 使用情况
6. **安全交付**：使用加密渠道，不留明文记录
7. **记录元数据**：在 customers.yaml 中记录创建/过期日期

### ❌ DON'T（禁止做法）

1. ❌ **共用 token**：多个客户使用同一个 token（无法单独撤销）
2. ❌ **无过期时间**：token 永久有效（泄漏风险高）
3. ❌ **过高权限**：给 Write/Admin 权限（客户可能误改代码）
4. ❌ **明文传输**：通过未加密邮件/IM 发送
5. ❌ **提交到 Git**：token 写入代码仓库（即使是私有仓库）
6. ❌ **不记录**：不知道哪个 token 给了哪个客户
7. ❌ **忘记撤销**：客户合同到期后 token 仍然有效

---

## 常见问题

### Q1: Token 泄漏了怎么办？

**立即操作**：
1. 访问 GitHub → Settings → Tokens，撤销该 token
2. 为客户创建新 token
3. 通知客户更新（如果客户主动报告泄漏）
4. 审查 GitHub Insights → Traffic 查看是否有异常访问

### Q2: 客户说 token 无效？

**排查步骤**：
```bash
# 1. 验证 token 格式
echo $TOKEN | grep "^github_pat_"

# 2. 测试 token 是否有效
curl -H "Authorization: Bearer $TOKEN" \
     https://api.github.com/repos/dreamlx/LoomGraph

# 3. 检查 token 是否过期
# 访问 https://github.com/settings/tokens?type=beta

# 4. 检查客户 IP 是否在白名单
```

### Q3: 如何批量续期？

**脚本化**（推荐使用 GitHub API）：
```bash
# 使用管理脚本
python scripts/manage_tokens.py --renew-all --days 90
```

### Q4: Deploy Key 与 PAT 的区别？

| 特性 | Fine-grained PAT | Deploy Key |
|------|-----------------|------------|
| 使用场景 | pip install（人机交互） | CI/CD（机器访问） |
| 权限范围 | 可访问多个仓库 | 单个仓库 |
| 需要用户账号 | 是 | 否 |
| 支持 pip | ✅ | ❌ |
| IP 限制 | ✅ | ❌ |

**结论**：客户使用 pip 安装必须用 PAT，Deploy Key 不适用。

---

## 附录：Token 管理脚本模板

完整脚本见 `scripts/manage_tokens.py`（待创建）。

核心功能：
- YAML 解析 `customers/customers.yaml`
- 过期检查（距离今天 < 30 天）
- GitHub API 验证 token 状态
- 生成安装命令模板
- 记录 token 变更历史

---

## 参考资料

- [GitHub Fine-grained PAT 文档](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token)
- [pip 从私有仓库安装](https://pip.pypa.io/en/stable/topics/authentication/)
- [企业 Token 安全最佳实践](https://owasp.org/www-community/vulnerabilities/API_Keys_and_Tokens)
