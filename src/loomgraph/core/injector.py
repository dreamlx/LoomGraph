"""Batch injection of codeindex results into LightRAG.

This module implements the inject_parse_result() function defined in
docs/api/DATA_CONTRACT.md Section 4.

Uses LightRAG HTTP API for all storage operations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .lightrag_client import LightRAGAPIError, LightRAGClient
from .mapper import (
    detect_language,
    map_call_to_relation,
    map_import_to_relation,
    map_inheritance_to_relation,
    map_symbol_to_entity,
)
from .models import InjectResult, ParseResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def inject_parse_result(
    client: LightRAGClient,
    result: ParseResult,
) -> InjectResult:
    """Inject codeindex parse result into LightRAG via HTTP API.

    This function transforms codeindex ParseResult into LightRAG entities
    and relations, then calls the LightRAG HTTP API.

    Args:
        client: LightRAGClient instance for HTTP API calls
        result: ParseResult from codeindex

    Returns:
        InjectResult with counts of injected entities and relations

    Example:
        >>> from loomgraph.core.lightrag_client import LightRAGClient
        >>> client = LightRAGClient("http://internal.example.invalid:3001")
        >>> result = codeindex.parse_file("src/auth/service.py")
        >>> inject_result = await inject_parse_result(client, result)
        >>> print(f"Injected {inject_result.entities} entities")
    """
    file_path = str(result.path)
    language = detect_language(file_path)
    errors: list[str] = []

    # Module name for import relations (derive from file path)
    module_name = _path_to_module_name(result.path)

    # 1. Inject entities (symbols)
    entity_count = 0
    for symbol in result.symbols:
        try:
            entity = map_symbol_to_entity(symbol, file_path, language)

            await client.create_entity(entity.entity_name, entity.entity_data)
            entity_count += 1
            logger.debug(f"Injected entity: {entity.entity_name}")

        except LightRAGAPIError as e:
            error_msg = f"Failed to inject entity {symbol.name}: {e.message}"
            logger.warning(error_msg)
            errors.append(error_msg)
        except Exception as e:
            error_msg = f"Failed to inject entity {symbol.name}: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)

    # 2. Inject call relations
    relation_count = 0
    for call in result.calls:
        try:
            rel = map_call_to_relation(call, file_path)
            await client.create_relation(rel.src_id, rel.tgt_id, rel.edge_data)
            relation_count += 1
            logger.debug(f"Injected CALLS relation: {rel.src_id} -> {rel.tgt_id}")

        except LightRAGAPIError as e:
            error_msg = f"Failed to inject call {call.caller}->{call.callee}: {e.message}"
            logger.warning(error_msg)
            errors.append(error_msg)
        except Exception as e:
            error_msg = f"Failed to inject call {call.caller}->{call.callee}: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)

    # 3. Inject inheritance relations
    for inh in result.inheritances:
        try:
            rel = map_inheritance_to_relation(inh, file_path)
            await client.create_relation(rel.src_id, rel.tgt_id, rel.edge_data)
            relation_count += 1
            logger.debug(f"Injected INHERITS relation: {rel.src_id} -> {rel.tgt_id}")

        except LightRAGAPIError as e:
            error_msg = f"Failed to inject inheritance {inh.child}->{inh.parent}: {e.message}"
            logger.warning(error_msg)
            errors.append(error_msg)
        except Exception as e:
            error_msg = f"Failed to inject inheritance {inh.child}->{inh.parent}: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)

    # 4. Inject import relations
    for imp in result.imports:
        try:
            rels = map_import_to_relation(imp, module_name, file_path)
            for rel in rels:
                await client.create_relation(rel.src_id, rel.tgt_id, rel.edge_data)
                relation_count += 1
                logger.debug(f"Injected IMPORTS relation: {rel.src_id} -> {rel.tgt_id}")

        except LightRAGAPIError as e:
            error_msg = f"Failed to inject import {imp.module}: {e.message}"
            logger.warning(error_msg)
            errors.append(error_msg)
        except Exception as e:
            error_msg = f"Failed to inject import {imp.module}: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)

    return InjectResult(
        file_path=file_path,
        entities=entity_count,
        relations=relation_count,
        errors=errors,
    )


def _path_to_module_name(path: Path) -> str:
    """Convert file path to Python module name.

    Args:
        path: File path (e.g., Path("src/auth/service.py"))

    Returns:
        Module name (e.g., "src.auth.service")
    """
    # Remove file extension
    stem = path.with_suffix("")

    # Convert path separators to dots
    parts = stem.parts

    # Skip common root directories
    skip_roots = {"src", "lib", "app"}
    if parts and parts[0] in skip_roots:
        parts = parts[1:]

    return ".".join(parts)


async def inject_parse_results_batch(
    client: LightRAGClient,
    results: list[ParseResult],
) -> list[InjectResult]:
    """Inject multiple parse results into LightRAG.

    Args:
        client: LightRAGClient instance
        results: List of ParseResult from codeindex

    Returns:
        List of InjectResult, one per file
    """
    inject_results: list[InjectResult] = []

    for result in results:
        if result.error:
            logger.warning(f"Skipping file with parse error: {result.path} - {result.error}")
            inject_results.append(
                InjectResult(
                    file_path=str(result.path),
                    entities=0,
                    relations=0,
                    errors=[f"Parse error: {result.error}"],
                )
            )
            continue

        inject_result = await inject_parse_result(client, result)
        inject_results.append(inject_result)

    return inject_results
