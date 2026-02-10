"""End-to-end tests with real LightRAG API on H200.

These tests require:
1. LightRAG running on H200: http://internal.example.invalid:3001
2. Network access to H200 (no proxy)

Set SKIP_E2E_TESTS=1 to skip these tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Skip if E2E tests disabled
pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("SKIP_E2E_TESTS", "").lower() in ("1", "true", "yes"),
        reason="SKIP_E2E_TESTS is set",
    ),
]

# H200 LightRAG endpoint
LIGHTRAG_URL = os.getenv("LIGHTRAG_URL", "http://internal.example.invalid:3001")


@pytest.fixture
def lightrag_client():
    """Create LightRAG client for H200."""
    from loomgraph.core.lightrag_client import LightRAGClient

    return LightRAGClient(base_url=LIGHTRAG_URL, timeout=30.0)


class TestLightRAGConnection:
    """Test LightRAG API connectivity."""

    @pytest.mark.asyncio
    async def test_health_check(self, lightrag_client) -> None:
        """Test LightRAG health endpoint."""
        result = await lightrag_client.health_check()

        assert result["status"] == "healthy"
        assert "core_version" in result

    @pytest.mark.asyncio
    async def test_create_entity(self, lightrag_client) -> None:
        """Test entity creation via HTTP API."""
        import uuid

        # Use unique name to avoid conflicts
        entity_name = f"E2ETestEntity_{uuid.uuid4().hex[:8]}"

        result = await lightrag_client.create_entity(
            entity_name,
            {
                "entity_type": "CLASS",
                "description": "E2E test entity for LoomGraph integration",
                "source_id": "tests/e2e/test.py:1",
            },
        )

        assert result["status"] == "success"
        assert entity_name in result["message"]


class TestFullPipeline:
    """Test full codeindex → LoomGraph → LightRAG pipeline."""

    @pytest.mark.asyncio
    async def test_parse_and_inject(
        self, lightrag_client, temp_python_file: Path
    ) -> None:
        """Test parsing a file and injecting into LightRAG."""
        import uuid

        from codeindex.parser import parse_file

        from loomgraph.core.adapter import adapt_parse_result
        from loomgraph.core.injector import inject_parse_result

        # Step 1: Parse with codeindex
        ci_result = parse_file(temp_python_file)
        assert ci_result.error is None
        assert len(ci_result.symbols) > 0

        # Step 2: Adapt to LoomGraph format
        lg_result = adapt_parse_result(ci_result)

        # Add unique prefix to avoid conflicts with previous test runs
        prefix = f"E2E_{uuid.uuid4().hex[:6]}_"
        for symbol in lg_result.symbols:
            symbol.name = prefix + symbol.name

        # Step 3: Inject into LightRAG
        inject_result = await inject_parse_result(lightrag_client, lg_result)

        # Verify
        assert inject_result.entities > 0
        # Some relations may fail if target entity doesn't exist (expected for imports)
        print(f"Injected: {inject_result.entities} entities, {inject_result.relations} relations")
        if inject_result.errors:
            print(f"Errors (expected for imports): {inject_result.errors[:3]}")

    @pytest.mark.asyncio
    async def test_query_after_inject(self, lightrag_client) -> None:
        """Test querying data after injection."""
        import uuid

        # First create some test entities
        prefix = f"QueryTest_{uuid.uuid4().hex[:6]}"

        await lightrag_client.create_entity(
            f"{prefix}_AuthService",
            {
                "entity_type": "CLASS",
                "description": "Service that handles user authentication and login",
                "source_id": "test/auth.py:1",
            },
        )

        await lightrag_client.create_entity(
            f"{prefix}_LoginMethod",
            {
                "entity_type": "METHOD",
                "description": "Method that validates username and password",
                "source_id": "test/auth.py:10",
            },
        )

        # Query for authentication-related entities
        result = await lightrag_client.query(
            f"What is {prefix}_AuthService?",
            mode="local",
        )

        assert "response" in result
        # The response should mention our test entity
        print(f"Query response: {result['response'][:200]}...")
