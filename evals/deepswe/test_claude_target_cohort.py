"""Pure contract tests for the Claude DeepSWE cohort planner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("run_claude_target_cohort.py")
_SPEC = importlib.util.spec_from_file_location("run_claude_target_cohort", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _task_row(task_id: str = "fixture-task", stratum: str = "codeindex-python") -> dict[str, object]:
    return {
        "task_id": task_id,
        "stratum": stratum,
        "language": "python",
        "backend": "codeindex",
        "l2_content_hash": "available",
        "repository_url": "https://example.invalid/repo",
        "base_commit_hash": "0" * 40,
        "gold_production_paths": ["src/example.py"],
        "gold_existing_production_paths": ["src/example.py"],
        "gold_new_production_paths": [],
    }


def _write_task(root: Path, *, image: str = "example/image:1") -> Path:
    task_dir = root / "tasks" / "fixture-task"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        "[metadata]\n"
        'task_id = "fixture-task"\n'
        'language = "python"\n'
        "\n[environment]\n"
        f'docker_image = "{image}"\n'
    )
    (task_dir / "instruction.md").write_text("Find the production entry point.\n")
    return task_dir


def test_load_task_spec_reads_instruction_and_environment_image_only(tmp_path: Path) -> None:
    task_dir = _write_task(tmp_path)

    spec = _MODULE.load_task_spec(tmp_path, _task_row())

    assert spec.task_id == "fixture-task"
    assert spec.image == "example/image:1"
    assert spec.instruction_file == task_dir / "instruction.md"
    assert spec.instruction_file.read_text() == "Find the production entry point.\n"


def test_counterbalanced_orders_alternate_first_condition() -> None:
    assert _MODULE.condition_order(1) == ("baseline", "treatment")
    assert _MODULE.condition_order(2) == ("treatment", "baseline")
    assert _MODULE.condition_order(3) == ("baseline", "treatment")


def test_plan_pairs_matching_replicates_and_separates_surfaces(tmp_path: Path) -> None:
    task = _MODULE.TaskSpec(
        task_id="fixture-task",
        stratum="codeindex-python",
        language="python",
        backend="codeindex",
        image="example/image:1",
        task_dir=tmp_path / "task",
        instruction_file=tmp_path / "instruction.md",
    )
    plan = _MODULE.build_plan(
        [task],
        output_root=tmp_path / "out",
        replicates=3,
        use_mode="voluntary",
        model="sonnet",
        max_budget_usd="0.50",
        tool_call_budget=7,
        loomgraph_binary="loomgraph",
        orientation_runner=tmp_path / "claude_orientation.py",
    )

    runs = plan["tasks"][0]["replicates"]
    assert [rep["order"] for rep in runs] == [
        ["baseline", "treatment"],
        ["treatment", "baseline"],
        ["baseline", "treatment"],
    ]
    for rep in runs:
        assert rep["pair_key"] == "fixture-task:codeindex-python:voluntary:" + rep["replicate"]
        assert [run["condition"] for run in rep["runs"]] == rep["order"]
        assert {run["tool_surface"] for run in rep["runs"]} == {"text-only", "additive"}
        assert all(run["use_mode"] == "voluntary" for run in rep["runs"])


def test_docker_copy_command_has_no_solution_or_manifest_path() -> None:
    command = _MODULE.docker_copy_command("container-id", Path("/tmp/out/source"))

    assert command == ["docker", "cp", "container-id:/app", "/tmp/out/source"]
    assert all("solution" not in part and "target-manifest" not in part for part in command)


def test_docker_pull_command_is_explicit_for_auditable_source_preparation() -> None:
    assert _MODULE.docker_pull_command("example/image:1") == [
        "docker",
        "pull",
        "example/image:1",
    ]
    assert _MODULE.docker_image_presence_command("example/image:1") == [
        "docker",
        "image",
        "inspect",
        "example/image:1",
    ]


def test_treatment_index_uses_manifest_backend_and_adapter_owned_storage() -> None:
    command = _MODULE.loomgraph_index_command(
        "/tmp/loomgraph", Path("/tmp/source"), "codegraph"
    )

    assert command == [
        "/tmp/loomgraph",
        "index",
        "--clear",
        "--backend",
        "codegraph",
        "/tmp/source",
    ]
    assert all("solution" not in part and "target-manifest" not in part for part in command)
    assert _MODULE.loomgraph_storage_env(Path("/tmp/run/storage")) == {
        "LOOMGRAPH_STORAGE__DB_PATH": "/tmp/run/storage/{workspace}.db"
    }
    assert _MODULE.adapter_storage_root(Path("/tmp/run")) == Path(
        "/tmp/run/loomgraph-storage"
    )


def test_codegraph_setup_command_keeps_the_source_path_explicit() -> None:
    assert _MODULE.codegraph_init_command(Path("/tmp/source")) == [
        "codegraph",
        "init",
        "/tmp/source",
    ]


def test_codegraph_setup_artifact_is_excluded_from_model_phase_status(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    exclude_path = source_dir / ".git" / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True)
    exclude_path.write_text("# local setup\n")

    result = _MODULE._exclude_setup_artifact(source_dir, ".codegraph/")
    _MODULE._exclude_setup_artifact(source_dir, ".codegraph/")

    assert result == exclude_path
    assert exclude_path.read_text().splitlines().count(".codegraph/") == 1


def test_docker_provenance_commands_are_metadata_only() -> None:
    assert _MODULE.docker_image_id_command("container-id") == [
        "docker",
        "inspect",
        "--format",
        "{{.Image}}",
        "container-id",
    ]
    assert _MODULE.docker_image_digest_command("example/image:1") == [
        "docker",
        "image",
        "inspect",
        "--format",
        "{{json .RepoDigests}}",
        "example/image:1",
    ]


def test_orientation_command_calls_existing_runner_and_adds_only_additive_surface(
    tmp_path: Path,
) -> None:
    task = _MODULE.TaskSpec(
        task_id="fixture-task",
        stratum="codeindex-python",
        language="python",
        backend="codeindex",
        image="example/image:1",
        task_dir=tmp_path / "task",
        instruction_file=tmp_path / "instruction.md",
    )
    command = _MODULE.orientation_command(
        task,
        condition="treatment",
        use_mode="voluntary",
        model="sonnet",
        max_budget_usd="0.50",
        tool_call_budget=7,
        loomgraph_binary="loomgraph",
        source_dir=tmp_path / "source",
        output_dir=tmp_path / "run",
        orientation_runner=tmp_path / "claude_orientation.py",
    )

    assert "claude_orientation.py" in command[1]
    assert _MODULE.command_value(command, "--condition") == "treatment"
    assert _MODULE.command_value(command, "--treatment-surface") == "additive"
    assert _MODULE.command_value(command, "--use-mode") == "voluntary"
    assert "--require-trust" not in command


def test_orientation_instruction_is_pre_edit_only_and_has_no_host_oracle_leakage(
    tmp_path: Path,
) -> None:
    task = _MODULE.TaskSpec(
        task_id="fixture-task",
        stratum="codeindex-python",
        language="python",
        backend="codeindex",
        image="example/image:1",
        task_dir=tmp_path,
        instruction_file=tmp_path / "instruction.md",
    )
    task.instruction_file.write_text("Implement a cache.\n")

    instruction = _MODULE.orientation_instruction(task, tool_call_budget=7)

    assert "Pre-edit navigation only" in instruction
    assert "do not solve this task" in instruction
    assert "at most 6 navigation tool calls" in instruction
    assert "at most five existing production-code paths" in instruction
    assert "target-manifest" not in instruction
    assert "solution" not in instruction


def test_assisted_mode_is_explicitly_reserved_for_future_driver_support() -> None:
    with pytest.raises(ValueError, match="future"):
        _MODULE.validate_use_mode("assisted")


def test_dry_run_is_json_stable_and_does_not_need_docker_or_model(tmp_path: Path) -> None:
    task = _MODULE.TaskSpec(
        task_id="fixture-task",
        stratum="codeindex-python",
        language="python",
        backend="codeindex",
        image="example/image:1",
        task_dir=tmp_path / "task",
        instruction_file=tmp_path / "instruction.md",
    )
    plan = _MODULE.build_plan(
        [task],
        output_root=tmp_path / "out",
        replicates=1,
        use_mode="voluntary",
        model="sonnet",
        max_budget_usd="0.50",
        loomgraph_binary="loomgraph",
        orientation_runner=tmp_path / "claude_orientation.py",
    )
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"))

    assert json.loads(encoded)["schema_version"] == 1
    assert "docker cp" not in encoded
    assert "solution" not in encoded
    assert "target-manifest" not in encoded
