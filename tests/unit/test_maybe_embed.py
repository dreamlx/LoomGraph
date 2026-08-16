"""maybe_embed_entities() tests — gated by embedding.enabled, default off."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from loomgraph.cli._common import maybe_embed_entities
from loomgraph.core.config import reset_settings


@pytest.fixture(autouse=True)
def reset_global_settings() -> None:
    reset_settings()
    yield
    reset_settings()


class TestEnabledGate:
    async def test_default_disabled_skips(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LOOMGRAPH_EMBEDDING__ENABLED", raising=False)
        entities: list[dict[str, Any]] = [
            {"entity_name": "A", "description": "test"}
        ]
        with patch(
            "loomgraph.storage.factory.create_embedding_client"
        ) as factory:
            n = await maybe_embed_entities(entities)
        assert n == 0
        assert "embedding" not in entities[0]
        factory.assert_not_called()

    async def test_enabled_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOOMGRAPH_EMBEDDING__ENABLED", "true")
        entities: list[dict[str, Any]] = [
            {"entity_name": "A", "description": "test"},
            {"entity_name": "B", "description": "test2"},
        ]
        mock_client = AsyncMock()
        mock_client.embed.return_value = type(
            "R", (), {"embeddings": [[0.1] * 768, [0.2] * 768]}
        )()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch(
            "loomgraph.storage.factory.create_embedding_client",
            return_value=mock_client,
        ):
            n = await maybe_embed_entities(entities)
        assert n == 2
        assert entities[0]["embedding"] == [0.1] * 768
        assert entities[1]["embedding"] == [0.2] * 768


class TestFilter:
    async def test_skips_entities_without_description(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_EMBEDDING__ENABLED", "true")
        entities: list[dict[str, Any]] = [
            {"entity_name": "A"},  # no description
            {"entity_name": "B", "description": "real"},
        ]
        mock_client = AsyncMock()
        mock_client.embed.return_value = type(
            "R", (), {"embeddings": [[0.5] * 768]}
        )()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch(
            "loomgraph.storage.factory.create_embedding_client",
            return_value=mock_client,
        ):
            n = await maybe_embed_entities(entities)
        assert n == 1
        assert "embedding" not in entities[0]
        assert entities[1]["embedding"] == [0.5] * 768
        mock_client.embed.assert_awaited_once_with(["real"])

    async def test_skips_already_embedded_entities(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_EMBEDDING__ENABLED", "true")
        entities: list[dict[str, Any]] = [
            {"entity_name": "A", "description": "x", "embedding": [0.0] * 768},
        ]
        with patch(
            "loomgraph.storage.factory.create_embedding_client"
        ) as factory:
            n = await maybe_embed_entities(entities)
        assert n == 0
        factory.assert_not_called()


class TestDegenerateVector:
    async def test_zero_vector_skipped_not_attached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Provider returning 200-OK-but-zero (e.g. overload) would poison
        KNN — every query lands at distance ~1.0 (observed in a tmp e2e
        after a busy index). Skip degenerate vectors instead of attaching."""
        monkeypatch.setenv("LOOMGRAPH_EMBEDDING__ENABLED", "true")
        entities: list[dict[str, Any]] = [
            {"entity_name": "A", "description": "x"},  # gets zero vector
            {"entity_name": "B", "description": "y"},  # gets normal vector
        ]
        mock_client = AsyncMock()
        mock_client.embed.return_value = type(
            "R", (), {"embeddings": [[0.0] * 768, [0.5] * 768]}
        )()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch(
            "loomgraph.storage.factory.create_embedding_client",
            return_value=mock_client,
        ):
            n = await maybe_embed_entities(entities)
        assert n == 1  # only the non-degenerate one attached
        assert "embedding" not in entities[0]  # zero vector skipped
        assert entities[1]["embedding"] == [0.5] * 768


class TestFailureMode:
    async def test_embedding_failure_returns_zero_no_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_EMBEDDING__ENABLED", "true")
        entities: list[dict[str, Any]] = [
            {"entity_name": "A", "description": "x"},
        ]
        mock_client = AsyncMock()
        mock_client.embed.side_effect = ConnectionError("service down")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch(
            "loomgraph.storage.factory.create_embedding_client",
            return_value=mock_client,
        ):
            n = await maybe_embed_entities(entities)
        assert n == 0
        assert "embedding" not in entities[0]


class TestFailLoudOnBuiltinErrors:
    async def test_builtin_config_error_raises(self, monkeypatch):
        """#158 review C1-3: deterministic builtin/download errors must not
        be swallowed into a green zero-vector index."""
        from loomgraph.core.embedding_pipeline import maybe_embed_entities
        from loomgraph.embedding.builtin import BuiltinEmbeddingError

        monkeypatch.setenv("LOOMGRAPH_EMBEDDING__ENABLED", "true")

        monkeypatch.setattr(
            "loomgraph.storage.factory.create_embedding_client",
            lambda: (_ for _ in ()).throw(
                BuiltinEmbeddingError("needs [embed] extra")))

        with pytest.raises(BuiltinEmbeddingError):
            await maybe_embed_entities(
                [{"entity_name": "A", "description": "x"}])
