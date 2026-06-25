"""maybe_embed_entities() — caller-side embedding step tests."""

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


class TestBackendGate:
    async def test_runs_on_sqlite_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
            "loomgraph.embedding.jina.JinaEmbeddingClient",
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
        monkeypatch.setenv("LOOMGRAPH_STORAGE__BACKEND", "sqlite")
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
            "loomgraph.embedding.jina.JinaEmbeddingClient",
            return_value=mock_client,
        ):
            n = await maybe_embed_entities(entities)
        assert n == 1
        assert "embedding" not in entities[0]
        assert entities[1]["embedding"] == [0.5] * 768
        # Only the entity with a description goes to the service
        mock_client.embed.assert_awaited_once_with(["real"])

    async def test_skips_already_embedded_entities(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_STORAGE__BACKEND", "sqlite")
        entities: list[dict[str, Any]] = [
            {"entity_name": "A", "description": "x", "embedding": [0.0] * 768},
        ]
        with patch("loomgraph.embedding.jina.JinaEmbeddingClient") as mock_cls:
            n = await maybe_embed_entities(entities)
        assert n == 0
        mock_cls.assert_not_called()


class TestFailureMode:
    async def test_embedding_failure_returns_zero_no_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_STORAGE__BACKEND", "sqlite")
        entities: list[dict[str, Any]] = [
            {"entity_name": "A", "description": "x"},
        ]
        mock_client = AsyncMock()
        mock_client.embed.side_effect = ConnectionError("service down")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch(
            "loomgraph.embedding.jina.JinaEmbeddingClient",
            return_value=mock_client,
        ):
            n = await maybe_embed_entities(entities)
        assert n == 0
        assert "embedding" not in entities[0]
