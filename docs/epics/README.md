# LoomGraph Epic 文档索引

本目录包含所有 Epic（史诗级功能）的详细设计文档。

## 📁 目录结构

```
epics/
├── active/         # 当前版本的 Epic（v0.7.0）
├── completed/      # 已完成的 Epic（v0.6.0 及以前）
└── README.md       # 本文件
```

---

## 🔥 Active Epics（v0.7.0）

| Epic | 标题 | 版本 | 状态 | 文档 |
|------|------|------|------|------|
| EPIC-003 | 增量更新策略 | v0.7.0 | ✅ 已完成 | [active/EPIC-003-update-strategy.md](active/EPIC-003-update-strategy.md) |
| EPIC-008 | 搜索体系重构 | v0.7.0 | ✅ 已完成 | [active/EPIC-008-search-architecture-redesign.md](active/EPIC-008-search-architecture-redesign.md) |
| EPIC-009 | 图谱拓扑债务分析 | v0.7.0 | ✅ 已完成 | [active/EPIC-009-graph-topology-debt-analysis.md](active/EPIC-009-graph-topology-debt-analysis.md) |

---

## ✅ Completed Epics（v0.6.0 及以前）

| Epic | 标题 | 版本 | 状态 | 文档 |
|------|------|------|------|------|
| EPIC-002 | Git 集成 + Warm Update | v0.2.x | ✅ 已完成 | [completed/EPIC-002-git-integration-skills.md](completed/EPIC-002-git-integration-skills.md) |
| EPIC-004 | 双向调度器 (deps/overview) | v0.2.5 | ✅ 已完成 | [completed/EPIC-004-bidirectional-orchestrator.md](completed/EPIC-004-bidirectional-orchestrator.md) |
| EPIC-005 | Workspace 管理 | v0.4.0 | ✅ 已完成 | [completed/EPIC-005-workspace-management.md](completed/EPIC-005-workspace-management.md) |
| EPIC-006 | 跨 Workspace 对比 | v0.5.0 | ✅ 已完成 | [completed/EPIC-006-cross-workspace-comparison.md](completed/EPIC-006-cross-workspace-comparison.md) |
| EPIC-007 | 研发熵减 Skills | v0.6.0 | ✅ 已完成 | [completed/EPIC-007-entropy-reduction-skills.md](completed/EPIC-007-entropy-reduction-skills.md) |

---

## 📋 Planned Epics（未来版本）

| Epic | 标题 | 版本 | 状态 | Issue |
|------|------|------|------|-------|
| EPIC-010 | MCP Server — IDE 集成 | v0.8.0 | 📅 计划中 | [#19](https://github.com/dreamlx/LoomGraph/issues/19) |

---

## 📖 Epic 生命周期

```
计划 → 设计 (Epic 文档) → 实现 → 测试 → 发布 → 归档
```

1. **计划阶段**：创建 GitHub Issue（label: epic）
2. **设计阶段**：编写 Epic 文档（docs/epics/），ADR（如需要）
3. **实现阶段**：开发功能，TDD，提交代码
4. **测试阶段**：单元测试 + 集成测试
5. **发布阶段**：合并到 main，创建 tag，更新 CHANGELOG
6. **归档阶段**：
   - 关闭 GitHub Issue
   - Epic 文档移至 `completed/`（下一版本发布后）
   - `active/` 保留最新版本的 Epic

---

## 🔗 相关资源

- **ROADMAP**: [../ROADMAP.md](../ROADMAP.md)
- **CHANGELOG**: [../../CHANGELOG.md](../../CHANGELOG.md)
- **ADR**: [../adr/](../adr/)
- **GitHub Issues**: https://github.com/dreamlx/LoomGraph/issues

---

**最后更新**: 2026-02-22
**当前版本**: v0.7.0
