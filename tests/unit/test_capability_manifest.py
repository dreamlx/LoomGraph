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

from evals.run_capability_manifest import check_manifest


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
