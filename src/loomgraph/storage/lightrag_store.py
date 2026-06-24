"""LightRAG adapter implementing the GraphStore contract.

Wraps `LightRAGClient` so existing call sites (CLI / core) can depend on
the backend-agnostic `GraphStore` interface while staying on the LightRAG
HTTP backend during EPIC-011 Phase 1-2. Phase 5 removes this adapter.
"""

from __future__ import annotations

from typing import Any

from loomgraph.core.lightrag_client import LightRAGClient
from loomgraph.storage.base import GraphStore


class LightRAGGraphStore(GraphStore):
    """GraphStore implementation backed by LightRAG HTTP API.

    Forwards each contract method to the underlying LightRAGClient,
    discarding HTTP response payloads to honor the ABC's `None` return
    types. Callers needing batched insert with progress callback should
    reach for the underlying client via `self.client` until Phase 2
    promotes the batching API into the ABC itself.
    """

    def __init__(self, client: LightRAGClient) -> None:
        self.client = client

    # ----- Entity CRUD -----

    async def create_entity(
        self, entity_name: str, entity_data: dict[str, Any]
    ) -> None:
        await self.client.create_entity(entity_name, entity_data)

    async def entity_exists(self, entity_name: str) -> bool:
        return await self.client.entity_exists(entity_name)

    async def get_all_entities(self) -> list[dict[str, Any]]:
        return await self.client.get_all_entities()

    # ----- Relation CRUD -----

    async def create_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_data: dict[str, Any],
    ) -> None:
        await self.client.create_relation(
            source_entity, target_entity, relation_data
        )

    async def get_all_relations(self) -> list[dict[str, Any]]:
        return await self.client.get_all_relations()

    # ----- Bulk insert -----

    async def insert_custom_kg(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        chunks: list[dict[str, Any]] | None = None,
    ) -> None:
        await self.client.insert_custom_kg(entities, relationships, chunks)

    # ----- Delete -----

    async def delete_all(self) -> None:
        await self.client.delete_all()

    async def delete_by_source(self, source_ids: list[str]) -> None:
        await self.client.delete_by_source(source_ids)

    # ----- Source / workspace queries -----

    async def get_source_ids(
        self, source_prefix: str | None = None
    ) -> list[str]:
        return await self.client.get_source_ids(source_prefix=source_prefix)

    async def list_workspaces(self) -> list[str]:
        return await self.client.list_workspaces()

    # ----- Analytics -----

    async def get_orphan_entities(
        self,
        exclude_types: list[str] | None = None,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.client.get_orphan_entities(
            exclude_types=exclude_types,
            source_prefix=source_prefix,
        )

    async def get_degree_distribution(
        self,
        direction: str = "in",
        min_degree: int = 5,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.client.get_degree_distribution(
            direction=direction,
            min_degree=min_degree,
            source_prefix=source_prefix,
        )

    async def get_graph_stats(
        self,
        source_prefix: str | None = None,
        module_depth: int = 2,
    ) -> dict[str, Any]:
        return await self.client.get_graph_stats(
            source_prefix=source_prefix,
            module_depth=module_depth,
        )
