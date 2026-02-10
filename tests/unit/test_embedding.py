"""Unit tests for the embedding module."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from loomgraph.core.config import EmbeddingConfig
from loomgraph.embedding.jina import JinaEmbeddingClient


@pytest.fixture
def embedding_config() -> EmbeddingConfig:
    """Create test embedding config."""
    return EmbeddingConfig(
        provider="jina",
        model="jinaai/jina-embeddings-v2-base-code",
        base_url="http://localhost:8080",
        batch_size=2,  # Small batch for testing
        max_length=8192,
        dimension=768,
        timeout=30.0,
    )


@pytest.fixture
def mock_response() -> list[list[float]]:
    """Create mock embedding response."""
    # 768-dimensional mock embeddings
    return [[0.1] * 768, [0.2] * 768]


class TestJinaEmbeddingClient:
    """Tests for JinaEmbeddingClient."""

    def test_init_with_config(self, embedding_config: EmbeddingConfig) -> None:
        """Should initialize with provided config."""
        client = JinaEmbeddingClient(embedding_config)
        assert client.dimension == 768
        assert client.max_length == 8192

    def test_dimension_property(self, embedding_config: EmbeddingConfig) -> None:
        """Should return correct dimension."""
        client = JinaEmbeddingClient(embedding_config)
        assert client.dimension == 768

    def test_max_length_property(self, embedding_config: EmbeddingConfig) -> None:
        """Should return correct max length."""
        client = JinaEmbeddingClient(embedding_config)
        assert client.max_length == 8192

    @pytest.mark.asyncio
    async def test_embed_empty_list(self, embedding_config: EmbeddingConfig) -> None:
        """Should return empty result for empty input."""
        client = JinaEmbeddingClient(embedding_config)
        result = await client.embed([])
        assert result.embeddings == []
        assert result.model == embedding_config.model

    @pytest.mark.asyncio
    async def test_embed_single_text(
        self, embedding_config: EmbeddingConfig, mock_response: list[list[float]]
    ) -> None:
        """Should embed a single text."""
        client = JinaEmbeddingClient(embedding_config)

        # Mock the HTTP response
        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = [mock_response[0]]
        mock_httpx_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_httpx_response)
            mock_get_client.return_value = mock_client

            embedding = await client.embed_single("def hello(): pass")

            assert len(embedding) == 768
            assert embedding == mock_response[0]

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(
        self, embedding_config: EmbeddingConfig, mock_response: list[list[float]]
    ) -> None:
        """Should embed multiple texts."""
        client = JinaEmbeddingClient(embedding_config)

        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = mock_response
        mock_httpx_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_httpx_response)
            mock_get_client.return_value = mock_client

            result = await client.embed(["def hello(): pass", "class Foo: pass"])

            assert len(result.embeddings) == 2
            assert len(result.embeddings[0]) == 768

    @pytest.mark.asyncio
    async def test_embed_batching(self, embedding_config: EmbeddingConfig) -> None:
        """Should batch requests when input exceeds batch_size."""
        # batch_size = 2, so 3 texts should result in 2 batches
        client = JinaEmbeddingClient(embedding_config)

        batch1_response = [[0.1] * 768, [0.2] * 768]
        batch2_response = [[0.3] * 768]

        mock_responses = [
            MagicMock(json=MagicMock(return_value=batch1_response), raise_for_status=MagicMock()),
            MagicMock(json=MagicMock(return_value=batch2_response), raise_for_status=MagicMock()),
        ]

        with patch.object(client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=mock_responses)
            mock_get_client.return_value = mock_client

            result = await client.embed(["text1", "text2", "text3"])

            assert len(result.embeddings) == 3
            assert mock_client.post.call_count == 2  # Two batches

    @pytest.mark.asyncio
    async def test_embed_openai_format_response(
        self, embedding_config: EmbeddingConfig
    ) -> None:
        """Should handle OpenAI-compatible response format."""
        client = JinaEmbeddingClient(embedding_config)

        # OpenAI-compatible format
        openai_response = {
            "data": [
                {"embedding": [0.1] * 768, "index": 0},
                {"embedding": [0.2] * 768, "index": 1},
            ],
            "usage": {"total_tokens": 100},
        }

        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = openai_response
        mock_httpx_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_httpx_response)
            mock_get_client.return_value = mock_client

            result = await client.embed(["text1", "text2"])

            assert len(result.embeddings) == 2

    @pytest.mark.asyncio
    async def test_embed_with_retry_success_on_first_try(
        self, embedding_config: EmbeddingConfig, mock_response: list[list[float]]
    ) -> None:
        """Should succeed without retry when first attempt works."""
        client = JinaEmbeddingClient(embedding_config)

        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = mock_response
        mock_httpx_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_httpx_response)
            mock_get_client.return_value = mock_client

            result = await client.embed_with_retry(["text1", "text2"])

            assert len(result.embeddings) == 2
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_embed_with_retry_success_on_retry(
        self, embedding_config: EmbeddingConfig, mock_response: list[list[float]]
    ) -> None:
        """Should retry and succeed after initial failure."""
        client = JinaEmbeddingClient(embedding_config)

        # First call fails, second succeeds
        mock_success = MagicMock()
        mock_success.json.return_value = mock_response
        mock_success.raise_for_status = MagicMock()

        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=[
                    httpx.HTTPStatusError(
                        "Error", request=MagicMock(), response=error_response
                    ),
                    mock_success,
                ]
            )
            mock_get_client.return_value = mock_client

            result = await client.embed_with_retry(
                ["text1", "text2"], max_retries=2, retry_delay=0.01
            )

            assert len(result.embeddings) == 2
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_context_manager(self, embedding_config: EmbeddingConfig) -> None:
        """Should work as async context manager."""
        async with JinaEmbeddingClient(embedding_config) as client:
            assert client is not None
            assert client.dimension == 768
