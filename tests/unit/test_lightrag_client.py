"""Tests for loomgraph.core.lightrag_client module."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from loomgraph.core.lightrag_client import LightRAGAPIError, LightRAGClient


class TestLightRAGClient:
    """Tests for LightRAGClient class."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    def test_removes_trailing_slash(self) -> None:
        """Should remove trailing slash from base_url."""
        client = LightRAGClient(base_url="http://localhost:3001/")
        assert client.base_url == "http://localhost:3001"


class TestDeleteAll:
    """Tests for delete_all method."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_delete_all_success(self, client: LightRAGClient) -> None:
        """Should successfully delete all documents."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"status": "ok", "deleted": 42}'
        mock_response.json.return_value = {"status": "ok", "deleted": 42}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.delete_all()

            assert result == {"status": "ok", "deleted": 42}
            mock_client.delete.assert_called_once_with(
                "http://localhost:3001/documents"
            )

    @pytest.mark.asyncio
    async def test_delete_all_empty_response(self, client: LightRAGClient) -> None:
        """Should handle empty response body."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.content = b""

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.delete_all()

            assert result == {}

    @pytest.mark.asyncio
    async def test_delete_all_api_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b'{"detail": "Internal server error"}'
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.delete_all()

            assert exc_info.value.status_code == 500
            assert "Internal server error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_all_connection_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on connection failure."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete.side_effect = httpx.RequestError("Connection refused")
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.delete_all()

            assert "Connection failed" in str(exc_info.value)


class TestCreateEntity:
    """Tests for create_entity method."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_create_entity_success(self, client: LightRAGClient) -> None:
        """Should successfully create an entity."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entity_name": "test", "created": True}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.create_entity(
                "TestClass",
                {"entity_type": "class", "description": "A test class"},
            )

            assert result["created"] is True
            mock_client.post.assert_called_once()


class TestQuery:
    """Tests for query method."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_query_success(self, client: LightRAGClient) -> None:
        """Should successfully query."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Found 3 relevant functions",
            "references": [],
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.query("user authentication", mode="hybrid")

            assert "response" in result
            mock_client.post.assert_called_once()
