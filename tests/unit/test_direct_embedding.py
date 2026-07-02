"""DirectEmbeddingClient tests — OpenAI-compatible /v1/embeddings."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from loomgraph.embedding.base import EmbeddingClient
from loomgraph.embedding.direct import DirectEmbeddingClient, EmbeddingAPIError


def _make_response(
    *, status: int = 200, json_body: dict | None = None, text: str = ""
) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        request=httpx.Request("POST", "http://x/v1/embeddings"),
        json=json_body,
        text=text if json_body is None else None,
    )


@pytest.fixture
def post_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def patched_post(post_mock: AsyncMock) -> Any:
    with patch("httpx.AsyncClient.post", post_mock) as p:
        yield p


class TestWiring:
    async def test_is_embedding_client(self) -> None:
        c = DirectEmbeddingClient(base_url="http://x", model="m")
        assert isinstance(c, EmbeddingClient)

    def test_strips_trailing_slash(self) -> None:
        c = DirectEmbeddingClient(base_url="http://x/", model="m")
        assert c.base_url == "http://x"

    def test_dimension_property(self) -> None:
        c = DirectEmbeddingClient(base_url="http://x", model="m", dimension=1024)
        assert c.dimension == 1024

    def test_max_length_property(self) -> None:
        c = DirectEmbeddingClient(base_url="http://x", model="m", max_length=2048)
        assert c.max_length == 2048

    def test_headers_no_key(self) -> None:
        c = DirectEmbeddingClient(base_url="http://x", model="m")
        assert "Authorization" not in c._headers()

    def test_headers_with_key(self) -> None:
        c = DirectEmbeddingClient(base_url="http://x", model="m", api_key="sk-1")
        assert c._headers()["Authorization"] == "Bearer sk-1"


class TestEmbed:
    async def test_empty_input_returns_empty(self) -> None:
        c = DirectEmbeddingClient(base_url="http://x", model="m")
        result = await c.embed([])
        assert result.embeddings == []

    async def test_returns_embeddings(
        self, post_mock: AsyncMock, patched_post: Any
    ) -> None:
        post_mock.return_value = _make_response(
            json_body={
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]},
                ],
                "usage": {"total_tokens": 7},
            }
        )
        c = DirectEmbeddingClient(base_url="http://x", model="m")
        result = await c.embed(["a", "b"])
        assert result.embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        assert result.usage["total_tokens"] == 7
        assert result.model == "m"

    async def test_payload_shape(
        self, post_mock: AsyncMock, patched_post: Any
    ) -> None:
        post_mock.return_value = _make_response(
            json_body={"data": [{"embedding": [0.0]}]}
        )
        c = DirectEmbeddingClient(
            base_url="http://x", model="nomic-embed-text", api_key="sk-1"
        )
        await c.embed(["hi"])
        _args, kwargs = post_mock.call_args
        assert kwargs["json"]["model"] == "nomic-embed-text"
        assert kwargs["json"]["input"] == ["hi"]
        assert kwargs["headers"]["Authorization"] == "Bearer sk-1"

    async def test_url_no_double_v1(
        self, post_mock: AsyncMock, patched_post: Any
    ) -> None:
        """Regression (#71): base_url already carries /v1 (OpenAI convention,
        matches every EmbeddingConfig default), so the client must append only
        /embeddings — not /v1/embeddings, which produced /v1/v1/embeddings → 404
        and silently left every vec table empty."""
        post_mock.return_value = _make_response(
            json_body={"data": [{"embedding": [0.0]}]}
        )
        c = DirectEmbeddingClient(base_url="http://localhost:11434/v1", model="m")
        await c.embed(["hi"])
        url = post_mock.call_args[0][0]
        assert url == "http://localhost:11434/v1/embeddings"
        assert "/v1/v1/" not in url

    async def test_batches_split_at_batch_size(
        self, post_mock: AsyncMock, patched_post: Any
    ) -> None:
        post_mock.return_value = _make_response(
            json_body={"data": [{"embedding": [0.0]}]}
        )
        c = DirectEmbeddingClient(
            base_url="http://x", model="m", batch_size=2
        )
        # 5 texts → 3 batches (2 + 2 + 1)
        await c.embed(["a", "b", "c", "d", "e"])
        assert post_mock.call_count == 3

    async def test_embed_single(
        self, post_mock: AsyncMock, patched_post: Any
    ) -> None:
        post_mock.return_value = _make_response(
            json_body={"data": [{"embedding": [0.7]}]}
        )
        c = DirectEmbeddingClient(base_url="http://x", model="m")
        emb = await c.embed_single("hi")
        assert emb == [0.7]


class TestErrors:
    async def test_4xx_raises_api_error(
        self, post_mock: AsyncMock, patched_post: Any
    ) -> None:
        post_mock.return_value = _make_response(
            status=401, json_body={"error": {"message": "bad key"}}
        )
        c = DirectEmbeddingClient(base_url="http://x", model="m")
        with pytest.raises(EmbeddingAPIError, match="401"):
            await c.embed(["x"])

    async def test_connection_error_raises_api_error(
        self, post_mock: AsyncMock, patched_post: Any
    ) -> None:
        post_mock.side_effect = httpx.ConnectError("down")
        c = DirectEmbeddingClient(base_url="http://x", model="m")
        with pytest.raises(EmbeddingAPIError, match="Connection failed"):
            await c.embed(["x"])

    async def test_malformed_response_raises(
        self, post_mock: AsyncMock, patched_post: Any
    ) -> None:
        post_mock.return_value = _make_response(json_body={"unexpected": "shape"})
        c = DirectEmbeddingClient(base_url="http://x", model="m")
        with pytest.raises(EmbeddingAPIError, match="Malformed"):
            await c.embed(["x"])


class TestContextManager:
    async def test_aenter_aexit(self) -> None:
        async with DirectEmbeddingClient(base_url="http://x", model="m") as c:
            assert isinstance(c, DirectEmbeddingClient)
