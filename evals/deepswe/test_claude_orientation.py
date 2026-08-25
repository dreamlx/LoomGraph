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


def test_additive_treatment_storage_is_adapter_owned() -> None:
    command = _MODULE.build_command(
        condition="treatment",
        instruction="orient",
        model="sonnet",
        budget_usd="0.50",
        loomgraph_binary="/tmp/loomgraph",
        treatment_surface="additive",
        storage_root=Path("/tmp/run/loomgraph-storage"),
    )

    env = json.loads(_argument(command, "--mcp-config"))["mcpServers"]["loomgraph"]["env"]
    assert env["LOOMGRAPH_STORAGE__DB_PATH"] == "/tmp/run/loomgraph-storage/{workspace}.db"


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


def test_scores_known_fixture_path_oracle_without_changing_packet_validity() -> None:
    observation = _MODULE.score_agent_use_fixture(
        "vulture-reachability-condition-impact",
        [
            {"path": "vulture/utils.py", "evidence": "utility"},
            {"path": "vulture/core.py", "evidence": "handoff"},
        ],
    )

    assert observation == {
        "id": "vulture-reachability-condition-impact",
        "task_class": "trust-adversary-dynamic-receiver",
        "rg_equivalent_single_query": False,
        "path_oracle": {
            "expected_paths": [
                "vulture/utils.py",
                "vulture/reachability.py",
                "vulture/core.py",
            ],
            "candidate_paths": ["vulture/utils.py", "vulture/core.py"],
            "matched_paths": ["vulture/utils.py", "vulture/core.py"],
            "missing_paths": ["vulture/reachability.py"],
            "unexpected_paths": [],
            "path_recall": 2 / 3,
            "exact_path_set": False,
        },
    }


def test_does_not_score_an_unknown_agent_use_task() -> None:
    assert _MODULE.score_agent_use_fixture("unknown-task", []) is None


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


def test_stream_summary_records_resolution_from_successful_graph_result() -> None:
    resolution = {
        "resolved_ratio": 0.2,
        "internal_unresolved_ratio": 0.3,
        "external_unresolved_ratio": 0.4,
    }
    summary = _MODULE.summarize_stream(
        [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "graph-1",
                            "name": "mcp__loomgraph__loomgraph_graph",
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
                            "tool_use_id": "graph-1",
                            "content": json.dumps(
                                {"success": True, "data": {"source_id": "src/x.py:1", "resolution": resolution}}
                            ),
                        }
                    ]
                },
            },
        ]
    )

    assert summary["graph_resolutions"] == [resolution]


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
            "graph_resolutions": [trust["resolution"]],
        },
        require_trust=True,
    )

    assert packet["status"] == "complete"
    assert packet["trust"] == trust
    assert packet["trust_observation"]["treatment_resolution_matches_graph"] is True


def test_trust_required_treatment_rejects_resolution_not_returned_by_graph() -> None:
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
                    "availability": "available",
                    "edge_trust": "graph evidence",
                    "resolution": {
                        "resolved_ratio": 0.2,
                        "internal_unresolved_ratio": 0.3,
                        "external_unresolved_ratio": 0.4,
                    },
                },
            },
            "graph_resolutions": [
                {
                    "resolved_ratio": 0.1,
                    "internal_unresolved_ratio": 0.3,
                    "external_unresolved_ratio": 0.4,
                }
            ],
        },
        require_trust=True,
    )

    assert packet["status"] == "unverified_treatment_trust_resolution"
    assert packet["trust_observation"]["treatment_resolution_matches_graph"] is False


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


def _temporal_raw_response(
    *,
    success: bool = True,
    base_ref: str = "base",
    head_ref: str = "head",
    base_backend: str = "codeindex",
    head_backend: str = "codeindex",
    base_provisioned: str = "created",
    head_provisioned: str = "reused",
    content_status: str = "available",
) -> dict[str, object]:
    return {
        "success": success,
        "data": {
            "base": {
                "ref": base_ref,
                "sha": "base-sha",
                "workspace": "fixture:base",
                "provisioned": base_provisioned,
            },
            "head": {
                "ref": head_ref,
                "sha": "head-sha",
                "workspace": "fixture:head",
                "provisioned": head_provisioned,
            },
            "diff": {
                "broken_chains": [
                    {
                        "src": "app.handlers.keep_legacy",
                        "tgt": "app.auth.legacy_token",
                        "keywords": "CALLS",
                    }
                ],
                "content_comparison": {
                    "status": content_status,
                    "reason": None if content_status == "available" else "unavailable",
                    "base_backend": base_backend,
                    "head_backend": head_backend,
                },
            },
            "duration_seconds": 0.42,
        },
    }


