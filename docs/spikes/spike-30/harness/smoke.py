"""Smoke runner — exercises Path A + Path B in dry_run mode on one task.

Confirms:
- Task JSON loads against schema
- Path A renders README_AI tree successfully
- Path B can subprocess `loomgraph find` against the fixture
- No API key needed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make `harness` importable as a package when run as `python -m`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import path_a_readme, path_b_loomgraph
from harness.schemas import GroundTruth, Task


def load_task(json_path: Path) -> Task:
    data = json.loads(json_path.read_text())
    gt = GroundTruth(**data.pop("ground_truth"))
    return Task(**data, ground_truth=gt)


def main() -> None:
    task_file = Path(__file__).parent / "tasks" / "loomgraph" / "A-1.json"
    # __file__ = docs/spikes/spike-30/harness/smoke.py → repo root is parents[4]
    fixture_root = Path(__file__).resolve().parents[4]
    task = load_task(task_file)

    print(f"=== Smoke: {task.task_id} (class {task.task_class}/{task.subtype}) ===")
    print(f"fixture: {fixture_root}")
    print(f"prompt: {task.prompt[:80]}...")
    print(f"ground_truth.expected ({len(task.ground_truth.expected)} entities):")
    for e in task.ground_truth.expected:
        print(f"  - {e}")
    print()

    print("=== Path A (README) — dry run ===")
    a = path_a_readme.run(task, fixture_root, dry_run=True)
    print(f"  estimated input tokens: {a.input_tokens}")
    print(f"  context preview (first 200 chars):")
    print(f"    {a.turns[0].content}")
    print()

    print("=== Path B (LOOMGRAPH) — dry run ===")
    b = path_b_loomgraph.run(task, fixture_root, dry_run=True)
    print(f"  estimated input tokens: {b.input_tokens}")
    print(f"  tool call: {b.turns[0].tool_name}({b.turns[0].tool_input})")
    print(f"  tool output preview (first 400 chars):")
    print(f"    {b.turns[0].content}")


if __name__ == "__main__":
    main()
