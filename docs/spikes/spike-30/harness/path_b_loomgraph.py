"""Path B — agent gets structured graph access via loomgraph CLI tools.

The agent can call:
- loomgraph_find(query, type?)
- loomgraph_graph(entity, direction?, depth?)
- loomgraph_topology(module?)
- loomgraph_impact(target, depth?)

Outputs are the same JSON loomgraph CLI emits — agent reads it directly.
Max 10 turns per task per PLAN.md §4.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .schemas import AgentRun, Task, TurnLog

MAX_TURNS = 10

TOOLS = [
    {
        "name": "loomgraph_find",
        "description": (
            "Fuzzy-match entities by name. Returns up to 20 matches with "
            "entity_type, source_id (file:line), and a relevance score. Use "
            "this first to find the exact qualified name of an entity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name fragment to search for."},
                "entity_type": {
                    "type": "string",
                    "description": "Optional filter: class | function | method | module.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "loomgraph_graph",
        "description": (
            "Walk the CALLS/INHERITS/IMPORTS edges of a specific entity. "
            "Returns callers (who calls this) and callees (who this calls). "
            "Use after loomgraph_find to confirm the exact entity name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Qualified entity name (e.g. 'ClassName.method').",
                },
                "direction": {
                    "type": "string",
                    "enum": ["callers", "callees", "both"],
                    "description": "Default: both.",
                },
                "depth": {"type": "integer", "description": "Default: 1."},
            },
            "required": ["entity"],
        },
    },
    {
        "name": "loomgraph_topology",
        "description": (
            "Topology smells across the workspace: orphan entities (no callers/"
            "callees), hub entities (many callers), god functions (many callees)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": "Optional source_id prefix to filter (e.g. 'src/loomgraph/cli').",
                },
            },
        },
    },
    {
        "name": "loomgraph_impact",
        "description": (
            "Analyze impact of changing a target (commit ref / file / entity). "
            "Returns direct + indirect callers up to specified depth."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "git ref or entity name"},
                "depth": {"type": "integer", "description": "Default: 2."},
            },
            "required": ["target"],
        },
    },
]


SYSTEM_PROMPT = """You are a code-understanding agent with access to the
`loomgraph` knowledge graph for a codebase. Available tools query a SQLite +
sqlite-vec graph built deterministically from tree-sitter AST extraction.

Use the tools to gather concrete answers. Tool output is JSON — read it
precisely. Don't guess entity names; always loomgraph_find first to get
the exact qualified name.

