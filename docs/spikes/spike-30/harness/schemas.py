"""Task + result schemas for spike #30.

Each Task captures:
- WHAT the agent is asked (`prompt`)
- WHAT counts as a correct answer (`ground_truth`)
- Which class (A-F) and sub-type (e.g. F1) — for per-class verdict aggregation
- Which fixture (loomgraph / internal-ts) — for fixture-level analysis

The agent under test gets ONLY `prompt`. Ground truth is for scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TaskClass = Literal["A", "B", "C", "D", "E", "F"]
SubType = str  # e.g. "A1", "E2", "F3"
Path = Literal["README", "LOOMGRAPH"]


@dataclass
class GroundTruth:
    """Hand-labelled correct answer.

    Different classes need different structures:
    - A/B/E: set of qualified entity names (callers, chain elements)
    - C: list of accepted summary keywords / phrases
    - D: set of related entity names
    - F: a "wrong but plausible" set the agent must NOT confuse with the right answer

    Shape stays flexible (dict) so per-class scorers can interpret freely.
    """

    expected: list[str] = field(default_factory=list)
    # F-class: entities that look like answers but are wrong (collision targets)
    misresolution_traps: list[str] = field(default_factory=list)
    # C-class: must contain at least one of these phrases (substring match, lowercased)
    must_mention: list[str] = field(default_factory=list)
    # Allow extra room per class:
    notes: str = ""


@dataclass
class Task:
    """A single spike task."""

    task_id: str             # e.g. "loomgraph-A-1"
    fixture: str             # "loomgraph" or "internal-ts"
    task_class: TaskClass
    subtype: SubType
    prompt: str              # what the agent sees
    ground_truth: GroundTruth
    # Why this task tests what its class claims to test — auditable
    rationale: str = ""
    # Where in the fixture the ground truth came from (auditor can re-check)
    sources: list[str] = field(default_factory=list)


@dataclass
class TurnLog:
    """One agent turn (tool call or response)."""

    turn_index: int
    role: str                # "assistant" or "tool"
    content: str             # text or tool call summary
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: str | None = None


@dataclass
class AgentRun:
    """One end-to-end agent run for one task on one path."""

    task_id: str
    path: Path
    run_index: int            # 0..N-1 (for N=3)
    final_answer: str         # parsed answer (entity names / summary text)
    turns: list[TurnLog] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    wall_seconds: float = 0.0
    error: str | None = None  # set if run failed before reaching final answer


@dataclass
class ScoredRun:
    """Per-run score, computed by judge.py against ground truth."""

    task_id: str
    path: Path
    run_index: int
    correctness: float        # 1.0 / 0.5 / 0.0
    recall: float             # |answer ∩ truth| / |truth|, 0..1
    hallucination_count: int  # entities in answer that don't exist in fixture
    misresolution_count: int  # F-class only: existed but wrong target
    tokens_total: int
    wall_seconds: float