def _temporal_payload(*, availability: str = "available") -> dict[str, object]:
    comparison = (
        {
            "base_ref": "base",
            "head_ref": "head",
            "base_backend": "codeindex",
            "head_backend": "codeindex",
            "base_provisioned": "created",
            "head_provisioned": "reused",
            "content_comparison": {"status": "available", "reason": None},
        }
        if availability == "available"
        else None
    )
    return {
        "findings": [
            {
                "kind": "broken_chain",
                "src": "app.handlers.keep_legacy",
                "tgt": "app.auth.legacy_token",
                "relation": "CALLS",
                "evidence": "raw branch diff",
            }
        ],
        "trust": {"availability": availability, "comparison": comparison},
    }


def test_temporal_additive_command_allows_only_branch_diff() -> None:
    command = _MODULE.build_command(
        condition="treatment",
        instruction="compare base and head",
        model="sonnet",
        budget_usd="0.50",
        loomgraph_binary="/tmp/loomgraph",
        treatment_surface="temporal-additive",
    )

    assert _argument(command, "--tools") == "Read,Glob,Grep"
    assert _argument(command, "--allowedTools") == (
        "mcp__loomgraph__loomgraph_branch_diff"
    )
    config = json.loads(_argument(command, "--mcp-config"))
    assert config["mcpServers"]["loomgraph"]["env"] == {
        "LOOMGRAPH_MCP_ALLOWED_TOOLS": "loomgraph_branch_diff"
    }
    schema = json.loads(_argument(command, "--json-schema"))
    assert schema["required"] == ["findings", "trust"]
    assert "candidates" not in schema["properties"]


def test_temporal_command_keeps_snapshot_storage_adapter_owned() -> None:
    command = _MODULE.build_command(
        condition="treatment",
        instruction="compare base and head",
        model="sonnet",
        budget_usd="0.50",
        loomgraph_binary="/tmp/loomgraph",
        treatment_surface="temporal-additive",
        storage_root=Path("/tmp/v2-run/loomgraph-storage"),
    )

    env = json.loads(_argument(command, "--mcp-config"))["mcpServers"]["loomgraph"]["env"]
    assert env["LOOMGRAPH_STORAGE__DB_PATH"] == "/tmp/v2-run/loomgraph-storage/{workspace}.db"


def test_temporal_instruction_requires_raw_field_fidelity_in_each_arm() -> None:
    baseline = _MODULE._append_temporal_protocol_requirement("compare", "baseline")
    treatment = _MODULE._append_temporal_protocol_requirement("compare", "treatment")

    assert "availability to unavailable" in baseline
    assert "comparison to null" in baseline
    assert "copy the returned ref, backend, and provisioning fields exactly" in treatment
    assert "raw comparison may omit reason" in treatment
    assert "adapter-normalized absence as null" in treatment


def test_temporal_raw_parser_accepts_successful_codeindex_comparison() -> None:
    parsed = _MODULE.parse_temporal_branch_diff_response(_temporal_raw_response())

    assert parsed["valid"] is True
    assert parsed["reason"] is None
    assert parsed["comparison"] == {
        "base_ref": "base",
        "head_ref": "head",
        "base_sha": "base-sha",
        "head_sha": "head-sha",
        "base_workspace": "fixture:base",
        "head_workspace": "fixture:head",
        "base_backend": "codeindex",
        "head_backend": "codeindex",
        "base_provisioned": "created",
        "head_provisioned": "reused",
        "content_comparison": {"status": "available", "reason": None},
    }


def test_temporal_raw_parser_normalizes_an_omitted_available_reason() -> None:
    raw = _temporal_raw_response()
    del raw["data"]["diff"]["content_comparison"]["reason"]

    parsed = _MODULE.parse_temporal_branch_diff_response(raw)

    assert parsed["valid"] is True
    assert parsed["comparison"]["content_comparison"] == {
        "status": "available",
        "reason": None,
    }


def test_temporal_raw_parser_rejects_failed_envelope_with_explicit_reason() -> None:
    parsed = _MODULE.parse_temporal_branch_diff_response(
        {"success": False, "error": {"code": "BRANCH_DIFF_FAILED"}}
    )

    assert parsed == {"valid": False, "reason": "raw_response_not_success"}


def test_temporal_raw_parser_rejects_ref_backend_and_provisioning_mismatches() -> None:
    assert _MODULE.parse_temporal_branch_diff_response(
        _temporal_raw_response(base_ref="main")
    )["reason"] == "base_ref_mismatch"
    assert _MODULE.parse_temporal_branch_diff_response(
        _temporal_raw_response(head_backend="codegraph")
    )["reason"] == "head_backend_mismatch"
    assert _MODULE.parse_temporal_branch_diff_response(
        _temporal_raw_response(base_provisioned="invalid")
    )["reason"] == "base_provisioning_invalid"


