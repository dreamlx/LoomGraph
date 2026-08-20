"""Contract tests for the Claude Code orientation runner."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_MODULE_PATH = Path(__file__).with_name("claude_orientation.py")
_SPEC = importlib.util.spec_from_file_location("claude_orientation", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _argument(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


def test_baseline_command_exposes_only_text_navigation_tools() -> None:
    command = _MODULE.build_command(
        condition="baseline",
        instruction="orient",
        model="sonnet",
        budget_usd="0.50",
        loomgraph_binary="loomgraph",
    )

    assert _argument(command, "--tools") == "Read,Glob,Grep"
    assert json.loads(_argument(command, "--mcp-config")) == {"mcpServers": {}}
    assert "--allowedTools" not in command


def test_treatment_command_exposes_only_native_loomgraph_tools() -> None:
    command = _MODULE.build_command(
        condition="treatment",
        instruction="orient",
        model="sonnet",
        budget_usd="0.50",
        loomgraph_binary="/tmp/loomgraph",
    )

    assert _argument(command, "--tools") == ""
    assert json.loads(_argument(command, "--mcp-config")) == {
        "mcpServers": {
            "loomgraph": {"command": "/tmp/loomgraph", "args": ["mcp", "serve"]}
        }
    }
    assert _argument(command, "--allowedTools") == (
        "mcp__loomgraph__loomgraph_find,mcp__loomgraph__loomgraph_graph"
    )
    assert command[-2:] == ["--", "orient"]


def test_stream_summary_reads_structured_result_and_observed_mcp_calls() -> None:
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "mcp__loomgraph__loomgraph_find",
                        "input": {"query": "Layer"},
                    }
                ]
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "structured_output": {
                "candidates": [{"path": "src/layers.py", "evidence": "Layer API"}]
            },
        },
    ]

    summary = _MODULE.summarize_stream(events)

    assert summary["final_result_seen"] is True
    assert summary["payload"] == {
        "candidates": [{"path": "src/layers.py", "evidence": "Layer API"}]
    }
    assert summary["final_result"] == events[-1]
    assert summary["loomgraph_tools"] == ["mcp__loomgraph__loomgraph_find"]


def test_stream_summary_accepts_json_result_fallback() -> None:
    summary = _MODULE.summarize_stream(
        [
            {
                "type": "result",
                "subtype": "success",
                "result": '{"candidates":[{"path":"src/x.py","evidence":"x"}]}',
            }
        ]
    )

    assert summary["payload"]["candidates"][0]["path"] == "src/x.py"


def test_packet_marks_source_mutation_invalid_even_with_valid_payload() -> None:
    packet = _MODULE.build_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=False,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {"candidates": [{"path": "src/x.py", "evidence": "x"}]},
            "loomgraph_tools": ["mcp__loomgraph__loomgraph_graph"],
        },
    )

    assert packet["status"] == "invalid_source_mutation"
    assert packet["pre_edit"] is False
    assert packet["tooling"]["loomgraph"]["used"] is True


def test_packet_rejects_malformed_schema_payload() -> None:
    packet = _MODULE.build_packet(
        condition="baseline",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={"final_result_seen": True, "payload": {"candidates": [{"path": "src/x.py"}]}, "loomgraph_tools": []},
    )

    assert packet["status"] == "missing_or_invalid_agent_response"
