"""HTTP client for LightRAG API.

This module provides an async HTTP client for interacting with
LightRAG's REST API endpoints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LightRAGAPIError(Exception):
    """Exception raised when LightRAG API returns an error."""

    def __init__(self, message: str, status_code: int | None = None, detail: str | None = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


@dataclass
class LightRAGClient:
    """Async HTTP client for LightRAG API.

    Example:
        >>> client = LightRAGClient("http://internal.example.invalid:3001")
        >>> await client.health_check()
        >>> await client.create_entity("MyClass", {"entity_type": "CLASS", ...})
    """

    base_url: str
    timeout: float = 30.0

    def __post_init__(self) -> None:
        # Remove trailing slash
        self.base_url = self.base_url.rstrip("/")

    async def health_check(self) -> dict[str, Any]:
        """Check if LightRAG service is healthy.

        Returns:
            Health status dict from LightRAG

        Raises:
            LightRAGAPIError: If service is unhealthy or unreachable
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise LightRAGAPIError(
                    f"Health check failed: {e}",
                    status_code=e.response.status_code,
                ) from e
            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def create_entity(
        self,
        entity_name: str,
        entity_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an entity in LightRAG.

        Args:
            entity_name: Unique name for the entity (e.g., "UserService.login")
            entity_data: Entity attributes including:
                - entity_type: Type of entity (CLASS, FUNCTION, METHOD, etc.)
                - description: Description combining signature + docstring
                - source_id: Location in format "file:line"

        Returns:
            Response from LightRAG with created entity info

        Raises:
            LightRAGAPIError: If entity creation fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/graph/entity/create",
                    json={
                        "entity_name": entity_name,
                        "entity_data": entity_data,
                    },
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Failed to create entity '{entity_name}': {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def create_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a relation between two entities in LightRAG.

        Args:
            source_entity: Name of the source entity
            target_entity: Name of the target entity
            relation_data: Relation attributes including:
                - description: Description of the relation
                - keywords: Relation type (CALLS, IMPORTS, INHERITS, etc.)
                - source_id: Location in format "file:line"

        Returns:
            Response from LightRAG with created relation info

        Raises:
            LightRAGAPIError: If relation creation fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/graph/relation/create",
                    json={
                        "source_entity": source_entity,
                        "target_entity": target_entity,
                        "relation_data": relation_data,
                    },
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Failed to create relation '{source_entity}' -> '{target_entity}': {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def query(
        self,
        query: str,
        mode: str = "hybrid",
    ) -> dict[str, Any]:
        """Query the knowledge graph.

        Args:
            query: Natural language query
            mode: Query mode - "local", "global", "hybrid", "naive"

        Returns:
            Query response with results

        Raises:
            LightRAGAPIError: If query fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/query",
                    json={
                        "query": query,
                        "mode": mode,
                    },
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Query failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def entity_exists(self, entity_name: str) -> bool:
        """Check if an entity exists in the graph.

        Args:
            entity_name: Name of the entity to check

        Returns:
            True if entity exists, False otherwise
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/graph/entity/exists",
                    params={"entity_name": entity_name},
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("exists", False)
                return False
            except httpx.RequestError:
                return False

    async def delete_all(self) -> dict[str, Any]:
        """Delete all data from LightRAG (Cold Rebuild).

        This clears all entities, relations, chunks, and caches.
        Use with caution - this operation is irreversible.

        Returns:
            Response from LightRAG confirming deletion

        Raises:
            LightRAGAPIError: If deletion fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.delete(f"{self.base_url}/documents")
                data = response.json() if response.content else {}

                if response.status_code >= 400:
                    detail = data.get("detail", str(data)) if data else f"HTTP {response.status_code}"
                    raise LightRAGAPIError(
                        f"Failed to delete all documents: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                logger.info("Successfully deleted all documents from LightRAG")
                return data

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def insert_custom_kg(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        chunks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Batch insert custom knowledge graph data.

        This is more efficient than individual create_entity/create_relation calls.

        Args:
            entities: List of entity dicts with entity_name, entity_type, description, source_id
            relationships: List of relation dicts with src_id, tgt_id, description, keywords
            chunks: Optional list of chunk dicts with content, source_id

        Returns:
            Response with counts of inserted items

        Raises:
            LightRAGAPIError: If insertion fails

        Example:
            >>> entities = [{"entity_name": "MyClass", "entity_type": "class", ...}]
            >>> relations = [{"src_id": "MyClass", "tgt_id": "Base", "keywords": "INHERITS"}]
            >>> result = await client.insert_custom_kg(entities, relations)
        """
        custom_kg = {
            "entities": entities,
            "relationships": relationships,
        }
        if chunks:
            custom_kg["chunks"] = chunks

        async with httpx.AsyncClient(timeout=self.timeout * 3, trust_env=False) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/documents/insert_custom_kg",
                    json={"custom_kg": custom_kg},
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Failed to insert custom KG: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                logger.info(
                    f"Inserted custom KG: {data.get('details', {}).get('entities_count', 0)} entities, "
                    f"{data.get('details', {}).get('relationships_count', 0)} relations"
                )
                return data

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e
