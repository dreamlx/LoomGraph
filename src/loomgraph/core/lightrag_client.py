"""HTTP client for LightRAG API.

This module provides an async HTTP client for interacting with
LightRAG's REST API endpoints.
"""

from __future__ import annotations

import asyncio
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

        # With workspace isolation
        >>> client = LightRAGClient("http://internal.example.invalid:3001", workspace="erp")
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

        Calls DELETE /graph/clear which clears all 11 storage layers
        (graph, vectors, chunks, etc.) in one request.

        Returns:
            Response from the clear operation

        Raises:
            LightRAGAPIError: If deletion fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                resp = await client.delete(
                    f"{self.base_url}/graph/clear",
                    headers=self._get_headers(),
                )
                data = resp.json() if resp.content else {}
                if resp.status_code >= 400:
                    detail = data.get("detail", str(data)) if data else f"HTTP {resp.status_code}"
                    raise LightRAGAPIError(
                        f"Failed to clear graph: {detail}",
                        status_code=resp.status_code,
                        detail=detail,
                    )
                logger.info("Cleared all storage layers via /graph/clear")
                # Wait for async storage cleanup to complete
                await asyncio.sleep(3)
                return {"graph": data}
            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def delete_by_source(self, source_ids: list[str]) -> dict[str, Any]:
        """Delete all data associated with given source_ids.

        Used for warm update: delete old data for changed files before re-injecting.

        Args:
            source_ids: List of source_id strings (e.g., file paths)

        Returns:
            Response with deletion counts

        Raises:
            LightRAGAPIError: If deletion fails
        """
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.request(
                    "DELETE",
                    f"{self.base_url}/graph/by_source",
                    headers=self._get_headers(),
                    json={"source_ids": source_ids},
                )
                data = response.json() if response.content else {}

                if response.status_code >= 400:
                    detail = data.get("detail", str(data)) if data else f"HTTP {response.status_code}"
                    raise LightRAGAPIError(
                        f"Failed to delete by source: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                logger.info(f"Deleted data for {len(source_ids)} source(s)")
                return data

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    def _calculate_timeout(self, entity_count: int) -> float:
        """Calculate dynamic timeout based on payload size.

        Heuristic: base 30s + 1s per 200 entities, minimum 60s for any batch.

        Args:
            entity_count: Number of entities in the batch

        Returns:
            Timeout in seconds
        """
        dynamic = max(60.0, 30.0 + entity_count / 200.0)
        # Never less than configured timeout × 3 (backward compatibility)
        return max(dynamic, self.timeout * 3)

    async def insert_custom_kg(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        chunks: list[dict[str, Any]] | None = None,
        *,
        batch_size: int = 5000,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        """Batch insert custom knowledge graph data.

        For large payloads (>batch_size entities), automatically splits into
        multiple HTTP calls to avoid timeouts.

        Args:
            entities: List of entity dicts with entity_name, entity_type, description, source_id
            relationships: List of relation dicts with src_id, tgt_id, description, keywords
            chunks: Optional list of chunk dicts with content, source_id
            batch_size: Max entities per HTTP call (default 5000)
            progress_callback: Optional callable(batch_num, total_batches, entities_in_batch)

        Returns:
            Response with counts of inserted items

        Raises:
            LightRAGAPIError: If insertion fails

        Example:
            >>> entities = [{"entity_name": "MyClass", "entity_type": "class", ...}]
            >>> relations = [{"src_id": "MyClass", "tgt_id": "Base", "keywords": "INHERITS"}]
            >>> result = await client.insert_custom_kg(entities, relations)
        """
        total_entities = len(entities)

        # Small payload: single call (no splitting needed)
        if total_entities <= batch_size:
            return await self._insert_custom_kg_single(
                entities, relationships, chunks, total_entities,
            )

        # Large payload: split into batches
        logger.info(
            f"Large payload ({total_entities} entities), splitting into "
            f"batches of {batch_size}"
        )

        # Build entity name set per batch for relation routing
        batches: list[tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]] | None]] = []
        for i in range(0, total_entities, batch_size):
            batch_entities = entities[i:i + batch_size]
            batch_entity_names = {e.get("entity_name", "") for e in batch_entities}

            # Route relations: include if src or tgt is in this batch
            batch_relations = [
                r for r in relationships
                if r.get("src_id", "") in batch_entity_names
                or r.get("tgt_id", "") in batch_entity_names
            ]

            # Route chunks: include if source_id matches any entity's source_id
            batch_source_ids = {e.get("source_id", "") for e in batch_entities}
            batch_chunks = None
            if chunks:
                batch_chunks = [
                    c for c in chunks
                    if c.get("source_id", "") in batch_source_ids
                    or c.get("full_doc_id", "") in batch_source_ids
                ]

            batches.append((batch_entities, batch_relations, batch_chunks))

        total_batches = len(batches)
        combined_result: dict[str, Any] = {
            "status": "success",
            "details": {"entities_count": 0, "relationships_count": 0},
            "batches": total_batches,
        }

        for batch_num, (b_entities, b_relations, b_chunks) in enumerate(batches, 1):
            if progress_callback:
                progress_callback(batch_num, total_batches, len(b_entities))

            logger.info(
                f"Batch {batch_num}/{total_batches}: "
                f"{len(b_entities)} entities, {len(b_relations)} relations"
            )

            result = await self._insert_custom_kg_single(
                b_entities, b_relations, b_chunks, len(b_entities),
            )
            details = result.get("details", {})
            combined_result["details"]["entities_count"] += details.get(
                "entities_count", len(b_entities)
            )
            combined_result["details"]["relationships_count"] += details.get(
                "relationships_count", len(b_relations)
            )

        return combined_result

    async def _insert_custom_kg_single(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        chunks: list[dict[str, Any]] | None,
        entity_count: int,
    ) -> dict[str, Any]:
        """Execute a single insert_custom_kg HTTP call."""
        custom_kg: dict[str, Any] = {
            "entities": entities,
            "relationships": relationships,
        }
        if chunks:
            custom_kg["chunks"] = chunks

        timeout = self._calculate_timeout(entity_count)
        logger.debug(f"insert_custom_kg timeout: {timeout:.0f}s for {entity_count} entities")

        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
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

            except httpx.ReadTimeout as e:
                raise LightRAGAPIError(
                    f"Timeout after {timeout:.0f}s inserting {entity_count} entities. "
                    f"Try increasing api_timeout in .loomgraph.yaml or use a smaller batch.",
                ) from e
            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

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

    async def get_orphan_entities(
        self,
        exclude_types: list[str] | None = None,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get orphan entities (0 in-degree + 0 out-degree).

        Calls server-side endpoint if available. Raises on failure
        so TopologyAnalyzer can fall back to client-side computation.

        Args:
            exclude_types: Entity types to exclude (e.g. ["module"])
            source_prefix: Filter by source_id prefix

        Returns:
            List of orphan entity dicts

        Raises:
            LightRAGAPIError: If endpoint is not available or request fails
        """
        params: dict[str, Any] = {}
        if exclude_types:
            params["exclude_types"] = ",".join(exclude_types)
        if source_prefix:
            params["source_prefix"] = source_prefix

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/graph/orphans",
                    headers=self._get_headers(),
                    params=params,
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Get orphan entities failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data if isinstance(data, list) else data.get("entities", [])

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def get_degree_distribution(
        self,
        direction: str = "in",
        min_degree: int = 5,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get entities exceeding a degree threshold.

        Args:
            direction: "in" for callers or "out" for callees
            min_degree: Minimum degree to include
            source_prefix: Filter by source_id prefix

        Returns:
            List of entity dicts with degree info

        Raises:
            LightRAGAPIError: If endpoint is not available or request fails
        """
        params: dict[str, Any] = {
            "direction": direction,
            "min_degree": min_degree,
        }
        if source_prefix:
            params["source_prefix"] = source_prefix

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/graph/degree",
                    headers=self._get_headers(),
                    params=params,
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Get degree distribution failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data if isinstance(data, list) else data.get("entities", [])

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def get_graph_stats(
        self,
        source_prefix: str | None = None,
        module_depth: int = 2,
    ) -> dict[str, Any]:
        """Get graph statistics (entity/relation counts, coupling).

        Args:
            source_prefix: Filter by source_id prefix. Also stripped from
                source_ids before module extraction for coupling analysis.
            module_depth: Directory depth for module extraction in coupling
                analysis (default: 2). e.g. depth=2: "src/core/config.py" → "src/core"

        Returns:
            Dict with entity_count, relation_count, cross_module_relations,
            intra_module_relations, coupling_density.

        Raises:
            LightRAGAPIError: If endpoint is not available or request fails
        """
        params: dict[str, Any] = {}
        if source_prefix:
            params["source_prefix"] = source_prefix
        if module_depth != 2:
            params["module_depth"] = module_depth

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/graph/stats",
                    headers=self._get_headers(),
                    params=params,
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Get graph stats failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e

    async def get_source_ids(
        self,
        source_prefix: str | None = None,
    ) -> list[str]:
        """Get deduplicated list of source_ids from entities.

        Args:
            source_prefix: Filter by source_id prefix

        Returns:
            List of unique source_id strings

        Raises:
            LightRAGAPIError: If endpoint is not available or request fails
        """
        params: dict[str, Any] = {}
        if source_prefix:
            params["source_prefix"] = source_prefix

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/graph/source_ids",
                    headers=self._get_headers(),
                    params=params,
                )
                data = response.json()

                if response.status_code >= 400:
                    detail = data.get("detail", str(data))
                    raise LightRAGAPIError(
                        f"Get source IDs failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

                return data if isinstance(data, list) else data.get("source_ids", [])

            except httpx.RequestError as e:
                raise LightRAGAPIError(f"Connection failed: {e}") from e
