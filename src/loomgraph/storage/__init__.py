"""Storage backend abstractions for LoomGraph.

GraphStore is the backend-agnostic interface for entity/relation persistence
and graph analytics. See EPIC-011 / ADR-013.
"""

from __future__ import annotations

from loomgraph.storage.base import GraphStore
from loomgraph.storage.factory import create_graph_store, create_llm_client
from loomgraph.storage.sqlite_store import SqliteGraphStore

__all__ = [
    "GraphStore",
    "SqliteGraphStore",
    "create_graph_store",
    "create_llm_client",
]
