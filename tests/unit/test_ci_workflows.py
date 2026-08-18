"""CI workflow guards — the #76 PATH-bypass class outside product code.

Product code invokes codeindex exclusively as
``[sys.executable, "-m", "codeindex.cli", ...]`` (graph_export_ingest /
impact extractor / check_codeindex / loomgraph codeindex passthrough) so the
pinned ``ai-codeindex`` dep is what actually runs. A bare ``codeindex`` in a
workflow ``run:`` block resolves via PATH instead — if a runner image ever
ships a codeindex ahead of the venv install, CI computes changed-file sets
under a different version's semantics than the one loomgraph tests against.
#183 caught the one remaining bare invocation.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"

# `codeindex` invoked as a shell command: not part of a longer token
# (`ai-codeindex` has a leading `-`; `codeindex.cli` has a trailing dot).
_BARE_CODEINDEX_CMD = re.compile(r"(?<![\w.\-/])codeindex\s")


def _run_command_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(lineno, line)`` for executable lines only: ``run: |`` literal
    blocks (tracked by indentation) and single-line ``run: <cmd>`` forms.
    Step names / YAML comments mention codeindex freely — they don't execute."""
    in_run = False
    run_indent = 0
    for i, line in enumerate(text.splitlines(), start=1):
        if in_run:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if len(line) - len(line.lstrip()) > run_indent:
                yield i, line
                continue
            in_run = False  # dedent ends the block; fall through
        m_block = re.match(r"^(\s*)run:\s*\|\s*$", line)
        if m_block:
            in_run = True
            run_indent = len(m_block.group(1))
            continue
        m_inline = re.match(r"^\s*run:\s*(\S.*)$", line)
        if m_inline:
            yield i, m_inline.group(1)


def test_no_bare_codeindex_invocation_in_workflows() -> None:
    offenders: list[str] = []
    for wf in sorted(WORKFLOWS_DIR.glob("*.yml")):
        for i, line in _run_command_lines(wf.read_text(encoding="utf-8")):
            if "loomgraph codeindex" in line:
                continue  # pinned-env passthrough — the sanctioned form
            if _BARE_CODEINDEX_CMD.search(line):
                offenders.append(f"{wf.name}:{i}: {line.strip()}")
    assert offenders == [], (
        "Bare `codeindex` PATH lookup in CI workflows (#76 class, #183): "
        f"{offenders}. Invoke as `python -m codeindex.cli <args>` so the "
        "job's installed ai-codeindex is what actually runs."
    )
