#!/usr/bin/env python3
"""Run one read-only Claude Code orientation condition with durable artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BASELINE_TOOLS = "Read,Glob,Grep"
TOOL_CALL_BUDGET = 5
LOOMGRAPH_TOOLS = [
    "mcp__loomgraph__loomgraph_find",
    "mcp__loomgraph__loomgraph_graph",
]
LOOMGRAPH_SERVER_TOOLS = ["loomgraph_find", "loomgraph_graph"]
TEMPORAL_ADDITIVE_SURFACE = "temporal-additive"
TEMPORAL_REVIEW_ADDITIVE_SURFACE = "temporal-review-additive"
TEMPORAL_REVIEW_V2_ADDITIVE_SURFACE = "temporal-review-v2-additive"
TEMPORAL_REVIEW_V3_ADDITIVE_SURFACE = "temporal-review-v3-adapter-trust"
TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE = "temporal-review-v4-navigation-evidence"
TEMPORAL_REVIEW_V5_ADDITIVE_SURFACE = "temporal-review-v5-navigation-evidence"
TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE = "temporal-review-v6-navigation-evidence"
TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE = "temporal-review-v7-primary-navigation-evidence"
TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE = "temporal-review-v8-primary-navigation-evidence"
TEMPORAL_MCP_TOOL = "mcp__loomgraph__loomgraph_branch_diff"
TEMPORAL_SERVER_TOOL = "loomgraph_branch_diff"
TEMPORAL_MCP_TOOLS = [TEMPORAL_MCP_TOOL]
TEMPORAL_SERVER_TOOLS = [TEMPORAL_SERVER_TOOL]
TEMPORAL_PROVISIONED_STATES = {"created", "reused", "rebuilt"}
RESOLUTION_KEYS = (
    "resolved_ratio",
    "internal_unresolved_ratio",
    "external_unresolved_ratio",
)
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
TRUSTED_ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates", "trust"],
    "properties": {
        **ORIENTATION_SCHEMA["properties"],
        "trust": {
            "type": "object",
            "additionalProperties": False,
            "required": ["availability", "edge_trust", "resolution"],
            "properties": {
                "availability": {"type": "string", "enum": ["available", "unavailable"]},
                "edge_trust": {"type": "string", "minLength": 1},
                "resolution": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "resolved_ratio",
                        "internal_unresolved_ratio",
                        "external_unresolved_ratio",
                    ],
                    "properties": {
                        "resolved_ratio": {"type": ["number", "null"]},
                        "internal_unresolved_ratio": {"type": ["number", "null"]},
                        "external_unresolved_ratio": {"type": ["number", "null"]},
                    },
                },
            },
        },
    },
}
TEMPORAL_ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings", "trust"],
    "properties": {
        "findings": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "src", "tgt", "relation", "evidence"],
                "properties": {
                    "kind": {"type": "string", "enum": ["broken_chain"]},
                    "src": {"type": "string", "minLength": 1},
                    "tgt": {"type": "string", "minLength": 1},
                    "relation": {"type": "string", "enum": ["CALLS"]},
                    "evidence": {"type": "string", "minLength": 1},
                },
            },
        },
        "trust": {
            "type": "object",
            "additionalProperties": False,
            "required": ["availability", "comparison"],
            "properties": {
                "availability": {
                    "type": "string",
                    "enum": ["available", "unavailable"],
                },
                "comparison": {
                    "oneOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "base_ref",
                                "head_ref",
                                "base_backend",
                                "head_backend",
                                "base_provisioned",
                                "head_provisioned",
                                "content_comparison",
                            ],
                            "properties": {
                                "base_ref": {"type": "string", "minLength": 1},
                                "head_ref": {"type": "string", "minLength": 1},
                                "base_backend": {"type": "string", "minLength": 1},
                                "head_backend": {"type": "string", "minLength": 1},
                                "base_provisioned": {
                                    "type": "string",
                                    "enum": sorted(TEMPORAL_PROVISIONED_STATES),
                                },
                                "head_provisioned": {
                                    "type": "string",
                                    "enum": sorted(TEMPORAL_PROVISIONED_STATES),
                                },
                                "content_comparison": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["status", "reason"],
                                    "properties": {
                                        "status": {
                                            "type": "string",
                                            "enum": ["available", "partial", "unavailable"],
                                        },
                                        "reason": {"type": ["string", "null"]},
                                    },
                                },
                            },
                        },
                    ]
                },
            },
        },
    },
}
TEMPORAL_REVIEW_ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "review_loci", "trust"],
    "properties": {
        "decision": {"type": "string", "minLength": 1},
        "review_loci": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["symbol", "change", "evidence"],
                "properties": {
                    "symbol": {"type": "string", "minLength": 1},
                    "change": {"type": "string", "minLength": 1},
                    "evidence": {"type": "string", "minLength": 1},
                },
            },
        },
        "trust": TEMPORAL_ORIENTATION_SCHEMA["properties"]["trust"],
    },
}
TEMPORAL_REVIEW_V2_ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "review_loci", "trust"],
    "properties": {
        "decision": {
            "type": "object",
            "additionalProperties": False,
            "required": ["outcome", "boundary", "rationale"],
            "properties": {
                "outcome": {
                    "type": "string",
                    "enum": ["review_required", "review_required_with_uncertainty"],
                },
                "boundary": {
                    "type": "string",
                    "enum": [
                        "content_comparison_is_available",
                        "edge_delta_does_not_prove_behavior",
                        "content_comparison_is_unavailable",
                    ],
                },
                "rationale": {"type": "string", "minLength": 1},
            },
        },
        "review_loci": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "qualname", "evidence_kind", "rationale"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "qualname": {"type": "string", "minLength": 1},
                    "evidence_kind": {
                        "type": "string",
                        "enum": [
                            "source_text",
                            "content_delta",
                            "graph_delta",
                            "graph_boundary",
                        ],
                    },
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
        },
        "trust": TEMPORAL_ORIENTATION_SCHEMA["properties"]["trust"],
    },
}
TEMPORAL_REVIEW_V3_ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "review_loci"],
    "properties": {
        "decision": {
            "type": "object",
            "additionalProperties": False,
            "required": ["outcome", "boundary", "rationale"],
            "properties": {
                "outcome": {
                    "type": "string",
                    "enum": ["review_required", "review_required_with_uncertainty"],
                },
                "boundary": {
                    "type": "string",
                    "enum": [
                        "comparison_not_observed",
                        "content_comparison_available",
                        "content_comparison_unavailable",
                    ],
                },
                "rationale": {"type": "string", "minLength": 1},
            },
        },
        "review_loci": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "qualname", "rationale"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "qualname": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}
TEMPORAL_REVIEW_V4_ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "review_loci"],
    "properties": {
        "decision": {
            "type": "object",
            "additionalProperties": False,
            "required": ["boundary", "rationale"],
            "properties": {
                "boundary": {
                    "type": "string",
                    "enum": [
                        "comparison_not_observed",
                        "content_comparison_available",
                        "content_comparison_unavailable",
                    ],
                },
                "rationale": {"type": "string", "minLength": 1},
            },
        },
        "review_loci": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "qualname", "rationale"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "qualname": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

# V5 deliberately owns an independent schema artifact even though the
# model-visible navigation fields remain unchanged from v4.
TEMPORAL_REVIEW_V5_ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "review_loci"],
    "properties": {
        "decision": {
            "type": "object",
            "additionalProperties": False,
            "required": ["boundary", "rationale"],
            "properties": {
                "boundary": {
                    "type": "string",
                    "enum": [
                        "comparison_not_observed",
                        "content_comparison_available",
                        "content_comparison_unavailable",
                    ],
                },
                "rationale": {"type": "string", "minLength": 1},
            },
        },
        "review_loci": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "qualname", "rationale"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "qualname": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

# V6 deliberately makes the review target singular.  This removes the
# multi-locus answer surface that caused v5 semantic exclusions without
# weakening the task-specific AST identity oracle.
TEMPORAL_REVIEW_V6_ORIENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "review_locus"],
    "properties": {
        "decision": {
            "type": "object",
            "additionalProperties": False,
            "required": ["boundary", "rationale"],
            "properties": {
                "boundary": {
                    "type": "string",
                    "enum": [
                        "comparison_not_observed",
                        "content_comparison_available",
                        "content_comparison_unavailable",
                    ],
                },
                "rationale": {"type": "string", "minLength": 1},
            },
        },
        "review_locus": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "qualname", "rationale"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "qualname": {"type": "string", "minLength": 1},
                "rationale": {"type": "string", "minLength": 1},
            },
        },
    },
}

# V7 preserves the one-locus answer contract.  Its only protocol change is
# runtime model-identity comparison, which is recorded separately from this
# model-visible schema.
TEMPORAL_REVIEW_V7_ORIENTATION_SCHEMA: dict[str, Any] = {
    **TEMPORAL_REVIEW_V6_ORIENTATION_SCHEMA,
}

# V8 retains V7's one-locus schema.  Its independent protocol adds a persisted
# model_categories_valid witness; it is not model-visible answer content.
TEMPORAL_REVIEW_V8_ORIENTATION_SCHEMA: dict[str, Any] = {
    **TEMPORAL_REVIEW_V6_ORIENTATION_SCHEMA,
}


def _compact_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _is_temporal_surface(treatment_surface: str | None) -> bool:
    return treatment_surface in {
        TEMPORAL_ADDITIVE_SURFACE,
        TEMPORAL_REVIEW_ADDITIVE_SURFACE,
        TEMPORAL_REVIEW_V2_ADDITIVE_SURFACE,
        TEMPORAL_REVIEW_V3_ADDITIVE_SURFACE,
        TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE,
        TEMPORAL_REVIEW_V5_ADDITIVE_SURFACE,
        TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE,
        TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE,
        TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE,
    }


def build_command(
    *,
    condition: str,
    instruction: str,
    model: str,
    budget_usd: str,
    loomgraph_binary: str,
    treatment_surface: str = "mcp-only",
    require_trust: bool = False,
    storage_root: Path | None = None,
    temporal_review: bool = False,
    temporal_review_v2: bool = False,
    temporal_review_v3: bool = False,
    temporal_review_v4: bool = False,
    temporal_review_v5: bool = False,
    temporal_review_v6: bool = False,
    temporal_review_v7: bool = False,
    temporal_review_v8: bool = False,
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
        "project,local",
        "--disable-slash-commands",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--max-budget-usd",
        budget_usd,
        "--json-schema",
        _compact_json(
            TEMPORAL_REVIEW_V8_ORIENTATION_SCHEMA
            if temporal_review_v8
            else TEMPORAL_REVIEW_V7_ORIENTATION_SCHEMA
            if temporal_review_v7
            else TEMPORAL_REVIEW_V6_ORIENTATION_SCHEMA
            if temporal_review_v6
            else TEMPORAL_REVIEW_V5_ORIENTATION_SCHEMA
            if temporal_review_v5
            else TEMPORAL_REVIEW_V4_ORIENTATION_SCHEMA
            if temporal_review_v4
            else TEMPORAL_REVIEW_V3_ORIENTATION_SCHEMA
            if temporal_review_v3
            else TEMPORAL_REVIEW_V2_ORIENTATION_SCHEMA
            if temporal_review_v2
            else TEMPORAL_REVIEW_ORIENTATION_SCHEMA
            if temporal_review
            else TEMPORAL_ORIENTATION_SCHEMA
            if _is_temporal_surface(treatment_surface)
            else TRUSTED_ORIENTATION_SCHEMA
            if require_trust
            else ORIENTATION_SCHEMA
        ),
        "--strict-mcp-config",
    ]
    if condition == "baseline":
        command.extend(
            ["--tools", BASELINE_TOOLS, "--mcp-config", _compact_json({"mcpServers": {}})]
        )
    elif condition == "treatment":
        if treatment_surface not in {
            "mcp-only",
            "additive",
            TEMPORAL_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V2_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V3_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V5_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE,
        }:
            raise ValueError(f"unknown treatment surface: {treatment_surface}")
        if _is_temporal_surface(treatment_surface):
            temporal_env = {"LOOMGRAPH_MCP_ALLOWED_TOOLS": TEMPORAL_SERVER_TOOL}
            if storage_root is not None:
                temporal_env["LOOMGRAPH_STORAGE__DB_PATH"] = str(
                    storage_root / "{workspace}.db"
                )
            command.extend(
                [
                    "--tools",
                    BASELINE_TOOLS,
                    "--mcp-config",
                    _compact_json(
                        {
                            "mcpServers": {
                                "loomgraph": {
                                    "command": loomgraph_binary,
                                    "args": ["mcp", "serve"],
                                    "env": temporal_env,
                                }
                            }
                        }
                    ),
                    "--allowedTools",
                    TEMPORAL_MCP_TOOL,
                ]
            )
            command.extend(["--", instruction])
            return command
        mcp_env = {
            "LOOMGRAPH_MCP_ALLOWED_TOOLS": ",".join(LOOMGRAPH_SERVER_TOOLS)
        }
        if storage_root is not None:
            mcp_env["LOOMGRAPH_STORAGE__DB_PATH"] = str(
                storage_root / "{workspace}.db"
            )
        command.extend(
            [
                "--tools",
                BASELINE_TOOLS if treatment_surface == "additive" else "",
                "--mcp-config",
                _compact_json(
                    {
                        "mcpServers": {
                            "loomgraph": {
                                "command": loomgraph_binary,
                                "args": ["mcp", "serve"],
                                "env": mcp_env,
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


def _decode_json_object(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _temporal_invalid(reason: str) -> dict[str, Any]:
    return {"valid": False, "reason": reason}


def parse_temporal_branch_diff_response(
    raw_response: object,
    *,
    expected_base_ref: str = "base",
    expected_head_ref: str = "head",
    expected_backend: str = "codeindex",
) -> dict[str, Any]:
    """Validate one raw ``loomgraph_branch_diff`` MCP envelope."""
    raw = _decode_json_object(raw_response)
    if raw is None:
        return _temporal_invalid("raw_response_malformed")
    if raw.get("success") is not True:
        return _temporal_invalid("raw_response_not_success")
    data = raw.get("data")
    if not isinstance(data, dict):
        return _temporal_invalid("raw_response_missing_data")
    base = data.get("base")
    head = data.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        return _temporal_invalid("raw_response_missing_snapshot")
    if base.get("ref") != expected_base_ref:
        return _temporal_invalid("base_ref_mismatch")
    if head.get("ref") != expected_head_ref:
        return _temporal_invalid("head_ref_mismatch")
    for side, snapshot in (("base", base), ("head", head)):
        if not isinstance(snapshot.get("sha"), str) or not snapshot["sha"]:
            return _temporal_invalid(f"{side}_sha_missing")
        if not isinstance(snapshot.get("workspace"), str) or not snapshot["workspace"]:
            return _temporal_invalid(f"{side}_workspace_missing")
        if snapshot.get("provisioned") not in TEMPORAL_PROVISIONED_STATES:
            return _temporal_invalid(f"{side}_provisioning_invalid")
    diff = data.get("diff")
    if not isinstance(diff, dict):
        return _temporal_invalid("raw_response_missing_diff")
    content = diff.get("content_comparison")
    if not isinstance(content, dict):
        return _temporal_invalid("content_comparison_missing")
    if content.get("base_backend") != expected_backend:
        return _temporal_invalid("base_backend_mismatch")
    if content.get("head_backend") != expected_backend:
        return _temporal_invalid("head_backend_mismatch")
    if content.get("status") != "available":
        return _temporal_invalid("content_comparison_not_available")
    if content.get("reason") is not None:
        return _temporal_invalid("content_comparison_reason_mismatch")
    if content.get("reason") is not None:
        return _temporal_invalid("content_comparison_reason_mismatch")
    comparison = {
        "base_ref": base["ref"],
        "head_ref": head["ref"],
        "base_sha": base["sha"],
        "head_sha": head["sha"],
        "base_workspace": base["workspace"],
        "head_workspace": head["workspace"],
        "base_backend": content["base_backend"],
        "head_backend": content["head_backend"],
        "base_provisioned": base["provisioned"],
        "head_provisioned": head["provisioned"],
        "content_comparison": {
            "status": content["status"],
            "reason": content.get("reason"),
        },
    }
    return {
        "valid": True,
        "reason": None,
        "comparison": comparison,
        "broken_chains": diff.get("broken_chains", []),
        "duration_seconds": data.get("duration_seconds"),
    }


def _valid_temporal_payload(payload: object) -> bool:
    if not isinstance(payload, dict) or set(payload) != {"findings", "trust"}:
        return False
    findings = payload.get("findings")
    if not isinstance(findings, list) or not 1 <= len(findings) <= 5:
        return False
    if any(
        not isinstance(finding, dict)
        or set(finding) != {"kind", "src", "tgt", "relation", "evidence"}
        or any(not isinstance(finding[key], str) or not finding[key] for key in finding)
        for finding in findings
    ):
        return False
    trust = payload.get("trust")
    if not isinstance(trust, dict) or set(trust) != {"availability", "comparison"}:
        return False
    availability = trust.get("availability")
    comparison = trust.get("comparison")
    if availability == "unavailable":
        return comparison is None
    if availability != "available" or not isinstance(comparison, dict):
        return False
    if set(comparison) != {
        "base_ref", "head_ref", "base_backend", "head_backend",
        "base_provisioned", "head_provisioned", "content_comparison",
    }:
        return False
    if any(
        not isinstance(comparison[key], str) or not comparison[key]
        for key in (
            "base_ref", "head_ref", "base_backend", "head_backend",
            "base_provisioned", "head_provisioned",
        )
    ):
        return False
    if any(
        comparison[key] not in TEMPORAL_PROVISIONED_STATES
        for key in ("base_provisioned", "head_provisioned")
    ):
        return False
    content = comparison["content_comparison"]
    return (
        isinstance(content, dict)
        and set(content) == {"status", "reason"}
        and content["status"] in {"available", "partial", "unavailable"}
        and (content["reason"] is None or isinstance(content["reason"], str))
    )


def _temporal_model_matches_raw(payload: dict[str, Any], raw: dict[str, Any]) -> bool:
    comparison = payload["trust"]["comparison"]
    raw_comparison = raw["comparison"]
    for key in (
        "base_ref", "head_ref", "base_backend", "head_backend",
        "base_provisioned", "head_provisioned",
    ):
        if comparison[key] != raw_comparison[key]:
            return False
    return bool(comparison["content_comparison"] == raw_comparison["content_comparison"])


def build_temporal_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    return_code: int,
    summary: dict[str, object],
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
) -> dict[str, Any]:
    """Build the independent v2 temporal comparison packet."""
    payload = summary.get("payload")
    raw_responses = summary.get("raw_branch_diff_responses")
    if not isinstance(raw_responses, list):
        raw_responses = []
    observations = [parse_temporal_branch_diff_response(raw) for raw in raw_responses]
    valid_observations = [observation for observation in observations if observation["valid"]]
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    branch_tools = [name for name in tool_names if name == TEMPORAL_MCP_TOOL]
    unexpected = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected, list) or not all(isinstance(name, str) for name in unexpected):
        unexpected = []
    budget_overrun = len(tool_names) > TOOL_CALL_BUDGET
    valid_payload = _valid_temporal_payload(payload)
    answer_oracle: dict[str, object] | None = None
    if valid_payload:
        answer_oracle = _evaluate_temporal_task_answer(payload, condition)
    model_comparison_aligned = False
    if valid_observations and isinstance(payload, dict):
        model_comparison_aligned = any(
            payload["trust"]["availability"] == "available"
            and _temporal_model_matches_raw(payload, observation)
            for observation in valid_observations
        )
    invalid_reason: str | None = None
    if not source_clean:
        status, invalid_reason = "invalid_source_mutation", "source_mutation"
    elif return_code != 0:
        status, invalid_reason = "agent_error", "agent_return_code_nonzero"
    elif summary.get("final_result_seen") is not True or not valid_payload:
        status, invalid_reason = "missing_or_invalid_agent_response", "temporal_schema_invalid"
    elif budget_overrun:
        status, invalid_reason = "tool_call_budget_exceeded", "tool_call_budget_exceeded"
    elif unexpected:
        status, invalid_reason = "unexpected_mcp_tool", "unexpected_mcp_tool"
    elif condition == "baseline" and isinstance(payload, dict):
        if payload["trust"]["availability"] != "unavailable":
            status, invalid_reason = (
                "unverified_baseline_comparison_trust", "baseline_must_report_unavailable"
            )
        elif answer_oracle is not None and answer_oracle["passed"] is not True:
            status, invalid_reason = "task_finding_oracle_failed", "task_specific_oracle_mismatch"
        else:
            status = "complete"
    elif not valid_observations:
        status, invalid_reason = (
            "missing_treatment_comparison_evidence", "no_valid_branch_diff_response"
        )
    elif not model_comparison_aligned:
        status, invalid_reason = (
            "unverified_treatment_comparison_trust", "model_raw_comparison_mismatch"
        )
    elif answer_oracle is not None and answer_oracle["passed"] is not True:
        status, invalid_reason = "task_finding_oracle_failed", "task_specific_oracle_mismatch"
    else:
        status = "complete"
    return {
        "schema_version": 2,
        "protocol": TEMPORAL_ADDITIVE_SURFACE,
        "status": status,
        "invalid_reason": invalid_reason,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": TEMPORAL_ADDITIVE_SURFACE,
        "pre_edit": source_clean,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "findings": payload.get("findings", []) if isinstance(payload, dict) else [],
        "trust": payload.get("trust") if isinstance(payload, dict) else None,
        "trust_observation": {
            "raw_branch_diff_responses": raw_responses,
            "raw_branch_diff_observations": observations,
            "raw_comparison_aligned": model_comparison_aligned,
            "valid_raw_branch_diff_count": len(valid_observations),
        },
        "task_finding_observation": answer_oracle,
        "tool_call_count": len(tool_names),
        "tool_call_budget": TOOL_CALL_BUDGET,
        "tool_call_budget_overrun": budget_overrun,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {
            "requested": requested_model,
            "observed": summary.get("observed_models", []),
            "assistant_observed": summary.get("assistant_models", []),
            "session_observed": summary.get("session_models", []),
            "usage_observed": summary.get("usage_models", []),
        },
        "tooling": {
            "loomgraph": {
                "used": bool(branch_tools),
                "tools": branch_tools,
                "unexpected_tools": unexpected,
            }
        },
    }


def summarize_stream(
    events: list[dict[str, Any]], treatment_surface: str | None = None
) -> dict[str, object]:
    """Extract the final schema payload and observed native LoomGraph calls."""
    tool_names: list[str] = []
    tool_call_names: dict[str, str] = {}
    graph_resolutions: list[dict[str, float]] = []
    assistant_models: list[str] = []
    session_models: list[str] = []
    usage_models: list[str] = []
    for event in events:
        model = event.get("model")
        if isinstance(model, str):
            if event.get("type") == "assistant":
                assistant_models.append(model)
            else:
                session_models.append(model)
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        message_model = message.get("model")
        if isinstance(message_model, str):
            if event.get("type") == "assistant":
                assistant_models.append(message_model)
            else:
                session_models.append(message_model)
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name = item.get("name")
            if isinstance(name, str):
                tool_names.append(name)
                tool_id = item.get("id")
                if isinstance(tool_id, str):
                    tool_call_names[tool_id] = name

    structural_retrievals: list[dict[str, str]] = []
    raw_branch_diff_responses: list[dict[str, Any]] = []
    raw_branch_diff_events: list[dict[str, Any]] = []
    for event_index, event in enumerate(events):
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_result":
                continue
            tool_id = item.get("tool_use_id")
            if not isinstance(tool_id, str):
                continue
            tool_name = tool_call_names.get(tool_id)
            if tool_name not in LOOMGRAPH_TOOLS and tool_name != TEMPORAL_MCP_TOOL:
                continue
            if tool_name == TEMPORAL_MCP_TOOL:
                result_content = item.get("content")
                result_items = result_content if isinstance(result_content, list) else [result_content]
                for result_item in result_items:
                    text = result_item.get("text") if isinstance(result_item, dict) else result_item
                    result = _decode_json_object(text)
                    raw_text = text if isinstance(text, str) else _compact_json({"content": text})
                    raw_branch_diff_events.append(
                        {
                            "stream_event_index": event_index,
                            "tool_use_id": tool_id,
                            "raw_json_text": raw_text,
                            "raw_response": result,
                            "raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
                        }
                    )
                    if result is not None:
                        raw_branch_diff_responses.append(result)
                continue
            if tool_name not in LOOMGRAPH_TOOLS:
                continue
            result_content = item.get("content")
            result_items = result_content if isinstance(result_content, list) else [result_content]
            for result_item in result_items:
                text = result_item.get("text") if isinstance(result_item, dict) else result_item
                if not isinstance(text, str):
                    continue
                try:
                    result = json.loads(text)
                except json.JSONDecodeError:
                    continue
                data = result.get("data") if isinstance(result, dict) else None
                if result.get("success") is not True or not isinstance(data, dict):
                    continue
                if tool_name.endswith("loomgraph_find") and data.get("matches"):
                    structural_retrievals.append({"tool": tool_name, "evidence": "find_matches"})
                elif tool_name.endswith("loomgraph_graph") and data.get("source_id"):
                    structural_retrievals.append({"tool": tool_name, "evidence": "resolved_graph"})
                    resolution = data.get("resolution")
                    if (
                        isinstance(resolution, dict)
                        and set(resolution) == set(RESOLUTION_KEYS)
                        and all(isinstance(value, (int, float)) for value in resolution.values())
                    ):
                        graph_resolutions.append(
                            {key: float(resolution[key]) for key in RESOLUTION_KEYS}
                        )
                break

    payload: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None
    final_result_seen = False
    final_result_event_index: int | None = None
    for event_index in range(len(events) - 1, -1, -1):
        event = events[event_index]
        if event.get("type") != "result":
            continue
        final_result_seen = True
        if final_result is None:
            final_result = event
        structured = event.get("structured_output")
        if isinstance(structured, dict):
            payload = structured
            final_result_event_index = event_index
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
            final_result_event_index = event_index
            break

    for event in events:
        model_usage = event.get("modelUsage")
        if isinstance(model_usage, dict):
            usage_models.extend(name for name in model_usage if isinstance(name, str))

    assistant_models = list(dict.fromkeys(assistant_models))
    session_models = list(dict.fromkeys(session_models))
    usage_models = list(dict.fromkeys(usage_models))

    allowed_mcp_tools = (
        TEMPORAL_MCP_TOOLS
        if _is_temporal_surface(treatment_surface)
        else LOOMGRAPH_TOOLS
    )
    return {
        "final_result_seen": final_result_seen,
        "final_result_event_index": final_result_event_index,
        "final_result": final_result,
        "payload": payload,
        "tool_names": tool_names,
        "loomgraph_tools": [
            name
            for name in tool_names
            if name in allowed_mcp_tools
        ],
        "unexpected_mcp_tools": [
            name
            for name in tool_names
            if (
                name.startswith("mcp__")
                if _is_temporal_surface(treatment_surface)
                else name.startswith("mcp__loomgraph__")
            )
            and name not in allowed_mcp_tools
        ],
        "structural_retrievals": structural_retrievals,
        "graph_resolutions": graph_resolutions,
        "observed_models": list(
            dict.fromkeys([*session_models, *assistant_models, *usage_models])
        ),
        "assistant_models": assistant_models,
        "session_models": session_models,
        "usage_models": usage_models,
        "raw_branch_diff_responses": raw_branch_diff_responses,
        "raw_branch_diff_events": raw_branch_diff_events,
        "temporal_branch_diff_observations": [
            parse_temporal_branch_diff_response(response) for response in raw_branch_diff_responses
        ],
    }


def _v7_model_categories(events: list[dict[str, Any]]) -> dict[str, object]:
    """Preserve native model-label encounter order for the V7 identity contract."""
    raw: dict[str, list[str]] = {"assistant": [], "session": [], "usage": []}
    malformed = False
    for event in events:
        target = "assistant" if event.get("type") == "assistant" else "session"
        for value in (event.get("model"), event.get("message", {}).get("model") if isinstance(event.get("message"), dict) else None):
            if value is None:
                continue
            if not isinstance(value, str) or not value:
                malformed = True
            else:
                raw[target].append(value)
        usage = event.get("modelUsage")
        if usage is None:
            continue
        if not isinstance(usage, dict):
            malformed = True
            continue
        for value in usage:
            if not isinstance(value, str) or not value:
                malformed = True
            else:
                raw["usage"].append(value)
    result: dict[str, object] = {"model_categories_valid": not malformed}
    for name, labels in raw.items():
        result[f"{name}_models_raw"] = labels
        result[f"{name}_models_canonical"] = sorted(set(labels))
    if not raw["assistant"]:
        result["model_categories_valid"] = False
    return result


def summarize_temporal_review_v7_stream(events: list[dict[str, Any]]) -> dict[str, object]:
    """Keep V7 raw identity evidence without changing historical summarization."""
    return {
        **summarize_stream(events, TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE),
        **_v7_model_categories(events),
    }


def _valid_payload(payload: object, *, require_trust: bool) -> bool:
    expected_fields = {"candidates", "trust"} if require_trust else {"candidates"}
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        return False
    candidates = payload.get("candidates")
    valid_candidates = isinstance(candidates, list) and 1 <= len(candidates) <= 5 and all(
        isinstance(candidate, dict)
        and set(candidate) == {"path", "evidence"}
        and isinstance(candidate["path"], str)
        and bool(candidate["path"])
        and isinstance(candidate["evidence"], str)
        and bool(candidate["evidence"])
        for candidate in candidates
    )
    if not valid_candidates:
        return False
    if not require_trust:
        return True
    trust = payload.get("trust")
    if not isinstance(trust, dict) or set(trust) != {"availability", "edge_trust", "resolution"}:
        return False
    resolution = trust.get("resolution")
    availability = trust.get("availability")
    valid_resolution = isinstance(resolution, dict) and set(resolution) == set(RESOLUTION_KEYS)
    if not valid_resolution:
        return False
    assert isinstance(resolution, dict)
    return (
        availability in {"available", "unavailable"}
        and isinstance(trust.get("edge_trust"), str)
        and bool(trust["edge_trust"])
        and (
            all(isinstance(value, (int, float)) for value in resolution.values())
            if availability == "available"
            else all(value is None for value in resolution.values())
        )
    )


def normalize_candidate_paths(payload: object, source_dir: Path) -> dict[str, Any] | None:
    """Keep scored candidate paths repo-relative without rewriting raw output."""
    if not isinstance(payload, dict):
        return None
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return None

    source_root = source_dir.resolve()
    normalized_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return None
        path = candidate.get("path")
        if not isinstance(path, str):
            return None
        candidate_path = Path(path)
        if candidate_path.is_absolute():
            try:
                candidate_path = candidate_path.resolve().relative_to(source_root)
            except ValueError:
                return None
        if not candidate_path.parts or ".." in candidate_path.parts:
            return None
        normalized_candidates.append({**candidate, "path": candidate_path.as_posix()})
    return {**payload, "candidates": normalized_candidates}


def score_agent_use_fixture(
    task_id: str, candidates: object
) -> dict[str, object] | None:
    """Record a frozen path-oracle observation without changing packet validity."""
    manifest_path = Path(__file__).with_name("agent-use-fixtures.json")
    manifest = json.loads(manifest_path.read_text())
    fixtures = manifest.get("fixtures") if isinstance(manifest, dict) else None
    if not isinstance(fixtures, list):
        raise ValueError("agent-use fixture manifest has no fixtures list")
    fixture = next(
        (
            item
            for item in fixtures
            if isinstance(item, dict) and item.get("id") == task_id
        ),
        None,
    )
    if fixture is None:
        return None

    expected_paths = fixture.get("oracle_existing_paths")
    if not isinstance(expected_paths, list) or not all(
        isinstance(path, str) for path in expected_paths
    ):
        raise ValueError(f"agent-use fixture {task_id} has no valid path oracle")
    candidate_paths = [
        candidate["path"]
        for candidate in candidates
        if isinstance(candidate, dict) and isinstance(candidate.get("path"), str)
    ] if isinstance(candidates, list) else []
    expected_set = set(expected_paths)
    candidate_set = set(candidate_paths)
    matched_paths = [path for path in expected_paths if path in candidate_set]
    return {
        "id": task_id,
        "task_class": fixture.get("task_class"),
        "rg_equivalent_single_query": fixture.get("rg_equivalent_single_query"),
        "path_oracle": {
            "expected_paths": expected_paths,
            "candidate_paths": candidate_paths,
            "matched_paths": matched_paths,
            "missing_paths": [path for path in expected_paths if path not in candidate_set],
            "unexpected_paths": [path for path in candidate_paths if path not in expected_set],
            "path_recall": len(matched_paths) / len(expected_paths),
            "exact_path_set": (
                candidate_set == expected_set and len(candidate_paths) == len(candidate_set)
            ),
        },
    }


def build_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    return_code: int,
    summary: dict[str, object],
    requested_model: str = "",
    navigation_surface: str = "mcp-only",
    require_trust: bool = False,
    agent_execution_seconds: float | None = None,
    tool_call_budget: int = TOOL_CALL_BUDGET,
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
    structural_retrievals = summary.get("structural_retrievals")
    if not isinstance(structural_retrievals, list) or not all(
        isinstance(retrieval, dict) for retrieval in structural_retrievals
    ):
        structural_retrievals = []
    unexpected_mcp_tools = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected_mcp_tools, list) or not all(
        isinstance(name, str) for name in unexpected_mcp_tools
    ):
        unexpected_mcp_tools = []
    graph_resolutions = summary.get("graph_resolutions")
    if not isinstance(graph_resolutions, list) or not all(
        isinstance(resolution, dict)
        and set(resolution) == set(RESOLUTION_KEYS)
        and all(isinstance(value, (int, float)) for value in resolution.values())
        for resolution in graph_resolutions
    ):
        graph_resolutions = []
    def model_list(name: str) -> list[str]:
        models = summary.get(name)
        return (
            models
            if isinstance(models, list) and all(isinstance(model, str) for model in models)
            else []
        )

    observed_models = model_list("observed_models")
    assistant_models = model_list("assistant_models")
    session_models = model_list("session_models")
    usage_models = model_list("usage_models")
    trust = payload.get("trust") if isinstance(payload, dict) else None
    trust_resolution = trust.get("resolution") if isinstance(trust, dict) else None
    treatment_resolution_matches_graph = (
        any(trust_resolution == resolution for resolution in graph_resolutions)
        if require_trust and condition == "treatment"
        else None
    )
    if tool_call_budget < 1:
        raise ValueError("tool_call_budget must be positive")
    tool_call_budget_overrun = len(tool_names) > tool_call_budget
    if not source_clean:
        status = "invalid_source_mutation"
    elif return_code != 0:
        status = "agent_error"
    elif summary.get("final_result_seen") is not True or not _valid_payload(
        payload, require_trust=require_trust
    ):
        status = "missing_or_invalid_agent_response"
    elif (
        require_trust
        and condition == "treatment"
        and isinstance(payload, dict)
        and isinstance(trust, dict)
        and trust.get("availability") != "available"
    ):
        status = "missing_treatment_trust_evidence"
    elif require_trust and condition == "treatment" and not treatment_resolution_matches_graph:
        status = "unverified_treatment_trust_resolution"
    elif tool_call_budget_overrun:
        status = "tool_call_budget_exceeded"
    elif unexpected_mcp_tools:
        status = "unexpected_mcp_tool"
    elif condition == "treatment" and use_mode == "assisted" and not structural_retrievals:
        status = "missing_assisted_structural_retrieval"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "status": status,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": navigation_surface,
        "pre_edit": source_clean,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "candidates": payload.get("candidates", []) if isinstance(payload, dict) else [],
        "trust": trust if require_trust else None,
        "trust_observation": {
            "graph_resolutions": graph_resolutions,
            "treatment_resolution_matches_graph": treatment_resolution_matches_graph,
        },
        "tool_call_count": len(tool_names),
        "tool_call_budget": tool_call_budget,
        "tool_call_budget_overrun": tool_call_budget_overrun,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {
            "requested": requested_model,
            "observed": observed_models,
            "assistant_observed": assistant_models,
            "session_observed": session_models,
            "usage_observed": usage_models,
        },
        "tooling": {
            "loomgraph": {
                "used": bool(loomgraph_tools),
                "tools": loomgraph_tools,
                "unexpected_tools": unexpected_mcp_tools,
                "structural_retrievals": structural_retrievals,
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


def _evaluate_temporal_task_answer(payload: object, condition: str) -> dict[str, object]:
    """Load the v2-only task oracle without importing a sibling script as a package."""
    path = Path(__file__).resolve().parents[1] / "agent_use_v2_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("agent_use_v2_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load agent-use v2 fixture oracle")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    evaluator = getattr(
        module,
        "evaluate_baseline_answer" if condition == "baseline" else "evaluate_treatment_answer",
    )
    outcome = evaluator(payload)
    return {"passed": bool(outcome.passed), "failures": list(outcome.failures)}


def _load_temporal_review_module() -> Any:
    """Load the adapter-owned product-pilot contract without exposing it to Claude."""
    path = Path(__file__).resolve().parents[1] / "temporal_review_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("temporal_review_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load temporal-review fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_temporal_review_contract(task_id: str) -> object:
    module = _load_temporal_review_module()
    return module.load_temporal_review_contract(task_id)


def _load_temporal_review_v2_module() -> Any:
    """Load the separately preregistered v2 review contract."""
    path = Path(__file__).resolve().parents[1] / "temporal_review_v2_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("temporal_review_v2_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load temporal-review v2 fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_temporal_review_v2_contract(task_id: str) -> object:
    return _load_temporal_review_v2_module().contract(task_id)


def _load_temporal_review_v3_module() -> Any:
    """Load the independent v3 adapter-observed review contract."""
    path = Path(__file__).resolve().parents[1] / "temporal_review_v3_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("temporal_review_v3_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load temporal-review v3 fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_temporal_review_v3_contract(task_id: str) -> object:
    return _load_temporal_review_v3_module().contract(task_id)


def _load_temporal_review_v4_module() -> Any:
    """Load the independently preregistered v4 navigation contract."""
    path = Path(__file__).resolve().parents[1] / "temporal_review_v4_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("temporal_review_v4_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load temporal-review v4 fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_temporal_review_v4_contract(task_id: str) -> object:
    return _load_temporal_review_v4_module().contract(task_id)


def _load_temporal_review_v5_module() -> Any:
    """Load the independently preregistered v5 navigation contract."""
    path = Path(__file__).resolve().parents[1] / "temporal_review_v5_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("temporal_review_v5_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load temporal-review v5 fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_temporal_review_v5_contract(task_id: str) -> object:
    return _load_temporal_review_v5_module().contract(task_id)


def _load_temporal_review_v6_module() -> Any:
    """Load the independent v6 one-locus navigation contract."""
    path = Path(__file__).resolve().parents[1] / "temporal_review_v6_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("temporal_review_v6_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load temporal-review v6 fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_temporal_review_v6_contract(task_id: str) -> object:
    return _load_temporal_review_v6_module().contract(task_id)


def _load_temporal_review_v7_module() -> Any:
    """Load the independent v7 one-locus navigation contract."""
    path = Path(__file__).resolve().parents[1] / "temporal_review_v7_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("temporal_review_v7_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load temporal-review v7 fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def _load_temporal_review_v7_contract(task_id: str) -> object:
    return _load_temporal_review_v7_module().contract(task_id)


def _load_temporal_review_v8_module() -> Any:
    """Load the independent v8 one-locus navigation contract."""
    path = Path(__file__).resolve().parents[1] / "temporal_review_v8_fixtures.py"
    repo_root = str(path.parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    spec = importlib.util.spec_from_file_location("temporal_review_v8_fixtures_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load temporal-review v8 fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_temporal_review_v8_contract(task_id: str) -> object:
    return _load_temporal_review_v8_module().contract(task_id)

def _temporal_review_trust_matches_raw(payload: object, observation: object) -> bool:
    if not isinstance(payload, dict) or not isinstance(observation, dict):
        return False
    trust = payload.get("trust")
    return (
        isinstance(trust, dict)
        and trust.get("availability") == "available"
        and trust.get("comparison") == observation.get("comparison")
    )


def build_temporal_review_v3_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    source_dir: Path,
    return_code: int,
    summary: dict[str, object],
    contract: object,
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
) -> dict[str, Any]:
    """Build v3 evidence without asking the model to transcribe raw trust.

    The selected event is the last fully validated branch-diff response.  Its
    identity, raw bytes hash, comparison and semantic replay form one adapter
    certificate; evidence from different calls is never combined.
    """
    module = _load_temporal_review_v3_module()
    task_id = getattr(contract, "task_id", None)
    if not isinstance(task_id, str):
        raise ValueError("temporal-review v3 contract must declare task_id")
    payload = summary.get("payload")
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    unexpected = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected, list) or not all(isinstance(name, str) for name in unexpected):
        unexpected = []
    raw_events = summary.get("raw_branch_diff_events")
    if not isinstance(raw_events, list):
        raw_events = []
    parsed_events: list[dict[str, Any]] = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        raw = event.get("raw_response")
        observation = module.parse_raw_response(task_id, raw)
        parsed_events.append({**event, "observation": observation})
    final_result_event_index = summary.get("final_result_event_index")
    if not isinstance(final_result_event_index, int):
        final_result_event_index = None
    eligible_events = [
        event
        for event in parsed_events
        if final_result_event_index is not None
        and isinstance(event.get("stream_event_index"), int)
        and event["stream_event_index"] < final_result_event_index
    ]
    valid_events = [
        event
        for event in eligible_events
        if isinstance(event.get("observation"), dict)
        and event["observation"].get("valid") is True
    ]
    selected = valid_events[-1] if condition == "treatment" and valid_events else None
    selected_raw = selected.get("raw_response") if isinstance(selected, dict) else None
    selected_observation = selected.get("observation") if isinstance(selected, dict) else None
    if condition == "baseline":
        outcome = module.evaluate_answer(
            task_id, payload, condition=condition, source_root=source_dir
        )
    elif selected is not None:
        outcome = module.evaluate_answer(
            task_id,
            payload,
            condition=condition,
            source_root=source_dir,
            raw_response=selected_raw,
        )
    else:
        outcome = None
    answer_oracle = (
        {"passed": bool(outcome.passed), "failures": list(outcome.failures)}
        if outcome is not None
        else None
    )
    certificate = None
    if isinstance(selected, dict) and isinstance(selected_observation, dict):
        certificate = {
            "selected_raw_event_index": selected.get("stream_event_index"),
            "tool_use_id": selected.get("tool_use_id"),
            "raw_sha256": selected.get("raw_sha256"),
            "comparison": selected_observation.get("comparison"),
            "raw_valid": True,
            "source": "adapter_raw_branch_diff",
        }
    invalid_reason: str | None = None
    hard_protocol_stop = False
    if not source_clean:
        status, invalid_reason, hard_protocol_stop = (
            "invalid_source_mutation",
            "source_mutation",
            True,
        )
    elif return_code != 0:
        status, invalid_reason, hard_protocol_stop = "agent_error", "agent_return_code_nonzero", True
    elif summary.get("final_result_seen") is not True or not isinstance(payload, dict):
        status, invalid_reason = "missing_or_invalid_agent_response", "temporal_schema_invalid"
    elif len(tool_names) > TOOL_CALL_BUDGET:
        status, invalid_reason, hard_protocol_stop = (
            "tool_call_budget_exceeded",
            "tool_call_budget_exceeded",
            True,
        )
    elif unexpected:
        status, invalid_reason, hard_protocol_stop = "unexpected_mcp_tool", "unexpected_mcp_tool", True
    elif condition == "treatment" and not raw_events:
        status, invalid_reason, hard_protocol_stop = (
            "missing_treatment_comparison_evidence",
            "no_branch_diff_response",
            True,
        )
    elif condition == "treatment" and len(eligible_events) != len(parsed_events):
        status, invalid_reason, hard_protocol_stop = (
            "invalid_treatment_comparison_certificate",
            "branch_diff_response_after_final_result",
            True,
        )
    elif condition == "treatment" and len(valid_events) != len(eligible_events):
        status, invalid_reason, hard_protocol_stop = (
            "invalid_treatment_comparison_certificate",
            "raw_ref_backend_or_l2_mismatch",
            True,
        )
    elif condition == "treatment" and selected is None:
        status, invalid_reason, hard_protocol_stop = (
            "missing_treatment_comparison_evidence",
            "no_valid_branch_diff_response",
            True,
        )
    elif answer_oracle is None or answer_oracle["passed"] is not True:
        status, invalid_reason = "task_review_oracle_failed", "task_specific_oracle_mismatch"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "protocol": TEMPORAL_REVIEW_V3_ADDITIVE_SURFACE,
        "status": status,
        "invalid_reason": invalid_reason,
        "hard_protocol_stop": hard_protocol_stop,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": TEMPORAL_REVIEW_V3_ADDITIVE_SURFACE,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "decision": payload.get("decision") if isinstance(payload, dict) else None,
        "review_loci": payload.get("review_loci", []) if isinstance(payload, dict) else [],
        "trust_observation": {
            "raw_branch_diff_events": parsed_events,
            "valid_raw_branch_diff_count": len(valid_events),
            "selected_certificate": certificate,
        },
        "task_review_observation": answer_oracle,
        "tool_call_count": len(tool_names),
        "tool_call_budget": TOOL_CALL_BUDGET,
        "tool_call_budget_overrun": len(tool_names) > TOOL_CALL_BUDGET,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {"requested": requested_model, "observed": summary.get("observed_models", [])},
        "tooling": {
            "loomgraph": {
                "used": TEMPORAL_MCP_TOOL in tool_names,
                "tools": [name for name in tool_names if name == TEMPORAL_MCP_TOOL],
                "unexpected_tools": unexpected,
            }
        },
    }


def build_temporal_review_v4_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    source_dir: Path,
    return_code: int,
    summary: dict[str, object],
    contract: object,
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
) -> dict[str, Any]:
    """Build v4 evidence without a hidden decision-outcome score."""
    module = _load_temporal_review_v4_module()
    task_id = getattr(contract, "task_id", None)
    if not isinstance(task_id, str):
        raise ValueError("temporal-review v4 contract must declare task_id")
    payload = summary.get("payload")
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    unexpected = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected, list) or not all(isinstance(name, str) for name in unexpected):
        unexpected = []
    raw_events = summary.get("raw_branch_diff_events")
    if not isinstance(raw_events, list):
        raw_events = []
    parsed_events: list[dict[str, Any]] = []
    for event in raw_events:
        if isinstance(event, dict):
            parsed_events.append({**event, "observation": module.parse_raw_response(task_id, event.get("raw_response"))})
    final_result_event_index = summary.get("final_result_event_index")
    eligible_events = [
        event for event in parsed_events
        if isinstance(final_result_event_index, int)
        and isinstance(event.get("stream_event_index"), int)
        and event["stream_event_index"] < final_result_event_index
    ]
    valid_events = [
        event for event in eligible_events
        if isinstance(event.get("observation"), dict) and event["observation"].get("valid") is True
    ]
    selected = valid_events[-1] if condition == "treatment" and valid_events else None
    if condition == "baseline":
        outcome = module.evaluate_answer(task_id, payload, condition=condition, source_root=source_dir)
    elif selected is not None:
        outcome = module.evaluate_answer(
            task_id, payload, condition=condition, source_root=source_dir, raw_response=selected.get("raw_response")
        )
    else:
        outcome = None
    answer_oracle = {"passed": bool(outcome.passed), "failures": list(outcome.failures)} if outcome else None
    selected_observation = selected.get("observation") if isinstance(selected, dict) else None
    certificate = (
        {
            "selected_raw_event_index": selected.get("stream_event_index"),
            "tool_use_id": selected.get("tool_use_id"),
            "raw_sha256": selected.get("raw_sha256"),
            "comparison": selected_observation.get("comparison"),
            "raw_valid": True,
            "source": "adapter_raw_branch_diff",
        }
        if isinstance(selected, dict) and isinstance(selected_observation, dict)
        else None
    )
    invalid_reason: str | None = None
    hard_protocol_stop = False
    if not source_clean:
        status, invalid_reason, hard_protocol_stop = "invalid_source_mutation", "source_mutation", True
    elif return_code != 0:
        status, invalid_reason, hard_protocol_stop = "agent_error", "agent_return_code_nonzero", True
    elif summary.get("final_result_seen") is not True or not isinstance(payload, dict):
        status, invalid_reason = "missing_or_invalid_agent_response", "temporal_schema_invalid"
    elif len(tool_names) > TOOL_CALL_BUDGET:
        status, invalid_reason, hard_protocol_stop = "tool_call_budget_exceeded", "tool_call_budget_exceeded", True
    elif unexpected:
        status, invalid_reason, hard_protocol_stop = "unexpected_mcp_tool", "unexpected_mcp_tool", True
    elif condition == "treatment" and not raw_events:
        status, invalid_reason, hard_protocol_stop = "missing_treatment_comparison_evidence", "no_branch_diff_response", True
    elif condition == "treatment" and len(eligible_events) != len(parsed_events):
        status, invalid_reason, hard_protocol_stop = "invalid_treatment_comparison_certificate", "branch_diff_response_after_final_result", True
    elif condition == "treatment" and len(valid_events) != len(eligible_events):
        status, invalid_reason, hard_protocol_stop = "invalid_treatment_comparison_certificate", "raw_ref_backend_or_l2_mismatch", True
    elif condition == "treatment" and selected is None:
        status, invalid_reason, hard_protocol_stop = "missing_treatment_comparison_evidence", "no_valid_branch_diff_response", True
    elif answer_oracle is None or answer_oracle["passed"] is not True:
        status, invalid_reason = "task_review_oracle_failed", "task_specific_oracle_mismatch"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "protocol": TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE,
        "status": status,
        "invalid_reason": invalid_reason,
        "hard_protocol_stop": hard_protocol_stop,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "decision": payload.get("decision") if isinstance(payload, dict) else None,
        "review_loci": payload.get("review_loci", []) if isinstance(payload, dict) else [],
        "trust_observation": {
            "raw_branch_diff_events": parsed_events,
            "valid_raw_branch_diff_count": len(valid_events),
            "selected_certificate": certificate,
        },
        "task_review_observation": answer_oracle,
        "tool_call_count": len(tool_names),
        "tool_call_budget": TOOL_CALL_BUDGET,
        "tool_call_budget_overrun": len(tool_names) > TOOL_CALL_BUDGET,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {
            "requested": requested_model,
            "observed": summary.get("observed_models", []),
            "assistant_observed": summary.get("assistant_models", []),
            "session_observed": summary.get("session_models", []),
            "usage_observed": summary.get("usage_models", []),
        },
        "tooling": {
            "loomgraph": {
                "used": TEMPORAL_MCP_TOOL in tool_names,
                "tools": [name for name in tool_names if name == TEMPORAL_MCP_TOOL],
                "unexpected_tools": unexpected,
            }
        },
    }


def build_temporal_review_v5_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    source_dir: Path,
    return_code: int,
    summary: dict[str, object],
    contract: object,
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
) -> dict[str, Any]:
    """Build v5 evidence; tool calls are retained, never validity-gated."""
    module = _load_temporal_review_v5_module()
    task_id = getattr(contract, "task_id", None)
    if not isinstance(task_id, str):
        raise ValueError("temporal-review v5 contract must declare task_id")
    payload = summary.get("payload")
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    unexpected = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected, list) or not all(isinstance(name, str) for name in unexpected):
        unexpected = []
    raw_events = summary.get("raw_branch_diff_events")
    if not isinstance(raw_events, list):
        raw_events = []
    parsed_events = [
        {**event, "observation": module.parse_raw_response(task_id, event.get("raw_response"))}
        for event in raw_events
        if isinstance(event, dict)
    ]
    final_result_event_index = summary.get("final_result_event_index")
    eligible_events = [
        event for event in parsed_events
        if isinstance(final_result_event_index, int)
        and isinstance(event.get("stream_event_index"), int)
        and event["stream_event_index"] < final_result_event_index
    ]
    valid_events = [
        event for event in eligible_events
        if isinstance(event.get("observation"), dict) and event["observation"].get("valid") is True
    ]
    selected = valid_events[-1] if condition == "treatment" and valid_events else None
    if condition == "baseline":
        outcome = module.evaluate_answer(task_id, payload, condition=condition, source_root=source_dir)
    elif selected is not None:
        outcome = module.evaluate_answer(
            task_id, payload, condition=condition, source_root=source_dir,
            raw_response=selected.get("raw_response"),
        )
    else:
        outcome = None
    answer_oracle = {"passed": bool(outcome.passed), "failures": list(outcome.failures)} if outcome else None
    selected_observation = selected.get("observation") if isinstance(selected, dict) else None
    certificate = (
        {
            "selected_raw_event_index": selected.get("stream_event_index"),
            "tool_use_id": selected.get("tool_use_id"),
            "raw_sha256": selected.get("raw_sha256"),
            "comparison": selected_observation.get("comparison"),
            "raw_valid": True,
            "source": "adapter_raw_branch_diff",
        }
        if isinstance(selected, dict) and isinstance(selected_observation, dict)
        else None
    )
    invalid_reason: str | None = None
    hard_protocol_stop = False
    if not source_clean:
        status, invalid_reason, hard_protocol_stop = "invalid_source_mutation", "source_mutation", True
    elif return_code != 0:
        status, invalid_reason, hard_protocol_stop = "agent_error", "agent_return_code_nonzero", True
    elif summary.get("final_result_seen") is not True or not isinstance(payload, dict):
        status, invalid_reason = "missing_or_invalid_agent_response", "temporal_schema_invalid"
    elif unexpected:
        status, invalid_reason, hard_protocol_stop = "unexpected_mcp_tool", "unexpected_mcp_tool", True
    elif condition == "treatment" and not raw_events:
        status, invalid_reason, hard_protocol_stop = "missing_treatment_comparison_evidence", "no_branch_diff_response", True
    elif condition == "treatment" and len(eligible_events) != len(parsed_events):
        status, invalid_reason, hard_protocol_stop = "invalid_treatment_comparison_certificate", "branch_diff_response_after_final_result", True
    elif condition == "treatment" and len(valid_events) != len(eligible_events):
        status, invalid_reason, hard_protocol_stop = "invalid_treatment_comparison_certificate", "raw_ref_backend_or_l2_mismatch", True
    elif condition == "treatment" and selected is None:
        status, invalid_reason, hard_protocol_stop = "missing_treatment_comparison_evidence", "no_valid_branch_diff_response", True
    elif answer_oracle is None or answer_oracle["passed"] is not True:
        status, invalid_reason = "task_review_oracle_failed", "task_specific_oracle_mismatch"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "protocol": TEMPORAL_REVIEW_V5_ADDITIVE_SURFACE,
        "status": status,
        "invalid_reason": invalid_reason,
        "hard_protocol_stop": hard_protocol_stop,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": TEMPORAL_REVIEW_V5_ADDITIVE_SURFACE,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "decision": payload.get("decision") if isinstance(payload, dict) else None,
        "review_loci": payload.get("review_loci", []) if isinstance(payload, dict) else [],
        "trust_observation": {
            "raw_branch_diff_events": parsed_events,
            "valid_raw_branch_diff_count": len(valid_events),
            "selected_certificate": certificate,
        },
        "task_review_observation": answer_oracle,
        "tool_call_count": len(tool_names),
        "tool_call_names": tool_names,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {
            "requested": requested_model,
            "observed": summary.get("observed_models", []),
            "assistant_observed": summary.get("assistant_models", []),
            "session_observed": summary.get("session_models", []),
            "usage_observed": summary.get("usage_models", []),
        },
        "tooling": {
            "loomgraph": {
                "used": TEMPORAL_MCP_TOOL in tool_names,
                "tools": [name for name in tool_names if name == TEMPORAL_MCP_TOOL],
                "unexpected_tools": unexpected,
            }
        },
    }


def build_temporal_review_v6_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    source_dir: Path,
    return_code: int,
    summary: dict[str, object],
    contract: object,
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
) -> dict[str, Any]:
    """Build independent one-locus v6 evidence from the retained raw stream."""
    module = _load_temporal_review_v6_module()
    task_id = getattr(contract, "task_id", None)
    if not isinstance(task_id, str):
        raise ValueError("temporal-review v6 contract must declare task_id")
    payload = summary.get("payload")
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    unexpected = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected, list) or not all(isinstance(name, str) for name in unexpected):
        unexpected = []
    raw_events = summary.get("raw_branch_diff_events")
    if not isinstance(raw_events, list):
        raw_events = []
    parsed_events = [
        {**event, "observation": module.parse_raw_response(task_id, event.get("raw_response"))}
        for event in raw_events
        if isinstance(event, dict)
    ]
    final_result_event_index = summary.get("final_result_event_index")
    eligible_events = [
        event for event in parsed_events
        if isinstance(final_result_event_index, int)
        and isinstance(event.get("stream_event_index"), int)
        and event["stream_event_index"] < final_result_event_index
    ]
    valid_events = [
        event for event in eligible_events
        if isinstance(event.get("observation"), dict) and event["observation"].get("valid") is True
    ]
    selected = valid_events[-1] if condition == "treatment" and valid_events else None
    if condition == "baseline":
        outcome = module.evaluate_answer(task_id, payload, condition=condition, source_root=source_dir)
    elif selected is not None:
        outcome = module.evaluate_answer(
            task_id,
            payload,
            condition=condition,
            source_root=source_dir,
            raw_response=selected.get("raw_response"),
        )
    else:
        outcome = None
    answer_oracle = {"passed": bool(outcome.passed), "failures": list(outcome.failures)} if outcome else None
    selected_observation = selected.get("observation") if isinstance(selected, dict) else None
    certificate = (
        {
            "selected_raw_event_index": selected.get("stream_event_index"),
            "tool_use_id": selected.get("tool_use_id"),
            "raw_sha256": selected.get("raw_sha256"),
            "comparison": selected_observation.get("comparison"),
            "raw_valid": True,
            "source": "adapter_raw_branch_diff",
        }
        if isinstance(selected, dict) and isinstance(selected_observation, dict)
        else None
    )
    invalid_reason: str | None = None
    hard_protocol_stop = False
    if not source_clean:
        status, invalid_reason, hard_protocol_stop = "invalid_source_mutation", "source_mutation", True
    elif return_code != 0:
        status, invalid_reason, hard_protocol_stop = "agent_error", "agent_return_code_nonzero", True
    elif summary.get("final_result_seen") is not True or not isinstance(payload, dict):
        status, invalid_reason = "missing_or_invalid_agent_response", "temporal_schema_invalid"
    elif unexpected:
        status, invalid_reason, hard_protocol_stop = "unexpected_mcp_tool", "unexpected_mcp_tool", True
    elif condition == "treatment" and not raw_events:
        status, invalid_reason, hard_protocol_stop = "missing_treatment_comparison_evidence", "no_branch_diff_response", True
    elif condition == "treatment" and len(eligible_events) != len(parsed_events):
        status, invalid_reason, hard_protocol_stop = (
            "invalid_treatment_comparison_certificate", "branch_diff_response_after_final_result", True
        )
    elif condition == "treatment" and len(valid_events) != len(eligible_events):
        status, invalid_reason, hard_protocol_stop = (
            "invalid_treatment_comparison_certificate", "raw_ref_backend_or_l2_mismatch", True
        )
    elif condition == "treatment" and selected is None:
        status, invalid_reason, hard_protocol_stop = (
            "missing_treatment_comparison_evidence", "no_valid_branch_diff_response", True
        )
    elif answer_oracle is None or answer_oracle["passed"] is not True:
        status, invalid_reason = "task_review_oracle_failed", "task_specific_oracle_mismatch"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "protocol": TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE,
        "status": status,
        "invalid_reason": invalid_reason,
        "hard_protocol_stop": hard_protocol_stop,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "decision": payload.get("decision") if isinstance(payload, dict) else None,
        "review_locus": payload.get("review_locus") if isinstance(payload, dict) else None,
        "trust_observation": {
            "raw_branch_diff_events": parsed_events,
            "valid_raw_branch_diff_count": len(valid_events),
            "selected_certificate": certificate,
        },
        "task_review_observation": answer_oracle,
        "tool_call_count": len(tool_names),
        "tool_call_names": tool_names,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {
            "requested": requested_model,
            "observed": summary.get("observed_models", []),
            "assistant_observed": summary.get("assistant_models", []),
            "session_observed": summary.get("session_models", []),
            "usage_observed": summary.get("usage_models", []),
        },
        "tooling": {
            "loomgraph": {
                "used": TEMPORAL_MCP_TOOL in tool_names,
                "tools": [name for name in tool_names if name == TEMPORAL_MCP_TOOL],
                "unexpected_tools": unexpected,
            }
        },
    }


def build_temporal_review_v7_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    source_dir: Path,
    return_code: int,
    summary: dict[str, object],
    contract: object,
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
    fixture_module: Any | None = None,
    protocol: str = TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE,
) -> dict[str, Any]:
    """Build independent one-locus v7 evidence from the retained raw stream."""
    module = fixture_module or _load_temporal_review_v7_module()
    task_id = getattr(contract, "task_id", None)
    if not isinstance(task_id, str):
        raise ValueError("temporal-review v7 contract must declare task_id")
    payload = summary.get("payload")
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    unexpected = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected, list) or not all(isinstance(name, str) for name in unexpected):
        unexpected = []
    raw_events = summary.get("raw_branch_diff_events")
    if not isinstance(raw_events, list):
        raw_events = []
    parsed_events = [
        {**event, "observation": module.parse_raw_response(task_id, event.get("raw_response"))}
        for event in raw_events
        if isinstance(event, dict)
    ]
    final_result_event_index = summary.get("final_result_event_index")
    eligible_events = [
        event for event in parsed_events
        if isinstance(final_result_event_index, int)
        and isinstance(event.get("stream_event_index"), int)
        and event["stream_event_index"] < final_result_event_index
    ]
    valid_events = [
        event for event in eligible_events
        if isinstance(event.get("observation"), dict) and event["observation"].get("valid") is True
    ]
    selected = valid_events[-1] if condition == "treatment" and valid_events else None
    if condition == "baseline":
        outcome = module.evaluate_answer(task_id, payload, condition=condition, source_root=source_dir)
    elif selected is not None:
        outcome = module.evaluate_answer(
            task_id,
            payload,
            condition=condition,
            source_root=source_dir,
            raw_response=selected.get("raw_response"),
        )
    else:
        outcome = None
    answer_oracle = {"passed": bool(outcome.passed), "failures": list(outcome.failures)} if outcome else None
    selected_observation = selected.get("observation") if isinstance(selected, dict) else None
    certificate = (
        {
            "selected_raw_event_index": selected.get("stream_event_index"),
            "tool_use_id": selected.get("tool_use_id"),
            "raw_sha256": selected.get("raw_sha256"),
            "comparison": selected_observation.get("comparison"),
            "raw_valid": True,
            "source": "adapter_raw_branch_diff",
        }
        if isinstance(selected, dict) and isinstance(selected_observation, dict)
        else None
    )
    invalid_reason: str | None = None
    hard_protocol_stop = False
    model_categories_valid = summary.get("model_categories_valid") is True
    if not source_clean:
        status, invalid_reason, hard_protocol_stop = "invalid_source_mutation", "source_mutation", True
    elif return_code != 0:
        status, invalid_reason, hard_protocol_stop = "agent_error", "agent_return_code_nonzero", True
    elif summary.get("final_result_seen") is not True or not isinstance(payload, dict):
        status, invalid_reason = "missing_or_invalid_agent_response", "temporal_schema_invalid"
    elif not model_categories_valid:
        status, invalid_reason, hard_protocol_stop = (
            "invalid_model_identity_evidence", "model_identity_raw_labels_invalid", True
        )
    elif unexpected:
        status, invalid_reason, hard_protocol_stop = "unexpected_mcp_tool", "unexpected_mcp_tool", True
    elif condition == "treatment" and not raw_events:
        status, invalid_reason, hard_protocol_stop = "missing_treatment_comparison_evidence", "no_branch_diff_response", True
    elif condition == "treatment" and len(eligible_events) != len(parsed_events):
        status, invalid_reason, hard_protocol_stop = (
            "invalid_treatment_comparison_certificate", "branch_diff_response_after_final_result", True
        )
    elif condition == "treatment" and len(valid_events) != len(eligible_events):
        status, invalid_reason, hard_protocol_stop = (
            "invalid_treatment_comparison_certificate", "raw_ref_backend_or_l2_mismatch", True
        )
    elif condition == "treatment" and selected is None:
        status, invalid_reason, hard_protocol_stop = (
            "missing_treatment_comparison_evidence", "no_valid_branch_diff_response", True
        )
    elif answer_oracle is None or answer_oracle["passed"] is not True:
        status, invalid_reason = "task_review_oracle_failed", "task_specific_oracle_mismatch"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "protocol": protocol,
        "status": status,
        "invalid_reason": invalid_reason,
        "hard_protocol_stop": hard_protocol_stop,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": protocol,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "decision": payload.get("decision") if isinstance(payload, dict) else None,
        "review_locus": payload.get("review_locus") if isinstance(payload, dict) else None,
        "trust_observation": {
            "raw_branch_diff_events": parsed_events,
            "valid_raw_branch_diff_count": len(valid_events),
            "selected_certificate": certificate,
        },
        "task_review_observation": answer_oracle,
        "tool_call_count": len(tool_names),
        "tool_call_names": tool_names,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {
            "requested": requested_model,
            "observed": summary.get("observed_models", []),
            "assistant_models_raw": summary.get("assistant_models_raw", []),
            "session_models_raw": summary.get("session_models_raw", []),
            "usage_models_raw": summary.get("usage_models_raw", []),
            "assistant_models_canonical": summary.get("assistant_models_canonical", []),
            "session_models_canonical": summary.get("session_models_canonical", []),
            "usage_models_canonical": summary.get("usage_models_canonical", []),
            "raw_categories_valid": model_categories_valid,
        },
        "tooling": {
            "loomgraph": {
                "used": TEMPORAL_MCP_TOOL in tool_names,
                "tools": [name for name in tool_names if name == TEMPORAL_MCP_TOOL],
                "unexpected_tools": unexpected,
            }
        },
    }


def summarize_temporal_review_v8_stream(events: list[dict[str, Any]]) -> dict[str, object]:
    """V8 retains raw model occurrences and separately attests their validity."""
    return {
        **summarize_stream(events, TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE),
        **_v7_model_categories(events),
    }


def build_temporal_review_v8_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    source_dir: Path,
    return_code: int,
    summary: dict[str, object],
    contract: object,
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
) -> dict[str, Any]:
    """Build V8 evidence; V7 logic is reused only with its default disabled."""
    packet = build_temporal_review_v7_packet(
        condition=condition,
        use_mode=use_mode,
        source_clean=source_clean,
        source_dir=source_dir,
        return_code=return_code,
        summary=summary,
        contract=contract,
        requested_model=requested_model,
        agent_execution_seconds=agent_execution_seconds,
        fixture_module=_load_temporal_review_v8_module(),
        protocol=TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE,
    )
    model_evidence = packet.get("model")
    if isinstance(model_evidence, dict):
        model_evidence["model_categories_valid"] = summary.get("model_categories_valid") is True
    return packet


def build_temporal_review_v2_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    source_dir: Path,
    return_code: int,
    summary: dict[str, object],
    contract: object,
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
) -> dict[str, Any]:
    """Build an independently-scored v2 review packet from immutable run data."""
    module = _load_temporal_review_v2_module()
    task_id = getattr(contract, "task_id", None)
    if not isinstance(task_id, str):
        raise ValueError("temporal-review v2 contract must declare task_id")
    payload = summary.get("payload")
    raw_responses = summary.get("raw_branch_diff_responses")
    if not isinstance(raw_responses, list):
        raw_responses = []
    observations = [module.parse_raw_response(task_id, raw) for raw in raw_responses]
    valid_observations = [observation for observation in observations if observation["valid"]]
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    unexpected = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected, list) or not all(isinstance(name, str) for name in unexpected):
        unexpected = []
    raw_aligned = any(
        _temporal_review_trust_matches_raw(payload, observation) for observation in valid_observations
    )
    if condition == "baseline":
        outcome = module.evaluate_answer(task_id, payload, condition=condition, source_root=source_dir)
    else:
        outcomes = [
            module.evaluate_answer(
                task_id, payload, condition=condition, source_root=source_dir, raw_response=raw
            )
            for raw in raw_responses
        ]
        outcome = next((value for value in outcomes if value.passed), outcomes[0] if outcomes else None)
    answer_oracle = (
        {"passed": bool(outcome.passed), "failures": list(outcome.failures)}
        if outcome is not None
        else None
    )
    invalid_reason: str | None = None
    if not source_clean:
        status, invalid_reason = "invalid_source_mutation", "source_mutation"
    elif return_code != 0:
        status, invalid_reason = "agent_error", "agent_return_code_nonzero"
    elif summary.get("final_result_seen") is not True or not isinstance(payload, dict):
        status, invalid_reason = "missing_or_invalid_agent_response", "temporal_schema_invalid"
    elif len(tool_names) > TOOL_CALL_BUDGET:
        status, invalid_reason = "tool_call_budget_exceeded", "tool_call_budget_exceeded"
    elif unexpected:
        status, invalid_reason = "unexpected_mcp_tool", "unexpected_mcp_tool"
    elif condition == "treatment" and not valid_observations:
        status, invalid_reason = "missing_treatment_comparison_evidence", "no_valid_branch_diff_response"
    elif condition == "treatment" and not raw_aligned:
        status, invalid_reason = "unverified_treatment_comparison_trust", "model_raw_comparison_mismatch"
    elif answer_oracle is None or answer_oracle["passed"] is not True:
        status, invalid_reason = "task_review_oracle_failed", "task_specific_oracle_mismatch"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "protocol": TEMPORAL_REVIEW_V2_ADDITIVE_SURFACE,
        "status": status,
        "invalid_reason": invalid_reason,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": TEMPORAL_REVIEW_V2_ADDITIVE_SURFACE,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "decision": payload.get("decision") if isinstance(payload, dict) else None,
        "review_loci": payload.get("review_loci", []) if isinstance(payload, dict) else [],
        "trust": payload.get("trust") if isinstance(payload, dict) else None,
        "trust_observation": {
            "raw_branch_diff_responses": raw_responses,
            "raw_branch_diff_observations": observations,
            "raw_comparison_aligned": raw_aligned,
            "valid_raw_branch_diff_count": len(valid_observations),
        },
        "task_review_observation": answer_oracle,
        "tool_call_count": len(tool_names),
        "tool_call_budget": TOOL_CALL_BUDGET,
        "tool_call_budget_overrun": len(tool_names) > TOOL_CALL_BUDGET,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {"requested": requested_model, "observed": summary.get("observed_models", [])},
        "tooling": {
            "loomgraph": {
                "used": TEMPORAL_MCP_TOOL in tool_names,
                "tools": [name for name in tool_names if name == TEMPORAL_MCP_TOOL],
                "unexpected_tools": unexpected,
            }
        },
    }


def build_temporal_review_packet(
    *,
    condition: str,
    use_mode: str,
    source_clean: bool,
    return_code: int,
    summary: dict[str, object],
    contract: object,
    requested_model: str = "",
    agent_execution_seconds: float | None = None,
) -> dict[str, Any]:
    """Build one product-review packet using its adapter-owned contract."""
    module = _load_temporal_review_module()
    task_id = getattr(contract, "task_id", None)
    if not isinstance(task_id, str):
        raise ValueError("temporal-review contract must declare task_id")
    payload = summary.get("payload")
    raw_responses = summary.get("raw_branch_diff_responses")
    if not isinstance(raw_responses, list):
        raw_responses = []
    observations = [module.parse_temporal_review_raw_response(task_id, raw) for raw in raw_responses]
    valid_observations = [observation for observation in observations if observation["valid"]]
    tool_names = summary.get("tool_names")
    if not isinstance(tool_names, list) or not all(isinstance(name, str) for name in tool_names):
        tool_names = []
    branch_tools = [name for name in tool_names if name == TEMPORAL_MCP_TOOL]
    unexpected = summary.get("unexpected_mcp_tools")
    if not isinstance(unexpected, list) or not all(isinstance(name, str) for name in unexpected):
        unexpected = []
    budget_overrun = len(tool_names) > TOOL_CALL_BUDGET

    answer_oracle: dict[str, object] | None = None
    model_comparison_aligned = False
    if condition == "baseline":
        outcome = module.evaluate_temporal_review_answer(payload, condition, task_id)
        answer_oracle = {"passed": bool(outcome.passed), "failures": list(outcome.failures)}
    else:
        outcomes = [
            module.evaluate_temporal_review_answer(payload, condition, task_id, raw)
            for raw in raw_responses
        ]
        model_comparison_aligned = any(
            _temporal_review_trust_matches_raw(payload, observation)
            for observation in valid_observations
        )
        successful = next((outcome for outcome in outcomes if outcome.passed), None)
        if successful is not None:
            answer_oracle = {"passed": True, "failures": []}
        elif outcomes:
            answer_oracle = {
                "passed": False,
                "failures": list(outcomes[0].failures),
            }

    invalid_reason: str | None = None
    if not source_clean:
        status, invalid_reason = "invalid_source_mutation", "source_mutation"
    elif return_code != 0:
        status, invalid_reason = "agent_error", "agent_return_code_nonzero"
    elif summary.get("final_result_seen") is not True or not isinstance(payload, dict):
        status, invalid_reason = "missing_or_invalid_agent_response", "temporal_schema_invalid"
    elif budget_overrun:
        status, invalid_reason = "tool_call_budget_exceeded", "tool_call_budget_exceeded"
    elif unexpected:
        status, invalid_reason = "unexpected_mcp_tool", "unexpected_mcp_tool"
    elif condition == "baseline":
        if answer_oracle is None or answer_oracle["passed"] is not True:
            status, invalid_reason = "task_review_oracle_failed", "task_specific_oracle_mismatch"
        else:
            status = "complete"
    elif not valid_observations:
        status, invalid_reason = (
            "missing_treatment_comparison_evidence",
            "no_valid_branch_diff_response",
        )
    elif not model_comparison_aligned:
        status, invalid_reason = (
            "unverified_treatment_comparison_trust",
            "model_raw_comparison_mismatch",
        )
    elif answer_oracle is None or answer_oracle["passed"] is not True:
        status, invalid_reason = "task_review_oracle_failed", "task_specific_oracle_mismatch"
    else:
        status = "complete"
    return {
        "schema_version": 3,
        "protocol": TEMPORAL_REVIEW_ADDITIVE_SURFACE,
        "status": status,
        "invalid_reason": invalid_reason,
        "condition": condition,
        "orientation_mode": use_mode,
        "navigation_surface": TEMPORAL_REVIEW_ADDITIVE_SURFACE,
        "pre_edit": source_clean,
        "source_clean": source_clean,
        "source_clean_scope": "model_phase",
        "response_format": "json_schema",
        "semantic_packet": status == "complete",
        "decision": payload.get("decision") if isinstance(payload, dict) else None,
        "review_loci": payload.get("review_loci", []) if isinstance(payload, dict) else [],
        "trust": payload.get("trust") if isinstance(payload, dict) else None,
        "trust_observation": {
            "raw_branch_diff_responses": raw_responses,
            "raw_branch_diff_observations": observations,
            "raw_comparison_aligned": model_comparison_aligned,
            "valid_raw_branch_diff_count": len(valid_observations),
        },
        "task_review_observation": answer_oracle,
        "tool_call_count": len(tool_names),
        "tool_call_budget": TOOL_CALL_BUDGET,
        "tool_call_budget_overrun": budget_overrun,
        "agent_execution_seconds": agent_execution_seconds,
        "model": {
            "requested": requested_model,
            "observed": summary.get("observed_models", []),
            "assistant_observed": summary.get("assistant_models", []),
            "session_observed": summary.get("session_models", []),
            "usage_observed": summary.get("usage_models", []),
        },
        "tooling": {
            "loomgraph": {
                "used": bool(branch_tools),
                "tools": branch_tools,
                "unexpected_tools": unexpected,
            }
        },
    }


def _append_mode_requirement(instruction: str, use_mode: str) -> str:
    if use_mode == "voluntary":
        return instruction
    if use_mode == "assisted":
        navigation_limit = TOOL_CALL_BUDGET - 1
        return (
            f"{instruction}\n\nUse at least one available navigation tool before responding. "
            f"Use at most {navigation_limit} navigation tool calls; reserve one tool call "
            "for the required structured response."
        )
    raise ValueError(f"unknown use mode: {use_mode}")


def _append_temporal_protocol_requirement(instruction: str, condition: str) -> str:
    """Make the model-facing contract match adapter-owned raw comparison evidence."""
    if condition == "baseline":
        return (
            f"{instruction}\n\nNo comparison tool is available in this condition. In the JSON "
            "trust object, set availability to unavailable and comparison to null. Use at most "
            "four navigation calls; reserve one call for structured output."
        )
    if condition == "treatment":
        return (
            f"{instruction}\n\nUse the branch-diff tool before responding. In the JSON trust "
            "comparison, copy the returned ref, backend, and provisioning fields exactly. An available "
            "raw comparison may omit reason; represent that adapter-normalized absence as null. Do not "
            "replace fields with prose or display labels. "
            "Use at most four navigation calls; reserve one call for structured output."
        )
    raise ValueError(f"unknown condition: {condition}")


def _append_temporal_review_v3_requirement(instruction: str, condition: str) -> str:
    """Append only the v3 observable-tool rule, never raw trust fields."""
    if condition == "baseline":
        return (
            f"{instruction}\n\nNo comparison tool is available in this condition. "
            "Use at most four navigation calls; reserve one call for structured output."
        )
    if condition == "treatment":
        return (
            f"{instruction}\n\nUse the branch-diff tool before responding. Do not copy its "
            "raw response, identifiers, backend details, provisioning, status, or reason into the "
            "structured response. Use at most four navigation calls; reserve one call for structured output."
        )
    raise ValueError(f"unknown condition: {condition}")


def _append_temporal_review_v4_requirement(instruction: str, condition: str) -> str:
    """Append the public v4 comparison boundary requirement only."""
    if condition == "baseline":
        return (
            f"{instruction}\n\nNo comparison tool is available in this condition. Set decision.boundary "
            "to comparison_not_observed. Use at most four navigation calls; reserve one call for structured output."
        )
    if condition == "treatment":
        return (
            f"{instruction}\n\nUse the branch-diff tool before responding. Set decision.boundary from whether "
            "the tool makes content comparison available. Do not copy raw response, identifiers, backend details, "
            "provisioning, status, or reason into the structured response. Use at most four navigation calls; "
            "reserve one call for structured output."
        )
    raise ValueError(f"unknown condition: {condition}")


def _append_temporal_review_v5_requirement(instruction: str, condition: str) -> str:
    """Append v5's public boundary rule without an agent tool-call cap."""
    if condition == "baseline":
        return (
            f"{instruction}\n\nNo comparison tool is available in this condition. Set decision.boundary "
            "to comparison_not_observed."
        )
    if condition == "treatment":
        return (
            f"{instruction}\n\nUse the branch-diff tool before responding. Set decision.boundary from whether "
            "the tool makes content comparison available. Do not copy raw response, identifiers, backend details, "
            "provisioning, status, or reason into the structured response."
        )
    raise ValueError(f"unknown condition: {condition}")


