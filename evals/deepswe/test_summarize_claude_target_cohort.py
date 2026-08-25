"""Pure JSON contract tests for the Claude target-cohort summarizer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_MODULE_PATH = Path(__file__).with_name("summarize_claude_target_cohort.py")
_SPEC = importlib.util.spec_from_file_location("summarize_claude_target_cohort", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 2,
        "tasks": [
            {
                "task_id": "task-one",
                "stratum": "codeindex-python",
                "gold_production_paths": ["src/target.py"],
                "gold_existing_production_paths": ["src/target.py"],
                "gold_new_production_paths": [],
            }
        ],
    }


def _packet(
    *,
    condition: str,
    mode: str = "voluntary",
    paths: list[str] | None = None,
    source_clean: bool = True,
    overrun: bool = False,
    structural: bool = False,
    navigation_surface: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "complete",
        "condition": condition,
        "orientation_mode": mode,
        "navigation_surface": navigation_surface
        or ("text-only" if condition == "baseline" else "additive"),
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": True,
        "candidates": [
            {"path": path, "evidence": "observed"}
            for path in (paths if paths is not None else ["src/other.py"])
        ],
        # A stale model assertion must not control target scoring.
        "target_hit_at_5": True,
        "tool_call_count": 6 if overrun else 1,
        "tool_call_budget": 5,
        "tool_call_budget_overrun": overrun,
        "agent_execution_seconds": 10.0,
        "tooling": {
            "loomgraph": {
                "tools": ["mcp__loomgraph__loomgraph_find"] if structural else [],
                "structural_retrievals": (
                    [{"tool": "mcp__loomgraph__loomgraph_find", "evidence": "find_matches"}]
                    if structural
                    else []
                ),
            }
        },
    }


def _write_run(
    root: Path,
    *,
    condition: str,
    mode: str = "voluntary",
    replicate: int = 1,
    runtime: str = "claude-code",
    packet: dict[str, object] | None = None,
    seconds: float = 10.0,
) -> None:
    root.mkdir(parents=True)
    (root / "orientation.json").write_text(
        json.dumps(packet or _packet(condition=condition, mode=mode))
    )
    (root / "run.json").write_text(
        json.dumps(
            {
                "task_id": "task-one",
                "condition": condition,
                "use_mode": mode,
                "replicate": replicate,
                "runtime": runtime,
                "agent_execution_seconds": seconds,
            }
        )
    )


def test_summary_derives_target_hit_from_host_manifest_and_keeps_raw_rows(tmp_path: Path) -> None:
    manifest_path = tmp_path / "target-manifest.json"
    manifest_path.write_text(json.dumps(_manifest()))
    cohort = tmp_path / "cohort"
    _write_run(
        cohort / "baseline-voluntary-1",
        condition="baseline",
        packet=_packet(condition="baseline", paths=["src/target.py"]),
    )
    _write_run(
        cohort / "treatment-voluntary-1",
        condition="treatment",
        packet=_packet(
            condition="treatment", paths=["src/other.py"], structural=True
        ),
        seconds=7.0,
    )

    targets, manifest_sha = _MODULE.load_target_manifest(manifest_path)
    rows = _MODULE.summarize(cohort, targets)

    assert manifest_sha
    assert len(rows) == 2
    baseline = next(row for row in rows if row["condition"] == "baseline")
    treatment = next(row for row in rows if row["condition"] == "treatment")
    assert baseline["valid"] is True
    assert baseline["target_hit_at_5"] is True
    assert treatment["valid"] is True
    assert treatment["target_hit_at_5"] is False
    assert treatment["target_hit_at_5"] != treatment["packet_target_hit_at_5"]
    assert baseline["stratum"] == "codeindex-python"


def test_invalid_rows_and_exclusion_reasons_are_retained(tmp_path: Path) -> None:
    manifest_path = tmp_path / "target-manifest.json"
    manifest_path.write_text(json.dumps(_manifest()))
    cohort = tmp_path / "cohort"
    _write_run(
        cohort / "treatment-voluntary-1",
        condition="treatment",
        mode="assisted",
        packet=_packet(condition="treatment", mode="assisted", structural=False),
    )
    _write_run(
        cohort / "baseline-voluntary-2",
        condition="baseline",
        packet=_packet(condition="baseline", source_clean=False),
    )
    _write_run(
        cohort / "baseline-voluntary-3",
        condition="baseline",
        packet=_packet(condition="baseline", overrun=True),
    )

    targets, _ = _MODULE.load_target_manifest(manifest_path)
    rows = _MODULE.summarize(cohort, targets)

    assert len(rows) == 3
    assert all(row["valid"] is False for row in rows)
    assert any("additive_treatment_retrieval_missing" in row["exclusion_reasons"] for row in rows)
    assert any("source_not_clean" in row["exclusion_reasons"] for row in rows)
    assert any("tool_call_budget_exceeded" in row["exclusion_reasons"] for row in rows)
    assert all(row["target_hit_at_5"] is None for row in rows)


def test_voluntary_additive_nonuse_is_retained_as_valid_observed_nonuse(tmp_path: Path) -> None:
    manifest_path = tmp_path / "target-manifest.json"
    manifest_path.write_text(json.dumps(_manifest()))
    cohort = tmp_path / "cohort"
    _write_run(
        cohort / "treatment-voluntary-1",
        condition="treatment",
        packet=_packet(condition="treatment", structural=False),
    )

    targets, _ = _MODULE.load_target_manifest(manifest_path)
    rows = _MODULE.summarize(cohort, targets)

    assert rows[0]["valid"] is True
    assert rows[0]["structural_retrieval_observed"] is False


def test_driver_runner_failure_is_excluded_even_when_packet_looks_complete(tmp_path: Path) -> None:
    manifest_path = tmp_path / "target-manifest.json"
    manifest_path.write_text(json.dumps(_manifest()))
    cohort = tmp_path / "cohort"
    run_dir = cohort / "task-one" / "codeindex-python" / "voluntary" / "rep-01" / "baseline"
    output_dir = run_dir / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "orientation.json").write_text(json.dumps(_packet(condition="baseline")))
    (run_dir / "driver-run.json").write_text(
        json.dumps(
            {
                "task_id": "task-one",
                "condition": "baseline",
                "use_mode": "voluntary",
                "replicate": "01",
                "runner_return_code": 1,
            }
        )
    )

    targets, _ = _MODULE.load_target_manifest(manifest_path)
    rows = _MODULE.summarize(cohort, targets)

    assert rows[0]["valid"] is False
    assert "agent_return_code_nonzero" in rows[0]["exclusion_reasons"]


def test_pairs_require_same_task_mode_runtime_and_replicate(tmp_path: Path) -> None:
    manifest_path = tmp_path / "target-manifest.json"
    manifest_path.write_text(json.dumps(_manifest()))
    cohort = tmp_path / "cohort"
    _write_run(cohort / "baseline-voluntary-1", condition="baseline", seconds=10.0)
    _write_run(
        cohort / "treatment-voluntary-1",
        condition="treatment",
        packet=_packet(condition="treatment", structural=True),
        seconds=7.0,
    )
    _write_run(
        cohort / "treatment-assisted-1",
        condition="treatment",
        mode="assisted",
        packet=_packet(condition="treatment", mode="assisted", structural=True),
        seconds=8.0,
    )
    _write_run(
        cohort / "treatment-voluntary-1-other-runtime",
        condition="treatment",
        runtime="other-runtime",
        packet=_packet(condition="treatment", structural=True),
        seconds=6.0,
    )

    targets, _ = _MODULE.load_target_manifest(manifest_path)
    rows = _MODULE.summarize(cohort, targets)
    pairs = _MODULE.pair_efficiency(rows)

    assert len(pairs) == 1
    assert pairs[0]["use_mode"] == "voluntary"
    assert pairs[0]["runtime"] == "claude-code"
    assert pairs[0]["quality_eligible"] is True
    assert pairs[0]["agent_execution_seconds_delta"] == -3.0


def test_grouped_delta_summary_uses_inclusive_quartiles_without_pooling() -> None:
    rows: list[dict[str, object]] = []
    common = {
        "task_id": "task-one",
        "stratum": "codeindex-python",
        "runtime": "claude-code",
        "use_mode": "voluntary",
        "valid": True,
        "exclusion_reasons": [],
        "tool_call_budget_overrun": False,
    }
    for replicate, baseline, treatment in ((1, 100.0, 96.0), (2, 100.0, 98.0), (3, 100.0, 108.0)):
        rows.extend(
            [
                {**common, "condition": "baseline", "replicate": replicate, "run": f"b-{replicate}", "agent_execution_seconds": baseline},
                {**common, "condition": "treatment", "replicate": replicate, "run": f"t-{replicate}", "agent_execution_seconds": treatment},
            ]
        )

    summary = _MODULE.summarize_groups(_MODULE.pair_efficiency(rows))

    assert len(summary) == 1
    assert summary[0]["n_quality_eligible_pairs"] == 3
    assert summary[0]["agent_execution_seconds_delta"] == {
        "n": 3,
        "median": -2.0,
        "q1": -3.0,
        "q3": 3.0,
        "iqr": 6.0,
    }


def test_driver_failure_without_orientation_is_an_explicit_invalid_row(tmp_path: Path) -> None:
    manifest_path = tmp_path / "target-manifest.json"
    manifest_path.write_text(json.dumps(_manifest()))
    run_dir = tmp_path / "cohort" / "task-one" / "codeindex-python" / "voluntary" / "rep-01" / "baseline"
    run_dir.mkdir(parents=True)
    (run_dir / "driver-run.json").write_text(
        json.dumps(
            {
                "task_id": "task-one",
                "condition": "baseline",
                "use_mode": "voluntary",
                "replicate": "01",
                "status": "driver_error",
            }
        )
    )

    targets, _ = _MODULE.load_target_manifest(manifest_path)
    rows = _MODULE.summarize(tmp_path / "cohort", targets)

    assert len(rows) == 1
    assert rows[0]["valid"] is False
    assert "orientation.json_missing" in rows[0]["exclusion_reasons"]