def test_temporal_raw_parser_rejects_unavailable_content_comparison() -> None:
    parsed = _MODULE.parse_temporal_branch_diff_response(
        _temporal_raw_response(content_status="unavailable")
    )

    assert parsed["valid"] is False
    assert parsed["reason"] == "content_comparison_not_available"


def test_temporal_raw_parser_rejects_a_fabricated_available_reason() -> None:
    raw = _temporal_raw_response()
    raw["data"]["diff"]["content_comparison"]["reason"] = "model prose"

    assert _MODULE.parse_temporal_branch_diff_response(raw)["reason"] == (
        "content_comparison_reason_mismatch"
    )


def test_temporal_stream_summary_retains_raw_branch_diff_response() -> None:
    raw = _temporal_raw_response()
    summary = _MODULE.summarize_stream(
        [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "branch-1",
                            "name": "mcp__loomgraph__loomgraph_branch_diff",
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
                            "tool_use_id": "branch-1",
                            "content": [{"type": "text", "text": json.dumps(raw)}],
                        }
                    ]
                },
            },
        ],
        treatment_surface="temporal-additive",
    )

    assert summary["loomgraph_tools"] == [
        "mcp__loomgraph__loomgraph_branch_diff"
    ]
    assert summary["unexpected_mcp_tools"] == []
    assert summary["raw_branch_diff_responses"] == [raw]
    assert summary["temporal_branch_diff_observations"][0]["valid"] is True


def test_temporal_packet_accepts_raw_aligned_available_trust() -> None:
    raw = _temporal_raw_response()
    packet = _MODULE.build_temporal_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": _temporal_payload(),
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"],
            "loomgraph_tools": ["mcp__loomgraph__loomgraph_branch_diff"],
            "raw_branch_diff_responses": [raw],
            "temporal_branch_diff_observations": [
                _MODULE.parse_temporal_branch_diff_response(raw)
            ],
        },
    )

    assert packet["status"] == "complete"
    assert packet["schema_version"] == 2
    assert packet["findings"] == _temporal_payload()["findings"]
    assert packet["trust_observation"]["raw_comparison_aligned"] is True
    assert "path_oracle" not in packet
    assert "graph_resolutions" not in packet


def test_temporal_packet_rejects_model_raw_comparison_mismatch() -> None:
    payload = _temporal_payload()
    payload["trust"]["comparison"]["head_ref"] = "other"
    raw = _temporal_raw_response()
    packet = _MODULE.build_temporal_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": payload,
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"],
            "loomgraph_tools": ["mcp__loomgraph__loomgraph_branch_diff"],
            "raw_branch_diff_responses": [raw],
            "temporal_branch_diff_observations": [
                _MODULE.parse_temporal_branch_diff_response(raw)
            ],
        },
    )

    assert packet["status"] == "unverified_treatment_comparison_trust"
    assert packet["invalid_reason"] == "model_raw_comparison_mismatch"


def _temporal_review_raw_response(
    contract: object, *, content_status: str, content_reason: object
) -> dict[str, object]:
    refs = contract.refs
    return {
        "success": True,
        "data": {
            "base": {
                "ref": contract.base_ref,
                "sha": refs["base"]["commit_sha"],
                "workspace": "review:base",
                "provisioned": "created",
            },
            "head": {
                "ref": contract.head_ref,
                "sha": refs["head"]["commit_sha"],
                "workspace": "review:head",
                "provisioned": "reused",
            },
            "diff": {
                "broken_chains": [],
                "content_comparison": {
                    "status": content_status,
                    "reason": content_reason,
                    "base_backend": contract.backend,
                    "head_backend": contract.backend,
                },
            },
        },
    }


def _temporal_review_payload(contract: object) -> dict[str, object]:
    loci = [
        {"symbol": locus["symbol"], "change": locus["change"], "evidence": "raw diff"}
        for locus in contract.oracle["required_review_loci"]
    ]
    phrases = contract.oracle["required_decision_phrases"]
    decision = "；".join(phrases) if phrases else "需要复核实现责任"
    return {
        "decision": decision,
        "review_loci": loci,
        "trust": {
            "availability": "available",
            "comparison": {
                "base_ref": contract.base_ref,
                "head_ref": contract.head_ref,
                "base_backend": contract.backend,
                "head_backend": contract.backend,
                "base_provisioned": "created",
                "head_provisioned": "reused",
                "content_comparison": {
                    "status": contract.comparison_status,
                    "reason": contract.comparison_reason,
                },
            },
        },
    }


