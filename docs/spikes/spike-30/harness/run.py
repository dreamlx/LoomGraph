"""Day-2 orchestrator — runs path A + B × N runs across all (or filtered) tasks.

Per PLAN.md §9 + post-D5 sequential-per-task / parallel-per-path:
- Outer loop: tasks (sequential)
- Inner: A run × N, B run × N — can be threaded later; v1 sequential

Per PLAN.md §5: write each AgentRun to results/runs.jsonl as it completes
(crash-resilient, incremental partial results inspectable).

Usage:
  # Smoke (D6=C): one task per class
  DEEPSEEK_API_KEY=sk-... .venv/bin/python -m harness.run --smoke

  # Full flash baseline (D5=B)
  DEEPSEEK_API_KEY=sk-... .venv/bin/python -m harness.run --tier flash

  # Stronger-tier comparison
  DEEPSEEK_API_KEY=sk-... .venv/bin/python -m harness.run --tier pro
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import client as client_module
from harness import path_a_readme, path_b_loomgraph
from harness.schemas import AgentRun, GroundTruth, Task

REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS_DIR = Path(__file__).resolve().parent
TASKS_DIR = HARNESS_DIR / "tasks" / "loomgraph"
RESULTS_DIR = HARNESS_DIR / "results"

# Per D6=C: one task per class for the pre-flight smoke
SMOKE_TASK_IDS = ["loomgraph-A-1", "loomgraph-B-1", "loomgraph-C-1",
                  "loomgraph-D-1", "loomgraph-E-1", "loomgraph-F-1"]


def load_task(path: Path) -> Task:
    data = json.loads(path.read_text())
    gt = GroundTruth(**data.pop("ground_truth"))
    return Task(**data, ground_truth=gt)


def load_all_tasks() -> list[Task]:
    tasks = []
    for f in sorted(TASKS_DIR.glob("*.json")):
        tasks.append(load_task(f))
    return tasks


def run_one(
    task: Task,
    path: str,
    run_index: int,
    *,
    client,
    model: str,
) -> AgentRun:
    """Dispatch to the right runner."""
    if path == "README":
        return path_a_readme.run(
            task, REPO_ROOT, run_index=run_index, client=client, model=model
        )
    return path_b_loomgraph.run(
        task, REPO_ROOT, run_index=run_index, client=client, model=model
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true",
                        help="Only run SMOKE_TASK_IDS × N=1 per path")
    parser.add_argument("--tier", choices=["flash", "pro"], default="flash")
    parser.add_argument("-n", "--num-runs", type=int, default=3,
                        help="Runs per (task, path) — N in PLAN.md")
    parser.add_argument("--paths", default="README,LOOMGRAPH",
                        help="Comma-separated paths to run")
    parser.add_argument("--out", default=None,
                        help="JSONL output file (default: results/runs-<tier>[-smoke].jsonl)")
    args = parser.parse_args()

    if args.smoke:
        args.num_runs = 1

    paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    tasks = load_all_tasks()
    if args.smoke:
        tasks = [t for t in tasks if t.task_id in set(SMOKE_TASK_IDS)]
    if not tasks:
        print("No tasks matched.", file=sys.stderr)
        sys.exit(1)

    out_name = args.out or f"runs-{args.tier}{'-smoke' if args.smoke else ''}.jsonl"
    out_path = RESULTS_DIR / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        client = client_module.get_client()
    except client_module.MissingAPIKey as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(2)
    model = client_module.MODELS[args.tier]

    total_runs = len(tasks) * len(paths) * args.num_runs
    print(f"=== Spike-30 run ===")
    print(f"tier:    {args.tier} → {model}")
    print(f"tasks:   {len(tasks)} ({'smoke' if args.smoke else 'full'})")
    print(f"paths:   {paths}")
    print(f"N:       {args.num_runs}")
    print(f"total:   {total_runs} runs")
    print(f"output:  {out_path.relative_to(REPO_ROOT)}")
    print()

    t_start = time.perf_counter()
    completed = 0
    with out_path.open("w") as f:
        for task in tasks:
            print(f"[{task.task_id}] class={task.task_class} expected={len(task.ground_truth.expected)}")
            for path in paths:
                for run_index in range(args.num_runs):
                    t0 = time.perf_counter()
                    result = run_one(task, path, run_index, client=client, model=model)
                    elapsed = time.perf_counter() - t0
                    completed += 1
                    status = "✗" if result.error else "✓"
                    answer_preview = (result.final_answer or "")[:60].replace("\n", " ⏎ ")
                    print(f"  {status} {path:9s} run={run_index} "
                          f"{result.input_tokens:5d}in/{result.output_tokens:4d}out "
                          f"{elapsed:.1f}s → {answer_preview}")
                    f.write(json.dumps(dataclasses.asdict(result)) + "\n")
                    f.flush()
    wall = time.perf_counter() - t_start
    print()
    print(f"Done — {completed} runs in {wall:.0f}s")
    print(f"Results: {out_path}")


if __name__ == "__main__":
    main()
