"""Tests for explicit orientation-use and target-kind metrics."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_MODULE_PATH = Path(__file__).with_name("summarize-orientation-pilot.py")
_SPEC = importlib.util.spec_from_file_location("summarize_orientation_pilot", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_module)


def _packet(
    *, commands: list[str], paths: list[str], tool_call_count: int = 0,
    orientation_mode: str = "voluntary", retrieval_required: bool = False,
    retrieval_requirement_met: bool | None = None,
    retrieval_succeeded: bool | None = None,
) -> dict[str, object]:
    return {
        "status": "complete",
        "pre_edit": True,
        "response_format": "raw_json",
        "orientation_mode": orientation_mode,
        "tool_call_count": tool_call_count,
        "tool_call_budget": 5,
        "tool_call_budget_overrun": tool_call_count > 5,
        "retrieval_required": retrieval_required,
        "retrieval_requirement_met": retrieval_requirement_met,
        "candidates": [{"path": path} for path in paths],
        "tooling": {
            "loomgraph": {
                "used": bool(commands),
                "commands": commands,
                "retrieval_succeeded": retrieval_succeeded,
            }
        },
    }


def test_loomgraph_use_distinguishes_invocation_from_retrieval() -> None:
    assert _module.classify_loomgraph_use([]) == {
        "invoked": False,
        "retrieval_used": False,
        "index_only": False,
    }
    assert _module.classify_loomgraph_use(["$HOME/.local/bin/loomgraph index ."]) == {
        "invoked": True,
        "retrieval_used": False,
        "index_only": True,
    }
    assert _module.classify_loomgraph_use(
        ["$HOME/.local/bin/loomgraph index . && $HOME/.local/bin/loomgraph find OptimizedExpr"]
    ) == {"invoked": True, "retrieval_used": True, "index_only": False}
    assert _module.classify_loomgraph_use(
        ['"$HOME/.local/bin/loomgraph" find OptimizedExpr']
    ) == {"invoked": True, "retrieval_used": True, "index_only": False}


def test_score_records_observed_tool_budget_and_assisted_requirement() -> None:
    score = _module.score_packet(
        _packet(
            commands=["loomgraph find Widget"],
            paths=["src/widget.py"],
            tool_call_count=6,
            orientation_mode="assisted",
            retrieval_required=True,
            retrieval_requirement_met=True,
            retrieval_succeeded=True,
        ),
        None,
    )

    assert score["orientation_mode"] == "assisted"
    assert score["tool_call_count"] == 6
    assert score["tool_call_budget_overrun"] is True
    assert score["retrieval_required"] is True
    assert score["retrieval_requirement_met"] is True
    assert score["loomgraph_retrieval_succeeded"] is True


def test_score_keeps_a_failed_retrieval_attempt_distinct_from_success() -> None:
    score = _module.score_packet(
        _packet(
            commands=["loomgraph find Widget --workspace /app"],
            paths=["src/widget.py"],
            orientation_mode="assisted",
            retrieval_required=True,
            retrieval_requirement_met=False,
            retrieval_succeeded=False,
        ),
        None,
    )

    assert score["loomgraph_retrieval_used"] is True
    assert score["loomgraph_retrieval_succeeded"] is False
    assert score["retrieval_requirement_met"] is False


def test_target_metrics_separate_existing_navigation_from_new_file_planning() -> None:
    target = {
        "gold_existing_production_paths": ["src/existing.py", "src/other.py"],
        "gold_new_production_paths": ["src/created.py"],
    }

    score = _module.score_packet(
        _packet(
            commands=["loomgraph find Existing"],
            paths=["src/existing.py", "src/existing.py", "src/created.py"],
        ),
        target,
    )

    assert score["candidate_paths"] == ["src/existing.py", "src/created.py"]
    assert score["duplicate_candidate_paths"] == 1
    assert score["target_hit_at_5"] is True
    assert score["existing_target_recall_at_5"] == 0.5
    assert score["new_path_nominated_at_5"] is True


def test_invalid_packet_or_unknown_target_never_becomes_a_quality_hit() -> None:
    target = {
        "gold_existing_production_paths": ["src/existing.py"],
        "gold_new_production_paths": ["src/created.py"],
    }
    invalid = _packet(commands=[], paths=["src/existing.py"])
    invalid["pre_edit"] = False

    assert _module.score_packet(invalid, target)["target_hit_at_5"] is None
    assert _module.score_packet(_packet(commands=[], paths=["src/existing.py"]), None)[
        "target_hit_at_5"
    ] is None


def test_summary_recognizes_pier_job_and_trial_paths(tmp_path: Path) -> None:
    artifact = (
        tmp_path
        / "baseline-1"
        / "loomgraph-eval-baseline-vulture-persistent-analysis-cache"
        / "vulture-persistent-analysis-cache__abc123"
        / "artifacts"
        / "orientation.json"
    )
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps(_packet(commands=[], paths=["src/existing.py"])))
    targets = {
        "vulture-persistent-analysis-cache": {
            "gold_existing_production_paths": ["src/existing.py"],
            "gold_new_production_paths": [],
        }
    }

    rows = _module.summarize(tmp_path, targets)

    assert len(rows) == 1
    assert rows[0]["condition"] == "baseline"
    assert rows[0]["task_id"] == "vulture-persistent-analysis-cache"
    assert rows[0]["target_hit_at_5"] is True
