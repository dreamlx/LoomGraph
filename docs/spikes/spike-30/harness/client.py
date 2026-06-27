"""LLM client factory for the spike — pluggable model tiers.

Two tiers supported per PLAN.md §3 (post-G2 expansion):
- "flash"  — DeepSeek v4 flash, Haiku-class, primary verdict tier (~30B effective)
- "pro"    — DeepSeek v4 pro, stronger tier for G2 comparison subset

Both speak the Anthropic API protocol via DeepSeek's `/anthropic` endpoint.
Drop-in for the `anthropic.Anthropic` client used by path_a/b runners.

Key handling: the DeepSeek key is read from `DEEPSEEK_API_KEY` env var.
Never committed.
"""

from __future__ import annotations

import os
from typing import Any

_BASE_URL = "https://api.deepseek.com/anthropic"

MODELS = {
    "flash": "deepseek-v4-flash",  # primary
    "pro": "deepseek-v4-pro",      # stronger tier for G2 verification
}


class MissingAPIKey(RuntimeError):
    pass


def get_client(timeout: float = 120.0) -> Any:
    """Return an Anthropic-SDK client configured for DeepSeek's endpoint.

    Bypasses the dev shell's SOCKS proxy (`trust_env=False` on the
    underlying httpx client) so DeepSeek requests go direct.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise MissingAPIKey(
            "DEEPSEEK_API_KEY not set. Export it before running live mode:\n"
            "  export DEEPSEEK_API_KEY=<your-key>"
        )
    try:
        import anthropic
        import httpx
    except ImportError as e:
        raise RuntimeError(
            "anthropic SDK not installed in this venv. "
            "Install with: uv pip install anthropic"
        ) from e

    http_client = httpx.Client(timeout=timeout, trust_env=False)
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=_BASE_URL,
        http_client=http_client,
    )
