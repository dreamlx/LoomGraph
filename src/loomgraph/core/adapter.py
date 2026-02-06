"""Adapter to convert codeindex output to LoomGraph models.

This module bridges the gap between codeindex's ParseResult and
LoomGraph's internal ParseResult model.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loomgraph.core.models import (
    Call,
    Import,
    Inheritance,
    ParseResult,
    Symbol,
)

if TYPE_CHECKING:
    from codeindex.parser import ParseResult as CodeindexParseResult


def adapt_parse_result(codeindex_result: CodeindexParseResult) -> ParseResult:
    """Convert codeindex ParseResult to LoomGraph ParseResult.

    Args:
        codeindex_result: ParseResult from codeindex.parser.parse_file()

    Returns:
        LoomGraph ParseResult with adapted fields

    Example:
        >>> from codeindex.parser import parse_file
        >>> from loomgraph.core.adapter import adapt_parse_result
        >>> ci_result = parse_file(Path("src/auth.py"))
        >>> lg_result = adapt_parse_result(ci_result)
    """
    # Adapt symbols
    symbols = [
        Symbol(
            name=s.name,
            kind=s.kind,
            signature=s.signature,
            docstring=s.docstring,
            line_start=s.line_start,
            line_end=s.line_end,
        )
        for s in codeindex_result.symbols
    ]

    # Adapt imports
    # codeindex has: module, names, is_from
    # LoomGraph expects: module, alias, names
    imports = [
        Import(
            module=i.module,
            alias=None,  # codeindex doesn't track aliases yet
            names=i.names,
        )
        for i in codeindex_result.imports
    ]

    # Note: codeindex doesn't provide calls/inheritances yet
    # These will be empty until codeindex adds support
    calls: list[Call] = []
    inheritances: list[Inheritance] = []

    return ParseResult(
        path=Path(codeindex_result.path),
        symbols=symbols,
        imports=imports,
        calls=calls,
        inheritances=inheritances,
        module_docstring=codeindex_result.module_docstring,
        file_lines=codeindex_result.file_lines,
        error=codeindex_result.error,
    )
