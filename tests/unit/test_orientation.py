"""Unit tests for the deterministic Claude Code orientation policy."""

from __future__ import annotations

from loomgraph.core.orientation import decide_orientation


def test_local_task_stays_on_native_tools() -> None:
    result = decide_orientation(
        task_kind="local",
        policy="balanced",
        codeindex_available=False,
        git_repository=False,
        refs_resolved=False,
    )

    assert result["recommended_path"] == "native"
    assert result["availability"] == "available"
    assert result["tool_surface"] == ["agent_native_read", "agent_native_grep"]
    assert result["fallback"] is None


def test_cross_file_task_uses_light_path_when_codeindex_is_available() -> None:
    result = decide_orientation(
        task_kind="cross-file",
        policy="economy",
        codeindex_available=True,
        git_repository=False,
        refs_resolved=False,
    )

    assert result["recommended_path"] == "light"
    assert result["availability"] == "conditional"
    assert result["tool_surface"] == ["loomgraph_find", "loomgraph_graph"]
    assert result["evidence_budget"] == {"max_entities": 3, "max_relation_hops": 1}
    assert result["required_evidence"] == ["entity_identity", "relation_trust"]
    assert result["readiness"] == {
        "codeindex_executable": "available",
        "claude_mcp_surface": "unknown",
        "workspace_index": "unknown",
    }
    assert result["execution_boundary"]["recommended_path"] == "requires_existing_index"


def test_cross_file_task_degrades_explicitly_without_codeindex() -> None:
    result = decide_orientation(
        task_kind="cross-file",
        policy="balanced",
        codeindex_available=False,
        git_repository=False,
        refs_resolved=False,
    )

    assert result["recommended_path"] == "native"
    assert result["availability"] == "unavailable"
    assert result["fallback"] == {
        "path": "native",
        "reason": "codeindex_unavailable",
        "limitation": "cross-file relationship evidence is unavailable",
    }


def test_temporal_review_requires_resolved_refs_and_comparison_evidence() -> None:
    result = decide_orientation(
        task_kind="temporal-review",
        policy="deep",
        codeindex_available=True,
        git_repository=True,
        refs_resolved=True,
    )

    assert result["recommended_path"] == "temporal-review"
    assert result["availability"] == "conditional"
    assert result["tool_surface"] == ["loomgraph_branch_diff"]
    assert result["required_evidence"] == [
        "base_ref",
        "head_ref",
        "snapshot_identity",
        "content_comparison_status",
    ]
    assert result["readiness"]["snapshot_provisioning"] == "required"
    assert result["execution_boundary"]["recommended_path"] == (
        "may_provision_local_snapshot_cache"
    )


def test_temporal_review_never_fabricates_comparison_when_refs_are_unresolved() -> None:
    result = decide_orientation(
        task_kind="temporal-review",
        policy="balanced",
        codeindex_available=True,
        git_repository=True,
        refs_resolved=False,
    )

    assert result["recommended_path"] == "native"
    assert result["availability"] == "unavailable"
    assert result["fallback"] == {
        "path": "native",
        "reason": "comparison_unavailable",
        "limitation": "native navigation cannot prove a historical comparison",
    }
