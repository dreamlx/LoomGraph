"""Core module: configuration, mapping, injection, and indexing."""

from loomgraph.core.config import Settings, get_settings
from loomgraph.core.indexer import index_file, index_repository, scan_code_files
from loomgraph.core.injector import inject_parse_result, inject_parse_results_batch
from loomgraph.core.mapper import (
    detect_language,
    map_call_to_relation,
    map_import_to_relation,
    map_inheritance_to_relation,
    map_symbol_to_entity,
)
from loomgraph.core.models import (
    Call,
    EntityData,
    Import,
    IndexResult,
    Inheritance,
    InjectResult,
    ParseResult,
    RelationData,
    Symbol,
)

__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Models
    "Symbol",
    "Call",
    "Inheritance",
    "Import",
    "ParseResult",
    "EntityData",
    "RelationData",
    "InjectResult",
    "IndexResult",
    # Mapper
    "detect_language",
    "map_symbol_to_entity",
    "map_call_to_relation",
    "map_inheritance_to_relation",
    "map_import_to_relation",
    # Injector
    "inject_parse_result",
    "inject_parse_results_batch",
    # Indexer
    "scan_code_files",
    "index_repository",
    "index_file",
]
