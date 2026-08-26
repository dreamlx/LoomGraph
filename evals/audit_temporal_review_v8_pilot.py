"""Read-only integrity audit for a complete V8 temporal-review cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals import temporal_review_v8_fixtures as v8  # noqa: E402
from evals.deepswe import claude_orientation as orientation  # noqa: E402
from evals.run_temporal_review_v8_model_identity import (  # noqa: E402
    _IDENTITY_FIELDS,
    _MODEL_SURFACES,
    _categories_valid,
    _model_categories,
)
from evals.run_temporal_review_v8_pilot import (  # noqa: E402
    MANIFEST_ID,
    PROTOCOL,
    SURFACE,
    expected_cells,
)

AUDIT_PROTOCOL = "temporal-review-v8-pilot-audit"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return value


def _events(path: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            output.append(value)
    return output


def _payload(event: dict[str, Any]) -> object:
    structured = event.get("structured_output")
    if isinstance(structured, dict):
        return structured
    encoded = event.get("result")
    if isinstance(encoded, str):
        try:
            decoded = json.loads(encoded)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def _canonical(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return None


def _stream_payload(events: list[dict[str, Any]]) -> tuple[object, int | None]:
    for index in range(len(events) - 1, -1, -1):
        if events[index].get("type") == "result":
            value = _payload(events[index])
            if value is not None:
                return value, index
    return None, None


def _raw_branch_diff(
    task_id: str, events: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    tool_by_id: dict[str, str] = {}
    tool_names: list[str] = []
    raw: list[dict[str, Any]] = []
    for event_index, event in enumerate(events):
        message = event.get("message")
        contents = message.get("content") if isinstance(message, dict) else None
        if not isinstance(contents, list):
            continue
        for item in contents:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use" and isinstance(item.get("id"), str):
                name = item.get("name")
                if isinstance(name, str):
                    tool_by_id[item["id"]] = name
                    tool_names.append(name)
            if (
                item.get("type") != "tool_result"
                or tool_by_id.get(item.get("tool_use_id")) != orientation.TEMPORAL_MCP_TOOL
            ):
                continue
            values = (
                item.get("content")
                if isinstance(item.get("content"), list)
                else [item.get("content")]
            )
            for content in values:
                text = content.get("text") if isinstance(content, dict) else content
                if not isinstance(text, str):
                    continue
                try:
                    response = json.loads(text)
                except json.JSONDecodeError:
                    response = None
                raw.append(
                    {
                        "stream_event_index": event_index,
                        "tool_use_id": item.get("tool_use_id"),
                        "raw_response": response,
                        "raw_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "observation": v8.parse_raw_response(task_id, response),
                    }
                )
    return raw, tool_names


def _inner_mcp_surface_valid(
    command: list[str], condition: str, loomgraph_binary: str | None
) -> bool:
    """Validate the retained inner Claude MCP surface without path-specific assumptions."""
    if "--mcp-config" not in command or "--tools" not in command:
        return False
    try:
        config = json.loads(command[command.index("--mcp-config") + 1])
    except (IndexError, TypeError, json.JSONDecodeError):
        return False
    servers = config.get("mcpServers") if isinstance(config, dict) else None
    if condition == "baseline":
        return (
            servers == {}
            and "--allowedTools" not in command
            and "loomgraph" not in json.dumps(config, sort_keys=True)
        )
    if condition != "treatment" or "--allowedTools" not in command:
        return False
    try:
        allowed = command[command.index("--allowedTools") + 1]
        server = (
            servers.get("loomgraph")
            if isinstance(servers, dict) and set(servers) == {"loomgraph"}
            else None
        )
        env = server.get("env") if isinstance(server, dict) else None
        args = server.get("args") if isinstance(server, dict) else None
        executable = server.get("command") if isinstance(server, dict) else None
    except (IndexError, TypeError):
        return False
    return (
        allowed == orientation.TEMPORAL_MCP_TOOL
        and isinstance(executable, str)
        and executable == loomgraph_binary
        and args == ["mcp", "serve"]
        and isinstance(env, dict)
        and env.get("LOOMGRAPH_MCP_ALLOWED_TOOLS") == orientation.TEMPORAL_SERVER_TOOL
        and set(env).issubset({"LOOMGRAPH_MCP_ALLOWED_TOOLS", "LOOMGRAPH_STORAGE__DB_PATH"})
        and all(isinstance(key, str) and isinstance(value, str) for key, value in env.items())
    )


def _require_complete_root(root: Path) -> dict[str, Any]:
    if (root / "protocol-stop.json").exists():
        raise ValueError("refusing audit: V8 cohort has a protocol-stop record")
    design, result = _read(root / "preregistration.json"), _read(root / "pilot-results.json")
    if not (root / "environment.json").is_file():
        raise ValueError("V8 environment artifact is missing")
    identity = design.get("model_identity")
    if (
        design.get("protocol") != PROTOCOL
        or result.get("protocol") != PROTOCOL
        or design.get("manifest_id") != MANIFEST_ID
        or design.get("surface") != SURFACE
        or design.get("mode") != "voluntary"
        or not isinstance(identity, dict)
    ):
        raise ValueError("refusing non-V8 temporal-review cohort")
    prereg_version = identity.get("claude_version")
    if (
        identity.get("identity_mode") not in {"model-specific", "runtime-specific"}
        or not isinstance(prereg_version, dict)
        or prereg_version.get("return_code") != 0
        or identity.get("model_categories_valid") is not True
        or not _categories_valid(
            identity,
            requested_model=str(identity.get("requested_model", "")),
            identity_mode=str(identity.get("identity_mode", "")),
        )
    ):
        raise ValueError("V8 preregistration identity validity witness is invalid")
    if design.get("model") != identity.get("requested_model"):
        raise ValueError("V8 preregistration requested model does not match design")
    identity_path, stream_path = (
        root / "model-identity-preflight.json",
        root / "model-identity-preflight.stream.jsonl",
    )
    if (
        not identity_path.is_file()
        or not stream_path.is_file()
        or identity.get("identity_path") != identity_path.name
        or identity.get("stream_path") != stream_path.name
        or identity.get("identity_sha256") != hashlib.sha256(identity_path.read_bytes()).hexdigest()
        or identity.get("stream_sha256") != hashlib.sha256(stream_path.read_bytes()).hexdigest()
    ):
        raise ValueError("V8 retained preflight artifact is invalid")
    retained, categories = _read(identity_path), _model_categories(_events(stream_path))
    command = retained.get("command")
    command_sha256 = retained.get("command_sha256")
    command_valid = (
        isinstance(command, list)
        and all(isinstance(item, str) for item in command)
        and isinstance(command_sha256, str)
        and command_sha256
        == hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest()
    )
    if (
        retained.get("protocol") != "temporal-review-v8-model-identity"
        or retained.get("status") != "complete"
        or retained.get("requested_model") != design.get("model")
        or retained.get("identity_mode") != identity.get("identity_mode")
        or retained.get("claude_version") != identity.get("claude_version")
        or not isinstance(retained.get("claude_version"), dict)
        or retained["claude_version"].get("return_code") != 0
        or retained.get("command_sha256") != identity.get("command_sha256")
        or not command_valid
        or retained.get("model_categories_valid") is not True
        or categories.get("model_categories_valid") is not True
        or any(
            retained.get(field) != identity.get(field)
            or categories.get(field) != identity.get(field)
            for field in _IDENTITY_FIELDS
        )
    ):
        raise ValueError(
            "V8 retained preflight validity does not match raw stream and preregistration"
        )
    if orientation.summarize_stream(_events(stream_path)).get("final_result_seen") is not True:
        raise ValueError("V8 retained preflight stream has no final result")
    if design.get("expected_cells") != [
        {"task_id": task, "replicate": rep, "condition": condition}
        for task, rep, condition in expected_cells()
    ]:
        raise ValueError("V8 preregistration cell matrix was changed")
    expected_order = [
        {"task_id": task, "replicate": rep, "condition": arm}
        for task in v8.TASK_IDS
        for rep in (1, 2)
        for arm in (("baseline", "treatment") if rep % 2 else ("treatment", "baseline"))
    ]
    if design.get("execution_order") != expected_order:
        raise ValueError("V8 preregistration execution order was changed")
    if (
        design.get("manifest_sha256") != hashlib.sha256(v8.MANIFEST_PATH.read_bytes()).hexdigest()
        or design.get("selection_preflight_sha256") != v8.selection_preflight_sha256()
    ):
        raise ValueError("V8 frozen selection does not match preregistration")
    runs = result.get("runs")
    if (
        not isinstance(runs, list)
        or {
            (row.get("task_id"), row.get("replicate"), row.get("condition"))
            for row in runs
            if isinstance(row, dict)
        }
        != set(expected_cells())
        or len(runs) != len(expected_cells())
    ):
        raise ValueError("V8 result cell matrix is invalid")
    observed_order = [
        {
            "task_id": row.get("task_id"),
            "replicate": row.get("replicate"),
            "condition": row.get("condition"),
        }
        for row in runs
        if isinstance(row, dict)
    ]
    if observed_order != expected_order:
        raise ValueError("V8 pilot results do not retain preregistered execution order")
    return design


def _audit_cell(root: Path, task_id: str, replicate: int, condition: str) -> dict[str, Any]:
    cell = root / task_id / f"rep-{replicate:02d}" / condition
    required = [
        cell / "driver-run.json",
        cell / "output/orientation.json",
        cell / "output/run.json",
        cell / "output/command.json",
        cell / "output/pre-state.json",
        cell / "output/post-state.json",
        cell / "output/final-result.json",
        cell / "output/claude.stream.jsonl",
    ]
    if any(not path.is_file() for path in required):
        raise ValueError(f"V8 cell lacks immutable artifacts: {cell}")
    driver, packet, run = (_read(path) for path in required[:3])
    command = json.loads(required[3].read_text(encoding="utf-8"))
    pre, post, final = (_read(path) for path in required[4:7])
    design = _read(root / "preregistration.json")
    model = packet.get("model")
    stream = _model_categories(_events(required[-1]))
    identity = design["model_identity"]
    source = Path(str(driver.get("source_dir", "")))
    driver_command = driver.get("runner_command")
    driver_binary = (
        driver_command[driver_command.index("--loomgraph-binary") + 1]
        if isinstance(driver_command, list)
        and "--loomgraph-binary" in driver_command
        and driver_command.index("--loomgraph-binary") + 1 < len(driver_command)
        and isinstance(driver_command[driver_command.index("--loomgraph-binary") + 1], str)
        else None
    )
    inner_command_valid = (
        isinstance(command, list)
        and bool(command)
        and all(isinstance(value, str) for value in command)
        and "--model" in command
        and command[command.index("--model") + 1] == design.get("model")
        and "--strict-mcp-config" in command
        and "--tools" in command
        and "--mcp-config" in command
        and _inner_mcp_surface_valid(command, condition, driver_binary)
    )
    driver_command_valid = (
        isinstance(driver_command, list)
        and all(isinstance(value, str) for value in driver_command)
        and "--model" in driver_command
        and driver_command[driver_command.index("--model") + 1] == design.get("model")
        and "--condition" in driver_command
        and driver_command[driver_command.index("--condition") + 1] == condition
        and "--treatment-surface" in driver_command
        and driver_command[driver_command.index("--treatment-surface") + 1] == SURFACE
        and "--temporal-review-v8-contract" in driver_command
        and isinstance(driver_binary, str)
        and bool(driver_binary)
    )
    command_valid = inner_command_valid and driver_command_valid
    item = v8.contract(task_id)
    driver_contract_valid = (
        driver.get("task_id") == task_id
        and driver.get("replicate") == replicate
        and driver.get("condition") == condition
        and driver.get("manifest_id") == MANIFEST_ID
        and driver.get("contract")
        == {"base_ref": item.base_ref, "head_ref": item.head_ref, "backend": item.backend}
        and isinstance(driver.get("runner_command"), list)
        and "--temporal-review-v8-contract" in driver["runner_command"]
        and SURFACE in driver["runner_command"]
        and driver.get("environment_path") == str((root / "environment.json").resolve())
        and source.resolve() == (cell / "source").resolve()
    )
    events = _events(required[-1])
    stream_payload, final_index = _stream_payload(events)
    final_payload = _payload(final)
    final_payload_matches_stream = _canonical(final_payload) is not None and _canonical(
        final_payload
    ) == _canonical(stream_payload)
    raw, tool_names = _raw_branch_diff(task_id, events)
    before_final = [
        row for row in raw if final_index is not None and row["stream_event_index"] < final_index
    ]
    valid_raw = [row for row in before_final if row["observation"].get("valid") is True]
    selected = valid_raw[-1] if condition == "treatment" and valid_raw else None
    raw_trace_valid = (
        (
            final_index is not None
            and bool(before_final)
            and len(before_final) == len(raw)
            and len(valid_raw) == len(before_final)
        )
        if condition == "treatment"
        else not raw
    )
    forbidden_mcp = [
        name
        for name in tool_names
        if name.startswith("mcp__") and name != orientation.TEMPORAL_MCP_TOOL
    ]
    tool_trace_valid = (
        packet.get("tool_call_count") == len(tool_names)
        and packet.get("tool_call_names") == tool_names
        and not forbidden_mcp
        and (condition == "treatment" or not any(name.startswith("mcp__") for name in tool_names))
    )
    model_valid = (
        isinstance(model, dict)
        and model.get("requested") == identity.get("requested_model")
        and model.get("model_categories_valid") is True
        and all(
            model.get(field) == stream.get(field)
            for field in _IDENTITY_FIELDS
            if field != "model_categories_valid"
        )
        and stream.get("model_categories_valid") is True
        and all(
            stream.get(f"{surface}_models_canonical") == identity.get(f"{surface}_models_canonical")
            for surface in _MODEL_SURFACES
        )
    )
    source_clean = (
        packet.get("source_clean") is True
        and driver.get("source_clean") is True
        and driver.get("source_status_return_code") == 0
        and pre == post
        and post.get("porcelain") == ""
        and source.is_dir()
    )
    identity_valid = driver.get("model_identity_matches_preflight") is True and model_valid
    observed = packet.get("task_review_observation")
    if source_clean:
        semantic_outcome = v8.evaluate_answer(
            task_id,
            final_payload,
            condition=condition,
            source_root=source,
            raw_response=selected["raw_response"] if selected else None,
        )
        semantic = {"passed": semantic_outcome.passed, "failures": list(semantic_outcome.failures)}
    else:
        semantic = {"passed": False, "failures": ["source_checkout_missing_or_dirty"]}
    semantic_matches = isinstance(observed, dict) and observed == semantic
    trust = packet.get("trust_observation")
    certificate = trust.get("selected_certificate") if isinstance(trust, dict) else None
    certificate_matches = (
        (
            isinstance(certificate, dict)
            and selected is not None
            and certificate.get("selected_raw_event_index") == selected["stream_event_index"]
            and certificate.get("tool_use_id") == selected["tool_use_id"]
            and certificate.get("raw_sha256") == selected["raw_sha256"]
            and certificate.get("comparison") == selected["observation"].get("comparison")
        )
        if condition == "treatment"
        else certificate is None
    )
    warm = driver.get("warm_repeat")
    warm_valid = condition == "baseline"
    if condition == "treatment" and selected is not None and isinstance(warm, dict):
        warm_path = warm.get("raw_response_path")
        if isinstance(warm_path, str) and Path(warm_path).is_file():
            try:
                warm_response = json.loads(Path(warm_path).read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                warm_response = None
            warm_observation = v8.parse_raw_response(task_id, warm_response)
            comparison = warm_observation.get("comparison")
            warm_valid = (
                warm.get("return_code") == 0
                and Path(warm_path).resolve().is_relative_to(cell.resolve())
                and warm.get("parsed_raw_observation") == warm_observation
                and isinstance(comparison, dict)
                and comparison.get("base_provisioned") == "reused"
                and comparison.get("head_provisioned") == "reused"
            )
    valid = (
        packet.get("protocol") == SURFACE
        and packet.get("status") == "complete"
        and run.get("return_code") == 0
        and driver.get("runner_return_code") == 0
        and source_clean
        and identity_valid
        and driver_contract_valid
        and command_valid
        and raw_trace_valid
        and tool_trace_valid
        and final_payload_matches_stream
        and semantic["passed"] is True
        and semantic_matches
        and certificate_matches
        and warm_valid
    )
    return {
        "task_id": task_id,
        "replicate": replicate,
        "condition": condition,
        "status": "valid" if valid else "excluded",
        "source_clean": source_clean,
        "driver_contract_valid": driver_contract_valid,
        "command_valid": command_valid,
        "inner_command_valid": inner_command_valid,
        "driver_command_valid": driver_command_valid,
        "raw_mcp": {
            "count": len(raw),
            "valid_count": len(valid_raw),
            "selected": selected,
            "raw_trace_valid": raw_trace_valid,
        },
        "tool_trace": {
            "count": len(tool_names),
            "names": tool_names,
            "valid": tool_trace_valid,
            "forbidden_mcp": forbidden_mcp,
            "count_is_reporting_only": True,
        },
        "final_payload_matches_stream": final_payload_matches_stream,
        "semantic": semantic,
        "semantic_replay_matches_orientation": semantic_matches,
        "certificate_matches_rebuild": certificate_matches,
        "warm_valid": warm_valid,
        "model_identity_valid": identity_valid,
        "model_identity_raw_categories_match_stream": isinstance(model, dict)
        and all(model.get(field) == stream.get(field) for field in _IDENTITY_FIELDS),
        "exclusion_reason": None
        if valid
        else packet.get("invalid_reason") or "audit_replay_mismatch",
    }


def _expansion_gate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """May request, but never starts, a separately approved 72-run cohort."""
    pairs_by_task: dict[str, list[bool]] = {task: [] for task in v8.TASK_IDS}
    by_cell = {(row["task_id"], row["replicate"], row["condition"]): row for row in records}
    for task in v8.TASK_IDS:
        for replicate in (1, 2):
            baseline = by_cell.get((task, replicate, "baseline"))
            treatment = by_cell.get((task, replicate, "treatment"))
            if baseline is not None and treatment is not None:
                pairs_by_task[task].append(
                    baseline.get("status") == "valid" and treatment.get("status") == "valid"
                )
    complete_by_task = {task: sum(rows) for task, rows in pairs_by_task.items()}
    complete_count = sum(complete_by_task.values())
    ast_failure_count = sum(
        "review locus does not resolve in frozen head AST"
        in row.get("semantic", {}).get("failures", [])
        for row in records
    )
    structural_failure_count = sum(
        any(
            failure in {"answer top-level fields are invalid", "review locus fields are invalid"}
            for failure in row.get("semantic", {}).get("failures", [])
        )
        for row in records
    )
    semantic_mismatch_count = sum(
        row.get("semantic_replay_matches_orientation") is False for row in records
    )
    payload_mismatch_count = sum(
        row.get("final_payload_matches_stream") is False for row in records
    )
    identity_mismatch_count = sum(
        row.get("model_identity_valid") is not True
        or row.get("model_identity_raw_categories_match_stream") is not True
        for row in records
    )
    eligible = (
        len(records) == len(expected_cells())
        and complete_count >= 3
        and all(count >= 1 for count in complete_by_task.values())
        and ast_failure_count == 0
        and structural_failure_count == 0
        and semantic_mismatch_count == 0
        and payload_mismatch_count == 0
        and identity_mismatch_count == 0
    )
    return {
        "no_protocol_stop": True,
        "complete_valid_pair_count": complete_count,
        "complete_valid_pairs_by_task": complete_by_task,
        "ast_unresolvable_exclusion_count": ast_failure_count,
        "multiple_or_extra_structure_exclusion_count": structural_failure_count,
        "semantic_replay_mismatch_count": semantic_mismatch_count,
        "final_payload_stream_mismatch_count": payload_mismatch_count,
        "model_identity_integrity_mismatch_count": identity_mismatch_count,
        "eligible_to_request_72_run": eligible,
        "automatic_expansion_authorized": False,
        "next_action": "request_explicit_user_approval_for_72_run"
        if eligible
        else "do_not_request_72_run",
    }


def audit_pilot(output_root: Path) -> dict[str, object]:
    root = output_root.resolve()
    _require_complete_root(root)
    expected_paths = {
        Path(task) / f"rep-{replicate:02d}" / condition
        for task, replicate, condition in expected_cells()
    }
    observed_paths = {path.parent.relative_to(root) for path in root.glob("*/*/*/driver-run.json")}
    if observed_paths != expected_paths:
        raise ValueError("V8 discovered cell artifacts do not exactly equal preregistration")
    rows = [_audit_cell(root, task, rep, condition) for task, rep, condition in expected_cells()]
    return {
        "schema_version": 1,
        "protocol": AUDIT_PROTOCOL,
        "source_protocol": PROTOCOL,
        "records": rows,
        "expansion_gate": _expansion_gate(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_pilot(args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
