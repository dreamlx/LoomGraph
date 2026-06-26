"""Live smoke — one real DeepSeek call to validate the chain end-to-end.

Runs A-1 once on each path with deepseek-v4-flash. Total cost ≈ $0.01-0.05.
Validates:
- DeepSeek API key works
- anthropic SDK negotiates with DeepSeek's /anthropic endpoint
- Tool use in Path B actually round-trips
- Final-answer parsing makes sense

Usage:
  DEEPSEEK_API_KEY=sk-... .venv/bin/python docs/spikes/spike-30/harness/live_smoke.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import client as client_module
from harness import path_a_readme, path_b_loomgraph
from harness.schemas import GroundTruth, Task


def load_task(json_path: Path) -> Task:
    data = json.loads(json_path.read_text())
    gt = GroundTruth(**data.pop("ground_truth"))
    return Task(**data, ground_truth=gt)


def main() -> None:
    task_file = Path(__file__).parent / "tasks" / "loomgraph" / "A-1.json"
    fixture_root = Path(__file__).resolve().parents[4]
    task = load_task(task_file)

    try:
        client = client_module.get_client()
    except client_module.MissingAPIKey as e:
        print(f"❌ {e}")
        sys.exit(2)

    model = client_module.MODELS["flash"]
    print(f"=== Live smoke: {task.task_id} via {model} ===")
    print()

    print("--- Path A (README) ---")
    a = path_a_readme.run(task, fixture_root, client=client, model=model)
    if a.error:
        print(f"  ERROR: {a.error}")
    else:
        print(f"  tokens: in={a.input_tokens}, out={a.output_tokens}")
        print(f"  wall: {a.wall_seconds:.1f}s")
        print(f"  final answer (first 600 chars):")
        for line in a.final_answer[:600].splitlines()[:20]:
            print(f"    {line}")

    print()
    print("--- Path B (LOOMGRAPH) ---")
    b = path_b_loomgraph.run(task, fixture_root, client=client, model=model)
    if b.error:
        print(f"  ERROR: {b.error}")
    else:
        print(f"  tokens: in={b.input_tokens}, out={b.output_tokens}")
        print(f"  wall: {b.wall_seconds:.1f}s")
        print(f"  turns: {len(b.turns)}")
        for t in b.turns[:8]:
            if t.role == "tool":
                print(f"    [turn {t.turn_index}] tool {t.tool_name}({t.tool_input})")
            else:
                print(f"    [turn {t.turn_index}] {t.role}: {t.content[:80]}")
        print(f"  final answer (first 600 chars):")
        for line in b.final_answer[:600].splitlines()[:20]:
            print(f"    {line}")


if __name__ == "__main__":
    main()
