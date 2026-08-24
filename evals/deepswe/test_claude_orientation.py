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
    assert _argument(command, "--setting-sources") == "project,local"
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
            "loomgraph": {
                "command": "/tmp/loomgraph",
                "args": ["mcp", "serve"],
                "env": {"LOOMGRAPH_MCP_ALLOWED_TOOLS": "loomgraph_find,loomgraph_graph"},
            }
        }
    }
    assert _argument(command, "--allowedTools") == (
        "mcp__loomgraph__loomgraph_find,mcp__loomgraph__loomgraph_graph"
    )
    assert command[-2:] == ["--", "orient"]


def test_additive_treatment_keeps_text_navigation_and_mcp_allowlist() -> None:
    command = _MODULE.build_command(
        condition="treatment",
        instruction="orient",
        model="sonnet",
        budget_usd="0.50",
        loomgraph_binary="/tmp/loomgraph",
        treatment_surface="additive",
    )

    assert _argument(command, "--tools") == "Read,Glob,Grep"
    assert json.loads(_argument(command, "--mcp-config"))["mcpServers"]["loomgraph"]["env"] == {
        "LOOMGRAPH_MCP_ALLOWED_TOOLS": "loomgraph_find,loomgraph_graph"
    }


def test_trust_required_command_exposes_the_trust_output_contract() -> None:
    command = _MODULE.build_command(
        condition="treatment",
        instruction="orient",
        model="sonnet",
        budget_usd="0.50",
        loomgraph_binary="/tmp/loomgraph",
        require_trust=True,
    )

    schema = json.loads(_argument(command, "--json-schema"))
    assert schema["required"] == ["candidates", "trust"]
    assert schema["properties"]["trust"]["required"] == [
        "availability",
        "edge_trust",
        "resolution",
    ]
    assert schema["properties"]["trust"]["properties"]["resolution"]["required"] == [
        "resolved_ratio",
        "internal_unresolved_ratio",
        "external_unresolved_ratio",
    ]


def test_normalizes_source_absolute_candidate_paths_to_repo_relative() -> None:
    payload = {
        "candidates": [
            {"path": "/tmp/source/vulture/core.py", "evidence": "caller"},
            {"path": "vulture/utils.py", "evidence": "utility"},
        ]
    }

    assert _MODULE.normalize_candidate_paths(payload, Path("/tmp/source")) == {
        "candidates": [
            {"path": "vulture/core.py", "evidence": "caller"},
            {"path": "vulture/utils.py", "evidence": "utility"},
        ]
    }


def test_rejects_candidate_path_outside_the_source_root() -> None:
    payload = {"candidates": [{"path": "/tmp/other/secrets.py", "evidence": "outside"}]}

    assert _MODULE.normalize_candidate_paths(payload, Path("/tmp/source")) is None


def test_stream_summary_reads_structured_result_and_observed_mcp_calls() -> None:
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "find-1",
                        "name": "mcp__loomgraph__loomgraph_find",
                        "input": {"query": "Layer"},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "find-1",
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "success": True,
                                        "data": {"matches": [{"entity": "Layer"}]},
                                    }
                                ),
                            }
                        ],
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
    assert summary["structural_retrievals"] == [
        {"tool": "mcp__loomgraph__loomgraph_find", "evidence": "find_matches"}
    ]


def test_stream_summary_separates_assistant_models_from_session_and_usage_telemetry() -> None:
    summary = _MODULE.summarize_stream(
        [
            {"type": "system", "subtype": "init", "model": "glm-5.2[1M]"},
            {"type": "assistant", "message": {"model": "glm-5.3", "content": []}},
            {
                "type": "result",
                "modelUsage": {"glm-4.7": {}, "glm-5.2[1M]": {}},
                "structured_output": {
                    "candidates": [{"path": "src/x.py", "evidence": "x"}]
                },
            },
        ]
    )

    assert summary["assistant_models"] == ["glm-5.3"]
    assert summary["session_models"] == ["glm-5.2[1M]"]
    assert summary["usage_models"] == ["glm-4.7", "glm-5.2[1M]"]
    assert summary["observed_models"] == ["glm-5.2[1M]", "glm-5.3", "glm-4.7"]


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


def test_trust_required_packet_rejects_a_response_without_trust() -> None:
    packet = _MODULE.build_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {"candidates": [{"path": "src/x.py", "evidence": "x"}]},
        },
        require_trust=True,
    )

    assert packet["status"] == "missing_or_invalid_agent_response"


