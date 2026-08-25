#!/usr/bin/env python3
"""Plan and run the frozen Claude Code DeepSWE navigation cohort.

The driver is deliberately host-side.  It reads only task metadata and the
task instruction, materializes ``/app`` from the declared task image into an
adapter-owned source directory, and delegates the model phase to
``claude_orientation.py``.  Gold patches and the target manifest never enter
the source directory or the Claude command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

FROZEN_TASK_COUNT = 12
TASKS_PER_STRATUM = 4
DEFAULT_MODEL = "sonnet"
DEFAULT_BUDGET_USD = "0.50"
DEFAULT_TOOL_CALL_BUDGET = 7
DEFAULT_USE_MODE = "voluntary"
BASELINE_SURFACE = "text-only"
TREATMENT_SURFACE = "additive"
CONDITIONS: tuple[str, str] = ("baseline", "treatment")
USE_MODES = ("voluntary", "assisted")


@dataclass(frozen=True)
class TaskSpec:
    """The task metadata needed by the adapter, excluding gold artifacts."""

    task_id: str
    stratum: str
    language: str
    backend: str
    image: str
    task_dir: Path
    instruction_file: Path


def _string_field(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"manifest field {field!r} must be a non-empty string")
    return value


def load_target_manifest(path: Path, *, require_frozen: bool = True) -> list[dict[str, object]]:
    """Load and validate the host-only frozen target manifest."""
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read target manifest {path}: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 2:
        raise ValueError("target manifest must be schema_version 2")
    tasks = document.get("tasks")
    if not isinstance(tasks, list) or not all(isinstance(task, dict) for task in tasks):
        raise ValueError("target manifest must contain a list of task objects")
    rows = [task for task in tasks if isinstance(task, dict)]
    task_ids = [_string_field(task.get("task_id"), "task_id") for task in rows]
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("target manifest contains duplicate task ids")
    for task in rows:
        _string_field(task.get("stratum"), "stratum")
        _string_field(task.get("language"), "language")
        _string_field(task.get("backend"), "backend")
    if require_frozen:
        if len(rows) != FROZEN_TASK_COUNT:
            raise ValueError(
                f"frozen target manifest must contain {FROZEN_TASK_COUNT} tasks; got {len(rows)}"
            )
        counts: dict[str, int] = {}
        for task in rows:
            stratum = _string_field(task.get("stratum"), "stratum")
            counts[stratum] = counts.get(stratum, 0) + 1
        if set(counts.values()) != {TASKS_PER_STRATUM} or len(counts) != 3:
            raise ValueError("frozen target manifest must contain three strata with four tasks each")
    return rows


def _task_path(deepswe_root: Path, task_id: str) -> Path:
    """Resolve a manifest task id below ``DEEPSWE_DIR/tasks`` safely."""
    if not task_id or Path(task_id).name != task_id:
        raise ValueError(f"invalid DeepSWE task id: {task_id!r}")
    tasks_root = (deepswe_root / "tasks").resolve()
    task_dir = (tasks_root / task_id).resolve()
    try:
        task_dir.relative_to(tasks_root)
    except ValueError as exc:
        raise ValueError(f"task is outside DeepSWE tasks root: {task_id!r}") from exc
    return task_dir


def load_task_spec(deepswe_root: Path, manifest_row: dict[str, object]) -> TaskSpec:
    """Read one task's metadata and instruction, never its solution artifacts."""
    task_id = _string_field(manifest_row.get("task_id"), "task_id")
    task_dir = _task_path(deepswe_root, task_id)
    task_toml_path = task_dir / "task.toml"
    instruction_file = task_dir / "instruction.md"
    if not task_toml_path.is_file():
        raise FileNotFoundError(f"DeepSWE task metadata not found: {task_toml_path}")
    if not instruction_file.is_file():
        raise FileNotFoundError(f"DeepSWE task instruction not found: {instruction_file}")
    try:
        metadata_doc = tomllib.loads(task_toml_path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot parse {task_toml_path}: {exc}") from exc
    metadata = metadata_doc.get("metadata")
    environment = metadata_doc.get("environment")
    if not isinstance(metadata, dict) or metadata.get("task_id") != task_id:
        raise ValueError(f"task.toml metadata task_id does not match {task_id!r}")
    if not isinstance(environment, dict):
        raise ValueError(f"task.toml has no [environment] section: {task_toml_path}")
    image = _string_field(environment.get("docker_image"), "environment.docker_image")
    language = _string_field(manifest_row.get("language"), "language")
    backend = _string_field(manifest_row.get("backend"), "backend")
    if metadata.get("language") not in {None, language}:
        raise ValueError(f"task language mismatch for {task_id!r}")
    return TaskSpec(
        task_id=task_id,
        stratum=_string_field(manifest_row.get("stratum"), "stratum"),
        language=language,
        backend=backend,
        image=image,
        task_dir=task_dir,
        instruction_file=instruction_file,
    )


def select_task_specs(
    deepswe_root: Path,
    manifest_rows: Sequence[dict[str, object]],
    task_ids: Sequence[str] | None = None,
) -> list[TaskSpec]:
    """Materialize task metadata in frozen manifest order."""
    requested = set(task_ids or ())
    available = {
        _string_field(row.get("task_id"), "task_id"): row for row in manifest_rows
    }
    missing = requested - available.keys()
    if missing:
        raise ValueError(f"task id is absent from target manifest: {sorted(missing)}")
    rows = (
        [row for row in manifest_rows if _string_field(row.get("task_id"), "task_id") in requested]
        if requested
        else list(manifest_rows)
    )
    return [load_task_spec(deepswe_root, row) for row in rows]


def validate_use_mode(use_mode: str) -> None:
    """Keep assisted as a labelled future mode without silently running it."""
    if use_mode == "voluntary":
        return
    if use_mode == "assisted":
        raise ValueError("assisted mode is reserved for future separately labelled support")
    raise ValueError(f"unknown use mode: {use_mode}")


def condition_order(replicate: int) -> tuple[str, str]:
    """Return the deterministic counterbalanced order for one replicate."""
    if replicate < 1:
        raise ValueError("replicate must be positive")
    return CONDITIONS if replicate % 2 else ("treatment", "baseline")


def _run_dir(output_root: Path, task: TaskSpec, replicate: int, condition: str, use_mode: str) -> Path:
    return (
        output_root
        / task.task_id
        / task.stratum
        / use_mode
        / f"rep-{replicate:02d}"
        / condition
    )


def command_value(command: Sequence[str], flag: str) -> str:
    """Return a required single-value CLI option from a command list."""
    try:
        index = command.index(flag)
        return command[index + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError(f"command has no value for {flag}") from exc


def docker_create_command(image: str) -> list[str]:
    return ["docker", "create", "--rm", image]


def docker_pull_command(image: str) -> list[str]:
    """Build the explicit, provenance-recorded image preparation command."""
    return ["docker", "pull", image]


def docker_image_presence_command(image: str) -> list[str]:
    """Check whether an immutable image can be reused without network access."""
    return ["docker", "image", "inspect", image]


def loomgraph_index_command(
    loomgraph_binary: str, source_dir: Path, backend: str
) -> list[str]:
    """Prepare a treatment source for native MCP retrieval without agent input."""
    if backend not in {"codeindex", "codegraph"}:
        raise ValueError(f"unsupported LoomGraph backend: {backend!r}")
    return [loomgraph_binary, "index", "--clear", "--backend", backend, str(source_dir)]


def codegraph_init_command(source_dir: Path) -> list[str]:
    """Build the codegraph database before the adapter snapshots it."""
    return ["codegraph", "init", str(source_dir)]


def _exclude_setup_artifact(source_dir: Path, artifact: str) -> Path:
    """Keep declared setup state out of the model-phase source-clean check."""
    exclude_path = source_dir / ".git" / "info" / "exclude"
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    if artifact not in existing.splitlines():
        with exclude_path.open("a", encoding="utf-8") as exclude_file:
            if existing and not existing.endswith("\n"):
                exclude_file.write("\n")
            exclude_file.write(f"{artifact}\n")
    return exclude_path


def loomgraph_storage_env(storage_root: Path) -> dict[str, str]:
    """Keep the treatment index and its MCP server on the same external DB path."""
    return {"LOOMGRAPH_STORAGE__DB_PATH": str(storage_root / "{workspace}.db")}


def adapter_storage_root(run_dir: Path) -> Path:
    """Keep adapter state outside the orientation runner's output directory."""
    return run_dir / "loomgraph-storage"


def docker_copy_command(container_id: str, source_dir: Path) -> list[str]:
    """Copy only the task image's ``/app`` tree into the adapter source dir."""
    return ["docker", "cp", f"{container_id}:/app", str(source_dir)]


def docker_image_id_command(container_id: str) -> list[str]:
    """Build the metadata-only Docker inspection command for an immutable image id."""
    return ["docker", "inspect", "--format", "{{.Image}}", container_id]


def docker_image_digest_command(image: str) -> list[str]:
    """Build the metadata-only command for the registry digest, when available."""
    return ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image]


def orientation_command(
    task: TaskSpec,
    *,
    condition: str,
    use_mode: str,
    model: str,
    max_budget_usd: str,
    tool_call_budget: int,
    loomgraph_binary: str,
    source_dir: Path,
    output_dir: Path,
    orientation_runner: Path,
) -> list[str]:
    """Build one invocation of the existing host-side Claude orientation runner."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")
    validate_use_mode(use_mode)
    if tool_call_budget < 2:
        raise ValueError("tool_call_budget must reserve one structured-output call")
    command = [
        sys.executable,
        str(orientation_runner),
        "--condition",
        condition,
        "--task-id",
        task.task_id,
        "--source-dir",
        str(source_dir),
        "--instruction-file",
        str(task.instruction_file),
        "--output-dir",
        str(output_dir),
        "--use-mode",
        use_mode,
        "--model",
        model,
        "--max-budget-usd",
        max_budget_usd,
        "--tool-call-budget",
        str(tool_call_budget),
        "--loomgraph-binary",
        loomgraph_binary,
    ]
    if condition == "treatment":
        command.extend(["--treatment-surface", TREATMENT_SURFACE])
    return command


def orientation_instruction(task: TaskSpec, *, tool_call_budget: int) -> str:
    """Render a read-only navigation prompt without exposing host-only targets."""
    if tool_call_budget < 2:
        raise ValueError("tool_call_budget must reserve one structured-output call")
    task_text = task.instruction_file.read_text(encoding="utf-8").strip()
    navigation_limit = tool_call_budget - 1
    return (
        "Pre-edit navigation only: do not solve this task, edit source, propose a patch, "
        f"or run tests. Use at most {navigation_limit} navigation tool calls and reserve one call for "
        "structured output. Use the available navigation tools to identify at most five existing "
        "production-code paths that should be inspected before implementation. Explain each "
        "candidate briefly.\n\nTask context:\n"
        f"{task_text}\n"
    )


def _replace_command_value(command: list[str], flag: str, value: str) -> list[str]:
    """Replace a required one-value option while preserving the runner tool surface."""
    index = command.index(flag)
    updated = list(command)
    updated[index + 1] = value
    return updated


def build_plan(
    tasks: Sequence[TaskSpec],
    *,
    output_root: Path,
    replicates: int,
    use_mode: str = DEFAULT_USE_MODE,
    model: str = DEFAULT_MODEL,
    max_budget_usd: str = DEFAULT_BUDGET_USD,
    tool_call_budget: int = DEFAULT_TOOL_CALL_BUDGET,
    loomgraph_binary: str = "loomgraph",
    orientation_runner: Path | None = None,
) -> dict[str, object]:
    """Build a deterministic, JSON-safe cohort plan without external calls."""
    validate_use_mode(use_mode)
    if replicates < 1:
        raise ValueError("replicates must be positive")
    if tool_call_budget < 2:
        raise ValueError("tool_call_budget must reserve one structured-output call")
    runner = (orientation_runner or Path(__file__).with_name("claude_orientation.py")).resolve()
    root = output_root.resolve()
    task_plans: list[dict[str, object]] = []
    for task in tasks:
        replicate_plans: list[dict[str, object]] = []
        for replicate in range(1, replicates + 1):
            replicate_label = f"{replicate:02d}"
            order = list(condition_order(replicate))
            pair_key = f"{task.task_id}:{task.stratum}:{use_mode}:{replicate_label}"
            runs: list[dict[str, object]] = []
            for condition in order:
                run_dir = _run_dir(root, task, replicate, condition, use_mode)
                source_dir = run_dir / "source"
                output_dir = run_dir / "output"
                surface = BASELINE_SURFACE if condition == "baseline" else TREATMENT_SURFACE
                runs.append(
                    {
                        "condition": condition,
                        "use_mode": use_mode,
                        "tool_surface": surface,
                        "tool_call_budget": tool_call_budget,
                        "task_id": task.task_id,
                        "stratum": task.stratum,
                        "backend": task.backend,
                        "replicate": replicate_label,
                        "pair_key": pair_key,
                        "image": task.image,
                        "run_dir": str(run_dir),
                        "source_dir": str(source_dir),
                        "output_dir": str(output_dir),
                        "docker_create_command": docker_create_command(task.image),
                        "docker_copy_command": docker_copy_command(
                            "<container-id>", source_dir
                        ),
                        "orientation_command": orientation_command(
                            task,
                            condition=condition,
                            use_mode=use_mode,
                            model=model,
                            max_budget_usd=max_budget_usd,
                            tool_call_budget=tool_call_budget,
                            loomgraph_binary=loomgraph_binary,
                            source_dir=source_dir,
                            output_dir=output_dir,
                            orientation_runner=runner,
                        ),
                    }
                )
            replicate_plans.append(
                {
                    "replicate": replicate_label,
                    "order": order,
                    "pair_key": pair_key,
                    "runs": runs,
                }
            )
        task_plans.append(
            {
                "task_id": task.task_id,
                "stratum": task.stratum,
                "language": task.language,
                "backend": task.backend,
                "replicates": replicate_plans,
            }
        )
    return {
        "schema_version": 1,
        "protocol": "deep-swe-claude-target-cohort",
        "use_mode": use_mode,
        "model": model,
        "replicates": replicates,
        "tool_call_budget": tool_call_budget,
        "conditions": list(CONDITIONS),
        "baseline_tool_surface": BASELINE_SURFACE,
        "treatment_tool_surface": TREATMENT_SURFACE,
        "tasks": task_plans,
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _create_container(image: str) -> str:
    result = subprocess.run(
        docker_create_command(image), check=True, capture_output=True, text=True
    )
    container_id = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if not container_id:
        raise RuntimeError("docker create returned no container id")
    return container_id


def _pull_image(image: str) -> str:
    """Ensure the declared task image is present, reusing an auditable local copy."""
    local_image = subprocess.run(
        docker_image_presence_command(image), check=False, capture_output=True, text=True
    )
    if local_image.returncode == 0:
        return "reused_local"
    subprocess.run(docker_pull_command(image), check=True, capture_output=True, text=True)
    return "pulled"


def _image_provenance(container_id: str, image: str) -> dict[str, object]:
    """Read immutable Docker identity without reading files from the container."""
    image_id_result = subprocess.run(
        docker_image_id_command(container_id),
        check=True,
        capture_output=True,
        text=True,
    )
    image_id = image_id_result.stdout.strip()
    if not image_id:
        raise RuntimeError("docker inspect returned no immutable image id")
    digest_result = subprocess.run(
        docker_image_digest_command(image),
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        repo_digests = json.loads(digest_result.stdout.strip() or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("docker image inspect returned malformed RepoDigests") from exc
    if not isinstance(repo_digests, list) or not all(
        isinstance(digest, str) for digest in repo_digests
    ):
        raise RuntimeError("docker image inspect returned invalid RepoDigests")
    return {
        "image_id": image_id,
        # A local image can legitimately have no registry RepoDigest.  The
        # immutable content id remains the audit-grade fallback in that case.
        "image_digest": repo_digests[0] if repo_digests else image_id,
        "repo_digests": repo_digests,
    }


def _remove_container(container_id: str) -> bool:
    result = subprocess.run(
        ["docker", "rm", "-f", container_id],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run_one(run: dict[str, object]) -> dict[str, object]:
    """Materialize one isolated source and delegate its model phase."""
    run_dir = Path(_string_field(run.get("run_dir"), "run_dir"))
    source_dir = Path(_string_field(run.get("source_dir"), "source_dir"))
    output_dir = Path(_string_field(run.get("output_dir"), "output_dir"))
    image = _string_field(run.get("image"), "image")
    run_dir.mkdir(parents=True, exist_ok=False)
    orientation_value = run.get("orientation_command")
    orientation_items = (
        orientation_value
        if isinstance(orientation_value, list)
        and all(isinstance(item, str) for item in orientation_value)
        else []
    )
    metadata: dict[str, object] = {
        "schema_version": 1,
        "task_id": run.get("task_id"),
        "stratum": run.get("stratum"),
        "backend": run.get("backend"),
        "replicate": run.get("replicate"),
        "pair_key": run.get("pair_key"),
        "condition": run.get("condition"),
        "use_mode": run.get("use_mode"),
        "tool_surface": run.get("tool_surface"),
        "model": command_value(orientation_items, "--model") if orientation_items else None,
        "orientation_runner": orientation_items[1] if len(orientation_items) > 1 else None,
        "tool_call_budget": (
            command_value(orientation_items, "--tool-call-budget")
            if orientation_items
            else None
        ),
        "instruction": None,
        "image": image,
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "status": "driver_error",
        "source_clean": None,
        "source_git": {
            "pre_state_path": str(output_dir / "pre-state.json"),
            "post_state_path": str(output_dir / "post-state.json"),
            "pre_state": None,
            "post_state": None,
        },
    }
    container_id = ""
    try:
        metadata["image_pull_command"] = docker_pull_command(image)
        metadata["image_presence_command"] = docker_image_presence_command(image)
        metadata["image_pull_status"] = _pull_image(image)
        container_id = _create_container(image)
        metadata["container_id"] = container_id
        metadata.update(_image_provenance(container_id, image))
        source_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(docker_copy_command(container_id, source_dir), check=True)
        orientation = run.get("orientation_command")
        if not isinstance(orientation, list) or not all(
            isinstance(item, str) for item in orientation
        ):
            raise ValueError("invalid orientation command in run plan")
        instruction_path = run_dir / "orientation-instruction.md"
        tool_call_budget = int(command_value(orientation, "--tool-call-budget"))
        instruction = orientation_instruction(
            TaskSpec(
                task_id=_string_field(run.get("task_id"), "task_id"),
                stratum=_string_field(run.get("stratum"), "stratum"),
                language="",
                backend="",
                image=image,
                task_dir=Path(),
                instruction_file=Path(command_value(orientation, "--instruction-file")),
            ),
            tool_call_budget=tool_call_budget,
        )
        instruction_path.write_text(instruction, encoding="utf-8")
        metadata["instruction"] = {
            "path": str(instruction_path),
            "sha256": hashlib.sha256(instruction.encode()).hexdigest(),
            "mode": "pre_edit_navigation_only",
        }
        orientation = _replace_command_value(
            orientation, "--instruction-file", str(instruction_path)
        )
        if run.get("condition") == "treatment":
            storage_root = adapter_storage_root(run_dir)
            backend = _string_field(run.get("backend"), "backend")
            if backend == "codegraph":
                exclude_path = _exclude_setup_artifact(source_dir, ".codegraph/")
                codegraph_command = codegraph_init_command(source_dir)
                codegraph_setup: dict[str, object] = {
                    "command": codegraph_command,
                    "git_exclude_path": str(exclude_path),
                    "ignored_artifact": ".codegraph/",
                }
                metadata["codegraph_setup"] = codegraph_setup
                with (run_dir / "codegraph-init.log").open("w") as codegraph_log:
                    subprocess.run(
                        codegraph_command,
                        cwd=source_dir,
                        check=True,
                        stdout=codegraph_log,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                codegraph_setup["status"] = "complete"
            index_command = loomgraph_index_command(
                command_value(orientation, "--loomgraph-binary"),
                source_dir,
                backend,
            )
            metadata["index_command"] = index_command
            metadata["index_storage_env"] = loomgraph_storage_env(storage_root)
            with (run_dir / "loomgraph-index.log").open("w") as index_log:
                subprocess.run(
                    index_command,
                    cwd=source_dir,
                    env={**os.environ, **loomgraph_storage_env(storage_root)},
                    check=True,
                    stdout=index_log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            metadata["index_status"] = "complete"
            orientation.extend(["--storage-root", str(storage_root)])
        stdout_path = run_dir / "runner.stdout.log"
        with stdout_path.open("w") as stdout:
            result = subprocess.run(
                orientation,
                cwd=source_dir,
                check=False,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                text=True,
            )
        metadata["runner_return_code"] = result.returncode
        orientation_path = output_dir / "orientation.json"
        source_git = metadata["source_git"]
        if isinstance(source_git, dict):
            for state_name in ("pre", "post"):
                state_path = output_dir / f"{state_name}-state.json"
                if state_path.is_file():
                    state = json.loads(state_path.read_text())
                    if isinstance(state, dict):
                        source_git[f"{state_name}_state"] = state
        if orientation_path.is_file():
            packet = json.loads(orientation_path.read_text())
            if isinstance(packet, dict):
                metadata["status"] = packet.get("status", "missing_or_invalid_agent_response")
                metadata["source_clean"] = packet.get("source_clean")
        else:
            metadata["status"] = "missing_or_invalid_agent_response"
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        metadata["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if container_id:
            metadata["container_removed"] = _remove_container(container_id)
        _write_json(run_dir / "driver-run.json", metadata)
    return metadata


def run_cohort(
    tasks: Sequence[TaskSpec],
    *,
    output_root: Path,
    replicates: int = 3,
    use_mode: str = DEFAULT_USE_MODE,
    model: str = DEFAULT_MODEL,
    max_budget_usd: str = DEFAULT_BUDGET_USD,
    tool_call_budget: int = DEFAULT_TOOL_CALL_BUDGET,
    loomgraph_binary: str = "loomgraph",
    orientation_runner: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Run or materialize a cohort; raw orientation artifacts stay in output_root."""
    plan = build_plan(
        tasks,
        output_root=output_root,
        replicates=replicates,
        use_mode=use_mode,
        model=model,
        max_budget_usd=max_budget_usd,
        tool_call_budget=tool_call_budget,
        loomgraph_binary=loomgraph_binary,
        orientation_runner=orientation_runner,
    )
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    if dry_run:
        _write_json(output_root / "dry-run.json", plan)
        return plan
    _write_json(output_root / "cohort-plan.json", plan)
    results: list[dict[str, object]] = []
    planned_tasks = plan.get("tasks")
    if not isinstance(planned_tasks, list):
        raise RuntimeError("cohort plan has no task list")
    for task in planned_tasks:
        if not isinstance(task, dict):
            continue
        planned_replicates = task.get("replicates")
        if not isinstance(planned_replicates, list):
            continue
        for replicate in planned_replicates:
            if not isinstance(replicate, dict):
                continue
            planned_runs = replicate.get("runs")
            if not isinstance(planned_runs, list):
                continue
            for run in planned_runs:
                if isinstance(run, dict):
                    results.append(_run_one(run))
    output: dict[str, object] = {"plan": plan, "results": results}
    _write_json(output_root / "cohort-results.json", output)
    return output


def _default_deepswe_dir() -> Path:
    return Path(os.environ.get("DEEPSWE_DIR", str(Path.home() / "Projects/opensource/deep-swe")))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deepswe-dir", type=Path, default=_default_deepswe_dir())
    parser.add_argument(
        "--target-manifest",
        type=Path,
        default=Path(__file__).with_name("target-manifest.json"),
    )
    parser.add_argument("--task-id", action="append", help="restrict to one or more frozen task ids")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--use-mode", choices=USE_MODES, default=DEFAULT_USE_MODE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-budget-usd", default=DEFAULT_BUDGET_USD)
    parser.add_argument("--tool-call-budget", type=int, default=DEFAULT_TOOL_CALL_BUDGET)
    parser.add_argument("--loomgraph-binary", default="loomgraph")
    parser.add_argument(
        "--orientation-runner",
        type=Path,
        default=Path(__file__).with_name("claude_orientation.py"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    validate_use_mode(args.use_mode)
    rows = load_target_manifest(args.target_manifest)
    tasks = select_task_specs(args.deepswe_dir, rows, args.task_id)
    result = run_cohort(
        tasks,
        output_root=args.output_dir,
        replicates=args.replicates,
        use_mode=args.use_mode,
        model=args.model,
        max_budget_usd=args.max_budget_usd,
        tool_call_budget=args.tool_call_budget,
        loomgraph_binary=args.loomgraph_binary,
        orientation_runner=args.orientation_runner,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
