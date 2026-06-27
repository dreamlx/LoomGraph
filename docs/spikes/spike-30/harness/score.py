"""Day-2 scorer — reads runs JSONL → ScoredRun JSONL + per-class aggregates.

Reads each AgentRun, applies the per-class rules from judge.py, writes
per-run scores + prints per-class verdict table against PLAN.md §6
pre-registered thresholds.

Usage:
  .venv/bin/python -m harness.score \
    --runs results/runs-flash-smoke.jsonl \
    --out  results/scored-flash-smoke.jsonl
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import judge
from harness.schemas import AgentRun, GroundTruth, ScoredRun, Task, TurnLog

HARNESS_DIR = Path(__file__).resolve().parent
TASKS_DIR = HARNESS_DIR / "tasks" / "loomgraph"
REPO_ROOT = Path(__file__).resolve().parents[4]


def load_task(path: Path) -> Task:
    data = json.loads(path.read_text())
    gt = GroundTruth(**data.pop("ground_truth"))
    return Task(**data, ground_truth=gt)


def rebuild_run(d: dict) -> AgentRun:
    turns = [TurnLog(**t) for t in d.pop("turns", [])]
    return AgentRun(**d, turns=turns)


def load_runs(path: Path) -> list[AgentRun]:
    """Tolerate occasional malformed lines (race-corrupted entries)."""
    runs = []
    with path.open() as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(rebuild_run(json.loads(line)))
            except (json.JSONDecodeError, TypeError) as e:
                print(f"  skip line {i}: {type(e).__name__}", file=sys.stderr)
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    runs = load_runs(args.runs)
    tasks_by_id = {}
    for f in TASKS_DIR.glob("*.json"):
        t = load_task(f)
        tasks_by_id[t.task_id] = t

    # Build fixture universe once
    print(f"Loading fixture entity universe (may take ~10s)...", file=sys.stderr)
    universe = judge._fixture_entity_universe(REPO_ROOT)
    print(f"  universe size: {len(universe)} unique entities", file=sys.stderr)

    scored: list[ScoredRun] = []
    for r in runs:
        task = tasks_by_id.get(r.task_id)
        if task is None:
            print(f"  warn: no task for {r.task_id}", file=sys.stderr)
            continue
        scored.append(judge.score(r, task, universe))

    out = args.out or args.runs.with_name(args.runs.stem.replace("runs", "scored") + ".jsonl")
    with out.open("w") as f:
        for s in scored:
            f.write(json.dumps(dataclasses.asdict(s)) + "\n")
    print(f"\nWrote {len(scored)} scored runs → {out}", file=sys.stderr)

    # Aggregate per (task_id, path) median across runs, then per class
    by_task_path = defaultdict(list)
    for s in scored:
        by_task_path[(s.task_id, s.path)].append(s)

    print()
    print(f"{'TASK':18s} {'CLS':>4s}  {'PATH':10s}  {'CORR':>5s}  {'RECALL':>6s}  {'HALL':>4s}  {'MISRES':>6s}  {'TOK':>6s}")
    print("-" * 80)
    by_class_path = defaultdict(list)
    for (task_id, path), srs in sorted(by_task_path.items()):
        med_corr = median(s.correctness for s in srs)
        med_recall = median(s.recall for s in srs)
        med_hall = median(s.hallucination_count for s in srs)
        med_misres = median(s.misresolution_count for s in srs)
        med_tok = int(median(s.tokens_total for s in srs))
        cls = tasks_by_id[task_id].task_class
        print(f"{task_id:18s} {cls:>4s}  {path:10s}  {med_corr:>5.2f}  {med_recall:>6.2f}  {med_hall:>4d}  {med_misres:>6d}  {med_tok:>6d}")
        by_class_path[(cls, path)].append((med_corr, med_recall, med_hall, med_misres, med_tok))

    print()
    print(f"=== Per-class aggregates (median of task medians) ===")
    print(f"{'CLS':>4s}  {'PATH':10s}  {'CORR':>5s}  {'RECALL':>6s}  {'HALL':>4s}  {'MISRES':>6s}  {'N':>3s}")
    print("-" * 60)
    for (cls, path), rows in sorted(by_class_path.items()):
        if not rows:
            continue
        corr = median(r[0] for r in rows)
        recall = median(r[1] for r in rows)
        hall = median(r[2] for r in rows)
        misres = median(r[3] for r in rows)
        print(f"{cls:>4s}  {path:10s}  {corr:>5.2f}  {recall:>6.2f}  {hall:>4.0f}  {misres:>6.0f}  {len(rows):>3d}")

    # PLAN §6 gate evaluation
    print()
    print("=== PLAN.md §6 pre-registered gates (Path B - Path A delta) ===")
    deltas = {}
    for cls in ["A", "B", "C", "D", "E", "F"]:
        a_rows = by_class_path.get((cls, "README"), [])
        b_rows = by_class_path.get((cls, "LOOMGRAPH"), [])
        if not a_rows or not b_rows:
            continue
        d_corr = median(r[0] for r in b_rows) - median(r[0] for r in a_rows)
        d_recall = median(r[1] for r in b_rows) - median(r[1] for r in a_rows)
        a_misres = median(r[3] for r in a_rows)
        b_misres = median(r[3] for r in b_rows)
        deltas[cls] = (d_corr, d_recall, b_misres)
        green = (d_corr >= 0.20) or (d_recall >= 0.30)
        print(f"  Class {cls}: Δcorr={d_corr:+.2f}  Δrecall={d_recall:+.2f}  B_misres={b_misres:.0f}  "
              f"{'✓ GREEN-eligible' if green else '· no GREEN'}")


if __name__ == "__main__":
    main()
