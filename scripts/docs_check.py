#!/usr/bin/env python3
"""Docs consistency gate (`make docs-check`).

Every check here guards against drift that actually happened — each row
names the incident that motivated it:

  1. command-table sync (README.md + CLAUDE.md vs `loomgraph --help`)
     — README shipped a version behind (missing check/embed-backfill/
       git-metrics/hooks); CLAUDE.md missed `hooks` despite its own
       MUST-READ rule requiring the sync.
  2. generated artifacts must not be committed at repo root
     — CODEINDEX.md / PROJECT_SYMBOLS.md were tracked by accident.
  3. version three-source consistency — delegated to bump_version.py
     --check (release flow invariant).
  4. relative md links resolve — deleting docs/spikes left a dead link
     in docs/api/MCP_DESIGN.md.
  5. completion-report files at root — feedback-v0.2.0.md shipped for
     months after its era passed.

Exit 0 = docs healthy; non-zero with one line per failure otherwise.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Commands excluded from the table-sync rule. `version` is trivia;
# `setup-config` is deprecated and documented as such.
SYNC_EXEMPT = {"version"}
# Deprecated commands must still be *mentioned* (as deprecated), not absent.
MUST_MENTION = {"setup-config"}

GENERATED_ARTIFACTS = ("CODEINDEX.md", "PROJECT_SYMBOLS.md")
COMPLETION_REPORT_GLOBS = ("feedback-*.md",)

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def help_commands() -> set[str]:
    out = subprocess.run(
        [str(ROOT / ".venv/bin/loomgraph"), "--help"],
        capture_output=True, text=True, check=True,
    ).stdout
    cmds = set()
    in_cmds = False
    for line in out.splitlines():
        if line.strip() == "Commands:":
            in_cmds = True
            continue
        if not in_cmds:
            continue
        m = re.match(r"^  ([a-z][a-z-]+)\s", line)
        if m:
            cmds.add(m.group(1))
    return cmds


def doc_commands(path: Path) -> set[str]:
    """Commands mentioned as `loomgraph <cmd>` or `<cmd> / <cmd2>` table rows."""
    text = path.read_text()
    cmds = set(re.findall(r"loomgraph ([a-z][a-z-]+)", text))
    # table rows like `loomgraph compare / similar` — capture the tail too
    for group in re.findall(r"loomgraph ([a-z][a-z-]+(?:\s*/\s*[a-z][a-z-]+)+)", text):
        cmds.update(c.strip() for c in group.split("/"))
    return cmds


def check_command_sync(fails: list[str]) -> None:
    cmds = help_commands() - SYNC_EXEMPT
    for doc in ("README.md", "CLAUDE.md"):
        p = ROOT / doc
        mentioned = doc_commands(p)
        missing = cmds - mentioned
        if missing:
            fails.append(f"{doc}: command table missing {sorted(missing)}")
    for doc in ("README.md", "CLAUDE.md"):
        mentioned = doc_commands(ROOT / doc)
        absent = MUST_MENTION - mentioned
        if absent:
            fails.append(f"{doc}: deprecated commands {sorted(absent)} must "
                         "still be mentioned as deprecated")


def check_generated_artifacts(fails: list[str]) -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
        check=True,
    ).stdout.splitlines()
    for art in GENERATED_ARTIFACTS:
        if art in tracked:
            fails.append(f"generated artifact is tracked: {art} "
                         "(gitignore it; src/**/README_AI.md stay)")


def check_version_consistency(fails: list[str]) -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bump_version.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        fails.append(f"version three-source check failed:\n{r.stdout}{r.stderr}")


def check_md_links(fails: list[str]) -> None:
    for md in ROOT.rglob("*.md"):
        rel = md.relative_to(ROOT)
        parts = rel.parts
        if parts and parts[0] in {
            ".venv", "node_modules", "dist", "customers", "test_output"
        }:
            continue  # customers/ links outward; tool dirs are noise
        for target in MD_LINK.findall(md.read_text()):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = target.split("#", 1)[0]
            if not path:
                continue
            if not (md.parent / path).resolve().exists():
                fails.append(f"dead relative link {target!r} in {rel}")


def check_completion_reports(fails: list[str]) -> None:
    for pat in COMPLETION_REPORT_GLOBS:
        for hit in ROOT.glob(pat):
            fails.append(f"completion-report file at root: {hit.name} — "
                         "belongs in the PR/issue, not the repo")


def main() -> int:
    fails: list[str] = []
    check_command_sync(fails)
    check_generated_artifacts(fails)
    check_version_consistency(fails)
    check_md_links(fails)
    check_completion_reports(fails)

    if fails:
        print("docs-check: FAIL", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("docs-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
