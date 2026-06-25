"""
LoomGraph: Enterprise Code Intelligence Engine

Code understanding + retrieval over a local SQLite + sqlite-vec knowledge
graph, with pluggable OpenAI-compatible LLM and embedding providers.

Usage:
    from loomgraph import Settings
    from loomgraph.storage import create_graph_store

    store = await create_graph_store(workspace="myproj")
    # ... use store.get_all_entities() / search_similar() / ...
"""

from importlib.metadata import version as _pkg_version

__version__ = _pkg_version("loomgraph")
__author__ = "DreamLinx"

from loomgraph.core.config import Settings, get_settings
from loomgraph.core.indexer import index_file, index_repository, scan_code_files
from loomgraph.core.injector import inject_parse_result
from loomgraph.core.models import IndexResult, InjectResult, ParseResult

__all__ = [
    # Version
    "__version__",
    # Config
    "Settings",
    "get_settings",
    # Indexing
    "scan_code_files",
    "index_repository",
    "index_file",
    "inject_parse_result",
    # Models
    "ParseResult",
    "InjectResult",
    "IndexResult",
]
