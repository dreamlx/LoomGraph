"""Contract tests for the read-only provider capability manifest (#287)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from loomgraph.core.provider_capability import (
    ProviderCapabilityContractError,
    build_evidence_envelope,
    load_manifest,
    parse_manifest,
    provider_plan,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "provider-capability-manifest-v1.json"
)


def _manifest() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_example_manifest_keeps_provider_evidence_boundaries_distinct() -> None:
    manifest = load_manifest(FIXTURE_PATH)

    assert manifest["schema_version"] == 1
    capabilities = manifest["capabilities"]
    assert [(item["provider_id"], item["operation"], item["evidence_kind"]) for item in capabilities] == [
        ("codeindex", "structural_navigation", "structural_candidate"),
        ("cbm", "structural_navigation", "structural_candidate"),
        ("serena", "live_semantic", "live_semantic"),
        ("serena", "live_edit", "live_semantic"),
    ]


def test_conditional_external_capability_keeps_its_own_index_and_native_fallback() -> None:
    plan = provider_plan(load_manifest(FIXTURE_PATH), "cbm", "structural_navigation")

    assert plan == {
        "schema_version": 1,
        "recommended_path": "native",
        "availability": "conditional",
        "provider": {
            "id": "cbm",
            "version": "unknown",
            "operation": "structural_navigation",
            "evidence_kind": "structural_candidate",
            "snapshot_scope": "provider_index",
            "snapshot_identity": None,
            "index_owner": "provider",
            "data_scope": "unknown",
            "write_authority": "none",
        },
        "fallback": {
            "path": "native",
            "reason": "provider_not_discovered",
            "limitation": "provider capability is declared but not runtime-verified",
        },
    }


def test_unknown_provider_is_explicitly_unavailable_without_inference() -> None:
    plan = provider_plan(load_manifest(FIXTURE_PATH), "other", "live_semantic")

    assert plan == {
        "schema_version": 1,
        "recommended_path": "native",
        "availability": "unavailable",
        "provider": {"id": "other", "operation": "live_semantic"},
        "fallback": {
            "path": "native",
            "reason": "provider_capability_unknown",
            "limitation": "no declared provider capability matches this request",
        },
    }


def test_write_requiring_capability_never_becomes_an_automatic_path() -> None:
    manifest = load_manifest(FIXTURE_PATH)
    capability = next(
        item
        for item in manifest["capabilities"]
        if item["provider_id"] == "serena" and item["operation"] == "live_edit"
    )

    assert build_evidence_envelope(capability)["recommended_path"] == "native"
    assert build_evidence_envelope(capability)["fallback"] == {
        "path": "native",
        "reason": "provider_requires_user_authorization",
        "limitation": "provider operation may modify source and is not auto-selected",
    }


def test_temporal_comparison_requires_pinned_snapshot_identity() -> None:
    manifest = _manifest()
    manifest["capabilities"].append(
        {
            "provider_id": "cbm",
            "provider_version": "unknown",
            "operation": "temporal_comparison",
            "availability": "available",
            "reason": None,
            "evidence_kind": "temporal_comparison",
            "snapshot_scope": "pinned_comparison",
            "snapshot_identity": None,
            "index_owner": "provider",
            "data_scope": "unknown",
            "write_authority": "none",
        }
    )

    with pytest.raises(ProviderCapabilityContractError, match="pinned snapshot identity"):
        load_manifest_data(manifest)


def test_operation_cannot_upgrade_structural_candidate_to_live_semantic() -> None:
    manifest = _manifest()
    invalid = copy.deepcopy(manifest)
    invalid["capabilities"][0]["evidence_kind"] = "live_semantic"

    with pytest.raises(ProviderCapabilityContractError, match="evidence kind"):
        load_manifest_data(invalid)


def test_manifest_loading_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    before = path.read_bytes()

    load_manifest(path)

    assert path.read_bytes() == before
    assert sorted(item.name for item in tmp_path.iterdir()) == ["manifest.json"]


def load_manifest_data(manifest: dict[str, object]):
    """Use the public parser without making the production loader write a fixture."""
    return parse_manifest(manifest)