When you have the answer, output ONLY the answer — one qualified entity
name per line for "list" questions, a 1-2 sentence summary for "what does
X do" questions. Do not explain. Do not include entities not surfaced by
tool output."""


def _resolve_loomgraph_bin() -> str:
    """Find the loomgraph binary. Prefer the env override, then the dev
    venv next to the project, then PATH lookup."""
    if env := os.environ.get("LOOMGRAPH_BIN"):
        return env
    repo_root = Path(__file__).resolve().parents[4]
    venv_bin = repo_root / ".venv" / "bin" / "loomgraph"
    if venv_bin.exists():
        return str(venv_bin)
    return "loomgraph"  # fall back to PATH


_LOOMGRAPH_BIN = _resolve_loomgraph_bin()


def _run_loomgraph(args: list[str], *, cwd: Path, timeout: float = 30.0) -> str:
    """Subprocess `loomgraph <args>` in `cwd`. Returns stdout (JSON)."""
    try:
        result = subprocess.run(
            [_LOOMGRAPH_BIN, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "timeout"})
    except FileNotFoundError:
        return json.dumps(
            {"success": False, "error": "loomgraph CLI not on PATH"}
        )
    if result.returncode != 0 and not result.stdout:
        return json.dumps(
            {"success": False, "error": result.stderr.strip()[:500]}
        )
    return result.stdout.strip() or json.dumps(
        {"success": False, "error": "empty"}
    )


def _dispatch_tool(name: str, args: dict, *, fixture_root: Path) -> str:
    if name == "loomgraph_find":
        cli = ["find", args["query"]]
        if args.get("entity_type"):
            cli += ["--type", args["entity_type"]]
        cli += ["--limit", "20"]
        return _run_loomgraph(cli, cwd=fixture_root)
    if name == "loomgraph_graph":
        cli = ["graph", args["entity"]]
        if args.get("direction"):
            cli += ["--direction", args["direction"]]
        if args.get("depth"):
            cli += ["--depth", str(args["depth"])]
        return _run_loomgraph(cli, cwd=fixture_root)
    if name == "loomgraph_topology":
        cli = ["topology"]
        if args.get("module"):
            cli += ["--module", args["module"]]
        return _run_loomgraph(cli, cwd=fixture_root)
    if name == "loomgraph_impact":
        cli = ["impact", args["target"]]
        if args.get("depth"):
            cli += ["--depth", str(args["depth"])]
        return _run_loomgraph(cli, cwd=fixture_root)
    return json.dumps({"success": False, "error": f"unknown tool {name}"})


def run(
    task: Task,
    fixture_root: Path,
    run_index: int = 0,
    *,
    client=None,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 1024,
    dry_run: bool = False,
) -> AgentRun:
    """Execute Path B for one task with tool use loop."""
    if dry_run:
        # Just smoke that loomgraph_find works on the task subject.
        # Pull the most-cited proper-noun-like token from the prompt heuristically.
        # Cleanup punctuation around tokens.
        toks = [
            t.strip("`.,;:?!()'\"")
            for t in task.prompt.split()
            if any(c in t for c in (".", "_")) or (t[:1].isupper() and t[:1].isalpha())
        ]
        # Filter out boilerplate words
        sample = next(
            (t for t in toks if len(t) > 3 and not t.startswith("I")),
            "Settings",
        )
        out = _run_loomgraph(["find", sample, "--limit", "5"], cwd=fixture_root)
        return AgentRun(
            task_id=task.task_id,
            path="LOOMGRAPH",
            run_index=run_index,
            final_answer="[dry-run]",
            turns=[
                TurnLog(0, "tool", out[:400], tool_name="loomgraph_find",
                        tool_input={"query": sample, "limit": 5}),
            ],
            input_tokens=300,  # rough estimate for tool def + system
            output_tokens=0,
        )

    if client is None:
        raise RuntimeError(
            "Path B requires an Anthropic client (or dry_run=True). "
            "Set ANTHROPIC_API_KEY."
        )

    messages: list[dict] = [{"role": "user", "content": task.prompt}]
    turns: list[TurnLog] = []
    total_in = 0
    total_out = 0
    t0 = time.perf_counter()
    final_answer = ""

    for turn_index in range(MAX_TURNS):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as ex:
            return AgentRun(
                task_id=task.task_id,
                path="LOOMGRAPH",
                run_index=run_index,
                final_answer=final_answer,
                turns=turns,
                input_tokens=total_in,
                output_tokens=total_out,
                wall_seconds=time.perf_counter() - t0,
                error=f"{type(ex).__name__}: {ex}",
            )

        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens
        messages.append({"role": "assistant", "content": response.content})

        # Collect any text + any tool_use
        text_parts: list[str] = []
        tool_uses: list[tuple[str, str, dict]] = []  # (tool_use_id, name, input)
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append((block.id, block.name, dict(block.input)))

        text_combined = "".join(text_parts).strip()
        if text_combined:
            turns.append(
                TurnLog(turn_index, "assistant", text_combined)
            )

        if response.stop_reason == "end_turn" and not tool_uses:
            final_answer = text_combined
            break

        if not tool_uses:
            # Model stopped without tool call and without final answer — accept text
            final_answer = text_combined
            break

        # Dispatch tools, accumulate tool_result blocks
        tool_results = []
        for tu_id, name, args in tool_uses:
            out = _dispatch_tool(name, args, fixture_root=fixture_root)
            # Cap each tool output at 12k chars to avoid context blow-up
            if len(out) > 12_000:
                out = out[:12_000] + "\n[...truncated]"
            turns.append(
                TurnLog(
                    turn_index, "tool", out[:400],
                    tool_name=name, tool_input=args, tool_output=out[:400]
                )
            )
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu_id, "content": out}
            )
        messages.append({"role": "user", "content": tool_results})
    else:
        # Hit MAX_TURNS without end_turn
        final_answer = text_combined  # whatever the last assistant said

    return AgentRun(
        task_id=task.task_id,
        path="LOOMGRAPH",
        run_index=run_index,
        final_answer=final_answer,
        turns=turns,
        input_tokens=total_in,
        output_tokens=total_out,
        wall_seconds=time.perf_counter() - t0,
    )
