#!/usr/bin/env python3
"""Run one read-only Claude Code orientation condition with durable artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

BASELINE_TOOLS = "Read,Glob,Grep"
TOOL_CALL_BUDGET = 5
LOOMGRAPH_TOOLS = [
    "mcp__loomgraph__loomgraph_find",
    "mcp__loomgraph__loomgraph_graph",
]
ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "evidence"],
                "properties": {
                    "path": {"type": "string"},
                    "evidence": {"type": "string"},
                },
            },
        }
    },
}


def _compact_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def build_command(
    *,
    condition: str,
    instruction: str,
    model: str,
    budget_usd: str,
    loomgraph_binary: str,
) -> list[str]:
    """Build an isolated Claude invocation for exactly one condition."""
    command = [
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
        "local",
        "--disable-slash-commands",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--max-budget-usd",
        budget_usd,
        "--json-schema",
        _compact_json(ORIENTATION_SCHEMA),
        "--strict-mcp-config",
    ]
    if condition == "baseline":
        command.extend(
            ["--tools", BASELINE_TOOLS, "--mcp-config", _compact_json({"mcpServers": {}})]
        )
    elif condition == "treatment":
        command.extend(
            [
                "--tools",
                "",
                "--mcp-config",
                _compact_json(
                    {
                        "mcpServers": {
                            "loomgraph": {
                                "command": loomgraph_binary,
                                "args": ["mcp", "serve"],
                            }
                        }
                    }
                ),
                "--allowedTools",
                ",".join(LOOMGRAPH_TOOLS),
            ]
        )
    else:
        raise ValueError(f"unknown condition: {condition}")
    # --allowedTools consumes a variable number of values. The separator keeps
    # the actual task instruction out of that option in the treatment arm.
    command.extend(["--", instruction])
    return command


def summarize_stream(events: list[dict[str, Any]]) -> dict[str, object]:
    """Extract the final schema payload and observed native LoomGraph calls."""
    tool_names: list[str] = []
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name = item.get("name")
            if isinstance(name, str):
                tool_names.append(name)

    payload: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None
    final_result_seen = False
    for event in reversed(events):
        if event.get("type") != "result":
            continue
        final_result_seen = True
        if final_result is None:
            final_result = event
        structured = event.get("structured_output")
        if isinstance(structured, dict):
            payload = structured
            break
        result = event.get("result")
        if not isinstance(result, str):
            continue
        try:
            decoded = json.loads(result)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            payload = decoded
            break

    return {
        "final_result_seen": final_result_seen,
        "final_result": final_result,
        "payload": payload,
        "tool_names": tool_names,
        "loomgraph_tools": [name for name in tool_names if name in LOOMGRAPH_TOOLS],
    }


def _valid_payload(payload: object) -> bool:
    if not isinstance(payload, dict) or set(payload) != {"candidates"}:
        return False
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 5:
        return False
    return all(
        isinstance(candidate, dict)
        and set(candidate) == {"path", "evidence"}
        and isinstance(candidate["path"], str)
        and bool(candidate["path"])
        and isinstance(candidate["evidence"], str)
        and bool(candidate["evidence"])
        for candidate in candidates
    )


def build_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    return_code: int,
    summary: dict[str, object],
) -> dict[str, Any]:
    """Make source cleanliness dominate a syntactically valid agent response."""
    payload = summary.get("payload")
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    loomgraph_tools = summary.get("loomgraph_tools")
    if not isinstance(loomgraph_tools, list) or not all(
        isinstance(name, str) for name in loomgraph_tools
    ):
        loomgraph_tools = []
    if not source_clean:
        status = "invalid_source_mutation"
    elif return_code != 0:
        status = "agent_error"
    elif summary.get("final_result_seen") is not True or not _valid_payload(payload):
        status = "missing_or_invalid_agent_response"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "status": status,
        "condition": condition,
        "orientation_mode": use_mode,
        "pre_edit": source_clean,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "candidates": payload.get("candidates", []) if isinstance(payload, dict) else [],
        "tool_call_count": len(tool_names),
        "tool_call_budget": TOOL_CALL_BUDGET,
        "tool_call_budget_overrun": len(tool_names) > TOOL_CALL_BUDGET,
        "tooling": {
            "loomgraph": {
                "used": bool(loomgraph_tools),
                "tools": loomgraph_tools,
            }
        },
    }


def _repo_state(source_dir: Path) -> dict[str, str]:
    """Read only the Git fields that define a source-clean model phase."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    porcelain = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {"head": head, "porcelain": porcelain}


def _append_mode_requirement(instruction: str, use_mode: str) -> str:
    if use_mode == "voluntary":
        return instruction
    if use_mode == "assisted":
        return f"{instruction}\n\nUse at least one available navigation tool before responding."
    raise ValueError(f"unknown use mode: {use_mode}")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(args: argparse.Namespace) -> int:
    source_dir = args.source_dir.resolve()
    if not source_dir.is_dir():
        raise ValueError(f"source directory does not exist: {source_dir}")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    before = _repo_state(source_dir)
    if before["porcelain"]:
        raise ValueError("source directory must be clean before the model phase")

    instruction = _append_mode_requirement(args.instruction_file.read_text(), args.use_mode)
    command = build_command(
        condition=args.condition,
        instruction=instruction,
        model=args.model,
        budget_usd=args.max_budget_usd,
        loomgraph_binary=args.loomgraph_binary,
    )
    _write_json(output_dir / "command.json", command)

    events: list[dict[str, Any]] = []
    with (output_dir / "claude.stream.jsonl").open("w") as stream:
        process = subprocess.Popen(
            command,
            cwd=source_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            stream.write(line)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return_code = process.wait()

    after = _repo_state(source_dir)
    source_clean = before == after and not after["porcelain"]
    summary = summarize_stream(events)
    packet = build_packet(
        condition=args.condition,
        use_mode=args.use_mode,
        source_clean=source_clean,
        return_code=return_code,
        summary=summary,
    )
    _write_json(output_dir / "pre-state.json", before)
    _write_json(output_dir / "post-state.json", after)
    _write_json(output_dir / "final-result.json", summary["final_result"])
    _write_json(output_dir / "orientation.json", packet)
    _write_json(
        output_dir / "run.json",
        {
            "return_code": return_code,
            "final_result_seen": summary["final_result_seen"],
            "task_id": args.task_id,
        },
    )
    print(json.dumps(packet, sort_keys=True))
    return 0 if packet["status"] == "complete" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=("baseline", "treatment"), required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--instruction-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--use-mode", choices=("voluntary", "assisted"), default="voluntary")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-budget-usd", default="0.50")
    parser.add_argument("--loomgraph-binary", default="loomgraph")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
