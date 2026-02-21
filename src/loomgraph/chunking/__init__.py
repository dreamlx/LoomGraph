"""AST-aware code chunking using codeindex symbols.

Splits source files at symbol boundaries (functions, classes, methods)
so each chunk maps to exactly one code symbol. Uncovered lines (imports,
module-level code) are collected into a fallback chunk.

This gives finer-grained vector retrieval compared to fixed-size
token chunking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loomgraph.core.models import ParseResult


@dataclass
class Chunk:
    """A code chunk aligned to an AST symbol."""

    id: str
    content: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    symbol_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "symbol_name": self.symbol_name,
        }


def _make_chunk_id(module: str, symbol_name: str) -> str:
    """Build a deterministic chunk ID."""
    return f"chunk:{module}.{symbol_name}" if symbol_name else f"chunk:{module}.__file__"


def chunk_file(
    source: str,
    parse_result: ParseResult,
    module: str,
) -> list[Chunk]:
    """Split source code into AST-aligned chunks.

    Each symbol (function, class, method) becomes its own chunk.
    Lines not covered by any symbol are collected into a single
    fallback chunk (truncated to 2000 chars).

    Args:
        source: Raw source code text
        parse_result: codeindex ParseResult with symbol locations
        module: Dotted module name (e.g. "auth.service")

    Returns:
        List of Chunk objects
    """
    lines = source.splitlines(keepends=True)
    chunks: list[Chunk] = []
    covered: set[int] = set()

    for sym in sorted(parse_result.symbols, key=lambda s: s.line_start):
        start = max(sym.line_start - 1, 0)
        end = min(sym.line_end, len(lines))
        if start >= end:
            continue
        content = "".join(lines[start:end])
        if not content.strip():
            continue
        cid = _make_chunk_id(module, sym.name)
        chunks.append(Chunk(
            id=cid, content=content,
            file_path=str(parse_result.path),
            line_start=sym.line_start, line_end=sym.line_end,
            symbol_name=sym.name,
        ))
        covered.update(range(start, end))

    # Fallback chunk for uncovered lines (imports, module-level code)
    uncovered = [i for i in range(len(lines)) if i not in covered]
    if uncovered:
        content = "".join(lines[i] for i in uncovered)
        if content.strip():
            chunks.append(Chunk(
                id=_make_chunk_id(module, ""),
                content=content[:2000],
                file_path=str(parse_result.path),
                line_start=uncovered[0] + 1,
                line_end=uncovered[-1] + 1,
                symbol_name="",
            ))

    return chunks

