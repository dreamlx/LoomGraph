"""Path A — agent gets codeindex README_AI.md tree as context.

Realistic consumption: production users land here when codeindex has
already scanned, they have a tree of README_AI.md files at every dir.
Agent reads, reasons, answers.

No tool calls — README_AI is the entire context.
"""

from __future__ import annotations

import time
from pathlib import Path

from .schemas import AgentRun, Task, TurnLog

# Maximum chars of README_AI tree to include in context. Realistic agents
# truncate too — passing 200k+ tokens of README to a Haiku is unfair to
# Path A. Cap at ~30k chars (~7-8k tokens) which is what an agent would
# typically grep+sample if they tried to read it all.
MAX_README_CHARS = 30_000

# Skip vendored / build / cache dirs that contain READMEs for THIRD-PARTY
# code, not for the fixture under test.
EXCLUDE_DIRS = {
    ".venv", "venv", "env", ".env",
    "node_modules",
    "site-packages",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "target",
    ".git",
    "docs/spikes",  # don't include this spike's own task labels
}


def _collect_readme_tree(fixture_root: Path) -> str:
    """Concatenate all README_AI.md files under fixture_root, deepest-first
    by directory depth (so top-level overview comes last → most recent in
    context for Haiku's recency bias)."""
    all_readmes = list(fixture_root.rglob("README_AI.md"))
    readmes = []
    for r in all_readmes:
        rel_parts = r.relative_to(fixture_root).parts
        if any(part in EXCLUDE_DIRS for part in rel_parts):
            continue
        # also catch composite paths like docs/spikes
        rel_str = str(r.relative_to(fixture_root))
        if any(excl in rel_str for excl in EXCLUDE_DIRS if "/" in excl):
            continue
        readmes.append(r)
    readmes.sort(key=lambda p: (-len(p.relative_to(fixture_root).parts), str(p)))
    sections: list[str] = []
    total = 0
    for r in readmes:
        rel = r.relative_to(fixture_root)
        body = r.read_text(errors="replace")
        section = f"\n\n=== {rel} ===\n{body}"
        if total + len(section) > MAX_README_CHARS:
            sections.append(
                f"\n\n[truncated — {len(readmes)} README_AI files total, showing first {len(sections)}]"
            )
            break
        sections.append(section)
        total += len(section)
    return "".join(sections)


SYSTEM_PROMPT = """You are a code-understanding agent given codeindex-generated
README_AI.md files describing a codebase. Use them to answer the user's
question precisely. Output ONLY the answer — one qualified entity name per
line for "list" questions, a 1-2 sentence summary for "what does X do"
questions. Do not explain. Do not include entities you didn't find evidence
for in the READMEs."""


def build_messages(task: Task, fixture_root: Path) -> list[dict]:
    """Return the Anthropic-style message list. No tools."""
    context = _collect_readme_tree(fixture_root)
    user_content = (
        f"=== README_AI tree for {fixture_root.name} ===\n{context}\n\n"
        f"=== Question ===\n{task.prompt}"
    )
    return [{"role": "user", "content": user_content}]


def run(
    task: Task,
    fixture_root: Path,
    run_index: int = 0,
    *,
    client=None,
    model: str = "deepseek-v4-flash",
    max_tokens: int = 8000,  # DeepSeek v4 is reasoning-style; needs room for thinking + answer
    dry_run: bool = False,
) -> AgentRun:
    """Execute Path A for one task.

    `dry_run=True` returns the rendered context without calling the API —
    used for structural smoke / harness debugging.
    """
    messages = build_messages(task, fixture_root)

    if dry_run:
        return AgentRun(
            task_id=task.task_id,
            path="README",
            run_index=run_index,
            final_answer="[dry-run]",
            turns=[
                TurnLog(
                    turn_index=0,
                    role="user",
                    content=messages[0]["content"][:200] + "..."
                    if len(messages[0]["content"]) > 200
                    else messages[0]["content"],
                )
            ],
            input_tokens=len(messages[0]["content"]) // 4,  # rough estimate
            output_tokens=0,
        )

    if client is None:
        raise RuntimeError(
            "Path A requires an Anthropic client (or dry_run=True). "
            "Set ANTHROPIC_API_KEY and pass `anthropic.Anthropic()`."
        )

    t0 = time.perf_counter()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except Exception as ex:
        return AgentRun(
            task_id=task.task_id,
            path="README",
            run_index=run_index,
            final_answer="",
            error=f"{type(ex).__name__}: {ex}",
            wall_seconds=time.perf_counter() - t0,
        )

    wall = time.perf_counter() - t0
    # DeepSeek v4 returns interleaved thinking + text blocks. Final answer is
    # in text blocks. When the model legitimately refuses (e.g. "I cannot
    # find this in the READMEs, so I will output nothing"), the text block
    # is empty and we keep it empty — that's a true 0-recall result, not a
    # bug. Don't fabricate an answer from thinking-tail garble.
    text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    return AgentRun(
        task_id=task.task_id,
        path="README",
        run_index=run_index,
        final_answer=text.strip(),
        turns=[
            TurnLog(0, "user", messages[0]["content"][:200] + "..."),
            TurnLog(1, "assistant", text),
        ],
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        wall_seconds=wall,
    )
