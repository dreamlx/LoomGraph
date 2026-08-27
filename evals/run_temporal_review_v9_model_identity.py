"""Capture V9 model identity, including its persisted validity witness."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.deepswe import claude_orientation as orientation  # noqa: E402
from evals.temporal_review_v9_fixtures import REQUESTED_MODEL_LITERAL  # noqa: E402

PROTOCOL = "temporal-review-v9-model-identity"
REQUESTED_MODEL = REQUESTED_MODEL_LITERAL
FIXED_MAX_BUDGET_USD = "0.50"
CALIBRATION_SOURCE_SHA256 = "4ecef8c92de9e16713cff66da3f5e80c72c05097978984520578084824779490"
CALIBRATION_INSTRUCTION_SHA256 = "d3fdd39f6d6168253a56155fe22d92a234b084ff5d62f8b19e01ed547d712191"
CALIBRATION_TASK_ID = "v9-runtime-identity-calibration"
CALIBRATION_CELLS = (
    (1, "baseline"),
    (1, "treatment"),
    (2, "treatment"),
    (2, "baseline"),
)
_MODEL_SURFACES = ("assistant", "session", "usage")
_IDENTITY_FIELDS = tuple(
    f"{surface}_models_{kind}" for surface in _MODEL_SURFACES for kind in ("raw", "canonical")
) + ("model_categories_valid",)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _command(model: str, budget_usd: str) -> list[str]:
    _require_requested_model(model)
    return [
        "claude",
        "-p",
        "--model",
        model,
        "--effort",
        "low",
        "--output-format",
        "stream-json",
        "--verbose",
        "--setting-sources",
        "project,local",
        "--disable-slash-commands",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--max-budget-usd",
        budget_usd,
        "--json-schema",
        json.dumps(_SCHEMA, separators=(",", ":"), sort_keys=True),
        "--strict-mcp-config",
        "--tools",
        "",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--",
        "Return exactly the required JSON object.",
    ]


def _model_categories(events: list[dict[str, Any]]) -> dict[str, object]:
    return orientation._v7_model_categories(events)


def _require_requested_model(model: str) -> None:
    """V9 is an independently preregistered direct-Flash runtime only."""
    if model != REQUESTED_MODEL:
        raise ValueError(f"V9 requires --model {REQUESTED_MODEL}")


def command_uses_requested_model(command: object) -> bool:
    return (
        isinstance(command, list)
        and all(isinstance(item, str) for item in command)
        and "--model" in command
        and command.index("--model") + 1 < len(command)
        and command[command.index("--model") + 1] == REQUESTED_MODEL
    )


def _require_fixed_budget(budget_usd: str) -> None:
    if budget_usd != FIXED_MAX_BUDGET_USD:
        raise ValueError(f"V9 requires --max-budget-usd {FIXED_MAX_BUDGET_USD}")


def command_surface_fingerprint(outer: object, inner: object) -> str:
    """Hash a command surface while removing only run-local location/marker values."""
    if not isinstance(outer, list) or not isinstance(inner, list):
        raise ValueError("V9 command surface must be command lists")
    normalized_outer = list(outer)
    for flag in ("--source-dir", "--instruction-file", "--output-dir", "--task-id"):
        if flag in normalized_outer:
            normalized_outer[normalized_outer.index(flag) + 1] = f"<{flag[2:].upper()}>"
    for marker in ("--temporal-review-v9-calibration", "--temporal-review-v9-contract"):
        if marker in normalized_outer:
            normalized_outer[normalized_outer.index(marker)] = "--temporal-review-v9-marker"
    normalized_inner = list(inner)
    if "--" in normalized_inner:
        normalized_inner[normalized_inner.index("--") + 1] = "<TERMINAL_INSTRUCTION>"
    if "--mcp-config" in normalized_inner:
        index = normalized_inner.index("--mcp-config") + 1
        try:
            config = json.loads(normalized_inner[index])
            env = config.get("mcpServers", {}).get("loomgraph", {}).get("env", {})
            if isinstance(env, dict) and "LOOMGRAPH_STORAGE__DB_PATH" in env:
                env["LOOMGRAPH_STORAGE__DB_PATH"] = "<OUTPUT_STORAGE>"
            normalized_inner[index] = json.dumps(config, separators=(",", ":"), sort_keys=True)
        except (IndexError, TypeError, json.JSONDecodeError):
            pass
    return hashlib.sha256(
        json.dumps({"outer": normalized_outer, "inner": normalized_inner}, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _categories_valid(categories: object, *, requested_model: str, identity_mode: str) -> bool:
    if requested_model != REQUESTED_MODEL or identity_mode != "runtime-specific":
        return False
    if not isinstance(categories, dict) or categories.get("model_categories_valid") is not True:
        return False
    for surface in _MODEL_SURFACES:
        raw, canonical = (
            categories.get(f"{surface}_models_raw"),
            categories.get(f"{surface}_models_canonical"),
        )
        if (
            not isinstance(raw, list)
            or not raw
            or not all(isinstance(value, str) and value for value in raw)
            or canonical != sorted(set(raw))
        ):
            return False
    assistant = categories.get("assistant_models_canonical")
    return isinstance(assistant, list) and assistant == [requested_model]


def _events(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _calibration_source(path: Path) -> None:
    source = path / "src"
    source.mkdir(parents=True)
    (source / "calibration.py").write_text(
        "def calibration_marker() -> str:\n    return 'runtime-identity-only'\n",
        encoding="utf-8",
    )
    (path / ".codeindex.yaml").write_text("include:\n  - src/**\n", encoding="utf-8")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "v9-calibration@example.invalid"],
        ["git", "config", "user.name", "V9 Calibration"],
        ["git", "add", "src", ".codeindex.yaml"],
        ["git", "commit", "--quiet", "-m", "v9 calibration source"],
    ):
        subprocess.run(command, cwd=path, check=True, capture_output=True, text=True)


def _calibration_content(directory: Path) -> dict[str, str]:
    source = directory / "calibration-source" / "src" / "calibration.py"
    instruction = directory / "calibration-instruction.md"
    values = {"source_sha256": _sha256(source), "instruction_sha256": _sha256(instruction)}
    forbidden = ("manifest", "oracle", "target", "solution", "gold", "v9-resolution", "v9-sparse")
    text = source.read_text(encoding="utf-8").lower() + "\n" + instruction.read_text(encoding="utf-8").lower()
    if any(term in text for term in forbidden):
        raise ValueError("V9 calibration content leaks task evidence")
    if values != {
        "source_sha256": CALIBRATION_SOURCE_SHA256,
        "instruction_sha256": CALIBRATION_INSTRUCTION_SHA256,
    }:
        raise ValueError("V9 calibration content hash is not frozen")
    return values


def _calibration_outer_command(
    *, source: Path, instruction: Path, output: Path, condition: str, max_budget_usd: str, loomgraph_binary: str
) -> list[str]:
    return [
        sys.executable,
        str(_ROOT / "evals/deepswe/claude_orientation.py"),
        "--condition", condition,
        "--task-id", CALIBRATION_TASK_ID,
        "--source-dir", str(source),
        "--instruction-file", str(instruction),
        "--output-dir", str(output),
        "--use-mode", "voluntary",
        "--treatment-surface", orientation.TEMPORAL_REVIEW_V9_ADDITIVE_SURFACE,
        "--temporal-review-v9-calibration",
        "--model", REQUESTED_MODEL,
        "--max-budget-usd", max_budget_usd,
        "--loomgraph-binary", loomgraph_binary,
    ]


def _cell_categories(output: Path) -> dict[str, object]:
    stream = output / "claude.stream.jsonl"
    return _model_categories(_events(stream)) if stream.is_file() else {}


def _inner_surface_valid(command: object, condition: str, loomgraph_binary: str) -> bool:
    if not isinstance(command, list) or not command_uses_requested_model(command):
        return False
    try:
        tools = command[command.index("--tools") + 1]
        config = json.loads(command[command.index("--mcp-config") + 1])
    except (IndexError, TypeError, json.JSONDecodeError):
        return False
    servers = config.get("mcpServers") if isinstance(config, dict) else None
    if condition == "baseline":
        return tools == orientation.BASELINE_TOOLS and servers == {} and "--allowedTools" not in command
    if condition != "treatment":
        return False
    server = servers.get("loomgraph") if isinstance(servers, dict) and set(servers) == {"loomgraph"} else None
    return (
        tools == orientation.BASELINE_TOOLS
        and isinstance(server, dict)
        and server.get("command") == loomgraph_binary
        and server.get("args") == ["mcp", "serve"]
        and isinstance(server.get("env"), dict)
        and set(server["env"]).issubset({"LOOMGRAPH_MCP_ALLOWED_TOOLS", "LOOMGRAPH_STORAGE__DB_PATH"})
        and server["env"].get("LOOMGRAPH_MCP_ALLOWED_TOOLS") == orientation.TEMPORAL_SERVER_TOOL
        and "--allowedTools" in command
        and command[command.index("--allowedTools") + 1] == orientation.TEMPORAL_MCP_TOOL
    )


def _validate_calibration(directory: Path, record: object) -> dict[str, object]:
    if not isinstance(record, dict):
        raise ValueError("V9 calibration record is invalid")
    condition, replicate = record.get("condition"), record.get("replicate")
    if (replicate, condition) not in CALIBRATION_CELLS:
        raise ValueError("V9 calibration matrix was changed")
    output = directory / str(record.get("output_dir", ""))
    stream, command_path, packet_path = (
        output / "claude.stream.jsonl",
        output / "command.json",
        output / "orientation.json",
    )
    if not all(path.is_file() for path in (stream, command_path, packet_path)):
        raise ValueError("V9 calibration artifacts are missing")
    categories = _cell_categories(output)
    command = json.loads(command_path.read_text(encoding="utf-8"))
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    outer = record.get("outer_command")
    binary = outer[outer.index("--loomgraph-binary") + 1] if isinstance(outer, list) and "--loomgraph-binary" in outer else None
    if (
        record.get("stream_sha256") != _sha256(stream)
        or record.get("command_sha256") != _sha256(command_path)
        or record.get("outer_return_code") != 0
        or record.get("outer_command_sha256") != hashlib.sha256(
            json.dumps(record.get("outer_command"), separators=(",", ":")).encode()
        ).hexdigest()
        or record.get("command_surface_fingerprint") != command_surface_fingerprint(outer, command)
        or record.get("categories") != categories
        or not _categories_valid(categories, requested_model=REQUESTED_MODEL, identity_mode="runtime-specific")
        or not _inner_surface_valid(command, str(condition), binary if isinstance(binary, str) else "")
        or not isinstance(outer, list)
        or "--temporal-review-v9-calibration" not in outer
        or "--temporal-review-v9-contract" in outer
        or not command_uses_requested_model(outer)
        or "--condition" not in outer
        or outer[outer.index("--condition") + 1] != condition
        or "--task-id" not in outer
        or outer[outer.index("--task-id") + 1] != CALIBRATION_TASK_ID
        or "--treatment-surface" not in outer
        or outer[outer.index("--treatment-surface") + 1]
        != orientation.TEMPORAL_REVIEW_V9_ADDITIVE_SURFACE
        or not isinstance(packet, dict)
        or packet.get("status") != "complete"
        or packet.get("source_clean") is not True
        or packet.get("model", {}).get("model_categories_valid") is not True
    ):
        raise ValueError("V9 calibration evidence is invalid")
    return categories


def run_preflight(
    *, output_dir: Path, model: str, identity_mode: str, max_budget_usd: str, loomgraph_binary: str = "loomgraph"
) -> dict[str, object]:
    """Freeze a no-target baseline/treatment command-surface calibration matrix."""
    if identity_mode != "runtime-specific":
        raise ValueError("V9 identity_mode must be runtime-specific")
    _require_requested_model(model)
    _require_fixed_budget(max_budget_usd)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError("output_dir must not already exist")
    output_dir.mkdir(parents=True)
    source = output_dir / "calibration-source"
    _calibration_source(source)
    instruction = output_dir / "calibration-instruction.md"
    instruction.write_text(
        "This is a runtime identity calibration. Do not inspect task artifacts or call tools. "
        "Return the required JSON with comparison_not_observed and a review_locus for src/calibration.py.",
        encoding="utf-8",
    )
    content = _calibration_content(output_dir)
    version_run = subprocess.run(["claude", "--version"], cwd=_ROOT, capture_output=True, text=True)
    claude_version = {"command": ["claude", "--version"], "return_code": version_run.returncode, "stdout": version_run.stdout, "stderr": version_run.stderr}
    calibrations: list[dict[str, object]] = []
    for replicate, condition in CALIBRATION_CELLS:
        relative = Path("calibrations") / f"rep-{replicate:02d}" / condition / "output"
        cell_output = output_dir / relative
        outer = _calibration_outer_command(
            source=source, instruction=instruction, output=cell_output, condition=condition,
            max_budget_usd=max_budget_usd, loomgraph_binary=loomgraph_binary,
        )
        completed = subprocess.run(outer, cwd=_ROOT, capture_output=True, text=True)
        (cell_output.parent / "outer.stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (cell_output.parent / "outer.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        stream, command = cell_output / "claude.stream.jsonl", cell_output / "command.json"
        inner = json.loads(command.read_text(encoding="utf-8")) if command.is_file() else []
        record: dict[str, object] = {
            "replicate": replicate, "condition": condition, "output_dir": str(relative),
            "outer_command": outer,
            "outer_command_sha256": hashlib.sha256(json.dumps(outer, separators=(",", ":")).encode()).hexdigest(),
            "outer_return_code": completed.returncode,
            "stream_sha256": _sha256(stream) if stream.is_file() else None,
            "command_sha256": _sha256(command) if command.is_file() else None,
            "categories": _cell_categories(cell_output),
            "command_surface_fingerprint": command_surface_fingerprint(outer, inner),
        }
        calibrations.append(record)
    category_sets: list[dict[str, object]] = []
    for record in calibrations:
        categories = record.get("categories")
        if isinstance(categories, dict):
            category_sets.append(categories)
    aggregate = {
        f"{surface}_models_canonical": category_sets[0].get(f"{surface}_models_canonical") if category_sets else None
        for surface in _MODEL_SURFACES
    }
    aggregate["model_categories_valid"] = bool(category_sets) and all(
        _categories_valid(item, requested_model=model, identity_mode=identity_mode) for item in category_sets
    ) and all(
        item.get(f"{surface}_models_canonical") == aggregate[f"{surface}_models_canonical"]
        for item in category_sets for surface in _MODEL_SURFACES
    )
    aggregate["command_surface_fingerprints"] = {
        condition: next(
            (record.get("command_surface_fingerprint") for record in calibrations if record.get("condition") == condition),
            None,
        )
        for condition in ("baseline", "treatment")
    }
    aggregate_fingerprints = aggregate["command_surface_fingerprints"]
    assert isinstance(aggregate_fingerprints, dict)
    fingerprints_match = not any(
        record.get("command_surface_fingerprint")
        != aggregate_fingerprints.get(record.get("condition"))
        for record in calibrations
    )
    complete = (
        version_run.returncode == 0
        and aggregate["model_categories_valid"] is True
        and fingerprints_match
    )
    for record in calibrations:
        try:
            _validate_calibration(output_dir, record)
        except ValueError:
            complete = False
    result: dict[str, object] = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "status": "complete" if complete else "failed",
        "identity_mode": identity_mode,
        "requested_model": model,
        "calibration_protocol": "temporal-review-v9-no-target-runtime-calibration",
        "calibration_matrix": [
            {"replicate": replicate, "condition": condition} for replicate, condition in CALIBRATION_CELLS
        ],
        "calibrations": calibrations,
        "calibration_content": content,
        "aggregate": aggregate,
        "claude_version": claude_version,
    }
    _write(output_dir / "identity-preflight.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--identity-mode", choices=("model-specific", "runtime-specific"), required=True
    )
    parser.add_argument("--max-budget-usd", default=FIXED_MAX_BUDGET_USD)
    parser.add_argument("--loomgraph-binary", default="loomgraph")
    args = parser.parse_args()
    result = run_preflight(
        output_dir=args.output_dir,
        model=args.model,
        identity_mode=args.identity_mode,
        max_budget_usd=args.max_budget_usd,
        loomgraph_binary=args.loomgraph_binary,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
