"""End-to-end tests with real H200 LightRAG service.

These tests require access to H200 LightRAG API.
Set LIGHTRAG_API_URL environment variable or skip with SKIP_E2E_TESTS=1.

Example:
    LIGHTRAG_API_URL=http://internal.example.invalid:3001 pytest tests/integration/test_h200_e2e.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Get API URL from environment
LIGHTRAG_API_URL = os.getenv("LIGHTRAG_API_URL", "http://internal.example.invalid:3001")

# Skip all tests if SKIP_E2E_TESTS is set
pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("SKIP_E2E_TESTS", "").lower() in ("1", "true", "yes"),
        reason="SKIP_E2E_TESTS is set",
    ),
]


@pytest.fixture
async def lightrag_client():
    """Create a real LightRAG client."""
    from loomgraph.core.lightrag_client import LightRAGClient

    client = LightRAGClient(base_url=LIGHTRAG_API_URL, timeout=30.0)

    # Check connection
    try:
        await client.health_check()
    except Exception as e:
        pytest.skip(f"LightRAG not available at {LIGHTRAG_API_URL}: {e}")

    return client


class TestH200Connection:
    """Test connection to H200 LightRAG."""

    @pytest.mark.asyncio
    async def test_health_check(self, lightrag_client) -> None:
        """Test health check endpoint."""
        result = await lightrag_client.health_check()

        assert result["status"] == "healthy"
        assert "core_version" in result


class TestH200EntityOperations:
    """Test entity operations on H200."""

    @pytest.mark.asyncio
    async def test_create_entity(self, lightrag_client) -> None:
        """Test creating an entity on H200."""
        import time

        # Use unique name to avoid conflicts
        entity_name = f"LoomGraphTest_{int(time.time())}"

        result = await lightrag_client.create_entity(
            entity_name,
            {
                "entity_type": "CLASS",
                "description": "Integration test entity from LoomGraph",
                "source_id": "tests/integration/test_h200_e2e.py:1",
            },
        )

        assert result["status"] == "success"
        assert entity_name in result["message"]

    @pytest.mark.asyncio
    async def test_create_relation(self, lightrag_client) -> None:
        """Test creating a relation between entities on H200."""
        import time

        ts = int(time.time())
        src_name = f"LoomGraphTestSrc_{ts}"
        tgt_name = f"LoomGraphTestTgt_{ts}"

        # Create both entities first
        await lightrag_client.create_entity(
            src_name,
            {
                "entity_type": "CLASS",
                "description": "Source entity for relation test",
                "source_id": "tests/test.py:1",
            },
        )
        await lightrag_client.create_entity(
            tgt_name,
            {
                "entity_type": "METHOD",
                "description": "Target entity for relation test",
                "source_id": "tests/test.py:10",
            },
        )

        # Create relation
        result = await lightrag_client.create_relation(
            src_name,
            tgt_name,
            {
                "description": f"{src_name} contains {tgt_name}",
                "keywords": "CONTAINS",
                "source_id": "tests/test.py:10",
            },
        )

        assert result["status"] == "success"


class TestH200FullPipeline:
    """Test full injection pipeline on H200."""

    @pytest.mark.asyncio
    async def test_inject_python_file(
        self, lightrag_client, tmp_path: Path
    ) -> None:
        """Test injecting a parsed Python file into H200."""
        import time
        from codeindex.parser import parse_file
        from loomgraph.core.adapter import adapt_parse_result
        from loomgraph.core.injector import inject_parse_result

        # Create a unique test file to avoid entity conflicts
        ts = int(time.time())
        code = f'''"""Test module {ts}."""

class TestService_{ts}:
    """Test service class."""

    def test_method(self) -> bool:
        """Test method."""
        return True
'''
        test_file = tmp_path / f"test_service_{ts}.py"
        test_file.write_text(code)

        # Parse file
        ci_result = parse_file(test_file)
        lg_result = adapt_parse_result(ci_result)

        # Inject into H200
        inject_result = await inject_parse_result(lightrag_client, lg_result)

        # Verify - at least some entities should be created
        print(f"Injected {inject_result.entities} entities, {inject_result.relations} relations")
        if inject_result.errors:
            print(f"Errors: {inject_result.errors}")

        # Should have created at least the class
        assert inject_result.entities > 0

    @pytest.mark.asyncio
    async def test_query_after_inject(self, lightrag_client) -> None:
        """Test querying after injection."""
        result = await lightrag_client.query(
            "What is UserService?",
            mode="local",
        )

        assert "response" in result
        # The response should mention something about the entities
        print(f"Query response: {result['response'][:200]}...")
