"""DirectLLMClient tests — OpenAI-compatible chat completion."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from loomgraph.llm.base import LLMClient
from loomgraph.llm.direct import DirectLLMClient, LLMAPIError


def _make_response(
    *, status: int = 200, json_body: dict | None = None, text: str = ""
) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        request=httpx.Request("POST", "http://example/v1/chat/completions"),
        json=json_body,
        text=text if json_body is None else None,
    )


@pytest.fixture
def post_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def patched_client(post_mock: AsyncMock) -> Any:  # noqa: F821
    """Patch httpx.AsyncClient.post on every DirectLLMClient call."""
    with patch("httpx.AsyncClient.post", post_mock) as patched:
        yield patched


class TestBasicWiring:
    async def test_is_llm_client(self) -> None:
        c = DirectLLMClient(base_url="http://x", model="m")
        assert isinstance(c, LLMClient)

    def test_strips_trailing_slash(self) -> None:
        c = DirectLLMClient(base_url="http://x/", model="m")
        assert c.base_url == "http://x"

    def test_headers_no_key(self) -> None:
        c = DirectLLMClient(base_url="http://x", model="m")
        assert "Authorization" not in c._headers()

    def test_headers_with_key(self) -> None:
        c = DirectLLMClient(base_url="http://x", model="m", api_key="sk-1")
        assert c._headers()["Authorization"] == "Bearer sk-1"


class TestComplete:
    async def test_returns_message_content(
        self, post_mock: AsyncMock, patched_client: Any
    ) -> None:
        post_mock.return_value = _make_response(
            json_body={
                "choices": [{"message": {"content": "Hello"}}],
            }
        )
        c = DirectLLMClient(base_url="http://x", model="m")
        assert await c.complete("hi") == "Hello"

    async def test_payload_shape(
        self, post_mock: AsyncMock, patched_client: Any
    ) -> None:
        post_mock.return_value = _make_response(
            json_body={"choices": [{"message": {"content": "ok"}}]}
        )
        c = DirectLLMClient(
            base_url="http://x",
            model="glm-4-flash",
            api_key="sk-1",
            max_tokens=500,
            temperature=0.3,
        )
        await c.complete("what?")
        _args, kwargs = post_mock.call_args
        assert kwargs["json"]["model"] == "glm-4-flash"
        assert kwargs["json"]["max_tokens"] == 500
        assert kwargs["json"]["temperature"] == 0.3
        assert kwargs["json"]["messages"] == [
            {"role": "user", "content": "what?"}
        ]
        assert kwargs["headers"]["Authorization"] == "Bearer sk-1"


class TestErrorHandling:
    async def test_4xx_raises_llm_api_error(
        self, post_mock: AsyncMock, patched_client: Any
    ) -> None:
        post_mock.return_value = _make_response(
            status=429, json_body={"error": {"message": "rate limited"}}
        )
        c = DirectLLMClient(base_url="http://x", model="m")
        with pytest.raises(LLMAPIError, match="429"):
            await c.complete("hi")

    async def test_connection_error_raises_llm_api_error(
        self, post_mock: AsyncMock, patched_client: Any
    ) -> None:
        post_mock.side_effect = httpx.ConnectError("nope")
        c = DirectLLMClient(base_url="http://x", model="m")
        with pytest.raises(LLMAPIError, match="Connection failed"):
            await c.complete("hi")

    async def test_malformed_response_raises(
        self, post_mock: AsyncMock, patched_client: Any
    ) -> None:
        post_mock.return_value = _make_response(json_body={"weird": "shape"})
        c = DirectLLMClient(base_url="http://x", model="m")
        with pytest.raises(LLMAPIError, match="Malformed"):
            await c.complete("hi")
