"""Guard the shipped-skills surface (EPIC-014 / v0.13.0).

v0.13.0 removed the deprecated workflow skills (`loomgraph-debt-radar`,
`loomgraph-evolution`, `loomgraph-sync-advisor`) — their composite MCP tools
(`loomgraph_debt_audit` / `loomgraph_evolution_track` / `loomgraph_sync_advice`)
are the replacement. Only `loomgraph-init` and `loomgraph-setup` survive.

`install-skills` ships whatever lives in repo `skills/` (force-include copies
the whole dir into the wheel), so this directory IS the ship surface. Pin it
so an accidental re-add trips CI rather than silently re-shipping a removed
skill.
"""

from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
EXPECTED_SKILLS = {"loomgraph-init", "loomgraph-setup"}


def test_only_survivor_skills_ship() -> None:
    actual = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    assert actual == EXPECTED_SKILLS, (
        f"shipped-skills surface changed (symmetric diff: {actual ^ EXPECTED_SKILLS}). "
        f"v0.13.0 removed debt-radar/evolution/sync-advisor in favor of composite MCP "
        f"tools; only add a new skill here deliberately and update MCP_DESIGN.md."
    )


def test_survivors_have_skill_md() -> None:
    """Each shipped skill must define SKILL.md (Claude Code loader expects it)."""
    for name in EXPECTED_SKILLS:
        assert (SKILLS_DIR / name / "SKILL.md").is_file(), f"{name}/SKILL.md missing"
