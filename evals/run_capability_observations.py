#!/usr/bin/env python3
"""Raw observation contract for the #206 structural-capability runner.

This module deliberately has no score aggregation. A future fixture runner
uses ``validate_observation`` before writing cold/warm JSON artifacts, so an
incomplete command response cannot be mistaken for capability evidence.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
from argparse import ArgumentParser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.capability_fixtures import MaterializedFixture, materialize_fixture


class ObservationValidationError(ValueError):
    """A proposed raw capability observation is not publishable evidence."""


@dataclass(frozen=True)
class _Task:
    fixture_id: str
    query: tuple[str, ...]
    rg: tuple[str, ...] | None
    oracle: Callable[[dict[str, Any]], bool]
    uses_workspace: bool = True
    parser_distribution: str = "tree-sitter-python"
    comparison_query: tuple[str, ...] | None = None
    comparison_oracle: Callable[[dict[str, Any]], bool] | None = None
    supplemental_query: tuple[str, ...] | None = None
    supplemental_oracle: Callable[[dict[str, Any]], bool] | None = None
    requires_resolution_split: bool = False


def _definition_oracle(data: dict[str, Any]) -> bool:
    return any(
        match.get("entity") == "app.auth.AuthService"
        for match in data.get("matches", [])
        if isinstance(match, dict)
    )


def _direct_call_oracle(data: dict[str, Any]) -> bool:
    return any(
        edge.get("entity") == "app.auth.validate_token"
        for edge in data.get("callees", [])
        if isinstance(edge, dict)
    )


def _impact_oracle(data: dict[str, Any]) -> bool:
    impact = data.get("impact_analysis")
    if not isinstance(impact, dict):
        return False
    direct = impact.get("direct_callers", [])
    indirect = impact.get("indirect_callers", [])
    return (
        isinstance(data.get("risk_assessment"), dict)
        and "resolution" in data
        and any(
            caller.get("name") == "app.handlers.handle_login"
            for caller in direct
            if isinstance(caller, dict)
        )
        and any(
            caller.get("name") == "app.api.dispatch"
            for caller in indirect
            if isinstance(caller, dict)
        )
    )


def _deps_oracle(data: dict[str, Any]) -> bool:
    return isinstance(data.get("modules"), list) and bool(data["modules"])


def _branch_diff_oracle(data: dict[str, Any]) -> bool:
    diff = data.get("diff")
    return isinstance(diff, dict) and isinstance(diff.get("broken_chains"), list)


def _codegraph_branch_diff_oracle(data: dict[str, Any]) -> bool:
    diff = data.get("diff")
    if not isinstance(diff, dict):
        return False
    content = diff.get("content_comparison")
    return (
        isinstance(content, dict)
        and content.get("status") == "unavailable"
        and content.get("reason") == "backend_has_no_per_entity_content_hash"
    )


def _factory_oracle(data: dict[str, Any]) -> bool:
    return any(
        edge.get("entity") == "consumer.run"
        for edge in data.get("callers", [])
        if isinstance(edge, dict)
    )


def _path_alias_oracle(data: dict[str, Any]) -> bool:
    return any(
        edge.get("entity") == "src.models.Session"
        for edge in data.get("callees", [])
        if isinstance(edge, dict)
    ) and not any(
        edge.get("entity") == "src.index.Session"
        for edge in data.get("callees", [])
        if isinstance(edge, dict)
    )


def _debt_git_oracle(data: dict[str, Any]) -> bool:
    return any(
        issue.get("category") == "critical_hotspot"
        and issue.get("severity") == "P0"
        and issue.get("entity") == "app/hub.py"
        for issue in data.get("issues", [])
        if isinstance(issue, dict)
    )


def _hub_topology_oracle(data: dict[str, Any]) -> bool:
    callers = data.get("callers", [])
    return isinstance(callers, list) and {
        f"app.consumer_{number}.use_{number}" for number in range(1, 9)
    } == {
        caller.get("entity") for caller in callers if isinstance(caller, dict)
    }


_TASKS = {
    "overlap-definition": _Task(
        fixture_id="python-core",
        query=("find", "AuthService", "--type", "class", "-n", "1"),
        rg=("rg", "-n", "--glob", "*.py", "^class AuthService\\b", "."),
        oracle=_definition_oracle,
    ),
    "overlap-direct-static-call": _Task(
        fixture_id="python-core",
        query=(
            "graph", "app.handlers.handle_login", "--direction", "callees", "--depth", "1",
            "--relation-type", "CALLS",
        ),
        rg=("rg", "-n", "--glob", "*.py", "validate_token\\(token\\)", "app/handlers.py"),
        oracle=_direct_call_oracle,
    ),
    "structural-multihop-impact": _Task(
        fixture_id="python-history",
        query=("impact", "head", "--base", "base", "--depth", "2"),
        rg=None,
        oracle=_impact_oracle,
        requires_resolution_split=True,
    ),
    "structural-typed-deps": _Task(
        fixture_id="python-core",
        query=("deps", "-d", "2"),
        rg=None,
        oracle=_deps_oracle,
    ),
    "structural-branch-diff": _Task(
        fixture_id="python-history",
        query=("branch-diff", "base..head", "--backend", "codeindex"),
        rg=None,
        oracle=_branch_diff_oracle,
        uses_workspace=False,
        comparison_query=("branch-diff", "base..head", "--backend", "codegraph"),
        comparison_oracle=_codegraph_branch_diff_oracle,
    ),
    "structural-topology-debt-git": _Task(
        fixture_id="topology-debt-git",
        query=("debt", "--with-git", "--git-since", "10 years"),
        rg=None,
        oracle=_debt_git_oracle,
        supplemental_query=(
            "graph", "app.hub.HubFunc", "--direction", "callers", "--relation-type", "CALLS",
        ),
        supplemental_oracle=_hub_topology_oracle,
        requires_resolution_split=True,
    ),
    "trust-annotated-factory-receiver": _Task(
        fixture_id="factory-receiver",
        query=(
            "graph", "store.Store.create_entity", "--direction", "callers", "--relation-type", "CALLS",
        ),
        rg=None,
        oracle=_factory_oracle,
        requires_resolution_split=True,
    ),
    "trust-alias-barrel": _Task(
        fixture_id="ts-barrel-alias",
        query=(
            "graph", "src.alias_consumer", "--direction", "callees", "--relation-type", "REFERENCES",
            "--include-unresolved",
        ),
        rg=None,
        oracle=_path_alias_oracle,
        parser_distribution="tree-sitter-typescript",
        supplemental_query=(
            "graph", "src.consumer", "--direction", "callees", "--relation-type", "REFERENCES",
            "--include-unresolved",
        ),
        supplemental_oracle=_path_alias_oracle,
    ),
}


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ObservationValidationError(f"{field} must be an object")
    return value


def _non_empty_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ObservationValidationError(f"{field} must be a non-empty string")


def validate_observation(record: dict[str, object]) -> None:
    """Reject incomplete cold/warm observations before any result is written."""
    if record.get("schema_version") != 1:
        raise ObservationValidationError("schema_version must be 1")
    fixture = _mapping(record.get("fixture"), "fixture")
    _non_empty_string(fixture.get("id"), "fixture.id")
    sha = fixture.get("sha")
    if not isinstance(sha, str) or len(sha) != 64:
        raise ObservationValidationError("fixture.sha must be a 64-character hash")
    _non_empty_string(fixture.get("git_ref"), "fixture.git_ref")
    _non_empty_string(record.get("task_id"), "task_id")

    phase = record.get("phase")
    if phase not in {"cold", "warm"}:
        raise ObservationValidationError("phase must be cold or warm")

    toolchain = _mapping(record.get("toolchain"), "toolchain")
    for field in ("loomgraph_version", "codeindex_version", "backend"):
        _non_empty_string(toolchain.get(field), f"toolchain.{field}")
    parsers = _mapping(toolchain.get("parser_versions"), "toolchain.parser_versions")
    if not parsers:
        raise ObservationValidationError("toolchain.parser_versions must not be empty")

    operation = _mapping(record.get("operation"), "operation")
    for field in ("index_command", "query_command"):
        value = operation.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(part, str) for part in value):
            raise ObservationValidationError(f"operation.{field} must be non-empty strings")
    if not isinstance(operation.get("query_wall_ms"), int):
        raise ObservationValidationError("operation.query_wall_ms must be an integer")
    if not isinstance(operation.get("exit_code"), int):
        raise ObservationValidationError("operation.exit_code must be an integer")
    _non_empty_string(operation.get("raw_stdout"), "operation.raw_stdout")
    if not isinstance(operation.get("raw_stderr"), str):
        raise ObservationValidationError("operation.raw_stderr must be a string")
    if phase == "cold":
        if operation.get("reindexed") is not True:
            raise ObservationValidationError("cold observation must reindex")
        if not isinstance(operation.get("index_clear_wall_ms"), int):
            raise ObservationValidationError("cold observation needs index_clear_wall_ms")
    elif operation.get("reindexed") is not False:
        raise ObservationValidationError("warm observation must not be reindexed")

    answer = _mapping(record.get("answer"), "answer")
    if answer.get("status") not in {"complete", "partial", "ambiguous", "unavailable", "error"}:
        raise ObservationValidationError("answer.status is invalid")
    trust = _mapping(record.get("trust"), "trust")
    _non_empty_string(trust.get("workspace"), "trust.workspace")
    if not isinstance(trust.get("partial"), bool):
        raise ObservationValidationError("trust.partial must be boolean")
    resolution_value = trust.get("resolution")
    if resolution_value is not None:
        resolution = _mapping(resolution_value, "trust.resolution")
        for key in (
            "resolved_ratio",
            "internal_unresolved_ratio",
            "external_unresolved_ratio",
        ):
            if not isinstance(resolution.get(key), (int, float)):
                raise ObservationValidationError(f"trust.resolution.{key} must be numeric")

    oracle = _mapping(record.get("oracle"), "oracle")
    if not isinstance(oracle.get("passed"), bool):
        raise ObservationValidationError("oracle.passed must be boolean")
    if not isinstance(oracle.get("failures"), list):
        raise ObservationValidationError("oracle.failures must be a list")
    rg = _mapping(record.get("rg"), "rg")
    if rg.get("equivalence") not in {"equivalent", "unsupported"}:
        raise ObservationValidationError("rg.equivalence is invalid")

    comparison_value = record.get("comparison")
    if comparison_value is not None:
        comparison = _mapping(comparison_value, "comparison")
        _non_empty_string(comparison.get("backend"), "comparison.backend")
        availability = comparison.get("availability")
        if availability not in {"available", "infrastructure_unavailable"}:
            raise ObservationValidationError("comparison.availability is invalid")
        command = comparison.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise ObservationValidationError("comparison.command must be non-empty strings")
        if availability == "available":
            _non_empty_string(comparison.get("backend_version"), "comparison.backend_version")
            if not isinstance(comparison.get("exit_code"), int):
                raise ObservationValidationError("available comparison needs exit_code")
            _non_empty_string(comparison.get("raw_stdout"), "comparison.raw_stdout")
            oracle = _mapping(comparison.get("oracle"), "comparison.oracle")
            if not isinstance(oracle.get("passed"), bool):
                raise ObservationValidationError("comparison.oracle.passed must be boolean")
        else:
            _non_empty_string(comparison.get("infrastructure_error"), "comparison.infrastructure_error")

    supplemental_value = record.get("supplemental")
    if supplemental_value is not None:
        supplemental = _mapping(supplemental_value, "supplemental")
        command = supplemental.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise ObservationValidationError("supplemental.command must be non-empty strings")
        if not isinstance(supplemental.get("exit_code"), int):
            raise ObservationValidationError("supplemental.exit_code must be an integer")
        _non_empty_string(supplemental.get("raw_stdout"), "supplemental.raw_stdout")
        oracle = _mapping(supplemental.get("oracle"), "supplemental.oracle")
        if not isinstance(oracle.get("passed"), bool):
            raise ObservationValidationError("supplemental.oracle.passed must be boolean")


def _version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], int]:
    started = time.perf_counter_ns()
    completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    return completed, (time.perf_counter_ns() - started) // 1_000_000


def _json_data(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    return data if isinstance(data, dict) else {}


def _toolchain(task: _Task) -> dict[str, object]:
    return {
        "loomgraph_version": _version("loomgraph"),
        "codeindex_version": _version("ai-codeindex"),
        "parser_versions": {task.parser_distribution.removeprefix("tree-sitter-"): _version(task.parser_distribution)},
        "backend": "codeindex",
    }


def _executable_version(executable: str) -> str:
    try:
        completed = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    if completed.returncode != 0:
        return "unavailable"
    return completed.stdout.strip() or completed.stderr.strip() or "unavailable"


def _comparison(
    task: _Task,
    command_prefix: list[str],
    fixture: MaterializedFixture,
    env: dict[str, str],
) -> tuple[dict[str, object], dict[str, object]] | None:
    if task.comparison_query is None or task.comparison_oracle is None:
        return None
    command = [*command_prefix, *task.comparison_query]
    executable = shutil.which("codegraph")
    if executable is None:
        return (
            {
                "backend": "codegraph",
                "availability": "infrastructure_unavailable",
                "command": command,
                "infrastructure_error": "codegraph executable not found",
            },
            {"backend": "codegraph", "availability": "infrastructure_unavailable"},
        )
    completed, wall_ms = _run(command, fixture.path, env)
    data = _json_data(completed.stdout)
    passed = completed.returncode == 0 and task.comparison_oracle(data)
    content = data.get("diff", {}).get("content_comparison", {})
    trust: dict[str, object] = {"backend": "codegraph", "availability": "available"}
    if isinstance(content, dict):
        trust.update(
            {
                "content_comparison_status": content.get("status"),
                "content_comparison_reason": content.get("reason"),
                "comparable_shared": content.get("comparable_shared"),
                "uncomparable_shared": content.get("uncomparable_shared"),
            }
        )
    return (
        {
            "backend": "codegraph",
            "availability": "available",
            "backend_version": _executable_version(executable),
            "command": command,
            "wall_ms": wall_ms,
            "exit_code": completed.returncode,
            "raw_stdout": completed.stdout or completed.stderr,
            "raw_stderr": completed.stderr,
            "oracle": {
                "passed": passed,
                "failures": [] if passed else ["comparison did not match oracle"],
            },
        },
        trust,
    )


def _supplemental(
    task: _Task,
    command_prefix: list[str],
    fixture: MaterializedFixture,
    env: dict[str, str],
    workspace: str,
) -> dict[str, object] | None:
    if task.supplemental_query is None or task.supplemental_oracle is None:
        return None
    command = [*command_prefix, *task.supplemental_query]
    if task.uses_workspace:
        command.extend(["-w", workspace])
    completed, wall_ms = _run(command, fixture.path, env)
    passed = completed.returncode == 0 and task.supplemental_oracle(_json_data(completed.stdout))
    return {
        "command": command,
        "wall_ms": wall_ms,
        "exit_code": completed.returncode,
        "raw_stdout": completed.stdout or completed.stderr,
        "raw_stderr": completed.stderr,
        "oracle": {
            "passed": passed,
            "failures": [] if passed else ["supplemental answer did not match oracle"],
        },
    }


def _observation(
    task_id: str,
    task: _Task,
    fixture: MaterializedFixture,
    workspace: str,
    phase: str,
    index_command: list[str],
    index_wall_ms: int | None,
    query_command: list[str],
    completed: subprocess.CompletedProcess[str],
    query_wall_ms: int,
    rg: dict[str, object],
    comparison: tuple[dict[str, object], dict[str, object]] | None = None,
    supplemental: dict[str, object] | None = None,
) -> dict[str, object]:
    data = _json_data(completed.stdout)
    resolution = data.get("resolution")
    has_resolution_split = isinstance(resolution, dict) and all(
        isinstance(resolution.get(key), (int, float))
        for key in (
            "resolved_ratio",
            "internal_unresolved_ratio",
            "external_unresolved_ratio",
        )
    )
    passed = (
        completed.returncode == 0
        and task.oracle(data)
        and (not task.requires_resolution_split or has_resolution_split)
    )
    supplemental_passed = supplemental is None or bool(
        _mapping(supplemental.get("oracle"), "supplemental.oracle").get("passed")
    )
    passed = passed and supplemental_passed
    source_id = ""
    matches = data.get("matches", [])
    if isinstance(matches, list) and matches and isinstance(matches[0], dict):
        source_id = str(matches[0].get("source_id", ""))
    record: dict[str, object] = {
        "schema_version": 1,
        "fixture": {"id": fixture.fixture_id, "sha": fixture.sha, "git_ref": "head"},
        "task_id": task_id,
        "phase": phase,
        "toolchain": _toolchain(task),
        "operation": {
            "index_command": index_command,
            "query_command": query_command,
            "index_clear_wall_ms": index_wall_ms,
            "query_wall_ms": query_wall_ms,
            "reindexed": phase == "cold",
            "exit_code": completed.returncode,
            "raw_stdout": completed.stdout or completed.stderr,
            "raw_stderr": completed.stderr,
        },
        "answer": {"status": "complete" if passed else "error"},
        "trust": {
            "workspace": workspace,
            "partial": bool(data.get("partial", False)),
            "backend": "codeindex",
            "source_id": source_id,
        },
        "oracle": {
            "passed": passed,
            "failures": [] if passed else ["answer did not match oracle"],
        },
        "rg": rg,
    }
    if has_resolution_split:
        trust = record["trust"]
        assert isinstance(trust, dict)
        trust["resolution"] = resolution
    if comparison is not None:
        comparison_record, comparison_trust = comparison
        record["comparison"] = comparison_record
        trust = record["trust"]
        assert isinstance(trust, dict)
        trust["comparison"] = comparison_trust
    if supplemental is not None:
        record["supplemental"] = supplemental
    validate_observation(record)
    return record


def run_task(task_id: str, work_root: Path) -> list[dict[str, object]]:
    """Run one approved task twice and return independent cold/warm records."""
    try:
        task = _TASKS[task_id]
    except KeyError as exc:
        raise ValueError(f"unsupported capability task: {task_id}") from exc

    work_root.mkdir(parents=True, exist_ok=True)
    fixture = materialize_fixture(task.fixture_id, work_root / "fixture")
    workspace = f"capability-{task_id}"
    db_path = work_root / "state" / "{workspace}.db"
    db_path.parent.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["LOOMGRAPH_STORAGE__DB_PATH"] = str(db_path)
    # Exercise the installed product entrypoint. Running cli.main as a module
    # imports ``loomgraph.cli`` first and can skip Click command registration.
    command_prefix = [str(Path(sys.executable).with_name("loomgraph"))]
    index_command = [*command_prefix, "index", ".", "--clear", "-w", workspace]
    _, index_wall_ms = _run(index_command, fixture.path, env)
    query_command = [*command_prefix, *task.query]
    if task.uses_workspace:
        query_command.extend(["-w", workspace])
    cold_completed, cold_query_ms = _run(query_command, fixture.path, env)
    cold_comparison = _comparison(task, command_prefix, fixture, env)
    cold_supplemental = _supplemental(task, command_prefix, fixture, env, workspace)

    if task.rg is None:
        rg_record: dict[str, object] = {"equivalence": "unsupported", "command": None}
    else:
        try:
            rg_completed, _ = _run(list(task.rg), fixture.path, env)
        except FileNotFoundError:
            # A missing calibration tool invalidates only the rg arm. It must
            # not turn a LoomGraph observation into a fake regression or an
            # implicit claim that rg produced no answer.
            rg_record = {
                "equivalence": "equivalent",
                "command": list(task.rg),
                "available": False,
                "infrastructure_error": "rg executable not found",
            }
        else:
            rg_record = {
                "equivalence": "equivalent",
                "command": list(task.rg),
                "available": True,
                "exit_code": rg_completed.returncode,
                "raw_stdout": rg_completed.stdout,
                "raw_stderr": rg_completed.stderr,
            }

    cold = _observation(
        task_id, task, fixture, workspace, "cold", index_command, index_wall_ms,
        query_command, cold_completed, cold_query_ms, rg_record, cold_comparison, cold_supplemental,
    )
    warm_completed, warm_query_ms = _run(query_command, fixture.path, env)
    warm_comparison = _comparison(task, command_prefix, fixture, env)
    warm_supplemental = _supplemental(task, command_prefix, fixture, env, workspace)
    warm = _observation(
        task_id, task, fixture, workspace, "warm", index_command, None,
        query_command, warm_completed, warm_query_ms, rg_record, warm_comparison, warm_supplemental,
    )
    return [cold, warm]


def write_observations(records: list[dict[str, object]], output: Path) -> None:
    """Write raw rows only; callers decide whether and how to summarize them."""
    for record in records:
        validate_observation(record)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))


def run_all(work_root: Path, output: Path) -> list[dict[str, object]]:
    """Run all eight reviewed tasks and write their independent raw rows."""
    records: list[dict[str, object]] = []
    for task_id in _TASKS:
        records.extend(run_task(task_id, work_root / task_id))
    write_observations(records, output)
    return records


def main() -> int:
    parser = ArgumentParser(description="Run raw #206 capability observations without scoring")
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = run_all(args.work_root, args.output)
    print(f"wrote {len(records)} raw capability observations to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
