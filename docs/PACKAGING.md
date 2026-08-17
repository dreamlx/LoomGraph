# LoomGraph 打包与发布指南

## 概述

LoomGraph 走**公开 PyPI** 发布（`pipx install loomgraph`）。发布流程由
GitHub Actions（`.github/workflows/release.yml`）驱动：push 一个 `v*` tag → CI
自动跑 test → build wheel/sdist → 发 PyPI（Trusted Publisher，OIDC，无需 token）
→ 发 GitHub Release（从 CHANGELOG 抽取正文）。

本仓库**不再维护**企业客户私有分发框架（GitHub PAT / 离线 tarball / 客户专属
INSTALL.md 已于 v0.16+ 移除）。

## 发布流程

### 1. bump 版本（三处一致）

版本唯一 source of truth 是 `pyproject.toml` 的 `version`。发布前确保三处一致：

| 文件 | 内容 |
|------|------|
| `pyproject.toml` | `version = "x.y.z"`（权威） |
| `customers/VERSION` | `x.y.z`（CI version-check 校验） |
| `CHANGELOG.md` | `[Unreleased]` → `[x.y.z] - YYYY-MM-DD` |

一键 bump（更新 pyproject + VERSION + CHANGELOG）：

```bash
python scripts/bump_version.py 0.16.0
```

或手动改三处。校验一致性：

```bash
python scripts/bump_version.py --check
```

### 1.5. self-dogfood gate（push tag 前必跑，人工执行）

`release.yml` 跑 ruff + pytest，但 CI 测不到"装机后真实索引 + 查询链路是否
正常"——v0.19.0 的 status/codeindex 路径漂移和 debt git 维度 cliff 都是 CI
全绿却 ship 到 PyPI 的 bug，靠发版前在**目标装机环境**跑一遍自查才暴露。

push `v*` tag 前在当前仓跑（.venv 已 `uv sync`，代表用户装机后的真实依赖）：

```bash
loomgraph index . --clear && loomgraph status && loomgraph debt --with-git
```

确认三点（任一异常 → **停，先修，不要打 tag**）：

- `index`：`entities_created > 0`、`resolved_ratio` 非 0、无 `WARNING:`
- `status`：`codeindex.version` 与 `loomgraph codeindex --version` **一致**
  （`path` 应是 venv python，不是 PATH 上的别的 binary — #76 PATH-bypass
  类的正反两面都靠这个判据抓）
- `debt`：`overall_health.breakdown.git` 不是 0-cliff（有 git 信号的仓
  应在 0–100 之间，不是非 0 即 100）；`issues[].source` 字段存在

> 这是人工 gate，不做进 CI。CI 只跑静态测试；self-dogfood 是"装机后真值"
> 的唯一来源。若自查发现 bug，修完重跑，**bug 修复不进同一 tag**（要么
> 升 patch 重发，要么若已 push tag 删 tag 重打——但 PyPI 不可覆盖，慎之）。

### 2. commit + tag + push

```bash
git add pyproject.toml customers/VERSION CHANGELOG.md
git commit -m "chore: bump version to 0.16.0"
git tag v0.16.0
git push origin main --tags
```

`.githooks/pre-push`（`scripts/install-hooks.sh` 安装）会在 push tag 前校验 tag
版本 == pyproject 版本 == VERSION，防止 tag 打错 commit。CI 的 `version-check`
job 是兜底。

### 3. CI 自动完成（release.yml）

push `v*` tag 后，`release.yml` 依次跑：

| job | 作用 |
|-----|------|
| `version-check` | tag vs pyproject vs VERSION 三处一致，不一致 fail-fast |
| `test` | Python 3.11 + 3.12，ruff + pytest tests/unit/ |
| `build` | `python -m build` 出 wheel + sdist，`twine check` 校验元数据 |
| `publish-pypi` | Trusted Publisher（OIDC）发 PyPI，**无需 API token** |
| `github-release` | 从 CHANGELOG.md 抽取本版本正文，建 GitHub Release，附 wheel/sdist |

约 1-2 分钟完成。验证：

```bash
pipx install loomgraph        # 应装到新版本
loomgraph version             # 预期 x.y.z
```

## CHANGELOG 维护策略

项目维护两份 CHANGELOG，面向不同读者：

| | `CHANGELOG.md`（根目录） | `customers/CHANGELOG.md` |
|---|---|---|
| **读者** | 开发者、AI Agent | 客户侧 Claude Code |
| **内容** | 全部变更（含 refactor、fix、docs） | 仅用户可感知的功能变更 |
| **格式** | [Keep a Changelog](https://keepachangelog.com) 英文 | 中文，含「更新方式」和「版本对比表」 |
| **更新时机** | 开发中随手更新 `[Unreleased]` | 发布时从根 CHANGELOG 挑选 |

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

1. `bump_version.py` 自动把 `[Unreleased]` → `[x.y.z] - date`，并补新空 `[Unreleased]`。
2. 从中挑选**客户可见项**写入 `customers/CHANGELOG.md`。
3. 提交两份 CHANGELOG 一起进 release commit。

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

## 安全注意事项

- **PyPI 发布**走 Trusted Publisher（OIDC），无需在 GitHub 存 PyPI token。配置在
  https://pypi.org/manage/project/loomgraph/settings/publishing/ 。
- **历史遗留**：v0.9.x 时代曾用 GitHub PAT 做私有分发，3 个 PAT 明文入了 git 历史
  （ba9feea 等，[customer]/[customer]/demo）。这些 token created 2026-02-24、90 天应已过期，
  但请到 https://github.com/settings/tokens 确认已 revoke 并 rotate。`git filter-repo`
  擦历史是破坏性操作，单独决策。
