"""LightRAG-backed LLMClient adapter.

Wraps `LightRAGClient.query()` so existing call sites (overview / impact)
can depend on `LLMClient` rather than the LightRAG RAG pipeline directly.
Phase 4 replaces this with `DirectLLMClient` that bypasses LightRAG.
"""

from __future__ import annotations

from loomgraph.core.lightrag_client import LightRAGClient
from loomgraph.llm.base import LLMClient


class LightRAGLLMClient(LLMClient):
    """LLMClient backed by `LightRAGClient.query()`.

    `mode` selects LightRAG's retrieval strategy (local / global / hybrid /
    naive / mix). overview.py historically used "local"; that remains the
    default here, callers may override per-instance.
    """

    def __init__(self, client: LightRAGClient, mode: str = "local") -> None:
        self.client = client
        self.mode = mode

    async def complete(self, prompt: str) -> str:
        data = await self.client.query(query=prompt, mode=self.mode)
        if isinstance(data, dict):
            return str(data.get("response", ""))
        return str(data)