def test_trust_required_packet_records_a_complete_trust_response() -> None:
    trust = {
        "availability": "available",
        "edge_trust": "resolved-only; unresolved edges omitted",
        "resolution": {
            "resolved_ratio": 0.2,
            "internal_unresolved_ratio": 0.3,
            "external_unresolved_ratio": 0.4,
        },
    }
    packet = _MODULE.build_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {
                "candidates": [{"path": "src/x.py", "evidence": "x"}],
                "trust": trust,
            },
        },
        require_trust=True,
    )

    assert packet["status"] == "complete"
    assert packet["trust"] == trust


def test_trust_required_packet_allows_an_explicit_unavailable_control() -> None:
    trust = {
        "availability": "unavailable",
        "edge_trust": "No graph-resolution evidence is available in this condition.",
        "resolution": {
            "resolved_ratio": None,
            "internal_unresolved_ratio": None,
            "external_unresolved_ratio": None,
        },
    }
    packet = _MODULE.build_packet(
        condition="baseline",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {
                "candidates": [{"path": "src/x.py", "evidence": "x"}],
                "trust": trust,
            },
        },
        require_trust=True,
    )

    assert packet["status"] == "complete"
    assert packet["trust"] == trust


def test_trust_required_treatment_rejects_unavailable_graph_evidence() -> None:
    packet = _MODULE.build_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {
                "candidates": [{"path": "src/x.py", "evidence": "x"}],
                "trust": {
                    "availability": "unavailable",
                    "edge_trust": "The graph was not queried for trust.",
                    "resolution": {
                        "resolved_ratio": None,
                        "internal_unresolved_ratio": None,
                        "external_unresolved_ratio": None,
                    },
                },
            },
        },
        require_trust=True,
    )

    assert packet["status"] == "missing_treatment_trust_evidence"


def test_packet_records_the_shared_tool_call_budget() -> None:
    packet = _MODULE.build_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {"candidates": [{"path": "src/x.py", "evidence": "x"}]},
            "tool_names": ["mcp__loomgraph__loomgraph_find"] * 6,
            "loomgraph_tools": ["mcp__loomgraph__loomgraph_find"] * 6,
        },
    )

    assert packet["tool_call_budget"] == 5
    assert packet["tool_call_budget_overrun"] is True
    assert packet["status"] == "tool_call_budget_exceeded"


def test_packet_records_raw_agent_execution_seconds() -> None:
    packet = _MODULE.build_packet(
        condition="baseline",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {"candidates": [{"path": "src/x.py", "evidence": "x"}]},
        },
        agent_execution_seconds=12.5,
    )

    assert packet["agent_execution_seconds"] == 12.5


def test_assisted_instruction_reserves_a_slot_for_structured_output() -> None:
    instruction = _MODULE._append_mode_requirement("orient", "assisted")

    assert "at least one available navigation tool" in instruction
    assert "at most 4 navigation tool calls" in instruction


def test_assisted_treatment_requires_successful_structural_retrieval() -> None:
    packet = _MODULE.build_packet(
        condition="treatment",
        use_mode="assisted",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {"candidates": [{"path": "src/x.py", "evidence": "x"}]},
            "loomgraph_tools": ["mcp__loomgraph__loomgraph_find"],
            "structural_retrievals": [],
        },
        requested_model="sonnet",
    )

    assert packet["status"] == "missing_assisted_structural_retrieval"


def test_packet_records_observed_model_identity_without_claiming_an_alias() -> None:
    packet = _MODULE.build_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {"candidates": [{"path": "src/x.py", "evidence": "x"}]},
            "observed_models": ["glm-5.2[1M]", "glm-5.3"],
            "assistant_models": ["glm-5.3"],
            "session_models": ["glm-5.2[1M]"],
            "usage_models": ["glm-4.7", "glm-5.2[1M]"],
        },
        requested_model="sonnet",
    )

    assert packet["model"] == {
        "requested": "sonnet",
        "observed": ["glm-5.2[1M]", "glm-5.3"],
        "assistant_observed": ["glm-5.3"],
        "session_observed": ["glm-5.2[1M]"],
        "usage_observed": ["glm-4.7", "glm-5.2[1M]"],
    }


def test_packet_labels_additive_navigation_surface() -> None:
    packet = _MODULE.build_packet(
        condition="treatment",
        use_mode="assisted",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": {"candidates": [{"path": "src/x.py", "evidence": "x"}]},
            "structural_retrievals": [
                {"tool": "mcp__loomgraph__loomgraph_find", "evidence": "find_matches"}
            ],
        },
        requested_model="sonnet",
        navigation_surface="additive",
    )

    assert packet["navigation_surface"] == "additive"
