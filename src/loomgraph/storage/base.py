"""GraphStore ABC — backend-agnostic storage contract.

Production implementation: `SqliteGraphStore` (SQLite + sqlite-vec
single-file backend; see ADR-013).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

ProgressCallback = Callable[[int, int, int], None]
"""Progress reporter: (batch_num, total_batches, entities_in_batch)."""


class GraphStore(ABC):
    """Storage contract for the code knowledge graph.

    All operations are async to admit both network-backed (LightRAG adapter)
    and in-process (SQLite) implementations. Workspace selection is established
    at construction time; this contract is single-workspace from the caller's
    perspective.
    """

    # ----- Entity CRUD -----

    @abstractmethod
    async def create_entity(
        self,
        entity_name: str,
        entity_data: dict[str, Any],
    ) -> None:
        """Insert or upsert a single entity keyed by entity_name."""

    @abstractmethod
    async def entity_exists(self, entity_name: str) -> bool:
        """Return True if an entity with the given name exists."""

    @abstractmethod
    async def get_all_entities(self) -> list[dict[str, Any]]:
        """Return all entities in the workspace."""

    # ----- Relation CRUD -----

    @abstractmethod
    async def create_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_data: dict[str, Any],
    ) -> None:
        """Insert or upsert a relation. Idempotent by (src, tgt, keywords)."""

    @abstractmethod
    async def get_all_relations(self) -> list[dict[str, Any]]:
        """Return all relations in the workspace."""

    # ----- Bulk insert -----

    @abstractmethod
    async def insert_custom_kg(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        chunks: list[dict[str, Any]] | None = None,
        *,
        batch_size: int = 5000,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Batch insert entities/relations/chunks.

        `batch_size` and `progress_callback` are honored by network-backed
        implementations to avoid HTTP timeouts on large payloads. In-process
        backends (SQLite) may ignore them or use them for progress display.
        """

    # ----- Delete -----

    @abstractmethod
    async def delete_all(self) -> None:
        """Clear all entities, relations, and chunks in the workspace."""

    @abstractmethod
    async def delete_by_source(self, source_ids: list[str]) -> None:
        """Delete entities/relations whose source_id is in the given list."""

    # ----- Source / workspace queries -----

    @abstractmethod
    async def get_source_ids(
        self,
        source_prefix: str | None = None,
    ) -> list[str]:
        """Return deduplicated source_ids, optionally filtered by prefix."""

    @abstractmethod
    async def list_workspaces(self) -> list[str]:
        """List all known workspace names (backend-level discovery)."""

    # ----- Analytics -----

    @abstractmethod
    async def get_orphan_entities(
        self,
        exclude_types: list[str] | None = None,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """Entities with 0 in-degree and 0 out-degree."""

    @abstractmethod
    async def get_degree_distribution(
        self,
        direction: str = "in",
        min_degree: int = 5,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """Entities exceeding a degree threshold.

        direction='in' counts callers (incoming edges); 'out' counts callees.
        """

    @abstractmethod
    async def get_graph_stats(
        self,
        source_prefix: str | None = None,
        module_depth: int = 2,
    ) -> dict[str, Any]:
        """Entity/relation counts and cross-module coupling density."""

    # ----- Vector search (Phase 2) -----

    async def search_similar(
        self,
        embedding: list[float],
        k: int = 10,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """KNN search over entity-description embeddings.

        Returns a list of `{entity_name, source_id, distance}` dicts,
        ascending distance (closest first). Default implementation raises
        `NotImplementedError` — backends without vector support should
        leave this method alone. Concrete vector backends override.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement search_similar()"
        )

    async def vector_count(self) -> int:
        """Number of entity-description vectors currently indexed.

        Backends without vector support report 0. Used by the semantic
        `search` command to give a clean "not indexed" error before
        attempting a KNN query against an empty vec table (whose behaviour
        is sqlite-vec-version-dependent).
        """
        return 0
