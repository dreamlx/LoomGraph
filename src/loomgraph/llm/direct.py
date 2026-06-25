"""DirectLLMClient — OpenAI-compatible chat completions, no RAG pipeline.

Talks directly to GLM-4.7 / OpenRouter / vLLM / any other backend that
speaks the `POST /v1/chat/completions` protocol. Replaces the LightRAG
adapter for `overview` summary generation and `impact` caller inference
(EPIC-011 Phase 4 / ADR-013).
"""

from __future__ import annotations

import httpx

from loomgraph.llm.base import LLMClient


class LLMAPIError(Exception):
    """Raised when the LLM provider returns a non-2xx response."""


class DirectLLMClient(LLMClient):
    """OpenAI-compatible LLM client.

    Single-turn `complete(prompt) -> str`. Streaming / multi-turn / tool
    calls are intentionally omitted — internal consumers don't need them.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str = "",
        timeout: float = 60.0,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def complete(self, prompt: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as http:
            try:
                resp = await http.post(url, headers=self._headers(), json=payload)
            except httpx.RequestError as e:
                raise LLMAPIError(f"Connection failed: {e}") from e

            if resp.status_code >= 400:
                detail = ""
                try:
                    detail = resp.json().get("error", {}).get("message") or resp.text
                except Exception:
                    detail = resp.text
                raise LLMAPIError(
                    f"LLM returned {resp.status_code}: {detail}"
                )

            try:
                data = resp.json()
                return str(data["choices"][0]["message"]["content"])
            except (KeyError, IndexError, ValueError) as e:
                raise LLMAPIError(f"Malformed LLM response: {e}") from e
