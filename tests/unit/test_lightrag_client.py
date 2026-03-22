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
    """Tests for delete_all method (clears all layers via /graph/clear)."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    def _make_response(self, status: int = 200, body: dict | None = None) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        if body is not None:
            resp.content = b"1"
            resp.json.return_value = body
        else:
            resp.content = b""
        return resp

    @pytest.mark.asyncio
    async def test_delete_all_success(self, client: LightRAGClient) -> None:
        """Should clear all layers via single /graph/clear call."""
        graph_resp = self._make_response(200, {"status": "success", "storages_cleared": 11})

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete.return_value = graph_resp
            mock_client_class.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.delete_all()

            assert result["graph"]["status"] == "success"
            assert mock_client.delete.call_count == 1
            mock_client.delete.assert_called_once_with(
                "http://localhost:3001/graph/clear",
                headers={},
            )

    @pytest.mark.asyncio
    async def test_delete_all_error_raises(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError when /graph/clear fails."""
        resp = self._make_response(500, {"detail": "Internal server error"})

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete.return_value = resp
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.delete_all()

            assert exc_info.value.status_code == 500

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

    @pytest.mark.asyncio
    async def test_delete_all_with_workspace(self) -> None:
        """Should send workspace header."""
        client = LightRAGClient(
            base_url="http://localhost:3001", timeout=5.0, workspace="my-ws"
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"1"
        resp.json.return_value = {"status": "success"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete.return_value = resp
            mock_client_class.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                await client.delete_all()

            mock_client.delete.assert_called_once_with(
                "http://localhost:3001/graph/clear",
                headers={"LIGHTRAG-WORKSPACE": "my-ws"},
            )


class TestDeleteBySource:
    """Tests for delete_by_source method."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_delete_by_source_success(self, client: LightRAGClient) -> None:
        """Should delete data for given source_ids."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"1"
        mock_response.json.return_value = {"deleted": 15}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.delete_by_source(["src/auth/service.py", "src/auth/utils.py"])

            assert result["deleted"] == 15
            mock_client.request.assert_called_once_with(
                "DELETE",
                "http://localhost:3001/graph/by_source",
                headers={},
                json={"source_ids": ["src/auth/service.py", "src/auth/utils.py"]},
            )

    @pytest.mark.asyncio
    async def test_delete_by_source_api_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on API failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b"1"
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.delete_by_source(["src/foo.py"])

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_by_source_connection_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on connection failure."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request.side_effect = httpx.RequestError("Connection refused")
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.delete_by_source(["src/foo.py"])

            assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_by_source_with_workspace(self) -> None:
        """Should send workspace header."""
        client = LightRAGClient(
            base_url="http://localhost:3001", timeout=5.0, workspace="my-ws"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"1"
        mock_response.json.return_value = {"deleted": 0}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            await client.delete_by_source(["src/foo.py"])

            mock_client.request.assert_called_once_with(
                "DELETE",
                "http://localhost:3001/graph/by_source",
                headers={"LIGHTRAG-WORKSPACE": "my-ws"},
                json={"source_ids": ["src/foo.py"]},
            )


class TestInsertCustomKG:
    """Tests for insert_custom_kg method."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_insert_custom_kg_success(self, client: LightRAGClient) -> None:
        """Should insert entities, relations, and chunks in one call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "details": {"entities_count": 3, "relationships_count": 2},
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            entities = [{"entity_name": "A", "entity_type": "class"}]
            relations = [{"src_id": "A", "tgt_id": "B", "keywords": "CALLS"}]
            chunks = [{"content": "test", "source_id": "test.py"}]

            result = await client.insert_custom_kg(entities, relations, chunks)

            assert result["status"] == "success"
            assert result["details"]["entities_count"] == 3

            # Verify the payload structure
            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["custom_kg"]["entities"] == entities
            assert call_args[1]["json"]["custom_kg"]["relationships"] == relations
            assert call_args[1]["json"]["custom_kg"]["chunks"] == chunks

    @pytest.mark.asyncio
    async def test_insert_custom_kg_without_chunks(self, client: LightRAGClient) -> None:
        """Should work without chunks."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "details": {}}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.insert_custom_kg(
                [{"entity_name": "X"}], [{"src_id": "X", "tgt_id": "Y"}],
            )

            assert result["status"] == "success"
            # chunks should not be in payload
            call_args = mock_client.post.call_args
            assert "chunks" not in call_args[1]["json"]["custom_kg"]

    @pytest.mark.asyncio
    async def test_insert_custom_kg_api_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on API failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.insert_custom_kg([{"entity_name": "X"}], [])

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_insert_custom_kg_connection_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on connection failure."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = httpx.RequestError("Connection refused")
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.insert_custom_kg([{"entity_name": "X"}], [])

            assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_insert_custom_kg_uses_dynamic_timeout(self, client: LightRAGClient) -> None:
        """Should use dynamic timeout based on entity count (minimum 60s)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "details": {}}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            await client.insert_custom_kg([], [])

            # Dynamic timeout: max(60.0, 30 + 0/200) = 60.0, max(60.0, 5*3=15) = 60.0
            mock_client_class.assert_called_once_with(timeout=60.0, trust_env=False)

    @pytest.mark.asyncio
    async def test_insert_custom_kg_timeout_scales_with_entities(self, client: LightRAGClient) -> None:
        """Timeout should scale with entity count for large payloads."""
        # 10000 entities: max(60, 30 + 10000/200) = max(60, 80) = 80
        # max(80, 5*3=15) = 80
        assert client._calculate_timeout(10000) == 80.0
        # 0 entities: max(60, 30) = 60, max(60, 15) = 60
        assert client._calculate_timeout(0) == 60.0
        # 20000 entities: max(60, 30 + 100) = 130, max(130, 15) = 130
        assert client._calculate_timeout(20000) == 130.0

    @pytest.mark.asyncio
    async def test_insert_custom_kg_batching(self, client: LightRAGClient) -> None:
        """Large payloads should be split into batches."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "details": {"entities_count": 3, "relationships_count": 0},
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            entities = [{"entity_name": f"E{i}", "entity_type": "class"} for i in range(6)]
            result = await client.insert_custom_kg(entities, [], batch_size=3)

            # Should have made 2 HTTP calls (6 entities / 3 per batch)
            assert mock_client.post.call_count == 2
            assert result["batches"] == 2
            assert result["details"]["entities_count"] == 6


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


class TestGetAllEntities:
    """Tests for get_all_entities method."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_get_all_entities_success(self, client: LightRAGClient) -> None:
        """Should return list of entities."""
        entities = [
            {"entity_name": "MyClass", "entity_type": "class", "source_id": "src/foo.py"},
            {"entity_name": "my_func", "entity_type": "function", "source_id": "src/bar.py"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = entities

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.get_all_entities()

            assert result == entities
            assert len(result) == 2
            mock_client.get.assert_called_once_with(
                "http://localhost:3001/graph/entities/all",
                headers={},
            )

    @pytest.mark.asyncio
    async def test_get_all_entities_with_workspace(self) -> None:
        """Should send workspace header."""
        client = LightRAGClient(
            base_url="http://localhost:3001", timeout=5.0, workspace="my-project"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            await client.get_all_entities()

            mock_client.get.assert_called_once_with(
                "http://localhost:3001/graph/entities/all",
                headers={"LIGHTRAG-WORKSPACE": "my-project"},
            )

    @pytest.mark.asyncio
    async def test_get_all_entities_api_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.get_all_entities()

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_get_all_entities_connection_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on connection failure."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.RequestError("Connection refused")
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.get_all_entities()

            assert "Connection failed" in str(exc_info.value)


class TestListWorkspaces:
    """Tests for list_workspaces method."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_list_workspaces_success(self, client: LightRAGClient) -> None:
        """Should return list of workspace names."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"workspaces": ["ws1", "ws2"], "count": 2}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.list_workspaces()

            assert result == ["ws1", "ws2"]
            mock_client.get.assert_called_once_with(
                "http://localhost:3001/api/workspaces",
                headers={},
            )

    @pytest.mark.asyncio
    async def test_list_workspaces_empty(self, client: LightRAGClient) -> None:
        """Should return empty list when no workspaces exist."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"workspaces": [], "count": 0}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.list_workspaces()

            assert result == []

    @pytest.mark.asyncio
    async def test_list_workspaces_api_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on API failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.list_workspaces()

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_list_workspaces_connection_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on connection failure."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.RequestError("Connection refused")
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.list_workspaces()

            assert "Connection failed" in str(exc_info.value)


class TestGetAllRelations:
    """Tests for get_all_relations method."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_get_all_relations_success(self, client: LightRAGClient) -> None:
        """Should return list of relations."""
        relations = [
            {"src_id": "MyClass", "tgt_id": "BaseClass", "relation_type": "INHERITS"},
            {"src_id": "my_func", "tgt_id": "helper", "relation_type": "CALLS"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = relations

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.get_all_relations()

            assert result == relations
            assert len(result) == 2
            mock_client.get.assert_called_once_with(
                "http://localhost:3001/graph/relations/all",
                headers={},
            )

    @pytest.mark.asyncio
    async def test_get_all_relations_api_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.get_all_relations()

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_get_all_relations_connection_error(self, client: LightRAGClient) -> None:
        """Should raise LightRAGAPIError on connection failure."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.RequestError("Connection refused")
            mock_client_class.return_value = mock_client

            with pytest.raises(LightRAGAPIError) as exc_info:
                await client.get_all_relations()

            assert "Connection failed" in str(exc_info.value)

