"""LLMClient ABC — backend-agnostic single-turn completion."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Minimal completion interface.

    `complete()` is the only required method; richer surfaces (system
    messages, streaming, multi-turn) are added when concrete consumers
    need them, not preemptively.
    """

    @abstractmethod
    async def complete(self, prompt: str) -> str:
        """Generate a text completion for the given prompt."""
