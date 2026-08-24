"""CI guard for the capability manifest (#206 Track A).

``evals/capability-manifest.json`` is a published evidence artifact pointing
at pytest nodeids. Without a guard, a renamed test makes the manifest silently
point at nothing — the evidence reads as "validated" when nothing ran (fake-green
gate, only the JSON's internal consistency was checked).

This test puts the manifest gate on CI via the importable ``check_manifest()``
so a stale or failing fixture reference breaks the suite here, not in some
future evidence citation.
"""

from __future__ import annotations

import pytest
from evals.run_capability_manifest import (
    ManifestValidationError,
    check_manifest,
    load_manifest,
    validate_manifest,
)


def test_capability_manifest_declares_reviewed_v1_matrix() -> None:
    """The published matrix stays capability/trust-first, never a speed score."""
    manifest = load_manifest()
    validate_manifest(manifest)

    assert manifest["schema_version"] == 2
    assert manifest["primary_question"].startswith("面对一个已声明的结构")
    assert len(manifest["fixtures"]) == 8
    assert {fixture["track"] for fixture in manifest["fixtures"]} == {"A", "B", "C"}
    assert {fixture["id"] for fixture in manifest["fixtures"]} == {
        "overlap-definition",
        "overlap-direct-static-call",
        "structural-multihop-impact",
        "structural-typed-deps",
        "structural-topology-debt-git",
        "structural-branch-diff",
        "trust-annotated-factory-receiver",
        "trust-alias-barrel",
    }
    assert manifest["agent_use_compatibility"]["not_scored"] is True


def test_capability_manifest_rejects_row_without_trust_contract() -> None:
    """A correct-looking oracle cannot enter v1 without uncertainty fields."""
    manifest = load_manifest()
    manifest["fixtures"][0].pop("trust_fields")

    with pytest.raises(ManifestValidationError, match="trust_fields"):
        validate_manifest(manifest)


def test_capability_manifest_all_fixtures_green() -> None:
    """Every capability-manifest fixture must resolve and pass.

    Failure modes this catches:
    - stale nodeid (test renamed/deleted) — fixture does not resolve,
    - live nodeid but the test fails — the asserted L2 contract regressed.
    """
    results = check_manifest()
    failed = [r for r in results if not r.ok]
    assert not failed, (
        f"{len(failed)}/{len(results)} capability fixture(ies) failed:\n"
        + "\n".join(f"  {r.fixture_id}: {r.detail}" for r in failed)
    )
