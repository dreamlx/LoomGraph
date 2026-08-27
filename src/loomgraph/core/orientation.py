"""Deterministic, read-only policy for an agent's first navigation step."""

from __future__ import annotations

from typing import Any

_POLICY_BUDGETS = {
    "economy": {"max_entities": 3, "max_relation_hops": 1},
    "balanced": {"max_entities": 6, "max_relation_hops": 2},
    "deep": {"max_entities": 12, "max_relation_hops": 3},
}


def _result(
    *,
    task_kind: str,
    policy: str,
    recommended_path: str,
    availability: str,
    tool_surface: list[str],
    required_evidence: list[str],
    fallback: dict[str, str] | None,
    readiness: dict[str, str],
    execution_boundary: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_kind": task_kind,
        "policy": policy,
        "recommended_path": recommended_path,
        "availability": availability,
        "tool_surface": tool_surface,
        "evidence_budget": dict(_POLICY_BUDGETS[policy]),
        "required_evidence": required_evidence,
        "fallback": fallback,
        "readiness": readiness,
        "execution_boundary": execution_boundary,
    }


def decide_orientation(
    *,
    task_kind: str,
    policy: str,
    codeindex_available: bool,
    git_repository: bool,
    refs_resolved: bool,
) -> dict[str, Any]:
    """Select the smallest evidence path without invoking a provider.

    Availability facts are supplied by the CLI or host adapter. This function
    intentionally never opens a graph store, creates an index, or calls tools.
    """
    if policy not in _POLICY_BUDGETS:
        raise ValueError(f"unsupported orientation policy: {policy}")
    if task_kind == "local":
        return _result(
            task_kind=task_kind,
            policy=policy,
            recommended_path="native",
            availability="available",
            tool_surface=["agent_native_read", "agent_native_grep"],
            required_evidence=[],
            fallback=None,
            readiness={"agent_native_tools": "available"},
            execution_boundary={"orientation": "read_only", "recommended_path": "read_only"},
        )
    if task_kind == "cross-file":
        if codeindex_available:
            return _result(
                task_kind=task_kind,
                policy=policy,
                recommended_path="light",
                availability="conditional",
                tool_surface=["loomgraph_find", "loomgraph_graph"],
                required_evidence=["entity_identity", "relation_trust"],
                fallback=None,
                readiness={
                    "codeindex_executable": "available",
                    "claude_mcp_surface": "unknown",
                    "workspace_index": "unknown",
                },
                execution_boundary={
                    "orientation": "read_only",
                    "recommended_path": "requires_existing_index",
                },
            )
        return _result(
            task_kind=task_kind,
            policy=policy,
            recommended_path="native",
            availability="unavailable",
            tool_surface=["agent_native_read", "agent_native_grep"],
            required_evidence=[],
            fallback={
                "path": "native",
                "reason": "codeindex_unavailable",
                "limitation": "cross-file relationship evidence is unavailable",
            },
            readiness={"codeindex_executable": "unavailable"},
            execution_boundary={"orientation": "read_only", "recommended_path": "read_only"},
        )
    if task_kind == "temporal-review":
        if codeindex_available and git_repository and refs_resolved:
            return _result(
                task_kind=task_kind,
                policy=policy,
                recommended_path="temporal-review",
                availability="conditional",
                tool_surface=["loomgraph_branch_diff"],
                required_evidence=[
                    "base_ref",
                    "head_ref",
                    "snapshot_identity",
                    "content_comparison_status",
                ],
                fallback=None,
                readiness={
                    "codeindex_executable": "available",
                    "claude_mcp_surface": "unknown",
                    "snapshot_provisioning": "required",
                },
                execution_boundary={
                    "orientation": "read_only",
                    "recommended_path": "may_provision_local_snapshot_cache",
                },
            )
        reason = "codeindex_unavailable" if not codeindex_available else "comparison_unavailable"
        return _result(
            task_kind=task_kind,
            policy=policy,
            recommended_path="native",
            availability="unavailable",
            tool_surface=["agent_native_read", "agent_native_grep"],
            required_evidence=[],
            fallback={
                "path": "native",
                "reason": reason,
                "limitation": "native navigation cannot prove a historical comparison",
            },
            readiness={
                "codeindex_executable": "available" if codeindex_available else "unavailable",
                "git_repository": "available" if git_repository else "unavailable",
                "resolved_refs": "available" if refs_resolved else "unavailable",
            },
            execution_boundary={"orientation": "read_only", "recommended_path": "read_only"},
        )
    raise ValueError(f"unsupported orientation task kind: {task_kind}")
