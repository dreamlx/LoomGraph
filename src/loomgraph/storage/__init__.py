"""Storage backend abstractions for LoomGraph.

GraphStore is the backend-agnostic interface for entity/relation persistence
and graph analytics. See EPIC-011 / ADR-013.
"""

from __future__ import annotations

from loomgraph.storage.base import GraphStore

__all__ = ["GraphStore"]
