"""Code health scoring — 8-dimension static analysis.

Dimensions (weight):
  CQ (15) — Code Quality: max production file lines
  TS (10) — Type Safety: `: any` count in TS/TSX
  MT (10) — Maintainability: TODO/HACK/FIXME + hardcoded URLs
  DC (10) — Dead Code: DEPRECATED/REMOVED/LEGACY marks
  IR (15) — Impact Risk (graph-based, default 10)
  MC (15) — Module Coupling (graph-based, default 10)
  TC (15) — Test Coverage of Change (default 10)
  CS (10) — Change Scope (default 10)

Score = weighted sum / 10, range 0-100.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileMetrics:
    """Raw metrics for a single file."""

    path: str
    lines: int = 0
    any_count: int = 0
    todos: int = 0
    hardcoded_urls: int = 0
    legacy_marks: int = 0
    is_test: bool = False


@dataclass
class HealthScore:
    """8-dimension health score result."""

    score: float = 0.0
    cq: int = 10
    ts: int = 10
    mt: int = 10
    dc: int = 10
    ir: int = 10
    mc: int = 10
    tc: int = 10
    cs: int = 10
    files_scanned: int = 0
    file_metrics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "dimensions": {
                "cq": self.cq, "ts": self.ts, "mt": self.mt, "dc": self.dc,
                "ir": self.ir, "mc": self.mc, "tc": self.tc, "cs": self.cs,
            },
            "files_scanned": self.files_scanned,
            "file_metrics": self.file_metrics,
        }


# ── File scanning ──────────────────────────────────────────────

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go",
    ".rs", ".rb", ".cpp", ".c", ".h", ".cs", ".swift", ".kt",
}


def scan_file(file_path: Path) -> FileMetrics | None:
    """Scan a single file for health metrics."""
    if file_path.suffix.lower() not in CODE_EXTENSIONS:
        return None
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines = content.split("\n")
    suffix = file_path.suffix.lower()
    is_ts = suffix in (".ts", ".tsx")
    is_test = (
        ".test." in file_path.name or ".spec." in file_path.name
        or "/tests/" in str(file_path).replace("\\", "/")
        or "_test." in file_path.name
    )

    metrics = FileMetrics(path=str(file_path), lines=len(lines), is_test=is_test)
    if is_test:
        return metrics

    if is_ts:
        metrics.any_count = len(re.findall(r":\s*any\b", content))
    metrics.todos = len(re.findall(r"\bTODO\b|\bHACK\b|\bFIXME\b", content))
    metrics.hardcoded_urls = len(re.findall(r"http://", content))
    metrics.legacy_marks = len(
        re.findall(r"//\s*DEPRECATED|//\s*REMOVED|//\s*LEGACY", content)
    )
    return metrics


# ── Aggregation & scoring ──────────────────────────────────────


def scan_directory(repo_path: Path) -> list[FileMetrics]:
    """Scan all code files in a directory."""
    results: list[FileMetrics] = []
    for p in repo_path.rglob("*"):
        if p.is_file() and not any(
            part.startswith(".") for part in p.relative_to(repo_path).parts
        ):
            m = scan_file(p)
            if m is not None:
                results.append(m)
    return results


def aggregate_metrics(file_metrics: list[FileMetrics]) -> dict[str, Any]:
    """Aggregate per-file metrics into repo-level numbers."""
    prod_files = [m for m in file_metrics if not m.is_test]
    max_lines = max((m.lines for m in prod_files), default=0)
    any_count = sum(m.any_count for m in prod_files)
    mt_issues = sum(m.todos + m.hardcoded_urls for m in prod_files)
    legacy_marks = sum(m.legacy_marks for m in prod_files)
    return {
        "max_lines": max_lines,
        "any_count": any_count,
        "mt_issues": mt_issues,
        "legacy_marks": legacy_marks,
        "total_files": len(file_metrics),
        "prod_files": len(prod_files),
        "test_files": len(file_metrics) - len(prod_files),
    }


def compute_score(
    metrics: dict[str, Any],
    *,
    ir: int = 10,
    mc: int = 10,
    tc: int = 10,
    cs: int = 10,
) -> HealthScore:
    """Compute 8-dimension health score (0-100)."""
    max_lines = metrics.get("max_lines", 0)
    any_count = metrics.get("any_count", 0)
    mt_issues = metrics.get("mt_issues", 0)
    legacy_marks = metrics.get("legacy_marks", 0)

    cq = 10 if max_lines <= 300 else 9 if max_lines <= 500 else 7 if max_lines <= 800 else 5
    ts = 10 if any_count == 0 else 9 if any_count <= 5 else 7 if any_count <= 15 else 5
    mt = 10 if mt_issues == 0 else 9 if mt_issues <= 5 else 7
    dc = 10 if legacy_marks == 0 else 9 if legacy_marks <= 3 else 7 if legacy_marks <= 8 else 5

    raw = cq * 15 + ts * 10 + mt * 10 + dc * 10 + ir * 15 + mc * 15 + tc * 15 + cs * 10
    score = HealthScore(
        score=round(raw / 10, 1),
        cq=cq, ts=ts, mt=mt, dc=dc,
        ir=ir, mc=mc, tc=tc, cs=cs,
        files_scanned=metrics.get("total_files", 0),
    )
    return score


async def compute_graph_dimensions(
    client: Any,
) -> dict[str, int]:
    """Compute IR and MC from the knowledge graph.

    IR (Impact Risk): based on max fan-in (callers) of any entity.
    MC (Module Coupling): based on cross-module relation ratio.
    """
    try:
        relations = await client.get_all_relations()
    except Exception:
        return {"ir": 10, "mc": 10}

    if not relations:
        return {"ir": 10, "mc": 10}

    # IR: max fan-in
    fan_in: dict[str, int] = {}
    for r in relations:
        kw = r.get("keywords", "")
        if "CALLS" in kw.upper():
            tgt = r.get("tgt_id", "")
            if tgt:
                fan_in[tgt] = fan_in.get(tgt, 0) + 1

    max_fan = max(fan_in.values()) if fan_in else 0
    ir = 10 if max_fan <= 3 else 9 if max_fan <= 6 else 7 if max_fan <= 10 else 5

    # MC: cross-module ratio
    cross = 0
    total = len(relations)
    for r in relations:
        src = r.get("src_id", "")
        tgt = r.get("tgt_id", "")
        if "." in src and "." in tgt:
            src_mod = src.rsplit(".", 1)[0]
            tgt_mod = tgt.rsplit(".", 1)[0]
            if src_mod != tgt_mod:
                cross += 1

    ratio = cross / total if total else 0
    mc = 10 if ratio <= 0.3 else 9 if ratio <= 0.5 else 7 if ratio <= 0.7 else 5

    return {"ir": ir, "mc": mc}

