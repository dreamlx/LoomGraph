# AGENTS.md

Codex 入口。本仓权威开发规范在 **[CLAUDE.md](CLAUDE.md)** —— 先读它(项目结构、
「操作前必读清单」、TDD 规则、发版 gate、整理 manifest 全在里面)。本文件只补
CLAUDE.md 之外、从 repo 推导不出的增量。

## 协作要点

- **网络**:git push / `gh` 偶发超时,加前缀 `HTTPS_PROXY=http://127.0.0.1:7890 <cmd>`
- **本地环境**:`source .venv/bin/activate`;依赖对齐用 `uv sync --extra dev`
  (裸 `uv pip install` 会漏 types-PyYAML 等 dev stubs → mypy 假红)
- **提交前三件套**:全量 `pytest tests/`(禁 marker 筛选当全集)+ `ruff check src/ tests/`
  + `mypy src/`(mypy 已进 CI,2026-08-18 起是硬门禁)
- **分支**:trunk-based,`feature/`/`fix/` 短分支 → PR squash merge(CI 在 PR 上跑,
  main 直接 push 不触发)
- **工作状态权威源**:open issues + `CHANGELOG.md` [Unreleased] + git log。
  不要找"状态/进度文档"——本仓 docs/ 不留完成态(见 CLAUDE.md)

## 产品哲学(评估 feature 提案时用)

#148 重定位后的分工:**codeindex 导航 / cbm 提取底座 / loomgraph 时间+比较层**。
loomgraph 的功能提案**默认拒绝变全**,除非服务时间/比较主线(branch-diff /
time-travel / compare 系);差异化核心是 renunciation(明确不做什么),不是功能
叠加。B epic(#185,已落地 branch-diff v1)就是这条主线的第一个实例。

## 自我工具

本仓自身是 loomgraph 用户。理解代码可直接用:`loomgraph status` /
`loomgraph find "<symbol>"` / `loomgraph graph "<entity>"` /
`loomgraph branch-diff <A>..<B>`(如 `branch-diff v0.19.0..HEAD` 看最近结构变化)。
MCP 工具(`loomgraph_find` 等)若已在配置中则原生可用。
