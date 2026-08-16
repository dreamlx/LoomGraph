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

    async def embed_query(self, text: str) -> list[float]:
        """Query-side embedding (#158).

        Providers with query/document asymmetry override this — e.g.
        CodeRankEmbed requires the task prefix
        ``Represent this query for searching relevant code: `` on queries
        and nothing on documents. Symmetric providers inherit this default.
        """
        return await self.embed_single(text)

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

    # Async context-manager protocol. Concrete clients (DirectEmbeddingClient)
    # override these; the base defaults exist so `async with
    # create_embedding_client() as client:` (embedding_pipeline.maybe_embed_entities)
    # is mypy-correct against the declared `EmbeddingClient` return type — the
    # concrete client is already an async CM at runtime. Stateless default;
    # resource-owning subclasses override `__aexit__` to release.
    async def __aenter__(self) -> "EmbeddingClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None
