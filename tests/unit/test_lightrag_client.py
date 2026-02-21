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
    async def test_insert_custom_kg_uses_extended_timeout(self, client: LightRAGClient) -> None:
        """Should use 3x timeout for large payloads."""
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

            # Verify timeout is 3x the base timeout (5.0 * 3 = 15.0)
            mock_client_class.assert_called_once_with(timeout=15.0, trust_env=False)


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


class TestBatchCreateGraphRetry:
    """Tests for retry logic in batch_create_graph."""

    @pytest.fixture
    def client(self) -> LightRAGClient:
        """Create a test client."""
        return LightRAGClient(base_url="http://localhost:3001", timeout=5.0)

    @pytest.mark.asyncio
    async def test_retry_on_500_then_success(self, client: LightRAGClient) -> None:
        """Should retry on 500 and succeed on next attempt."""
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        fail_resp.json.return_value = {"detail": "Internal server error"}

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"status": "ok"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # First call fails with 500, second succeeds
            mock_client.post.side_effect = [fail_resp, ok_resp]
            mock_client_class.return_value = mock_client

            entities = [{"entity_name": "Foo", "entity_type": "class", "description": "test"}]
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.batch_create_graph(entities, [], max_retries=3)

            assert result["details"]["entities_count"] == 1
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_records_error(self, client: LightRAGClient) -> None:
        """Should record error after all retries exhausted."""
        fail_resp = MagicMock()
        fail_resp.status_code = 502
        fail_resp.json.return_value = {"detail": "Bad Gateway"}
        fail_resp.text = "Bad Gateway"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = fail_resp
            mock_client_class.return_value = mock_client

            entities = [{"entity_name": "Foo", "entity_type": "class"}]
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.batch_create_graph(entities, [], max_retries=2)

            assert result["details"]["entities_count"] == 0
            assert result["status"] == "partial"
            # 1 initial + 2 retries = 3 calls
            assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, client: LightRAGClient) -> None:
        """Should NOT retry on 400 client errors."""
        bad_req = MagicMock()
        bad_req.status_code = 400
        bad_req.json.return_value = {"detail": "Bad request"}
        bad_req.text = "Bad request"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = bad_req
            mock_client_class.return_value = mock_client

            entities = [{"entity_name": "Foo", "entity_type": "class"}]
            result = await client.batch_create_graph(entities, [], max_retries=3)

            assert result["details"]["entities_count"] == 0
            # Only 1 call — no retries for 400
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_default_concurrency_is_5(self, client: LightRAGClient) -> None:
        """Default concurrency should be 5 (not 10)."""
        import inspect
        sig = inspect.signature(client.batch_create_graph)
        assert sig.parameters["concurrency"].default == 5

    @pytest.mark.asyncio
    async def test_relation_retry_on_503(self, client: LightRAGClient) -> None:
        """Should retry relation creation on 503."""
        # Entity creation succeeds immediately
        entity_ok = MagicMock()
        entity_ok.status_code = 200
        entity_ok.json.return_value = {"status": "ok"}

        # Relation: first 503, then success
        rel_fail = MagicMock()
        rel_fail.status_code = 503
        rel_fail.json.return_value = {"detail": "Service Unavailable"}

        rel_ok = MagicMock()
        rel_ok.status_code = 200
        rel_ok.json.return_value = {"status": "ok"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # Entity create → ok, Relation create → 503 → ok
            mock_client.post.side_effect = [entity_ok, rel_fail, rel_ok]
            mock_client_class.return_value = mock_client

            entities = [{"entity_name": "A", "entity_type": "class"}]
            relations = [{"src_id": "A", "tgt_id": "A", "keywords": "self"}]

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.batch_create_graph(entities, relations, max_retries=2)

            assert result["details"]["entities_count"] == 1
            assert result["details"]["relationships_count"] == 1
            assert mock_client.post.call_count == 3
