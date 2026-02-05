"""Embedding module for code vectorization."""

from loomgraph.embedding.base import EmbeddingClient
from loomgraph.embedding.jina import JinaEmbeddingClient

__all__ = ["EmbeddingClient", "JinaEmbeddingClient"]
