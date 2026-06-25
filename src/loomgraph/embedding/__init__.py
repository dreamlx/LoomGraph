"""Embedding clients — OpenAI-compatible /v1/embeddings for any provider.

EPIC-012 / Phase 6: `DirectEmbeddingClient` replaces the Jina TEI-only
client. Defaults to local Ollama; the OpenAI protocol covers OpenAI,
Voyage, GLM, vLLM, and any other compatible service.
"""

from __future__ import annotations

from loomgraph.embedding.base import EmbeddingClient, EmbeddingResult
from loomgraph.embedding.direct import DirectEmbeddingClient, EmbeddingAPIError

__all__ = [
    "EmbeddingClient",
    "EmbeddingResult",
    "DirectEmbeddingClient",
    "EmbeddingAPIError",
]
