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


def test_summary_records_pier_efficiency_fields_and_paired_deltas(tmp_path: Path) -> None:
    targets = {
        "vulture-persistent-analysis-cache": {
            "stratum": "codeindex-python",
            "gold_existing_production_paths": ["src/existing.py"],
            "gold_new_production_paths": [],
        }
    }
    for condition, input_tokens, cache_tokens, output_tokens, execution_end in (
        ("baseline", 100, 40, 20, "2026-08-19T00:00:08Z"),
        ("treatment", 80, 30, 15, "2026-08-19T00:00:07Z"),
    ):
        trial = (
            tmp_path
            / f"{condition}-assisted-1"
            / f"loomgraph-eval-{condition}-assisted-vulture-persistent-analysis-cache"
            / f"vulture-persistent-analysis-cache__{condition}"
        )
        artifact = trial / "artifacts" / "orientation.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(
            json.dumps(
                _packet(
                    commands=["loomgraph find Existing"] if condition == "treatment" else [],
                    paths=["src/existing.py"],
                    orientation_mode="assisted",
                    retrieval_required=condition == "treatment",
                    retrieval_requirement_met=True if condition == "treatment" else None,
                    retrieval_succeeded=True if condition == "treatment" else None,
                )
            )
        )
        (trial / "result.json").write_text(
            json.dumps(
                {
                    "started_at": "2026-08-19T00:00:00Z",
                    "finished_at": "2026-08-19T00:00:10Z",
                    "agent_setup": {
                        "started_at": "2026-08-19T00:00:01Z",
                        "finished_at": "2026-08-19T00:00:03Z",
                    },
                    "agent_execution": {
                        "started_at": "2026-08-19T00:00:03Z",
                        "finished_at": execution_end,
                    },
                    "agent_result": {
                        "n_input_tokens": input_tokens,
                        "n_cache_tokens": cache_tokens,
                        "n_output_tokens": output_tokens,
                        "cost_usd": 0.01 if condition == "baseline" else 0.008,
                    },
                }
            )
        )

    rows = _module.summarize(tmp_path, targets)
    pairs = _module.pair_efficiency(rows)

    treatment = next(row for row in rows if row["condition"] == "treatment")
    assert treatment["replicate"] == 1
    assert treatment["stratum"] == "codeindex-python"
    assert treatment["uncached_input_tokens"] == 50
    assert treatment["agent_execution_seconds"] == 4.0
    assert treatment["agent_setup_seconds"] == 2.0
    assert treatment["trial_wall_seconds"] == 10.0
    assert len(pairs) == 1
    assert pairs[0]["quality_eligible"] is True
    assert pairs[0]["uncached_input_tokens_delta"] == -10
    assert pairs[0]["agent_execution_seconds_delta"] == -1.0


def test_pair_with_unsuccessful_assisted_retrieval_has_no_efficiency_delta() -> None:
    base = {
        "task_id": "task",
        "stratum": "codegraph-js-ts",
        "use_mode": "assisted",
        "replicate": 1,
        "semantic_packet": True,
        "source_clean_model_phase": True,
        "uncached_input_tokens": 100,
    }
    pairs = _module.pair_efficiency(
        [
            {**base, "condition": "baseline", "run": "baseline"},
            {
                **base,
                "condition": "treatment",
                "run": "treatment",
                "loomgraph_retrieval_succeeded": False,
                "uncached_input_tokens": 80,
            },
        ]
    )

    assert pairs[0]["quality_eligible"] is False
    assert pairs[0]["uncached_input_tokens_delta"] is None


def test_pair_summary_reports_inclusive_median_and_iqr_without_pooling() -> None:
    base = {
        "task_id": "task",
        "stratum": "codegraph-js-ts",
        "use_mode": "assisted",
        "semantic_packet": True,
        "source_clean_model_phase": True,
        "loomgraph_retrieval_succeeded": True,
    }
    rows = []
    for replicate, (baseline, treatment) in enumerate(((100, 96), (100, 98), (100, 108)), 1):
        rows.extend(
            (
                {**base, "condition": "baseline", "replicate": replicate, "run": f"b-{replicate}", "uncached_input_tokens": baseline},
                {**base, "condition": "treatment", "replicate": replicate, "run": f"t-{replicate}", "uncached_input_tokens": treatment},
            )
        )

    summary = _module.summarize_pair_deltas(_module.pair_efficiency(rows))

    assert len(summary) == 1
    assert summary[0]["n_pairs"] == 3
    assert summary[0]["n_quality_eligible_pairs"] == 3
    assert summary[0]["uncached_input_tokens_delta"] == {
        "n": 3,
        "median": -2.0,
        "q1": -3.0,
        "q3": 3.0,
        "iqr": 6.0,
    }
