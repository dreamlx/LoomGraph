"""LLM client abstraction.

Decouples internal LLM consumers (overview / impact) from any specific
provider. v0.10.0 ships `DirectLLMClient` (OpenAI-compatible chat
completions). The LightRAG-backed adapter was removed in EPIC-011 Phase 5.
"""

from __future__ import annotations

from loomgraph.llm.base import LLMClient
from loomgraph.llm.direct import DirectLLMClient, LLMAPIError

__all__ = [
    "LLMClient",
    "DirectLLMClient",
    "LLMAPIError",
]
