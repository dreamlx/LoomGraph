"""Sticky embedding-provider resolution (#158).

Order (dreamlinx decision, #158 comment):
  1. explicit config provider → used verbatim (no probe, no persistence —
     the user owns this choice and may change it consciously)
  2. workspace meta ``embedding_provider`` → reused verbatim (stickiness)
  3. first use → probe ollama (settings api_url) → else builtin (downloads)

Why sticky: ollama (nomic-embed-text) and builtin (CodeRankEmbed) produce
INCOMPATIBLE vector spaces. Re-probing at every run would let an
ollama-up/ollama-down moment silently switch spaces and poison the vec0
table with mixed embeddings. Resolved once, recorded, then obeyed.
"""

from __future__ import annotations

from typing import Any

from loomgraph.embedding.base import EmbeddingClient

META_KEY = "embedding_provider"


class EmbeddingSpaceUnknownError(RuntimeError):
    """Workspace has vectors but no recorded provider (pre-#158 index).

    Auto-resolution here would guess the space and can silently mix
    incompatible embeddings — fail loud instead (codex review C1-1)."""


def explicit_provider() -> str | None:
    """Return the explicitly configured provider, or None for ``auto``."""
    from loomgraph.core.config import get_settings

    p = get_settings().embedding.provider
    return None if p == "auto" else p


async def probe_ollama() -> bool:
    """True when the configured ollama endpoint answers quickly."""
    import urllib.request

    from loomgraph.core.config import get_settings

    base = get_settings().embedding.api_url.rstrip("/")
    # api_url is the /v1 embeddings base; probe the service root.
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2) as resp:
            return bool(resp.status == 200)
    except Exception:  # noqa: BLE001 — any failure means "not reachable"
        return False


def make_builtin_client() -> EmbeddingClient:
    from loomgraph.embedding.builtin import BuiltinEmbeddingClient

    return BuiltinEmbeddingClient()


def _make_direct_client() -> EmbeddingClient:
    # Inlined (not via storage.factory) to avoid an import cycle once the
    # factory dispatches `auto` to this module.
    from loomgraph.core.config import get_settings
    from loomgraph.embedding.direct import DirectEmbeddingClient

    e = get_settings().embedding
    return DirectEmbeddingClient(
        base_url=e.api_url,
        model=e.model,
        api_key=e.api_key,
        timeout=e.timeout,
        batch_size=e.batch_size,
        dimension=e.dimension,
        max_length=e.max_length,
    )


class _ClientPair:
    """Async-context wrapper yielding (client, provider) and closing on exit."""

    def __init__(self, client: EmbeddingClient, provider: str) -> None:
        self._client = client
        self.provider = provider

    async def __aenter__(self) -> tuple[EmbeddingClient, str]:
        inner = getattr(self._client, "__aenter__", None)
        if inner is not None:
            await inner()
        return self._client, self.provider

    async def __aexit__(self, *args: Any) -> None:
        inner = getattr(self._client, "__aexit__", None)
        if inner is not None:
            await inner(*args)


async def resolve_embedding_client(store: Any) -> _ClientPair:
    """Resolve the embedding client per the sticky order (see module doc)."""
    explicit = explicit_provider()
    if explicit is not None:
        if explicit == "builtin":
            return _ClientPair(make_builtin_client(), "builtin")
        return _ClientPair(_make_direct_client(), explicit)

    get_meta = getattr(store, "get_meta", None)
    set_meta = getattr(store, "set_meta", None)
    if get_meta is not None:
        recorded = await get_meta(META_KEY)
        if recorded == "builtin":
            return _ClientPair(make_builtin_client(), "builtin")
        if recorded:
            return _ClientPair(_make_direct_client(), recorded)

        # Pre-#158 workspace: vectors exist but no provider was ever
        # recorded. Guessing the space here would let a builtin query
        # search ollama vectors (and persist the wrong provider) —
        # refuse and tell the user how to pin it (codex review C1-1).
        vector_count = getattr(store, "vector_count", None)
        if vector_count is not None and await vector_count() > 0:
            raise EmbeddingSpaceUnknownError(
                "workspace has embedded vectors but no recorded embedding "
                "provider (indexed before v0.18). Set embedding.provider "
                "explicitly (e.g. ollama) or re-index with "
                "`loomgraph index --clear .` to record the space."
            )

    chosen = "ollama" if await probe_ollama() else "builtin"
    if set_meta is not None:
        await set_meta(META_KEY, chosen)
    if chosen == "builtin":
        return _ClientPair(make_builtin_client(), "builtin")
    return _ClientPair(_make_direct_client(), chosen)


async def client_for_store(store: Any) -> _ClientPair:
    """Single construction entry: sticky-auto or explicit provider.

    Collapses the `provider == "auto" ? resolve : factory` branch that was
    copy-pasted across embedding_pipeline / _search / _backfill (pruner
    tension — three call sites had already diverged in failure semantics).
    Returns an async context manager yielding ``(client, provider)`` —
    use ``async with`` so the underlying client closes. Deterministic
    errors (missing extra / download / unknown space) raise; callers
    translate them into their own UX."""
    explicit = explicit_provider()
    if explicit == "builtin":
        return _ClientPair(make_builtin_client(), "builtin")
    if explicit is not None:
        return _ClientPair(_make_direct_client(), explicit)
    return await resolve_embedding_client(store)
