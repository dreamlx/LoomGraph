"""LLM client abstraction.

Decouples internal LLM consumers (overview / impact) from the LightRAG
RAG pipeline. Phase 1 ships the ABC + LightRAG adapter; Phase 4 adds
`DirectLLMClient` that talks to GLM-4.7 / OpenRouter / vLLM directly.
"""

from __future__ import annotations

from loomgraph.llm.base import LLMClient

__all__ = ["LLMClient"]
