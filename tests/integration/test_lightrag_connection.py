"""Test LightRAG connection and basic operations.

This test verifies that LoomGraph can communicate with LightRAG
via HTTP API and perform basic entity/relation operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# Skip all tests if database not available
pytestmark = pytest.mark.integration


class MockLightRAGClient:
    """Mock LightRAG HTTP client for testing."""

    def __init__(self, base_url: str = "http://mock:9621"):
        self.base_url = base_url
        self.entities: list[dict[str, Any]] = []
        self.relations: list[dict[str, Any]] = []

    async def health_check(self) -> dict[str, Any]:
        return {"status": "healthy"}

    async def create_entity(self, entity_name: str, entity_data: dict[str, Any]) -> dict[str, Any]:
        self.entities.append({"name": entity_name, "data": entity_data})
        return {"status": "success", "message": f"Entity '{entity_name}' created"}

    async def create_relation(
        self, source_entity: str, target_entity: str, relation_data: dict[str, Any]
    ) -> dict[str, Any]:
        self.relations.append({
            "src": source_entity,
            "tgt": target_entity,
            "data": relation_data,
        })
        return {"status": "success", "message": "Relation created"}

    async def query(self, query: str, mode: str = "hybrid") -> dict[str, Any]:
        return {"response": f"Mock response for: {query}", "references": []}


class TestLightRAGClient:
    """Test LightRAGClient interface."""

    @pytest.mark.asyncio
    async def test_client_import(self) -> None:
        """Test that LightRAGClient can be imported."""
        from loomgraph.core.lightrag_client import LightRAGClient

        assert LightRAGClient is not None

    @pytest.mark.asyncio
    async def test_entity_creation_mock(self) -> None:
        """Test entity creation with mock client."""
        from loomgraph.core.models import ParseResult, Symbol
        from loomgraph.core.injector import inject_parse_result

        # Create test data
        result = ParseResult(
            path=Path("/test/auth.py"),
            symbols=[
                Symbol(
                    name="UserService",
                    kind="class",
                    signature="class UserService",
                    docstring="User authentication service.",
                    line_start=1,
                    line_end=20,
                ),
                Symbol(
                    name="UserService.login",
                    kind="method",
                    signature="def login(self, username: str) -> bool",
                    docstring="Authenticate user.",
                    line_start=5,
                    line_end=10,
                ),
            ],
        )

        mock_client = MockLightRAGClient()
        inject_result = await inject_parse_result(mock_client, result)

        # Verify entities were created
        assert inject_result.entities == 2
        assert len(mock_client.entities) == 2

        # Check entity data structure
        user_service = mock_client.entities[0]
        assert user_service["name"] == "UserService"
        assert "entity_type" in user_service["data"]
        assert "description" in user_service["data"]


class TestFullPipelineMock:
    """Test full pipeline with mocks (no remote service required)."""

    @pytest.mark.asyncio
    async def test_codeindex_to_lightrag_pipeline(
        self, temp_python_file: Path
    ) -> None:
        """Test full pipeline: codeindex → adapter → injector."""
        from codeindex.parser import parse_file
        from loomgraph.core.adapter import adapt_parse_result
        from loomgraph.core.injector import inject_parse_result

        # Step 1: Parse with codeindex
        ci_result = parse_file(temp_python_file)
        assert ci_result.error is None
        assert len(ci_result.symbols) > 0

        # Step 2: Adapt to LoomGraph format
        lg_result = adapt_parse_result(ci_result)
        assert len(lg_result.symbols) == len(ci_result.symbols)

        # Step 3: Inject via mock client
        mock_client = MockLightRAGClient()
        inject_result = await inject_parse_result(mock_client, lg_result)

        # Verify
        assert inject_result.entities == len(lg_result.symbols)
        assert inject_result.errors == []

        # Check that entity data has expected fields
        for entity in mock_client.entities:
            assert "entity_type" in entity["data"]
            assert "description" in entity["data"]
            assert "source_id" in entity["data"]

        # Check that import relations were created
        assert inject_result.relations == len(lg_result.imports)
