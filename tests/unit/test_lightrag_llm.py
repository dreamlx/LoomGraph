"""LightRAGLLMClient adapter tests — verify query() forwarding + response extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from loomgraph.llm.base import LLMClient
from loomgraph.llm.lightrag_llm import LightRAGLLMClient


@pytest.fixture
def mock_client() -> AsyncMock:
    c = AsyncMock()
    c.query.return_value = {"response": "ok"}
    return c


class TestForwarding:
    async def test_complete_forwards_default_mode(
        self, mock_client: AsyncMock
    ) -> None:
        llm = LightRAGLLMClient(client=mock_client)
        await llm.complete("hello")
        mock_client.query.assert_awaited_once_with(query="hello", mode="local")

    async def test_complete_forwards_custom_mode(
        self, mock_client: AsyncMock
    ) -> None:
        llm = LightRAGLLMClient(client=mock_client, mode="hybrid")
        await llm.complete("hello")
        mock_client.query.assert_awaited_once_with(query="hello", mode="hybrid")


class TestResponseExtraction:
    async def test_dict_response(self, mock_client: AsyncMock) -> None:
        mock_client.query.return_value = {"response": "Hello world"}
        llm = LightRAGLLMClient(client=mock_client)
        result = await llm.complete("hi")
        assert result == "Hello world"

    async def test_dict_missing_response_key(
        self, mock_client: AsyncMock
    ) -> None:
        mock_client.query.return_value = {"something_else": "x"}
        llm = LightRAGLLMClient(client=mock_client)
        assert await llm.complete("hi") == ""

    async def test_non_dict_response_stringified(
        self, mock_client: AsyncMock
    ) -> None:
        mock_client.query.return_value = "plain text"
        llm = LightRAGLLMClient(client=mock_client)
        assert await llm.complete("hi") == "plain text"

    async def test_is_llm_client(self, mock_client: AsyncMock) -> None:
        llm = LightRAGLLMClient(client=mock_client)
        assert isinstance(llm, LLMClient)
