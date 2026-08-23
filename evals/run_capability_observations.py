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
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.capability_fixtures import MaterializedFixture, materialize_fixture


class ObservationValidationError(ValueError):
    """A proposed raw capability observation is not publishable evidence."""


@dataclass(frozen=True)
class _Task:
    fixture_id: str
    query: tuple[str, ...]
    rg: tuple[str, ...] | None
    oracle: Callable[[dict[str, Any]], bool]


def _definition_oracle(data: dict[str, Any]) -> bool:
    return any(
        match.get("entity") == "app.auth.AuthService"
        for match in data.get("matches", [])
        if isinstance(match, dict)
    )


_TASKS = {
    "overlap-definition": _Task(
        fixture_id="python-core",
        query=("find", "AuthService", "--type", "class", "-n", "1"),
        rg=("rg", "-n", "--glob", "*.py", "^class AuthService\\b", "."),
        oracle=_definition_oracle,
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

    oracle = _mapping(record.get("oracle"), "oracle")
    if not isinstance(oracle.get("passed"), bool):
        raise ObservationValidationError("oracle.passed must be boolean")
    if not isinstance(oracle.get("failures"), list):
        raise ObservationValidationError("oracle.failures must be a list")
    rg = _mapping(record.get("rg"), "rg")
    if rg.get("equivalence") not in {"equivalent", "unsupported"}:
        raise ObservationValidationError("rg.equivalence is invalid")


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


def _toolchain() -> dict[str, object]:
    return {
        "loomgraph_version": _version("loomgraph"),
        "codeindex_version": _version("ai-codeindex"),
        "parser_versions": {"python": _version("tree-sitter-python")},
        "backend": "codeindex",
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
) -> dict[str, object]:
    data = _json_data(completed.stdout)
    passed = completed.returncode == 0 and task.oracle(data)
    source_id = ""
    matches = data.get("matches", [])
    if isinstance(matches, list) and matches and isinstance(matches[0], dict):
        source_id = str(matches[0].get("source_id", ""))
    record: dict[str, object] = {
        "schema_version": 1,
        "fixture": {"id": fixture.fixture_id, "sha": fixture.sha, "git_ref": "head"},
        "task_id": task_id,
        "phase": phase,
        "toolchain": _toolchain(),
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
        "oracle": {"passed": passed, "failures": [] if passed else ["answer did not match oracle"]},
        "rg": rg,
    }
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
    query_command = [*command_prefix, *task.query, "-w", workspace]
    cold_completed, cold_query_ms = _run(query_command, fixture.path, env)

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
        query_command, cold_completed, cold_query_ms, rg_record,
    )
    warm_completed, warm_query_ms = _run(query_command, fixture.path, env)
    warm = _observation(
        task_id, task, fixture, workspace, "warm", index_command, None,
        query_command, warm_completed, warm_query_ms, rg_record,
    )
    return [cold, warm]
