#!/usr/bin/env python3
"""Capability-manifest gate (#206 Track A).

``evals/capability-manifest.json`` is a published evidence artifact: each
fixture asserts an L2 ``content_comparison`` contract by pointing at a pytest
nodeid. Left as inert JSON, a renamed test makes the manifest silently point at
a non-existent case — the evidence reads as "validated" when nothing ran
(fake-green gate: only the JSON's internal consistency is checked, not the
external truth that the test exists and is green).

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


def load_manifest() -> dict[str, object]:
    """Read the capability manifest; raise on malformed JSON."""
    with MANIFEST.open() as fh:
        data: dict[str, object] = json.load(fh)
    return data


def _pytest(nodeid: str, args: list[str]) -> tuple[int, str]:
    """Run ``pytest`` against ``nodeid``; return (exit_code, combined_output)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", nodeid, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def check_manifest() -> list[FixtureResult]:
    """Resolve + run every fixture; return one result per fixture.

    A fixture fails when:
    - its ``test`` nodeid does not resolve (renamed/deleted test), or
    - the test exists but does not pass.

    The gate is deliberately per-fixture: one stale reference fails the whole
    manifest rather than letting the surviving fixtures mask it.
    """
    manifest = load_manifest()
    results: list[FixtureResult] = []
    for fixture in manifest["fixtures"]:
        fid = fixture["id"]
        nodeid = fixture["test"]

        # Collection-only first: a stale nodeid exits 4 (USAGE), a live one 0.
        rc, out = _pytest(nodeid, ["--collect-only", "-q"])
        if rc != 0:
            results.append(FixtureResult(
                fid, nodeid, False,
                f"nodeid does not resolve (exit {rc}); test renamed or deleted?\n{out.strip()}",
            ))
            continue

        # Run the test for real.
        rc, out = _pytest(nodeid, ["-q"])
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
