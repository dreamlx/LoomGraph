"""Per-run scorer. Reads AgentRun + Task → ScoredRun.

Scoring rules (per PLAN.md §5):
- Correctness: 1.0 if answer matches expected set within tolerance, 0.5 partial, 0.0 none
- Recall: |answer ∩ expected| / |expected|
- Hallucination: count of answer entities NOT present anywhere in the fixture's known entity universe
- Misresolution (F-class only): count of answer entities in `misresolution_traps`
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .schemas import AgentRun, ScoredRun, Task


def _resolve_loomgraph_bin() -> str:
    if env := os.environ.get("LOOMGRAPH_BIN"):
        return env
    repo_root = Path(__file__).resolve().parents[4]
    venv_bin = repo_root / ".venv" / "bin" / "loomgraph"
    if venv_bin.exists():
        return str(venv_bin)
    return "loomgraph"


_LOOMGRAPH_BIN = _resolve_loomgraph_bin()


# Threshold: how much overlap with `expected` counts as "1.0 correct"
FULL_MATCH_RECALL = 0.7
PARTIAL_MATCH_RECALL = 0.3


def _normalize_entity(s: str) -> str:
    """Strip whitespace + markdown wrapping (backticks, brackets) +
    qualified-name punctuation noise from an entity-name candidate."""
    s = re.sub(r"\s+", "", s).strip()
    # Strip surrounding markdown / quote marks
    s = s.strip("`*_'\"")
    # Strip leading namespace if present — score on the last qualified segment
    # so `loomgraph.cli._analysis.topology` matches `topology` from expected.
    # But also accept fully qualified match — return both forms?
    # Simpler: keep full path, and also accept tail match in score().
    return s.strip(".").strip()


def _extract_answer_entities(answer_text: str) -> list[str]:
    """Pull entity-name-looking tokens out of the agent's final answer.

    Models surface answers as:
        `entity_name`
        - entity_name
        1. entity_name
        loomgraph.module.entity_name
        Class.method
    """
    entities = []
    for raw in answer_text.splitlines():
        # Strip bullets, numbering, leading whitespace
        line = re.sub(r"^[-•*>+\d\.\)\(\s]+", "", raw).strip()
        if not line:
            continue
        # Take first whitespace-bounded token, strip markdown wrappers
        first = line.split()[0]
        first = first.strip("`*_'\"().,;:")
        if not first:
            continue
        # Heuristic: real entity tokens have letters + (camelCase | underscore | dot)
        if re.search(r"[A-Za-z]", first) and (
            "_" in first or "." in first or re.search(r"[a-z][A-Z]", first)
            or first[0].isupper() or len(first) >= 3
        ):
            entities.append(_normalize_entity(first))
    return entities


def _fixture_entity_universe(fixture_root: Path) -> set[str]:
    """Pull all known qualified entity names from loomgraph workspace for
    hallucination detection. Run `loomgraph find` with an empty/wildcard
    query? CLI has no list-all, so use a broad search."""
    # Easiest: query find with the alphabet, dedupe. Hacky but fine for spike.
    universe: set[str] = set()
    for letter in "abcdefghijklmnopqrstuvwxyz_":
        try:
            out = subprocess.run(
                [_LOOMGRAPH_BIN, "find", letter, "--limit", "100"],
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

    # Match an answer entity against expected by:
    # (a) exact normalized match, or
    # (b) tail-segment match — e.g. answer `loomgraph.cli._search.find` matches expected `find`.
    # Expected names are also tail-checked against answer for the reverse case.
    def matches_expected(ans: str, exp_set: set[str]) -> bool:
        if ans in exp_set:
            return True
        # Tail of answer against expected
        tail = ans.rsplit(".", 1)[-1]
        if tail in exp_set:
            return True
        # Tail of expected against answer
        for e in exp_set:
            if "." in e and e.rsplit(".", 1)[-1] == ans:
                return True
        return False

    found_expected = set()
    for ans in answer_entities:
        if matches_expected(ans, expected):
            # Record which expected entity we matched (for accurate count)
            tail = ans.rsplit(".", 1)[-1]
            if ans in expected:
                found_expected.add(ans)
            elif tail in expected:
                found_expected.add(tail)
            else:
                # Reverse-tail match
                for e in expected:
                    if "." in e and e.rsplit(".", 1)[-1] == ans:
                        found_expected.add(e)
                        break

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

    # Hallucination: answer entities not in fixture at all (tail-aware too)
    def in_universe(e: str) -> bool:
        if e in fixture_universe:
            return True
        tail = e.rsplit(".", 1)[-1]
        if tail in fixture_universe:
            return True
        # universe has fully-qualified names; check if any universe entity ends with `.{e}`
        for u in fixture_universe:
            if "." in u and u.rsplit(".", 1)[-1] == e:
                return True
        return False

    hallucinations = [
        e for e in answer_entities
        if not in_universe(e) and e not in expected
    ]

    # Misresolution (any class with traps defined, not just F):
    misres = 0
    if task.ground_truth.misresolution_traps:
        traps = {_normalize_entity(t) for t in task.ground_truth.misresolution_traps}
        for ans in answer_entities:
            if ans in traps:
                misres += 1
                continue
            tail = ans.rsplit(".", 1)[-1]
            if tail in traps:
                misres += 1
                continue
            for t in traps:
                if "." in t and t.rsplit(".", 1)[-1] == ans:
                    misres += 1
                    break

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
