"""Jina Code V2 embedding client.

Uses Hugging Face Text Embeddings Inference (TEI) server or Jina API.
Optimized for code with 8K context window.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from loomgraph.core.config import EmbeddingConfig, get_settings

from .base import EmbeddingClient, EmbeddingResult

logger = logging.getLogger(__name__)


class JinaEmbeddingClient(EmbeddingClient):
    """Embedding client for Jina Code V2 via TEI or Jina API.

    Supports two modes:
    1. Local TEI server (default): POST /embed
    2. Jina API: POST https://api.jina.ai/v1/embeddings

    Example:
        >>> config = EmbeddingConfig(base_url="http://localhost:8080")
        >>> client = JinaEmbeddingClient(config)
        >>> result = await client.embed(["def hello(): pass", "class Foo: pass"])
        >>> len(result.embeddings)
        2
    """

    def __init__(
        self,
        config: EmbeddingConfig | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialize the Jina embedding client.

        Args:
            config: Embedding configuration. If None, uses global settings.
            api_key: Optional API key for Jina API (not needed for local TEI).
        """
        self._config = config or get_settings().embedding
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            self._client = httpx.AsyncClient(
                base_url=self._config.base_url,
                headers=headers,
                timeout=self._config.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> JinaEmbeddingClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def dimension(self) -> int:
        """Return the embedding dimension (768 for Jina Code V2)."""
        return self._config.dimension

    @property
    def max_length(self) -> int:
        """Return the maximum input length (8192 tokens for Jina Code V2)."""
        return self._config.max_length

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Generate embeddings for a list of texts.

        Automatically batches requests according to batch_size config.

        Args:
            texts: List of text strings (code snippets) to embed

        Returns:
            EmbeddingResult containing embeddings and metadata

        Raises:
            httpx.HTTPStatusError: If the API request fails
        """
        if not texts:
            return EmbeddingResult(embeddings=[], model=self._config.model)

        all_embeddings: list[list[float]] = []
        total_tokens = 0

        # Process in batches
        for i in range(0, len(texts), self._config.batch_size):
            batch = texts[i : i + self._config.batch_size]
            batch_result = await self._embed_batch(batch)
            all_embeddings.extend(batch_result["embeddings"])
            total_tokens += batch_result.get("usage", {}).get("total_tokens", 0)

        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self._config.model,
            usage={"total_tokens": total_tokens},
        )

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector as list of floats
        """
        result = await self.embed([text])
        return result.embeddings[0]

    async def _embed_batch(self, texts: list[str]) -> dict[str, Any]:
        """Embed a single batch of texts.

        Supports both TEI format and OpenAI-compatible format.

        Args:
            texts: Batch of texts (size <= batch_size)

        Returns:
            Dict with 'embeddings' and optional 'usage' keys
        """
        client = await self._get_client()

        # Try TEI format first (simpler)
        payload = {"inputs": texts}

        try:
            response = await client.post("/embed", json=payload)
            response.raise_for_status()
            data = response.json()

            # TEI returns list of embeddings directly
            if isinstance(data, list):
                return {"embeddings": data}

            # Or wrapped in a dict
            if "embeddings" in data:
                return data

            # OpenAI-compatible format
            if "data" in data:
                embeddings = [item["embedding"] for item in data["data"]]
                return {
                    "embeddings": embeddings,
                    "usage": data.get("usage", {}),
                }

            # Fallback: assume data is the embeddings
            return {"embeddings": data}

        except httpx.HTTPStatusError as e:
            logger.error(f"Embedding request failed: {e.response.status_code} - {e.response.text}")
            raise

    async def embed_with_retry(
        self,
        texts: list[str],
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> EmbeddingResult:
        """Embed texts with automatic retry on failure.

        Args:
            texts: List of texts to embed
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (exponential backoff)

        Returns:
            EmbeddingResult on success

        Raises:
            httpx.HTTPStatusError: If all retries fail
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return await self.embed(texts)
            except (httpx.HTTPStatusError, httpx.ConnectError) as e:
                last_error = e
                if attempt < max_retries:
                    delay = retry_delay * (2**attempt)
                    logger.warning(
                        f"Embedding attempt {attempt + 1} failed, retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)

        raise last_error  # type: ignore[misc]
