# LoomGraph 客户交付指南

## 📦 已准备的客户安装包

本目录包含 3 个客户的完整安装包，每个客户包含：
- `INSTALL.md` - 安装说明（含 Token）
- `config.yaml` - 服务配置文件

---

## 1️⃣ 智采云链（zcyl）

**目录**: `customers/zcyl/`

**安装命令**（pip）:
```bash
export LOOMGRAPH_TOKEN="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"
pip install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.9.2"
```

**安装命令**（pipx）:
```bash
export LOOMGRAPH_TOKEN="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"
pipx install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.9.2"
```

**配置信息**:
- LightRAG: `http://117.131.45.179:3020`
- 语言: Java
- Token 过期: 2026-05-25

**交付方式**: 企业微信密聊

---

## 2️⃣ 拼便宜（pinbianyi）

**目录**: `customers/pinbianyi/`

**安装命令**（pip）:
```bash
export LOOMGRAPH_TOKEN="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"
pip install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.9.2"
```

**安装命令**（pipx）:
```bash
export LOOMGRAPH_TOKEN="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"
pipx install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.9.2"
```

**配置信息**:
- LightRAG: `http://117.131.45.179:3010`
- 语言: PHP
- Token 过期: 2026-05-25

**交付方式**: 企业微信密聊

---

## 3️⃣ Demo 测试用户（demo）

**目录**: `customers/demo/`

**安装命令**（pip）:
```bash
export LOOMGRAPH_TOKEN="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"
pip install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.9.2"
```

**安装命令**（pipx）:
```bash
export LOOMGRAPH_TOKEN="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"
pipx install "loomgraph @ git+https://${LOOMGRAPH_TOKEN}@github.com/dreamlx/LoomGraph.git@v0.9.2"
```

**配置信息**:
- LightRAG: `http://117.131.45.179:3030`
- 语言: Python
- Token 过期: 2026-05-25

**交付方式**: 内部测试

---

## 📋 交付检查清单

### 交付前检查

- [x] 所有 Token 已验证有效
- [x] config.yaml 配置正确（LightRAG URL）
- [x] INSTALL.md 说明完整清晰
- [x] Token 已保存到密码管理器（作为备份）

### 交付后跟踪

- [ ] 客户已收到安装包
- [ ] 客户已成功安装
- [ ] 客户已验证 `loomgraph status` 通过
- [ ] 客户已完成首次索引

---

## 🔐 安全提醒

1. **交付渠道**:
   - ✅ 企业微信密聊
   - ✅ 加密邮件（ProtonMail）
   - ❌ 明文邮件
   - ❌ 微信公众号/群聊

2. **Token 管理**:
   - ✅ 所有 Token 过期日期: 2026-05-25
   - ✅ 提前 30 天预警（2026-04-25）
   - ✅ 每月 1 号运行: `python scripts/manage_tokens.py --check-expiry`

3. **文件保护**:
   - ✅ `customers/*/` 目录已在 `.gitignore`
   - ✅ 不会提交到 GitHub
   - ✅ 仅本地保存

---

## 📞 技术支持流程

### 客户遇到问题时

1. **安装问题**:
   ```bash
   # 验证 Token 是否有效
   python scripts/manage_tokens.py --verify <客户ID> --token <TOKEN>
   ```

2. **连接问题**:
   - 检查客户网络是否能访问 H200 服务器（117.131.45.179）
   - 验证 LightRAG 端口是否正确（zcyl:3020, pinbianyi:3010, demo:3030）

3. **Token 过期**:
   - 访问 https://github.com/settings/tokens?type=beta
   - 为客户创建新 Token
   - 更新 `customers.yaml` 和客户的 INSTALL.md

---

## 📊 当前状态

| 客户 | Token 状态 | 配置状态 | 交付状态 |
|------|-----------|---------|---------|
| zcyl | ✅ 有效（90天） | ✅ 已准备 | ⏳ 待交付 |
| pinbianyi | ✅ 有效（90天） | ✅ 已准备 | ⏳ 待交付 |
| demo | ✅ 有效（90天） | ✅ 已准备 | ⏳ 待交付 |

**下一步**: 通过安全渠道发送给客户

---

## 🛠️ 管理工具快速参考

```bash
# 查看所有客户状态
python scripts/manage_tokens.py --list

# 检查过期情况（每月 1 号）
python scripts/manage_tokens.py --check-expiry

# 验证 Token
python scripts/manage_tokens.py --verify zcyl --token <TOKEN>

# 重新生成安装命令
python scripts/manage_tokens.py --generate-install zcyl --version v0.9.2
```

---

**准备完成！现在可以交付给客户了。** 🎉
