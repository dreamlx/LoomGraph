"""LLM client abstraction.

Decouples internal LLM consumers (overview / impact) from the LightRAG
RAG pipeline. Phase 1 ships the ABC + LightRAG adapter; Phase 4 adds
`DirectLLMClient` that talks to GLM-4.7 / OpenRouter / vLLM directly.
"""

from __future__ import annotations

from loomgraph.llm.base import LLMClient
from loomgraph.llm.direct import DirectLLMClient, LLMAPIError
from loomgraph.llm.lightrag_llm import LightRAGLLMClient

__all__ = [
    "LLMClient",
    "LightRAGLLMClient",
    "DirectLLMClient",
    "LLMAPIError",
]
