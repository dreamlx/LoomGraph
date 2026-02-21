"""HTTP client for LightRAG API.

This module provides an async HTTP client for interacting with
LightRAG's REST API endpoints.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
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
        >>> client = LightRAGClient("http://117.131.45.179:3001")
        >>> await client.health_check()
        >>> await client.create_entity("MyClass", {"entity_type": "CLASS", ...})

        # With workspace isolation
        >>> client = LightRAGClient("http://117.131.45.179:3001", workspace="erp")
        >>> await client.insert_custom_kg(entities, relations)  # Stored in erp workspace
    """

    base_url: str
    timeout: float = 30.0
    workspace: str | None = None  # Optional workspace for multi-project isolation

    def __post_init__(self) -> None:
        # Remove trailing slash
        self.base_url = self.base_url.rstrip("/")

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers including workspace if set."""
        headers: dict[str, str] = {}
        if self.workspace:
            headers["LIGHTRAG-WORKSPACE"] = self.workspace
        return headers

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
                    headers=self._get_headers(),
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
                    headers=self._get_headers(),
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
                    headers=self._get_headers(),
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
                    headers=self._get_headers(),
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
                response = await client.delete(
                    f"{self.base_url}/documents",
                    headers=self._get_headers(),
                )
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
                    headers=self._get_headers(),
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

    async def batch_create_graph(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        concurrency: int = 10,
    ) -> dict[str, Any]:
        """Batch create entities and relations via graph endpoints.

        Three-pass approach:
        1. Create ALL project entities concurrently
        2. Auto-create stub entities for external dependencies
        3. Create ALL relations concurrently

        Uses /graph/entity/create and /graph/relation/create endpoints
        which populate the graph layer (queryable via /graphs, /graph/label/list).

        Args:
            entities: List of entity dicts from collect_kg_data().
                Each has: entity_name, entity_type, description, source_id, ...
            relationships: List of relation dicts from collect_kg_data().
                Each has: src_id, tgt_id, description, keywords, source_id, ...
            concurrency: Max concurrent HTTP requests (default: 10)

        Returns:
            Dict with entities_created, relations_created, external_stubs, errors
        """
        sem = asyncio.Semaphore(concurrency)
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        entity_errors: list[str] = []
        relation_errors: list[str] = []
        entities_created = 0
        entities_existing = 0
        relations_created = 0
        external_stubs_created = 0
        known_entities: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            # Pass 1: Create all project entities concurrently
            async def _create_entity(entity: dict[str, Any]) -> bool:
                nonlocal entities_created, entities_existing
                name = entity.get("entity_name", "")
                data = {k: v for k, v in entity.items() if k != "entity_name"}
                async with sem:
                    try:
                        resp = await client.post(
                            f"{self.base_url}/graph/entity/create",
                            headers=headers,
                            json={"entity_name": name, "entity_data": data},
                        )
                        if resp.status_code < 400:
                            entities_created += 1
                            known_entities.add(name)
                            return True
                        detail = resp.json().get("detail", resp.text)
                        if "already exist" in str(detail).lower():
                            entities_existing += 1
                            known_entities.add(name)
                            return True
                        entity_errors.append(f"{name}: {detail}")
                        return False
                    except Exception as e:
                        entity_errors.append(f"{name}: {e}")
                        return False

            await asyncio.gather(*[_create_entity(e) for e in entities])

            # Pass 1.5: Auto-create stub entities for external dependencies
            # Scan all relation endpoints; any target not in known_entities gets a stub
            missing_names: set[str] = set()
            for rel in relationships:
                for key in ("src_id", "tgt_id"):
                    name = rel.get(key, "")
                    if name and name not in known_entities:
                        missing_names.add(name)

            if missing_names:
                async def _create_stub(name: str) -> bool:
                    nonlocal external_stubs_created
                    async with sem:
                        try:
                            resp = await client.post(
                                f"{self.base_url}/graph/entity/create",
                                headers=headers,
                                json={
                                    "entity_name": name,
                                    "entity_data": {
                                        "entity_type": "external",
                                        "description": f"External dependency: {name}",
                                        "source_id": "external",
                                    },
                                },
                            )
                            if resp.status_code < 400:
                                external_stubs_created += 1
                                known_entities.add(name)
                                return True
                            detail = resp.json().get("detail", resp.text)
                            if "already exist" in str(detail).lower():
                                known_entities.add(name)
                                return True
                            return False
                        except Exception:
                            return False

                await asyncio.gather(*[_create_stub(n) for n in missing_names])
                logger.info(f"Created {external_stubs_created} stub entities for external dependencies")

            # Pass 2: Create all relations concurrently (all entities exist now)
            async def _create_relation(rel: dict[str, Any]) -> bool:
                nonlocal relations_created
                src = rel.get("src_id", "")
                tgt = rel.get("tgt_id", "")
                data = {k: v for k, v in rel.items() if k not in ("src_id", "tgt_id")}
                async with sem:
                    try:
                        resp = await client.post(
                            f"{self.base_url}/graph/relation/create",
                            headers=headers,
                            json={
                                "source_entity": src,
                                "target_entity": tgt,
                                "relation_data": data,
                            },
                        )
                        if resp.status_code < 400:
                            relations_created += 1
                            return True
                        detail = resp.json().get("detail", resp.text)
                        relation_errors.append(f"{src}->{tgt}: {detail}")
                        return False
                    except Exception as e:
                        relation_errors.append(f"{src}->{tgt}: {e}")
                        return False

            await asyncio.gather(*[_create_relation(r) for r in relationships])

        all_errors = entity_errors + relation_errors
        result: dict[str, Any] = {
            "status": "success" if not all_errors else "partial",
            "details": {
                "entities_count": entities_created,
                "entities_existing": entities_existing,
                "relationships_count": relations_created,
                "external_stubs": external_stubs_created,
            },
        }
        if all_errors:
            result["errors"] = all_errors[:20]
            result["errors_total"] = len(all_errors)

        logger.info(
            f"Batch graph: {entities_created}/{len(entities)} entities, "
            f"{relations_created}/{len(relationships)} relations, "
            f"{external_stubs_created} external stubs, "
            f"{len(all_errors)} errors"
        )
        return result

    async def list_workspaces(self) -> list[str]:
        """List all available workspaces.

        Calls GET /api/workspaces without workspace header to get global list.

        Returns:
            List of workspace name strings

        Raises:
            LightRAGAPIError: If request fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/workspaces",
                    headers=self._get_headers(),
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"List workspaces failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data.get("workspaces", [])

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def get_all_entities(self) -> list[dict[str, Any]]:
        """Get all entities from the knowledge graph.

        Returns:
            List of entity dicts

        Raises:
            LightRAGAPIError: If request fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/graph/entities/all",
                    headers=self._get_headers(),
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Get all entities failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data if isinstance(data, list) else data.get("entities", [])

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def get_all_relations(self) -> list[dict[str, Any]]:
        """Get all relations from the knowledge graph.

        Returns:
            List of relation dicts

        Raises:
            LightRAGAPIError: If request fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/graph/relations/all",
                    headers=self._get_headers(),
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Get all relations failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data if isinstance(data, list) else data.get("relations", [])

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e
