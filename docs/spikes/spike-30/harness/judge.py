"""Per-run scorer. Reads AgentRun + Task → ScoredRun.

Scoring rules (per PLAN.md §5):
- Correctness: 1.0 if answer matches expected set within tolerance, 0.5 partial, 0.0 none
- Recall: |answer ∩ expected| / |expected|
- Hallucination: count of answer entities NOT present anywhere in the fixture's known entity universe
- Misresolution (F-class only): count of answer entities in `misresolution_traps`
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .schemas import AgentRun, ScoredRun, Task

# Threshold: how much overlap with `expected` counts as "1.0 correct"
FULL_MATCH_RECALL = 0.7
PARTIAL_MATCH_RECALL = 0.3


def _normalize_entity(s: str) -> str:
    """Strip whitespace, qualified-name punctuation noise."""
    return re.sub(r"\s+", "", s).strip().strip(".")


def _extract_answer_entities(answer_text: str) -> list[str]:
    """Pull entity-name-looking tokens out of the agent's final answer.

    Heuristic: lines starting with optional bullet/numbering, containing
    dot or CamelCase, no spaces. We're generous because the prompt asked
    for "one entity per line".
    """
    entities = []
    for line in answer_text.splitlines():
        line = re.sub(r"^[-•*\d\.\)\(\s]+", "", line).strip()
        if not line:
            continue
        # Stop at first whitespace — entity names don't have spaces
        first = line.split()[0]
        first = first.rstrip(",.;:")
        if first and (re.search(r"[A-Z]", first) or "." in first or "_" in first):
            entities.append(_normalize_entity(first))
    return entities


def _fixture_entity_universe(fixture_root: Path) -> set[str]:
    """Pull all known qualified entity names from loomgraph workspace for
    hallucination detection. Run `loomgraph find` with an empty/wildcard
    query? CLI has no list-all, so use a broad search."""
    # Easiest: query find with the alphabet, dedupe. Hacky but fine for spike.
    universe: set[str] = set()
    for letter in "abcdefghijklmnopqrstuvwxyz":
        try:
            out = subprocess.run(
                ["loomgraph", "find", letter, "--limit", "100"],
                cwd=str(fixture_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            data = json.loads(out.stdout)
            for m in data.get("data", {}).get("matches", []):
                if m.get("entity"):
                    universe.add(_normalize_entity(m["entity"]))
        except Exception:
            continue
    return universe


def score(
    run: AgentRun,
    task: Task,
    fixture_universe: set[str],
) -> ScoredRun:
    """Compute ScoredRun from AgentRun against Task ground truth + fixture entities."""
    answer_entities = _extract_answer_entities(run.final_answer)
    expected = {_normalize_entity(e) for e in task.ground_truth.expected}
    found_expected = {e for e in answer_entities if e in expected}

    recall = len(found_expected) / len(expected) if expected else 0.0

    # Correctness tiers
    if recall >= FULL_MATCH_RECALL:
        correctness = 1.0
    elif recall >= PARTIAL_MATCH_RECALL:
        correctness = 0.5
    else:
        correctness = 0.0

    # For C-class: must_mention substring check
    if task.task_class == "C" and task.ground_truth.must_mention:
        text_lower = run.final_answer.lower()
        mentions = sum(
            1 for kw in task.ground_truth.must_mention
            if kw.lower() in text_lower
        )
        # Override correctness with phrase-match for C
        if mentions == len(task.ground_truth.must_mention):
            correctness = 1.0
        elif mentions >= 1:
            correctness = 0.5
        else:
            correctness = 0.0
        recall = mentions / max(1, len(task.ground_truth.must_mention))

    # Hallucination: answer entities not in fixture at all
    hallucinations = [
        e for e in answer_entities
        if e not in fixture_universe and e not in expected
    ]

    # Misresolution (F-class): answer entities that ARE in the misresolution_traps list
    misres = 0
    if task.task_class == "F" and task.ground_truth.misresolution_traps:
        traps = {_normalize_entity(t) for t in task.ground_truth.misresolution_traps}
        misres = sum(1 for e in answer_entities if e in traps)

    return ScoredRun(
        task_id=run.task_id,
        path=run.path,
        run_index=run.run_index,
        correctness=correctness,
        recall=recall,
        hallucination_count=len(hallucinations),
        misresolution_count=misres,
        tokens_total=run.input_tokens + run.output_tokens,
        wall_seconds=run.wall_seconds,
    )
