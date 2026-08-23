#!/usr/bin/env python3
"""Capability-manifest gate (#206 Track A).

``evals/capability-manifest.json`` is a published evidence artifact: each
fixture declares one structural/trust question, its oracle, required
uncertainty fields, and one or more pytest nodeids. Left as inert JSON, a
renamed test or an incomplete trust contract makes the evidence read as
"validated" when it is not (fake-green gate).

This gate resolves every fixture's nodeid via ``pytest --collect-only`` and
runs it, failing loud on a stale reference or a failing assertion. Run it
directly (``python evals/run_capability_manifest.py``) or via the
``tests/unit/test_capability_manifest.py`` guard, which puts it on CI.

Exits 0 only when every fixture's test resolves and passes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
MANIFEST = EVALS_DIR / "capability-manifest.json"
REPO_ROOT = EVALS_DIR.parent


@dataclass
class FixtureResult:
    """One fixture's gate outcome."""

    fixture_id: str
    nodeid: str
    ok: bool
    detail: str


class ManifestValidationError(ValueError):
    """The published v1 evidence contract is incomplete or malformed."""


_FIXTURE_KEYS = {
    "id", "track", "task_class", "question", "rg_single_query", "tests",
    "oracle", "trust_fields", "recording",
}
_VALID_TRACKS = {"A", "B", "C"}
_VALID_RG_EQUIVALENCE = {"equivalent", "unsupported"}


def load_manifest() -> dict[str, object]:
    """Read the capability manifest; raise on malformed JSON."""
    with MANIFEST.open() as fh:
        data: dict[str, object] = json.load(fh)
    return data


def validate_manifest(manifest: dict[str, object]) -> None:
    """Validate the reviewed capability/trust v1 contract before execution."""
    if manifest.get("schema_version") != 2:
        raise ManifestValidationError("schema_version must be 2")
    if not isinstance(manifest.get("primary_question"), str):
        raise ManifestValidationError("primary_question must be a string")

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not 6 <= len(fixtures) <= 8:
        raise ManifestValidationError("fixtures must contain 6-8 rows")

    fixture_ids: set[str] = set()
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise ManifestValidationError("each fixture must be an object")
        missing = _FIXTURE_KEYS - fixture.keys()
        if missing:
            raise ManifestValidationError(
                f"fixture {fixture.get('id', '<unknown>')} missing {sorted(missing)}"
            )
        fixture_id = fixture["id"]
        if not isinstance(fixture_id, str) or fixture_id in fixture_ids:
            raise ManifestValidationError("fixture ids must be unique strings")
        fixture_ids.add(fixture_id)
        if fixture["track"] not in _VALID_TRACKS:
            raise ManifestValidationError(f"fixture {fixture_id} has invalid track")
        if fixture["rg_single_query"] not in _VALID_RG_EQUIVALENCE:
            raise ManifestValidationError(
                f"fixture {fixture_id} has invalid rg_single_query"
            )
        tests = fixture["tests"]
        if not isinstance(tests, list) or not tests or not all(isinstance(test, str) for test in tests):
            raise ManifestValidationError(f"fixture {fixture_id} tests must be non-empty strings")
        if not isinstance(fixture["oracle"], dict) or not fixture["oracle"]:
            raise ManifestValidationError(f"fixture {fixture_id} oracle must be an object")
        trust_fields = fixture["trust_fields"]
        if not isinstance(trust_fields, list) or not trust_fields:
            raise ManifestValidationError(f"fixture {fixture_id} trust_fields must be non-empty")
        recording = fixture["recording"]
        if not isinstance(recording, dict) or recording.get("cold") != "required" or recording.get("warm") != "required":
            raise ManifestValidationError(
                f"fixture {fixture_id} recording must require independent cold and warm records"
            )

    agent_use = manifest.get("agent_use_compatibility")
    if not isinstance(agent_use, dict) or agent_use.get("not_scored") is not True:
        raise ManifestValidationError("agent_use_compatibility must be explicitly not_scored")


def _pytest(nodeids: list[str], args: list[str]) -> tuple[int, str]:
    """Run ``pytest`` against nodeids; return (exit_code, combined_output)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *nodeids, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def check_manifest() -> list[FixtureResult]:
    """Resolve + run every fixture; return one result per fixture.

    A fixture fails when:
    - one of its ``tests`` nodeids does not resolve (renamed/deleted test), or
    - the test exists but does not pass.

    The gate is deliberately per-fixture: one stale reference fails the whole
    manifest rather than letting the surviving fixtures mask it.
    """
    manifest = load_manifest()
    validate_manifest(manifest)
    results: list[FixtureResult] = []
    for fixture in manifest["fixtures"]:
        fid = fixture["id"]
        nodeids = fixture["tests"]
        nodeid = ", ".join(nodeids)

        # Collection-only first: a stale nodeid exits 4 (USAGE), a live one 0.
        rc, out = _pytest(nodeids, ["--collect-only", "-q"])
        if rc != 0:
            results.append(FixtureResult(
                fid, nodeid, False,
                f"nodeid does not resolve (exit {rc}); test renamed or deleted?\n{out.strip()}",
            ))
            continue

        # Run the test for real.
        rc, out = _pytest(nodeids, ["-q"])
        if rc != 0:
            results.append(FixtureResult(
                fid, nodeid, False,
                f"test exists but failed (exit {rc})\n{out.strip()}",
            ))
            continue

        results.append(FixtureResult(fid, nodeid, True, "passed"))
    return results


def main() -> int:
    results = check_manifest()
    width = max(len(r.fixture_id) for r in results)
    failed = [r for r in results if not r.ok]
    for r in results:
        mark = "OK  " if r.ok else "FAIL"
        print(f"  [{mark}] {r.fixture_id:<{width}} {r.nodeid}")
        if not r.ok:
            # Indent the detail under the failing line.
            for line in r.detail.splitlines():
                print(f"          {line}")
    print()
    if failed:
        print(f"{len(failed)}/{len(results)} capability fixture(ies) failed.")
        return 1
    print(f"{len(results)}/{len(results)} capability fixtures green.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
