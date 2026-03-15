"""Batch injection of codeindex results into LightRAG.

This module implements the inject_parse_result() function defined in
docs/api/DATA_CONTRACT.md Section 4.

Uses LightRAG HTTP API for all storage operations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


def collect_kg_data(
    result: ParseResult,
) -> tuple[list[dict], list[dict]]:
    """Collect entities and relations from a ParseResult without injecting.

    Returns data in insert_custom_kg format for batch injection.
    This avoids the ordering problem where cross-file relations fail
    because target entities haven't been created yet.

    Args:
        result: ParseResult from codeindex

    Returns:
        Tuple of (entities, relations) in insert_custom_kg dict format
    """
    file_path = str(result.path)
    language = detect_language(file_path)
    module_name = _path_to_module_name(result.path)

    entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    # Module entity
    entities.append({
        "entity_name": module_name,
        "entity_type": "module",
        "description": f"{language.capitalize()} module | {file_path}",
        "source_id": file_path,
        "file_path": file_path,
    })

    # Symbol entities
    for symbol in result.symbols:
        entity = map_symbol_to_entity(symbol, file_path, language)
        entities.append({
            "entity_name": entity.entity_name,
            **entity.entity_data,
        })

    # Call relations
    for call in result.calls:
        rel = map_call_to_relation(call, file_path)
        relations.append({
            "src_id": rel.src_id,
            "tgt_id": rel.tgt_id,
            **rel.edge_data,
        })

    # Inheritance relations
    for inh in result.inheritances:
        rel = map_inheritance_to_relation(inh, file_path)
        relations.append({
            "src_id": rel.src_id,
            "tgt_id": rel.tgt_id,
            **rel.edge_data,
        })

    # Import relations
    for imp in result.imports:
        rels = map_import_to_relation(imp, module_name, file_path)
        for rel in rels:
            relations.append({
                "src_id": rel.src_id,
                "tgt_id": rel.tgt_id,
                **rel.edge_data,
            })

    return entities, relations


def build_chunks(result: ParseResult) -> list[dict[str, Any]]:
    """Build insert_custom_kg chunks for a single file.

    Each file produces one chunk containing module docstring + symbol signatures,
    enabling semantic search over file contents.

    Args:
        result: ParseResult from codeindex

    Returns:
        List with one chunk dict (content, source_id, tokens, chunk_order_index, full_doc_id)
    """
    content_parts: list[str] = []
    if result.module_docstring:
        content_parts.append(result.module_docstring)
    for symbol in result.symbols:
        line = symbol.signature if symbol.signature else f"{symbol.kind} {symbol.name}"
        if symbol.docstring:
            line += f"\n  {symbol.docstring[:200]}"
        content_parts.append(line)

    content = "\n".join(content_parts)
    if not content:
        content = str(result.path)

    return [{
        "content": content,
        "source_id": str(result.path),
        "tokens": len(content.split()),
        "chunk_order_index": 0,
        "full_doc_id": str(result.path),
    }]


def create_external_stubs(
    all_entities: list[dict[str, Any]],
    all_relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create stub entities for external dependencies referenced in relations.

    Scans all relation src_id/tgt_id fields and creates an "external" stub entity
    for any name not found in the entity list.

    Args:
        all_entities: Collected entities from collect_kg_data()
        all_relations: Collected relations from collect_kg_data()

    Returns:
        List of stub entity dicts to append to all_entities
    """
    known = {e["entity_name"] for e in all_entities}
    stubs: list[dict[str, Any]] = []
    seen_stubs: set[str] = set()

    for rel in all_relations:
        for field in ("src_id", "tgt_id"):
            name = rel.get(field, "")
            if name and name not in known and name not in seen_stubs:
                stubs.append({
                    "entity_name": name,
                    "entity_type": "external",
                    "description": f"External dependency: {name}",
                    "source_id": "external",
                })
                seen_stubs.add(name)

    return stubs


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

    # 0. Create module entity first (needed for import relations)
    try:
        module_data = {
            "entity_type": "module",
            "description": f"Python module | {file_path}",
            "source_id": file_path,
            "file_path": file_path,
        }
        await client.create_entity(module_name, module_data)
        logger.debug(f"Created module entity: {module_name}")
    except LightRAGAPIError as e:
        # Module might already exist, that's OK
        if "already exists" not in str(e.message).lower():
            logger.warning(f"Failed to create module entity {module_name}: {e.message}")
    except Exception as e:
        logger.warning(f"Failed to create module entity {module_name}: {e}")

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
        Module name (e.g., "auth.service")
    """
    # Remove file extension
    stem = path.with_suffix("")

    # Get parts, handling absolute paths
    parts = list(stem.parts)

    # For absolute paths, find 'src' or similar and start from there
    # e.g., src/loomgraph/core -> loomgraph.core
    anchor_dirs = {"src", "lib", "app", "pkg", "packages"}
    for i, part in enumerate(parts):
        if part in anchor_dirs:
            parts = parts[i + 1:]  # Skip the anchor dir itself
            break
    else:
        # No anchor found, try to use just the last few parts
        # This handles paths without src/ prefix
        if len(parts) > 3:
            parts = parts[-3:]  # Take last 3 parts as fallback

    # Filter out root/drive parts (like "/" on Unix or "C:" on Windows)
    parts = [p for p in parts if p and p != "/"]

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
