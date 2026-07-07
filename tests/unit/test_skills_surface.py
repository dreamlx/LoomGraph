"""Ship-surface guard: which skills the wheel bundles (#64).

The deprecated workflow skills (loomgraph-debt-radar / -evolution /
-sync-advisor) were removed in v0.15.0 — replaced by the loomgraph_debt_audit
/ loomgraph_evolution_track / loomgraph_sync_advice MCP composites. This
test pins the surviving set so a stale skill dir doesn't silently creep
back into the wheel via hatch's force-include.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"


def test_only_init_and_setup_skills_remain():
    """Deprecated workflow skills removed in v0.15.0 (#64)."""
    present = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    deprecated = {
        "loomgraph-debt-radar",
        "loomgraph-evolution",
        "loomgraph-sync-advisor",
    }
    assert deprecated.isdisjoint(present), (
        f"deprecated skills still bundled: {deprecated & present}"
    )
    assert {"loomgraph-init", "loomgraph-setup"}.issubset(present)
