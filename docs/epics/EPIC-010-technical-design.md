# EPIC-010 技术实施设计

**关联**: [EPIC-010](EPIC-010-git-metrics-integration.md), [ADR-013](../adr/ADR-013-git-knowledge-graph-integration.md)
**状态**: Draft
**日期**: 2026-03-06

---

## 目录

1. [架构设计](#架构设计)
2. [数据结构详细设计](#数据结构详细设计)
3. [核心算法实现](#核心算法实现)
4. [API 设计](#api-设计)
5. [性能优化策略](#性能优化策略)
6. [错误处理](#错误处理)
7. [测试策略](#测试策略)
8. [迁移路径](#迁移路径)

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Layer                            │
│  ┌──────────────┐  ┌────────────┐  ┌─────────────┐     │
│  │ debt command │  │ git-metrics│  │   trends    │     │
│  └──────┬───────┘  └─────┬──────┘  └──────┬──────┘     │
└─────────┼────────────────┼────────────────┼────────────┘
          │                │                │
┌─────────▼────────────────▼────────────────▼────────────┐
│                  Core Layer                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │           DebtAnalyzer (Orchestrator)            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │  │
│  │  │ Quality     │  │ Topology    │  │   Git    │ │  │
│  │  │ Analyzer    │  │ Analyzer    │  │ Metrics  │ │  │
│  │  └─────────────┘  └─────────────┘  └──────────┘ │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         GitMetricsAnalyzer (New)                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │  │
│  │  │ Git Parser  │  │ Hotspot     │  │ Bus      │ │  │
│  │  │             │  │ Detector    │  │ Factor   │ │  │
│  │  └─────────────┘  └─────────────┘  └──────────┘ │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         TrendsAnalyzer (v0.11)                   │  │
│  │  ┌─────────────┐  ┌─────────────┐               │  │
│  │  │ History     │  │ Linear      │               │  │
│  │  │ Manager     │  │ Regression  │               │  │
│  │  └─────────────┘  └─────────────┘               │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
          │                │                │
┌─────────▼────────────────▼────────────────▼─────────────┐
│                   Data Layer                            │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │ LightRAG   │  │ Git Cache  │  │ Metrics History  │  │
│  │ (Graph)    │  │ (JSON)     │  │ (JSON Time-      │  │
│  │            │  │            │  │  series)         │  │
│  └────────────┘  └────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 模块依赖

```
debt_analyzer.py
├── topology.py (existing)
├── git_metrics.py (new)
│   ├── git_parser.py (new)
│   └── git.py (existing - utils)
└── trends.py (v0.11, new)
    └── history_manager.py (v0.11, new)
```

---

## 数据结构详细设计

### 1. GitMetrics 核心数据结构

```python
# src/loomgraph/core/git_metrics.py

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class FileMetrics:
    """单文件的 Git 历史指标.

    Attributes:
        source_id: 文件路径（与 LightRAG entities 对齐）
        change_frequency: N 个月内的提交次数
        last_modified: 最后修改时间
        last_modified_days: 距今天数
        authors: 贡献者列表（按提交数排序）
        primary_author: 主要贡献者（>50% 提交）
        bug_fix_count: 包含 "fix|bug" 的提交数
        total_commits: 总提交数
        bug_fix_ratio: bug_fix_count / total_commits
        lines_added: 累计新增行数
        lines_deleted: 累计删除行数
        churn: lines_added + lines_deleted（代码变动量）
        created_at: 首次创建时间
        age_days: 代码年龄（距今天数）
    """
    source_id: str
    change_frequency: int
    last_modified: datetime
    last_modified_days: int
    authors: list[str]
    primary_author: str | None
    bug_fix_count: int
    total_commits: int
    bug_fix_ratio: float
    lines_added: int
    lines_deleted: int
    churn: int
    created_at: datetime
    age_days: int

    def to_dict(self) -> dict:
        """序列化为 dict（用于缓存）."""
        return {
            "source_id": self.source_id,
            "change_frequency": self.change_frequency,
            "last_modified": self.last_modified.isoformat(),
            "last_modified_days": self.last_modified_days,
            "authors": self.authors,
            "primary_author": self.primary_author,
            "bug_fix_count": self.bug_fix_count,
            "total_commits": self.total_commits,
            "bug_fix_ratio": self.bug_fix_ratio,
            "lines_added": self.lines_added,
            "lines_deleted": self.lines_deleted,
            "churn": self.churn,
            "created_at": self.created_at.isoformat(),
            "age_days": self.age_days,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileMetrics":
        """从 dict 反序列化."""
        return cls(
            source_id=data["source_id"],
            change_frequency=data["change_frequency"],
            last_modified=datetime.fromisoformat(data["last_modified"]),
            last_modified_days=data["last_modified_days"],
            authors=data["authors"],
            primary_author=data.get("primary_author"),
            bug_fix_count=data["bug_fix_count"],
            total_commits=data["total_commits"],
            bug_fix_ratio=data["bug_fix_ratio"],
            lines_added=data["lines_added"],
            lines_deleted=data["lines_deleted"],
            churn=data["churn"],
            created_at=datetime.fromisoformat(data["created_at"]),
            age_days=data["age_days"],
        )


@dataclass
class Hotspot:
    """高频变更热点文件.

    Hotspot = 高变更频率 × 文件规模（潜在风险大）
    """
    file: str
    change_freq: int            # N 个月内提交次数
    lines: int                  # 文件行数（可选，从 codeindex）
    hotspot_score: int          # 0-100 综合评分
    rank: int                   # 排名（1 = 最危险）

    def __repr__(self) -> str:
        return f"Hotspot({self.file}, freq={self.change_freq}, score={self.hotspot_score})"


@dataclass
class BusFactor:
    """知识孤岛 / 总线因子分析.

    Bus Factor = 1 → 只有一个人知道这个模块（高风险）
    """
    file: str
    owner: str                  # 主要维护者
    contributors: int           # 独立贡献者数量
    ownership_ratio: float      # owner 提交占比（0-1）
    total_commits: int          # 总提交数
    risk_level: str             # "critical" / "high" / "medium"

    def __repr__(self) -> str:
        return f"BusFactor({self.file}, owner={self.owner}, contributors={self.contributors})"


@dataclass
class GitMetricsResult:
    """Git 分析结果（完整报告）.

    Attributes:
        repo_path: Git 仓库根路径
        since: 分析时间窗口（e.g., "3 months"）
        analyzed_at: 分析时间戳
        file_metrics: 按 source_id 索引的文件指标
        hotspots: 高频变更文件列表（降序）
        bus_factor: 知识孤岛文件列表
        summary: 汇总统计
    """
    repo_path: Path
    since: str
    analyzed_at: datetime
    file_metrics: dict[str, FileMetrics]
    hotspots: list[Hotspot]
    bus_factor: list[BusFactor]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """序列化为 dict（用于缓存 + CLI 输出）."""
        return {
            "repo_path": str(self.repo_path),
            "since": self.since,
            "analyzed_at": self.analyzed_at.isoformat(),
            "file_metrics": {k: v.to_dict() for k, v in self.file_metrics.items()},
            "hotspots": [
                {
                    "file": h.file,
                    "change_freq": h.change_freq,
                    "lines": h.lines,
                    "hotspot_score": h.hotspot_score,
                    "rank": h.rank,
                }
                for h in self.hotspots
            ],
            "bus_factor": [
                {
                    "file": b.file,
                    "owner": b.owner,
                    "contributors": b.contributors,
                    "ownership_ratio": b.ownership_ratio,
                    "total_commits": b.total_commits,
                    "risk_level": b.risk_level,
                }
                for b in self.bus_factor
            ],
            "summary": self.summary,
        }
```

### 2. DebtIssue 扩展

```python
# src/loomgraph/core/debt_analyzer.py (扩展现有 DebtIssue)

@dataclass
class DebtIssue:
    # 现有字段
    id: str
    severity: str  # P0 / P1 / P2
    category: str  # orphan_entity / god_function / ... / critical_hotspot (新)
    entity: str
    entity_type: str
    location: dict[str, str]
    metrics: dict[str, Any]
    details: dict[str, Any]
    suggestion: str
    estimated_effort: dict[str, Any]
    references: list[str]

    # 新增字段（Git 维度）
    confidence: str | None = None        # high / medium / low (for orphans)
    is_hotspot: bool = False             # True (for god functions with high change_freq)
    trend: str | None = None             # "increasing" / "stable" / "decreasing" (v0.11)
    git_metrics: dict[str, Any] | None = None  # 原始 git 数据引用

    def to_dict(self) -> dict:
        """序列化（兼容现有逻辑）."""
        result = {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "entity": self.entity,
            "entity_type": self.entity_type,
            "location": self.location,
            "metrics": self.metrics,
            "details": self.details,
            "suggestion": self.suggestion,
            "estimated_effort": self.estimated_effort,
            "references": self.references,
        }

        # 只在有值时才添加新字段（向后兼容）
        if self.confidence:
            result["confidence"] = self.confidence
        if self.is_hotspot:
            result["is_hotspot"] = self.is_hotspot
        if self.trend:
            result["trend"] = self.trend
        if self.git_metrics:
            result["git_metrics"] = self.git_metrics

        return result
```

### 3. 缓存数据结构

```python
# ~/.loomgraph/cache/git-metrics.json

{
  "schema_version": "1.0",
  "cache_created_at": "2026-03-06T15:30:00+00:00",
  "ttl_hours": 24,
  "repo_path": "/Users/dreamlinx/Dropbox/Projects/LoomGraph",
  "since": "3 months",
  "data": {
    "file_metrics": {
      "src/auth/user_service.py": {
        "change_frequency": 12,
        "last_modified": "2026-03-01T10:30:00+00:00",
        "last_modified_days": 5,
        "authors": ["alice", "bob"],
        "primary_author": "alice",
        "bug_fix_ratio": 0.33,
        ...
      }
    },
    "hotspots": [...],
    "bus_factor": [...]
  }
}
```

---

## 核心算法实现

### 1. Git Log 解析器

```python
# src/loomgraph/core/git_parser.py

import subprocess
from datetime import datetime, timezone
from pathlib import Path


class GitLogParser:
    """Git log 解析器（健壮性优先）."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def parse_commits(self, since: str = "3 months") -> list[dict]:
        """解析 git log 为结构化数据.

        Args:
            since: 时间窗口（git log --since 格式）

        Returns:
            List of commit dicts:
            [
                {
                    "sha": "abc123",
                    "author": "alice",
                    "timestamp": datetime(...),
                    "message": "fix: auth timeout",
                    "files": ["src/auth/user_service.py"],
                    "stats": {"src/auth/user_service.py": {"added": 10, "deleted": 5}}
                },
                ...
            ]

        Raises:
            GitError: If not a git repository or git command fails
        """
        # 检查是否是 git 仓库
        if not self._is_git_repository():
            raise GitError(f"Not a git repository: {self.repo_path}")

        # git log 格式：%H|%an|%at|%s
        # %H = commit hash
        # %an = author name
        # %at = author timestamp (unix)
        # %s = subject (commit message)
        cmd = [
            "git",
            "log",
            f"--since={since}",
            "--format=%H|%an|%at|%s",
            "--numstat",  # 获取文件变更统计
        ]

        result = self._run_git_command(cmd)
        return self._parse_log_output(result.stdout)

    def _is_git_repository(self) -> bool:
        """检查是否是 git 仓库."""
        try:
            self._run_git_command(["git", "rev-parse", "--is-inside-work-tree"])
            return True
        except GitError:
            return False

    def _run_git_command(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """运行 git 命令（错误处理）."""
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,  # 防止卡住
            )
            return result
        except subprocess.CalledProcessError as e:
            raise GitError(f"Git command failed: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise GitError(f"Git command timeout: {' '.join(cmd)}")

    def _parse_log_output(self, output: str) -> list[dict]:
        """解析 git log --numstat 输出.

        格式：
        abc123|alice|1709280600|fix: auth timeout

        10  5   src/auth/user_service.py
        2   1   src/auth/utils.py

        def456|bob|1709194200|feat: add oauth

        15  0   src/auth/oauth.py

        Returns:
            [
                {
                    "sha": "abc123",
                    "author": "alice",
                    "timestamp": datetime(...),
                    "message": "fix: auth timeout",
                    "files": ["src/auth/user_service.py", "src/auth/utils.py"],
                    "stats": {
                        "src/auth/user_service.py": {"added": 10, "deleted": 5},
                        "src/auth/utils.py": {"added": 2, "deleted": 1}
                    }
                },
                ...
            ]
        """
        commits = []
        lines = output.strip().split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # 解析 commit header
            if "|" in line:
                parts = line.split("|", maxsplit=3)
                if len(parts) != 4:
                    i += 1
                    continue

                sha, author, timestamp_str, message = parts
                commit = {
                    "sha": sha,
                    "author": author,
                    "timestamp": datetime.fromtimestamp(
                        int(timestamp_str), tz=timezone.utc
                    ),
                    "message": message,
                    "files": [],
                    "stats": {},
                }

                # 解析 numstat（后续行）
                i += 1
                while i < len(lines):
                    stat_line = lines[i].strip()
                    if not stat_line or "|" in stat_line:
                        break

                    # numstat 格式：<added>\t<deleted>\t<file>
                    parts = stat_line.split("\t")
                    if len(parts) == 3:
                        added_str, deleted_str, file_path = parts
                        # 处理二进制文件（added/deleted = "-"）
                        try:
                            added = int(added_str)
                            deleted = int(deleted_str)
                        except ValueError:
                            added = deleted = 0

                        commit["files"].append(file_path)
                        commit["stats"][file_path] = {
                            "added": added,
                            "deleted": deleted,
                        }

                    i += 1

                commits.append(commit)
            else:
                i += 1

        return commits


class GitError(Exception):
    """Git 操作错误."""
    pass
```

### 2. Hotspot 检测算法

```python
# src/loomgraph/core/git_metrics.py

class GitMetricsAnalyzer:
    def __init__(
        self,
        repo_path: Path,
        since: str = "3 months",
        hotspot_threshold: int = 10,
        bus_factor_threshold: int = 2,
    ):
        self.repo_path = repo_path
        self.since = since
        self.hotspot_threshold = hotspot_threshold
        self.bus_factor_threshold = bus_factor_threshold
        self.parser = GitLogParser(repo_path)

    def analyze(self) -> GitMetricsResult:
        """主分析入口."""
        # 1. 解析 git log
        commits = self.parser.parse_commits(self.since)

        # 2. 聚合文件级指标
        file_metrics = self._aggregate_file_metrics(commits)

        # 3. 检测 Hotspot
        hotspots = self._detect_hotspots(file_metrics)

        # 4. 检测 Bus Factor
        bus_factor = self._detect_bus_factor(file_metrics)

        # 5. 汇总统计
        summary = self._calculate_summary(file_metrics, hotspots, bus_factor)

        return GitMetricsResult(
            repo_path=self.repo_path,
            since=self.since,
            analyzed_at=datetime.now(timezone.utc),
            file_metrics=file_metrics,
            hotspots=hotspots,
            bus_factor=bus_factor,
            summary=summary,
        )

    def _aggregate_file_metrics(self, commits: list[dict]) -> dict[str, FileMetrics]:
        """聚合每个文件的 Git 指标."""
        file_data: dict[str, dict] = {}  # file_path → aggregated data

        for commit in commits:
            for file_path, stats in commit["stats"].items():
                if file_path not in file_data:
                    file_data[file_path] = {
                        "commits": [],
                        "authors": set(),
                        "author_commits": {},
                        "bug_fix_count": 0,
                        "lines_added": 0,
                        "lines_deleted": 0,
                    }

                data = file_data[file_path]
                data["commits"].append(commit)
                data["authors"].add(commit["author"])

                # 作者提交统计
                author = commit["author"]
                data["author_commits"][author] = data["author_commits"].get(author, 0) + 1

                # Bug fix 检测
                if self._is_bug_fix(commit["message"]):
                    data["bug_fix_count"] += 1

                # 代码变动量
                data["lines_added"] += stats["added"]
                data["lines_deleted"] += stats["deleted"]

        # 转换为 FileMetrics
        result = {}
        now = datetime.now(timezone.utc)

        for file_path, data in file_data.items():
            commits = data["commits"]
            authors = list(data["authors"])
            author_commits = data["author_commits"]

            # 找到主要维护者（>50% 提交）
            total_commits = len(commits)
            primary_author = None
            for author, count in author_commits.items():
                if count / total_commits > 0.5:
                    primary_author = author
                    break

            # 最后修改时间
            last_commit = max(commits, key=lambda c: c["timestamp"])
            last_modified = last_commit["timestamp"]
            last_modified_days = (now - last_modified).days

            # 首次创建时间
            first_commit = min(commits, key=lambda c: c["timestamp"])
            created_at = first_commit["timestamp"]
            age_days = (now - created_at).days

            # Bug fix ratio
            bug_fix_ratio = data["bug_fix_count"] / total_commits if total_commits > 0 else 0

            result[file_path] = FileMetrics(
                source_id=file_path,
                change_frequency=total_commits,
                last_modified=last_modified,
                last_modified_days=last_modified_days,
                authors=sorted(authors, key=lambda a: author_commits[a], reverse=True),
                primary_author=primary_author,
                bug_fix_count=data["bug_fix_count"],
                total_commits=total_commits,
                bug_fix_ratio=bug_fix_ratio,
                lines_added=data["lines_added"],
                lines_deleted=data["lines_deleted"],
                churn=data["lines_added"] + data["lines_deleted"],
                created_at=created_at,
                age_days=age_days,
            )

        return result

    def _is_bug_fix(self, message: str) -> bool:
        """检测 commit message 是否是 bug fix."""
        keywords = ["fix", "bug", "patch", "hotfix", "bugfix", "fixed"]
        message_lower = message.lower()
        return any(kw in message_lower for kw in keywords)

    def _detect_hotspots(self, file_metrics: dict[str, FileMetrics]) -> list[Hotspot]:
        """检测高频变更热点.

        Algorithm:
            hotspot_score = change_frequency × log10(churn + 1) × 10
            (churn 越大，文件越复杂，变更风险越高)
        """
        hotspots = []

        for file_path, metrics in file_metrics.items():
            if metrics.change_frequency < self.hotspot_threshold:
                continue

            # 计算 hotspot score
            import math
            score = int(
                metrics.change_frequency
                * math.log10(metrics.churn + 1)
                * 10
            )
            score = min(score, 100)  # cap at 100

            hotspots.append(
                Hotspot(
                    file=file_path,
                    change_freq=metrics.change_frequency,
                    lines=0,  # 稍后从 codeindex 填充
                    hotspot_score=score,
                    rank=0,  # 稍后排序填充
                )
            )

        # 按 score 降序排序
        hotspots.sort(key=lambda h: h.hotspot_score, reverse=True)

        # 填充 rank
        for i, hotspot in enumerate(hotspots, start=1):
            hotspot.rank = i

        return hotspots

    def _detect_bus_factor(self, file_metrics: dict[str, FileMetrics]) -> list[BusFactor]:
        """检测知识孤岛 / 总线因子.

        Bus Factor = 1 → 只有一个人维护（高风险）
        """
        silos = []

        for file_path, metrics in file_metrics.items():
            contributors = len(metrics.authors)

            if contributors > self.bus_factor_threshold:
                continue

            # 计算 ownership ratio
            if metrics.primary_author:
                author_commits = sum(
                    1 for c in metrics.authors if c == metrics.primary_author
                )
                ownership_ratio = author_commits / metrics.total_commits
            else:
                ownership_ratio = 1.0 / contributors if contributors > 0 else 1.0

            # 风险等级
            if contributors == 1:
                risk_level = "critical"
            elif contributors == 2 and ownership_ratio > 0.7:
                risk_level = "high"
            else:
                risk_level = "medium"

            silos.append(
                BusFactor(
                    file=file_path,
                    owner=metrics.primary_author or metrics.authors[0],
                    contributors=contributors,
                    ownership_ratio=ownership_ratio,
                    total_commits=metrics.total_commits,
                    risk_level=risk_level,
                )
            )

        # 按 contributors 升序排序（风险最高的在前）
        silos.sort(key=lambda b: (b.contributors, -b.ownership_ratio))

        return silos

    def _calculate_summary(
        self,
        file_metrics: dict[str, FileMetrics],
        hotspots: list[Hotspot],
        bus_factor: list[BusFactor],
    ) -> dict:
        """汇总统计."""
        return {
            "total_files": len(file_metrics),
            "total_hotspots": len(hotspots),
            "critical_hotspots": sum(1 for h in hotspots if h.hotspot_score >= 80),
            "total_silos": len(bus_factor),
            "critical_silos": sum(1 for b in bus_factor if b.risk_level == "critical"),
            "avg_change_frequency": (
                sum(m.change_frequency for m in file_metrics.values()) / len(file_metrics)
                if file_metrics
                else 0
            ),
        }
```

### 3. DebtAnalyzer Join 逻辑

```python
# src/loomgraph/core/debt_analyzer.py (扩展现有类)

class DebtAnalyzer:
    def __init__(
        self,
        client: LightRAGClient | None = None,
        codeindex_data: dict | None = None,
    ):
        self.client = client
        self.codeindex_data_raw = codeindex_data
        self.issues: list[DebtIssue] = []

    async def analyze(
        self,
        codeindex_data: dict | None = None,
        module: str | None = None,
        with_git: bool = False,  # 新参数
        git_since: str = "3 months",
    ) -> dict:
        """主分析入口（扩展三维）."""
        if codeindex_data:
            self.codeindex_data_raw = codeindex_data

        self.issues = []

        # 维度 1: Quality (codeindex)
        quality_score = self._analyze_quality_issues(self.codeindex_data_raw)

        # 维度 2: Topology (graph)
        topology_score = 100
        if self.client:
            topology_score = await self._analyze_topology_issues(module)

        # 维度 3: Git (时间)
        git_score = 100
        git_metrics = None
        if with_git:
            git_analyzer = GitMetricsAnalyzer(Path.cwd(), since=git_since)
            try:
                git_metrics = git_analyzer.analyze()
                git_score = self._analyze_git_issues(git_metrics)
                self._enrich_with_git_metrics(git_metrics)
            except GitError as e:
                logger.warning(f"Git analysis failed: {e}. Skipping git dimension.")
                # git_score 保持 100（不惩罚非 git 项目）

        # 三维评分
        if with_git:
            total_score = (quality_score + topology_score + git_score) // 3
        else:
            total_score = (quality_score + topology_score) // 2

        # 构建报告
        health = self._calculate_overall_health(
            quality_score=quality_score,
            topology_score=topology_score,
            git_score=git_score if with_git else None,
        )

        return {
            "schema_version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project": "unknown",  # TODO: 从 git remote 提取
            "generator": {
                "tool": "loomgraph",
                "version": "0.10.0",
            },
            "overall_health": health,
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendations": self._generate_recommendations(),
        }

    def _analyze_git_issues(self, git_metrics: GitMetricsResult) -> int:
        """生成 Git 维度的 debt issues.

        Returns:
            git_score (0-100，penalty-based)
        """
        penalty = 0

        # 1. Critical Hotspot (P0)
        for hotspot in git_metrics.hotspots:
            if hotspot.hotspot_score >= 80:
                self.issues.append(
                    DebtIssue(
                        id=f"debt-git-{len(self.issues) + 1:03d}",
                        severity="P0",
                        category="critical_hotspot",
                        entity=hotspot.file,
                        entity_type="file",
                        location={"file": hotspot.file},
                        metrics={
                            "change_frequency": hotspot.change_freq,
                            "hotspot_score": hotspot.hotspot_score,
                            "rank": hotspot.rank,
                        },
                        details={},
                        suggestion=(
                            f"⚠️ Critical hotspot: {hotspot.change_freq} changes "
                            f"in {git_metrics.since}. High instability risk. Refactor ASAP."
                        ),
                        estimated_effort={},
                        references=[],
                    )
                )
                penalty += 15

        # 2. Knowledge Silo (P1)
        for silo in git_metrics.bus_factor:
            if silo.risk_level == "critical":
                self.issues.append(
                    DebtIssue(
                        id=f"debt-git-{len(self.issues) + 1:03d}",
                        severity="P1",
                        category="knowledge_silo",
                        entity=silo.file,
                        entity_type="file",
                        location={"file": silo.file},
                        metrics={
                            "owner": silo.owner,
                            "contributors": silo.contributors,
                            "ownership_ratio": silo.ownership_ratio,
                        },
                        details={},
                        suggestion=(
                            f"Only {silo.owner} knows this code (bus factor = {silo.contributors}). "
                            "Add documentation or pair programming."
                        ),
                        estimated_effort={},
                        references=[],
                    )
                )
                penalty += 5

        return max(0, 100 - penalty)

    def _enrich_with_git_metrics(self, git_metrics: GitMetricsResult) -> None:
        """为现有 issues 添加 Git 维度信息（置信度 / Hotspot 标记）."""
        file_metrics = git_metrics.file_metrics

        for issue in self.issues:
            source_id = issue.location.get("file", "")
            git_data = file_metrics.get(source_id)

            if not git_data:
                continue

            # 1. Orphan 置信度
            if issue.category == "orphan_entity":
                days = git_data.last_modified_days

                if days > 365:
                    issue.confidence = "high"
                    issue.suggestion += " (1 year+ no changes, high confidence dead code)"
                elif days > 90:
                    issue.confidence = "medium"
                    issue.suggestion += " (3 months+ no changes, possibly dead code)"
                else:
                    issue.confidence = "low"
                    issue.suggestion += " (recently modified, may be new or dynamic call)"

                issue.git_metrics = {
                    "last_modified_days": days,
                    "change_frequency": git_data.change_frequency,
                }

            # 2. God Function Hotspot 标记
            if issue.category == "god_function":
                freq = git_data.change_frequency

                if freq > 10:
                    issue.is_hotspot = True
                    issue.severity = "P0"  # 升级严重度
                    issue.suggestion += (
                        f" ⚠️ Hotspot: {freq} changes in {git_metrics.since}. "
                        "High instability + high coupling = critical risk."
                    )

                issue.git_metrics = {
                    "change_frequency": freq,
                    "bug_fix_ratio": git_data.bug_fix_ratio,
                }

    def _calculate_overall_health(
        self,
        quality_score: int = 100,
        topology_score: int = 100,
        git_score: int | None = None,
    ) -> dict:
        """计算整体健康度（支持三维）."""
        # 现有逻辑 + git_score
        if git_score is not None:
            total_score = (quality_score + topology_score + git_score) // 3
            breakdown = {
                "quality": quality_score,
                "topology": topology_score,
                "git": git_score,
            }
        else:
            total_score = (quality_score + topology_score) // 2
            breakdown = {
                "quality": quality_score,
                "topology": topology_score,
            }

        # 其余逻辑不变...
        grade = self._score_to_grade(total_score)

        return {
            "total_score": total_score,
            "grade": grade,
            "breakdown": breakdown,
            "summary": {
                "total_entities": 0,  # TODO: 从 LightRAG 获取
                "p0_issues": sum(1 for i in self.issues if i.severity == "P0"),
                "p1_issues": sum(1 for i in self.issues if i.severity == "P1"),
                "p2_issues": sum(1 for i in self.issues if i.severity == "P2"),
            },
        }
```

---

## API 设计

### CLI 接口

```bash
# 1. Git Metrics 独立分析（调试用）
loomgraph git-metrics ./src \
  --since "3 months" \
  --output metrics.json

# 输出：GitMetricsResult JSON

# 2. Debt 分析（集成 Git）
loomgraph debt \
  --codeindex-data debt.json \
  --with-git \
  --git-since "3 months" \
  --format json

# 输出：三维债务报告

# 3. Trends 分析（v0.11）
loomgraph trends \
  --entity "UserService.authenticate" \
  --months 6

# 输出：ASCII 图表 + 趋势判定
```

### Python API

```python
# 1. GitMetricsAnalyzer
from loomgraph.core.git_metrics import GitMetricsAnalyzer
from pathlib import Path

analyzer = GitMetricsAnalyzer(Path.cwd(), since="3 months")
result = analyzer.analyze()

print(f"Hotspots: {len(result.hotspots)}")
print(f"Silos: {len(result.bus_factor)}")

# 2. DebtAnalyzer (扩展)
from loomgraph.core.debt_analyzer import DebtAnalyzer
from loomgraph.core.lightrag_client import LightRAGClient

client = LightRAGClient(base_url="http://localhost:3001", workspace="myproject")
analyzer = DebtAnalyzer(client=client)

report = await analyzer.analyze(
    codeindex_data=codeindex_data,
    with_git=True,
    git_since="3 months"
)

print(f"Total score: {report['overall_health']['total_score']}/100")
```

---

## 性能优化策略

### 1. 缓存机制

```python
# src/loomgraph/core/git_metrics.py

class GitMetricsCache:
    """Git metrics 缓存管理器."""

    CACHE_DIR = Path.home() / ".loomgraph" / "cache"
    TTL_HOURS = 24

    @classmethod
    def get(cls, repo_path: Path, since: str) -> GitMetricsResult | None:
        """从缓存读取（如果未过期）."""
        cache_file = cls._get_cache_file(repo_path, since)

        if not cache_file.exists():
            return None

        # 检查 TTL
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime, tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600

        if age_hours > cls.TTL_HOURS:
            return None  # 过期

        # 读取缓存
        try:
            with open(cache_file) as f:
                data = json.load(f)
                # TODO: 反序列化为 GitMetricsResult
                return data
        except Exception:
            return None

    @classmethod
    def set(cls, result: GitMetricsResult) -> None:
        """写入缓存."""
        cache_file = cls._get_cache_file(result.repo_path, result.since)
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    @classmethod
    def _get_cache_file(cls, repo_path: Path, since: str) -> Path:
        """缓存文件路径（按 repo + since 生成）."""
        # 使用 repo 路径 hash + since 作为文件名
        import hashlib
        key = f"{repo_path.resolve()}|{since}"
        hash_key = hashlib.md5(key.encode()).hexdigest()
        return cls.CACHE_DIR / f"git-metrics-{hash_key}.json"
```

### 2. 增量分析

```python
# 只分析最近 N 个月（避免解析全部历史）
commits = self.parser.parse_commits(since="3 months")  # 而非 --all
```

### 3. 并行处理

```python
# git log 可以按目录并行
import asyncio

async def analyze_parallel(self, paths: list[Path]) -> dict:
    """并行分析多个目录."""
    tasks = [
        asyncio.to_thread(self.parser.parse_commits, path)
        for path in paths
    ]
    results = await asyncio.gather(*tasks)
    return self._merge_results(results)
```

---

## 错误处理

### 1. 非 Git 项目

```python
class GitMetricsAnalyzer:
    def analyze(self) -> GitMetricsResult:
        """自动检测并 graceful fallback."""
        try:
            commits = self.parser.parse_commits(self.since)
        except GitError as e:
            logger.warning(f"Git analysis failed: {e}. Skipping.")
            # 返回空结果
            return GitMetricsResult(
                repo_path=self.repo_path,
                since=self.since,
                analyzed_at=datetime.now(timezone.utc),
                file_metrics={},
                hotspots=[],
                bus_factor=[],
                summary={"total_files": 0},
            )
```

### 2. Git 版本检查

```python
def _check_git_version(self) -> None:
    """检查 Git 版本（>= 2.0）."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        # 解析版本号（git version 2.39.1）
        version_str = result.stdout.split()[2]
        major_version = int(version_str.split(".")[0])

        if major_version < 2:
            raise GitError(f"Git version {version_str} too old. Require >= 2.0")

    except Exception as e:
        raise GitError(f"Git not found or version check failed: {e}")
```

---

## 测试策略

### 1. 单元测试

```python
# tests/unit/test_git_parser.py

def test_parse_git_log():
    """测试 git log 解析."""
    output = """
abc123|alice|1709280600|fix: auth timeout

10  5   src/auth/user_service.py
2   1   src/auth/utils.py

def456|bob|1709194200|feat: add oauth

15  0   src/auth/oauth.py
    """

    parser = GitLogParser(Path("."))
    commits = parser._parse_log_output(output)

    assert len(commits) == 2
    assert commits[0]["sha"] == "abc123"
    assert commits[0]["author"] == "alice"
    assert len(commits[0]["files"]) == 2
    assert commits[0]["stats"]["src/auth/user_service.py"] == {"added": 10, "deleted": 5}
```

### 2. 集成测试

```python
# tests/integration/test_debt_with_git.py

@pytest.mark.asyncio
async def test_debt_with_git_integration():
    """E2E 测试：债务分析 + Git 集成."""
    # 准备测试数据
    codeindex_data = {...}  # mock codeindex output

    # 分析（with git）
    client = LightRAGClient(base_url="http://localhost:3001")
    analyzer = DebtAnalyzer(client=client)
    report = await analyzer.analyze(
        codeindex_data=codeindex_data,
        with_git=True,
        git_since="3 months"
    )

    # 验证三维评分
    assert "git" in report["overall_health"]["breakdown"]
    assert report["overall_health"]["git"] >= 0

    # 验证新增 issue 类别
    categories = {i["category"] for i in report["issues"]}
    assert "critical_hotspot" in categories or "knowledge_silo" in categories

    # 验证 Orphan 置信度
    orphans = [i for i in report["issues"] if i["category"] == "orphan_entity"]
    if orphans:
        assert orphans[0].get("confidence") in ["high", "medium", "low"]
```

---

## 迁移路径

### Phase 1: 向后兼容（v0.10.0）

```bash
# 现有命令完全不受影响
loomgraph debt --codeindex-data debt.json
# → 输出不变（二维评分）

# 新增可选 flag
loomgraph debt --codeindex-data debt.json --with-git
# → 输出包含 git 维度（三维评分）
```

### Phase 2: 数据迁移（无需迁移）

- Git metrics 是**临时数据**（缓存 1 天）
- 不需要迁移现有 LightRAG 数据
- 完全向后兼容

### Phase 3: 文档更新

1. **CLAUDE.md**: 新增 `--with-git` 说明
2. **CLI_DESIGN.md**: 更新命令参数
3. **README.md**: 新增 Hotspot 示例

---

## 下一步行动

1. **Review 本设计文档**（用户确认）
2. **创建 GitHub Issue**（EPIC-010）
3. **开始 Feature 1 实施**（GitMetricsAnalyzer）

---

**文档版本**: v1.0
**最后更新**: 2026-03-06
