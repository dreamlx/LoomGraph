"""DirectEmbeddingClient — OpenAI-compatible POST /v1/embeddings.

Talks to any backend speaking the OpenAI embeddings protocol — Ollama (default,
local), OpenAI, Voyage, GLM, vLLM, or any custom OpenAI-compatible service.
Replaces the Jina TEI-only client (EPIC-012 / Phase 6).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from loomgraph.embedding.base import EmbeddingClient, EmbeddingResult


class EmbeddingAPIError(Exception):
    """Raised when the embedding provider returns a non-2xx response."""


class DirectEmbeddingClient(EmbeddingClient):
    """OpenAI-compatible embedding client.

    Auto-batches inputs by `batch_size`. No streaming, no retries — failures
    surface as `EmbeddingAPIError`; callers (e.g. `maybe_embed_entities`)
    decide whether to swallow or propagate.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str = "",
        timeout: float = 30.0,
        batch_size: int = 32,
        dimension: int = 768,
        max_length: int = 8192,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.batch_size = batch_size
        self._dimension = dimension
        self._max_length = max_length

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def max_length(self) -> int:
        return self._max_length

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(embeddings=[], model=self.model)

        all_embeds: list[list[float]] = []
        total_tokens = 0

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_data = await self._embed_batch(batch)
            all_embeds.extend(batch_data["embeddings"])
            total_tokens += batch_data.get("usage", {}).get("total_tokens", 0)

        return EmbeddingResult(
            embeddings=all_embeds,
            model=self.model,
            usage={"total_tokens": total_tokens},
        )

    async def embed_single(self, text: str) -> list[float]:
        result = await self.embed([text])
        return result.embeddings[0]

    async def _embed_batch(self, texts: list[str]) -> dict[str, Any]:
        # base_url carries the OpenAI-style base incl. /v1 (every
        # EmbeddingConfig default does), so append only /embeddings. Appending
        # /v1/embeddings here yielded /v1/v1/embeddings → 404 (#71).
        url = f"{self.base_url}/embeddings"
        payload = {"model": self.model, "input": texts}
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as http:
            try:
                resp = await http.post(url, headers=self._headers(), json=payload)
            except httpx.RequestError as e:
                raise EmbeddingAPIError(f"Connection failed: {e}") from e

            if resp.status_code >= 400:
                detail = ""
                try:
                    detail = (
                        resp.json().get("error", {}).get("message")
                        or resp.text
                    )
                except Exception:
                    detail = resp.text
                raise EmbeddingAPIError(
                    f"Embedding API returned {resp.status_code}: {detail}"
                )

            try:
                data = resp.json()
                embeddings = [item["embedding"] for item in data["data"]]
            except (KeyError, IndexError, ValueError) as e:
                raise EmbeddingAPIError(
                    f"Malformed embedding response: {e}"
                ) from e

            return {
                "embeddings": embeddings,
                "usage": data.get("usage", {}),
            }

    # Symmetry with JinaEmbeddingClient — some callers use context-manager idiom.
    async def __aenter__(self) -> DirectEmbeddingClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        # Stateless: per-call AsyncClient, nothing to close.
        await asyncio.sleep(0)
