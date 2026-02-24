# GitHub Token 管理 - 快速开始

## 📌 5 分钟上手指南

### 场景 1: 为新客户创建 Token

```bash
# Step 1: 访问 GitHub Settings
open https://github.com/settings/tokens?type=beta

# Step 2: 点击 "Generate new token"，填写:
#   - Token name: loomgraph-客户名-20260224
#   - Expiration: 90 days
#   - Repository access: Only select repositories → LoomGraph
#   - Permissions: Contents (Read-only)

# Step 3: 复制生成的 token（只显示一次！）
#   格式: github_pat_xxxxxxxxxxxxxxxxxxxxx

# Step 4: 保存到密码管理器
#   1Password Vault: LoomGraph 客户 Tokens
#   项目名: zcyl-token
#   内容: github_pat_xxxxx

# Step 5: 记录到 customers.yaml
vim customers/customers.yaml
```

添加以下内容：
```yaml
zcyl:
  name: "智采云链"
  contact: "张三 <zhangsan@zcyl.com>"

  github_token_name: "loomgraph-zcyl-20260224"
  github_token_created: "2026-02-24"
  github_token_expires: "2026-05-25"
  github_token_last_4: "a1b2"  # token 最后 4 位

  lightrag_url: "http://x.x.x.x:3020"
  language_hint: "Java"
  language_parser: "ai-codeindex[java]"
  exclude_dirs: "target/, build/"
```

```bash
# Step 6: 生成安装命令
python scripts/manage_tokens.py --generate-install zcyl --version v0.8.0

# Step 7: 通过企业微信密聊发送给客户（替换 YOUR_GITHUB_TOKEN）
```

---

### 场景 2: 定期检查 Token 过期情况

```bash
# 每月 1 号运行
python scripts/manage_tokens.py --check-expiry

# 输出示例:
# ⚠️  即将过期（30 天内）:
#   - zcyl (loomgraph-zcyl-20260224): 25 天后过期
#
# ✅ 正常:
#   - trial (loomgraph-trial-20260301): 65 天后过期

# 为即将过期的客户创建新 token（重复场景 1）
```

---

### 场景 3: Token 泄漏应急处理

```bash
# Step 1: 立即撤销
open https://github.com/settings/tokens?type=beta
# 找到泄漏的 token → 点击 Revoke

# Step 2: 创建新 token（场景 1）

# Step 3: 通知客户更新
```

---

### 场景 4: 客户合同到期

```bash
# Step 1: 撤销 token
open https://github.com/settings/tokens?type=beta

# Step 2: 从 customers.yaml 移除或注释该客户

# Step 3: 归档客户配置
mkdir -p customers/archived
mv customers/客户名 customers/archived/
```

---

## 🛠️ 管理工具速查

| 命令 | 用途 | 频率 |
|------|------|------|
| `--check-expiry` | 检查过期情况 | 每月 1 号 |
| `--list` | 查看所有 token | 按需 |
| `--generate-install` | 生成安装命令 | 新客户/续期 |
| `--verify` | 验证 token 有效性 | 故障排查 |

---

## 📋 客户安装指南（发给客户）

### 推荐方式（环境变量）

```bash
# 将 token 保存到环境变量（添加到 ~/.bashrc 或 ~/.zshrc）
export LOOMGRAPH_TOKEN="github_pat_xxxxxxxxxxxxx"

# 安装最新版本
pip install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.8.0"

# 验证安装
loomgraph version
```

### CI/CD 集成

```yaml
# GitHub Actions
steps:
  - name: Install LoomGraph
    env:
      LOOMGRAPH_TOKEN: ${{ secrets.LOOMGRAPH_TOKEN }}
    run: |
      pip install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.8.0"
```

```groovy
// Jenkins
withCredentials([string(credentialsId: 'loomgraph-token', variable: 'LOOMGRAPH_TOKEN')]) {
    sh '''
        pip install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.8.0"
    '''
}
```

---

## ⚠️ 安全检查清单

创建 Token 时必须确认：
- [ ] Token 名称包含客户名和日期（便于识别）
- [ ] 设置了过期时间（≤ 90 天）
- [ ] 权限仅限 `Contents: Read-only`（最小权限）
- [ ] 仅授权 LoomGraph 仓库（不是所有仓库）
- [ ] 如果客户有固定 IP，配置了 IP 白名单
- [ ] Token 保存到密码管理器（不是明文文件）
- [ ] 在 customers.yaml 中记录了元数据

交付 Token 时必须确认：
- [ ] 使用加密渠道（企业微信密聊/ProtonMail）
- [ ] 不通过明文邮件/未加密 IM 发送
- [ ] 不截图（截图可能留存在云端）
- [ ] 提醒客户妥善保管（不要分享给他人）

---

## 🔗 相关文档

| 文档 | 内容 |
|------|------|
| [TOKEN_MANAGEMENT.md](TOKEN_MANAGEMENT.md) | 完整 Token 管理指南 |
| [PACKAGING.md](../PACKAGING.md) | 打包与部署流程 |
| `scripts/manage_tokens.py --help` | 管理工具使用说明 |

---

## ❓ 常见问题

### Q: Token 能用多久？
**A**: 建议 90 天，最长不超过 1 年。系统会在过期前 30 天预警。

### Q: 一个 Token 能给多个客户用吗？
**A**: ❌ 不推荐。每个客户独立 token，方便单独撤销。

### Q: Token 泄漏了怎么办？
**A**: 立即访问 GitHub Settings 撤销，然后创建新 token。

### Q: 客户说 401 Unauthorized？
**A**: 可能原因：
1. Token 过期（检查 `--check-expiry`）
2. Token 被撤销（在 GitHub 上确认）
3. 客户 IP 不在白名单（如果配置了 IP 限制）

### Q: 如何批量续期？
**A**:
```bash
# 1. 检查即将过期的客户
python scripts/manage_tokens.py --check-expiry

# 2. 为每个客户创建新 token（GitHub UI）
# 3. 更新 customers.yaml
# 4. 通知客户更新
```

---

**需要帮助？** 查看 [TOKEN_MANAGEMENT.md](TOKEN_MANAGEMENT.md) 完整文档
