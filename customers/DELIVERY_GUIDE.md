# LoomGraph 客户交付指南

> ⚠️ **历史文档（LightRAG + GitHub TOKEN 私有分发时代）**：本指南记录的是 v0.9.x 时代的
> 客户交付流程，使用 GitHub PAT 私有分发 + 远程 LightRAG 服务。**v0.16+ 起 LoomGraph 已
> 走公开 PyPI（`pipx install loomgraph`）+ 本地 SQLite，不再需要 TOKEN / LightRAG / 远程
> endpoint。** 本文件保留作历史追溯，新客户交付请用 `customers/README.template.md`。
>
> ⚠️ **安全**：历史提交（ba9feea 等）曾含真实 GitHub PAT 明文（customer/customer/demo 各 2 个）。
> 当前文件已脱敏，但 **git 历史仍含明文 token**。这些 token 应已过期（created 2026-02-24，
> 90 天），但请到 https://github.com/settings/tokens 确认已 revoke 并 rotate。

---

## 历史客户（v0.9.x 时代，已迁移或停用）

历史上本目录包含 3 个客户安装包，每个含 `INSTALL.md`（含 Token）+ `config.yaml`（LightRAG 配置）：

| 客户 | 语言 | 历史远程 endpoint | 历史交付方式 |
|------|------|------------------|-------------|
| 智采云链（customer） | Java | internal.example.invalid:3020 | 企业微信密聊 |
| 拼便宜（customer） | PHP | internal.example.invalid:3010 | 企业微信密聊 |
| Demo 测试用户（demo） | Python | internal.example.invalid:3030 | 内部测试 |

> internal.example.invalid（H200）已于 2026-07 退役。上述客户如仍在用，需迁移到本地 SQLite 架构
> （`pipx install loomgraph` + `loomgraph index .`，见 README.template.md）。

---

## 历史 Token 管理（已弃用）

历史上用 `scripts/manage_tokens.py` 管理 GitHub PAT：

```bash
python scripts/manage_tokens.py --list
python scripts/manage_tokens.py --check-expiry
python scripts/manage_tokens.py --verify <客户ID> --token <TOKEN>
```

> 公开 PyPI 时代无需 TOKEN。`manage_tokens.py` 脚本保留作历史参考，新流程不用。

---

## 当前交付流程（v0.16+）

见 [`customers/README.template.md`](README.template.md)：

1. 客户执行 `pipx install loomgraph`（公开 PyPI，无需 TOKEN）
2. 按需装语言 extra：`pipx install --force loomgraph[java]`
3. `loomgraph index .` 索引（本地 SQLite，零配置）
4. 配置 MCP（Claude Code/Cursor）：`loomgraph mcp install-config`

交付物仅是这份 README（由 `scripts/package.py` 从 template + `customers.yaml` 生成），
不再需要 `INSTALL.md` / `config.yaml` / TOKEN。
