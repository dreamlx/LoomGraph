"""Batch injection of codeindex results (legacy programmatic API).

DEPRECATED (#66): the batch helpers ``collect_kg_data`` / ``build_chunks`` /
``create_external_stubs`` were removed — ``loomgraph index``/``update`` now
consume the ``codeindex graph-export`` contract via
:mod:`loomgraph.core.graph_export_ingest`. What remains here is the legacy
file-level programmatic API (``inject_parse_result`` /
``inject_parse_results_batch``), retained for backwards compatibility. It still
uses simple-name keying (the collision-prone path #66 fixed for the CLI) and is
slated for removal in a follow-up.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from loomgraph.storage.base import GraphStore

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


# removed collect_kg_data / build_chunks / create_external_stubs (#66 — dead
# after `index`/`update` migrated to graph-export ingestion)


async def inject_parse_result(
    client: GraphStore,
    result: ParseResult,
) -> InjectResult:
    """Inject codeindex parse result into LightRAG via HTTP API.

    This function transforms codeindex ParseResult into LightRAG entities
    and relations, then calls the LightRAG HTTP API.

    Args:
        client: GraphStore instance (any backend)
        result: ParseResult from codeindex

    Returns:
        InjectResult with counts of injected entities and relations

    Example:
        >>> from loomgraph.storage import create_graph_store
        >>> client = await create_graph_store(workspace="myproj")
        >>> result = codeindex.parse_file("src/auth/service.py")
        >>> inject_result = await inject_parse_result(client, result)
        >>> print(f"Injected {inject_result.entities} entities")
    """
    file_path = str(result.path)
    language = detect_language(file_path)
    errors: list[str] = []

    # Module name for import relations (derive from file path)
    module_name = _path_to_module_name(result.path)

    # 0. Create module entity first (needed for import relations).
    # SQLite upsert is idempotent so "already exists" is no longer a special case.
    try:
        module_data = {
            "entity_type": "module",
            "description": f"Python module | {file_path}",
            "source_id": file_path,
            "file_path": file_path,
        }
        await client.create_entity(module_name, module_data)
        logger.debug(f"Created module entity: {module_name}")
    except Exception as e:
        logger.warning(f"Failed to create module entity {module_name}: {e}")

    # 1. Inject entities (symbols)
    entity_count = 0
    for symbol in result.symbols:
        try:
            entity = map_symbol_to_entity(symbol, file_path, language)
            await client.create_entity(entity.entity_name, entity.entity_data)
            entity_count += 1
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
    client: GraphStore,
    results: list[ParseResult],
) -> list[InjectResult]:
    """Inject multiple parse results into LightRAG.

    Args:
        client: GraphStore instance
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