def _append_temporal_review_v6_requirement(instruction: str, condition: str) -> str:
    """Append the v6 one-locus boundary rule without a tool-count limit."""
    if condition == "baseline":
        return (
            f"{instruction}\n\nNo comparison tool is available in this condition. Set decision.boundary "
            "to comparison_not_observed."
        )
    if condition == "treatment":
        return (
            f"{instruction}\n\nUse the branch-diff tool before responding. Set decision.boundary from whether "
            "the tool makes content comparison available. Do not copy raw response, identifiers, backend details, "
            "provisioning, status, or reason into the structured response."
        )
    raise ValueError(f"unknown condition: {condition}")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(args: argparse.Namespace) -> int:
    source_dir = args.source_dir.resolve()
    if not source_dir.is_dir():
        raise ValueError(f"source directory does not exist: {source_dir}")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    storage_root = (args.storage_root or output_dir / "loomgraph-storage").resolve()
    before = _repo_state(source_dir)
    if before["porcelain"]:
        raise ValueError("source directory must be clean before the model phase")

    temporal_review_contract: object | None = None
    temporal_review_v2_contract: object | None = None
    temporal_review_v3_contract: object | None = None
    temporal_review_v4_contract: object | None = None
    temporal_review_v5_contract: object | None = None
    temporal_review_v6_contract: object | None = None
    temporal_review_v7_contract: object | None = None
    temporal_review_v8_contract: object | None = None
    if args.temporal_review_contract:
        if args.treatment_surface != TEMPORAL_REVIEW_ADDITIVE_SURFACE:
            raise ValueError("temporal-review contract requires the temporal-review-additive surface")
        temporal_review_contract = _load_temporal_review_contract(args.task_id)
    if args.temporal_review_v2_contract:
        if args.temporal_review_contract:
            raise ValueError("temporal-review v1 and v2 contracts are mutually exclusive")
        if args.treatment_surface != TEMPORAL_REVIEW_V2_ADDITIVE_SURFACE:
            raise ValueError("temporal-review v2 contract requires the temporal-review-v2-additive surface")
        temporal_review_v2_contract = _load_temporal_review_v2_contract(args.task_id)
    if args.temporal_review_v3_contract:
        if args.temporal_review_contract or args.temporal_review_v2_contract:
            raise ValueError("temporal-review contracts are mutually exclusive")
        if args.treatment_surface != TEMPORAL_REVIEW_V3_ADDITIVE_SURFACE:
            raise ValueError("temporal-review v3 contract requires the v3 adapter-trust surface")
        temporal_review_v3_contract = _load_temporal_review_v3_contract(args.task_id)
    if args.temporal_review_v4_contract:
        if args.temporal_review_contract or args.temporal_review_v2_contract or args.temporal_review_v3_contract:
            raise ValueError("temporal-review contracts are mutually exclusive")
        if args.treatment_surface != TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE:
            raise ValueError("temporal-review v4 contract requires the v4 navigation-evidence surface")
        temporal_review_v4_contract = _load_temporal_review_v4_contract(args.task_id)
    if args.temporal_review_v5_contract:
        if any((args.temporal_review_contract, args.temporal_review_v2_contract, args.temporal_review_v3_contract, args.temporal_review_v4_contract)):
            raise ValueError("temporal-review contracts are mutually exclusive")
        if args.treatment_surface != TEMPORAL_REVIEW_V5_ADDITIVE_SURFACE:
            raise ValueError("temporal-review v5 contract requires the v5 navigation-evidence surface")
        temporal_review_v5_contract = _load_temporal_review_v5_contract(args.task_id)
    if args.temporal_review_v6_contract:
        if any((
            args.temporal_review_contract,
            args.temporal_review_v2_contract,
            args.temporal_review_v3_contract,
            args.temporal_review_v4_contract,
            args.temporal_review_v5_contract,
        )):
            raise ValueError("temporal-review contracts are mutually exclusive")
        if args.treatment_surface != TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE:
            raise ValueError("temporal-review v6 contract requires the v6 navigation-evidence surface")
        temporal_review_v6_contract = _load_temporal_review_v6_contract(args.task_id)
    if args.temporal_review_v7_contract:
        if any((
            args.temporal_review_contract,
            args.temporal_review_v2_contract,
            args.temporal_review_v3_contract,
            args.temporal_review_v4_contract,
            args.temporal_review_v5_contract,
            args.temporal_review_v6_contract,
        )):
            raise ValueError("temporal-review contracts are mutually exclusive")
        if args.treatment_surface != TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE:
            raise ValueError("temporal-review v7 contract requires the v7 primary-navigation surface")
        temporal_review_v7_contract = _load_temporal_review_v7_contract(args.task_id)
    if args.temporal_review_v8_contract:
        if any((
            args.temporal_review_contract,
            args.temporal_review_v2_contract,
            args.temporal_review_v3_contract,
            args.temporal_review_v4_contract,
            args.temporal_review_v5_contract,
            args.temporal_review_v6_contract,
            args.temporal_review_v7_contract,
        )):
            raise ValueError("temporal-review contracts are mutually exclusive")
        if args.treatment_surface != TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE:
            raise ValueError("temporal-review v8 contract requires the v8 primary-navigation surface")
        temporal_review_v8_contract = _load_temporal_review_v8_contract(args.task_id)

    instruction = _append_mode_requirement(args.instruction_file.read_text(), args.use_mode)
    if temporal_review_v8_contract is not None or temporal_review_v7_contract is not None or temporal_review_v6_contract is not None:
        instruction = _append_temporal_review_v6_requirement(instruction, args.condition)
    elif temporal_review_v5_contract is not None:
        instruction = _append_temporal_review_v5_requirement(instruction, args.condition)
    elif temporal_review_v4_contract is not None:
        instruction = _append_temporal_review_v4_requirement(instruction, args.condition)
    elif temporal_review_v3_contract is not None:
        instruction = _append_temporal_review_v3_requirement(instruction, args.condition)
    elif _is_temporal_surface(args.treatment_surface):
        instruction = _append_temporal_protocol_requirement(instruction, args.condition)
    command = build_command(
        condition=args.condition,
        instruction=instruction,
        model=args.model,
        budget_usd=args.max_budget_usd,
        loomgraph_binary=args.loomgraph_binary,
        treatment_surface=args.treatment_surface,
        require_trust=args.require_trust,
        storage_root=storage_root if args.condition == "treatment" else None,
        temporal_review=temporal_review_contract is not None,
        temporal_review_v2=temporal_review_v2_contract is not None,
        temporal_review_v3=temporal_review_v3_contract is not None,
        temporal_review_v4=temporal_review_v4_contract is not None,
        temporal_review_v5=temporal_review_v5_contract is not None,
        temporal_review_v6=temporal_review_v6_contract is not None,
        temporal_review_v7=temporal_review_v7_contract is not None,
        temporal_review_v8=temporal_review_v8_contract is not None,
    )
    _write_json(output_dir / "command.json", command)

    events: list[dict[str, Any]] = []
    started_at = time.monotonic()
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
    agent_execution_seconds = time.monotonic() - started_at

    after = _repo_state(source_dir)
    source_clean = before == after and not after["porcelain"]
    summary = (
        summarize_temporal_review_v8_stream(events)
        if args.treatment_surface == TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE
        else summarize_temporal_review_v7_stream(events)
        if args.treatment_surface == TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE
        else summarize_stream(events, args.treatment_surface)
    )
    if args.treatment_surface == TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE:
        if temporal_review_v8_contract is None:
            raise ValueError("temporal-review v8 surface requires a temporal-review v8 contract")
        packet = build_temporal_review_v8_packet(
            condition=args.condition,
            use_mode=args.use_mode,
            source_clean=source_clean,
            source_dir=source_dir,
            return_code=return_code,
            summary=summary,
            contract=temporal_review_v8_contract,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    elif args.treatment_surface == TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE:
        if temporal_review_v7_contract is None:
            raise ValueError("temporal-review v7 surface requires a temporal-review v7 contract")
        packet = build_temporal_review_v7_packet(
            condition=args.condition,
            use_mode=args.use_mode,
            source_clean=source_clean,
            source_dir=source_dir,
            return_code=return_code,
            summary=summary,
            contract=temporal_review_v7_contract,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    elif args.treatment_surface == TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE:
        if temporal_review_v6_contract is None:
            raise ValueError("temporal-review v6 surface requires a temporal-review v6 contract")
        packet = build_temporal_review_v6_packet(
            condition=args.condition,
            use_mode=args.use_mode,
            source_clean=source_clean,
            source_dir=source_dir,
            return_code=return_code,
            summary=summary,
            contract=temporal_review_v6_contract,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    elif args.treatment_surface == TEMPORAL_REVIEW_V5_ADDITIVE_SURFACE:
        if temporal_review_v5_contract is None:
            raise ValueError("temporal-review v5 surface requires a temporal-review v5 contract")
        packet = build_temporal_review_v5_packet(
            condition=args.condition,
            use_mode=args.use_mode,
            source_clean=source_clean,
            source_dir=source_dir,
            return_code=return_code,
            summary=summary,
            contract=temporal_review_v5_contract,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    elif args.treatment_surface == TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE:
        if temporal_review_v4_contract is None:
            raise ValueError("temporal-review v4 surface requires a temporal-review v4 contract")
        packet = build_temporal_review_v4_packet(
            condition=args.condition,
            use_mode=args.use_mode,
            source_clean=source_clean,
            source_dir=source_dir,
            return_code=return_code,
            summary=summary,
            contract=temporal_review_v4_contract,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    elif args.treatment_surface == TEMPORAL_REVIEW_V3_ADDITIVE_SURFACE:
        if temporal_review_v3_contract is None:
            raise ValueError("temporal-review v3 surface requires a temporal-review v3 contract")
        packet = build_temporal_review_v3_packet(
            condition=args.condition,
            use_mode=args.use_mode,
            source_clean=source_clean,
            source_dir=source_dir,
            return_code=return_code,
            summary=summary,
            contract=temporal_review_v3_contract,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    elif args.treatment_surface == TEMPORAL_REVIEW_V2_ADDITIVE_SURFACE:
        if temporal_review_v2_contract is None:
            raise ValueError("temporal-review v2 surface requires a temporal-review v2 contract")
        packet = build_temporal_review_v2_packet(
            condition=args.condition,
            use_mode=args.use_mode,
            source_clean=source_clean,
            source_dir=source_dir,
            return_code=return_code,
            summary=summary,
            contract=temporal_review_v2_contract,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    elif args.treatment_surface == TEMPORAL_REVIEW_ADDITIVE_SURFACE:
        if temporal_review_contract is None:
            raise ValueError("temporal-review surface requires a temporal-review contract")
        packet = build_temporal_review_packet(
            condition=args.condition, use_mode=args.use_mode, source_clean=source_clean,
            return_code=return_code, summary=summary,
            contract=temporal_review_contract,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    elif args.treatment_surface == TEMPORAL_ADDITIVE_SURFACE:
        packet = build_temporal_packet(
            condition=args.condition, use_mode=args.use_mode, source_clean=source_clean,
            return_code=return_code, summary=summary,
            requested_model=args.model,
            agent_execution_seconds=agent_execution_seconds,
        )
        packet["adapter_storage"] = {
            "root": str(storage_root),
            "db_path_pattern": str(storage_root / "{workspace}.db"),
        }
    else:
        summary["payload"] = normalize_candidate_paths(summary.get("payload"), source_dir)
        packet = build_packet(
            condition=args.condition,
            use_mode=args.use_mode,
            source_clean=source_clean,
            return_code=return_code,
            summary=summary,
            requested_model=args.model,
            navigation_surface=(args.treatment_surface if args.condition == "treatment" else "text-only"),
            require_trust=args.require_trust,
            agent_execution_seconds=agent_execution_seconds,
            tool_call_budget=args.tool_call_budget,
        )
        fixture_observation = score_agent_use_fixture(args.task_id, packet["candidates"])
        if fixture_observation is not None:
            packet["fixture_observation"] = fixture_observation
    _write_json(output_dir / "pre-state.json", before)
    _write_json(output_dir / "post-state.json", after)
    _write_json(output_dir / "final-result.json", summary["final_result"])
    _write_json(output_dir / "orientation.json", packet)
    _write_json(
        output_dir / "run.json",
        {
            "return_code": return_code,
            "final_result_seen": summary["final_result_seen"],
            "agent_execution_seconds": agent_execution_seconds,
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
    parser.add_argument(
        "--storage-root",
        type=Path,
        help="Adapter-owned LoomGraph storage; reuse only for an explicit warm repeat.",
    )
    parser.add_argument("--use-mode", choices=("voluntary", "assisted"), default="voluntary")
    parser.add_argument(
        "--treatment-surface",
        choices=(
            "mcp-only",
            "additive",
            TEMPORAL_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V2_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V3_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V4_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V5_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V6_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V7_ADDITIVE_SURFACE,
            TEMPORAL_REVIEW_V8_ADDITIVE_SURFACE,
        ),
        default="mcp-only",
        help="Treatment navigation surface; baseline is always text-only.",
    )
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-budget-usd", default="0.50")
    parser.add_argument("--tool-call-budget", type=int, default=TOOL_CALL_BUDGET)
    parser.add_argument(
        "--require-trust",
        action="store_true",
        help="Require edge and resolution trust fields in the structured response.",
    )
    parser.add_argument("--loomgraph-binary", default="loomgraph")
    parser.add_argument(
        "--temporal-review-contract",
        action="store_true",
        help="Load the adapter-owned temporal-review task contract for --task-id.",
    )
    parser.add_argument(
        "--temporal-review-v2-contract",
        action="store_true",
        help="Load the separately preregistered temporal-review v2 task contract.",
    )
    parser.add_argument(
        "--temporal-review-v3-contract",
        action="store_true",
        help="Load the independent v3 adapter-observed temporal-review contract.",
    )
    parser.add_argument(
        "--temporal-review-v4-contract",
        action="store_true",
        help="Load the independent v4 navigation-evidence contract.",
    )
    parser.add_argument(
        "--temporal-review-v5-contract",
        action="store_true",
        help="Load the independent v5 navigation-evidence contract.",
    )
    parser.add_argument(
        "--temporal-review-v6-contract",
        action="store_true",
        help="Load the independent v6 one-locus navigation-evidence contract.",
    )
    parser.add_argument(
        "--temporal-review-v7-contract",
        action="store_true",
        help="Load the independent v7 one-locus primary-navigation contract.",
    )
    parser.add_argument(
        "--temporal-review-v8-contract",
        action="store_true",
        help="Load the independent v8 one-locus primary-navigation contract.",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
