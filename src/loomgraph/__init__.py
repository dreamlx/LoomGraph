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

__all__ = [
    "__version__",
    "Settings",
    "get_settings",
]