def test_temporal_review_command_keeps_the_single_branch_diff_surface() -> None:
    command = _MODULE.build_command(
        condition="treatment",
        instruction="review base and head",
        model="sonnet",
        budget_usd="0.50",
        loomgraph_binary="/tmp/loomgraph",
        treatment_surface="temporal-review-additive",
        temporal_review=True,
    )

    assert _argument(command, "--tools") == "Read,Glob,Grep"
    assert _argument(command, "--allowedTools") == "mcp__loomgraph__loomgraph_branch_diff"
    schema = json.loads(_argument(command, "--json-schema"))
    assert set(schema["properties"]) == {"decision", "review_loci", "trust"}


def test_temporal_review_packet_accepts_codegraph_unavailable_as_uncertainty() -> None:
    contract = _MODULE._load_temporal_review_contract("sparse-risk-codegraph-uncertainty")
    raw = _temporal_review_raw_response(
        contract,
        content_status="unavailable",
        content_reason="backend_has_no_per_entity_content_hash",
    )
    packet = _MODULE.build_temporal_review_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": _temporal_review_payload(contract),
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"],
            "unexpected_mcp_tools": [],
            "raw_branch_diff_responses": [raw],
        },
        contract=contract,
    )

    assert packet["status"] == "complete"
    assert packet["trust"]["comparison"]["content_comparison"]["status"] == "unavailable"
    assert packet["trust_observation"]["raw_comparison_aligned"] is True


def test_temporal_review_packet_keeps_raw_alignment_separate_from_task_oracle() -> None:
    contract = _MODULE._load_temporal_review_contract("impact-low-resolution-review")
    payload = _temporal_review_payload(contract)
    payload["review_loci"][0]["change"] = "other"
    raw = _temporal_review_raw_response(
        contract,
        content_status="available",
        content_reason=None,
    )

    packet = _MODULE.build_temporal_review_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": payload,
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"],
            "unexpected_mcp_tools": [],
            "raw_branch_diff_responses": [raw],
        },
        contract=contract,
    )

    assert packet["status"] == "task_review_oracle_failed"
    assert packet["invalid_reason"] == "task_specific_oracle_mismatch"
    assert packet["trust_observation"]["raw_comparison_aligned"] is True


def test_temporal_packet_rejects_a_finding_that_misses_the_independent_oracle() -> None:
    payload = _temporal_payload()
    payload["findings"][0]["src"] = "app.handlers.other"
    raw = _temporal_raw_response()
    packet = _MODULE.build_temporal_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": payload,
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"],
            "loomgraph_tools": ["mcp__loomgraph__loomgraph_branch_diff"],
            "raw_branch_diff_responses": [raw],
        },
    )

    assert packet["status"] == "task_finding_oracle_failed"
    assert packet["task_finding_observation"]["passed"] is False


def test_temporal_packet_loads_its_oracle_after_runner_changes_to_fixture_cwd(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    raw = _temporal_raw_response()
    packet = _MODULE.build_temporal_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": _temporal_payload(),
            "tool_names": ["mcp__loomgraph__loomgraph_branch_diff"],
            "loomgraph_tools": ["mcp__loomgraph__loomgraph_branch_diff"],
            "raw_branch_diff_responses": [raw],
        },
    )

    assert packet["status"] == "complete"


def test_temporal_packet_rejects_treatment_without_successful_branch_diff() -> None:
    packet = _MODULE.build_temporal_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={"final_result_seen": True, "payload": _temporal_payload()},
    )

    assert packet["status"] == "missing_treatment_comparison_evidence"
    assert packet["invalid_reason"] == "no_valid_branch_diff_response"


def test_temporal_baseline_requires_explicit_unavailable_comparison() -> None:
    packet = _MODULE.build_temporal_packet(
        condition="baseline",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": _temporal_payload(availability="unavailable"),
        },
    )

    assert packet["status"] == "complete"
    assert packet["trust"] == {"availability": "unavailable", "comparison": None}


def test_temporal_packet_rejects_non_branch_mcp_tool() -> None:
    packet = _MODULE.build_temporal_packet(
        condition="treatment",
        use_mode="voluntary",
        source_clean=True,
        return_code=0,
        summary={
            "final_result_seen": True,
            "payload": _temporal_payload(),
            "tool_names": ["mcp__loomgraph__loomgraph_find"],
            "unexpected_mcp_tools": ["mcp__loomgraph__loomgraph_find"],
        },
    )

    assert packet["status"] == "unexpected_mcp_tool"
