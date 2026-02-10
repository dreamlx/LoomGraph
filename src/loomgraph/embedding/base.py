"""Abstract base class for embedding clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""

    embeddings: list[list[float]]
    model: str
    usage: dict[str, int] = field(default_factory=dict)


class EmbeddingClient(ABC):
    """Abstract base class for embedding clients.

    Implementations should handle:
    - Batching for large input lists
    - Rate limiting and retries
    - Input truncation to max_length
    """

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            EmbeddingResult containing embeddings and metadata
        """
        ...

    @abstractmethod
    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector as list of floats
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        ...

    @property
    @abstractmethod
    def max_length(self) -> int:
        """Return the maximum input length in tokens."""
        ...
