"""#158 sticky provider resolution: config > ollama-probe > builtin(download),
resolved once per workspace and persisted — never silently re-resolved."""

from __future__ import annotations

from loomgraph.embedding.resolve import resolve_embedding_client


class _Store:
    def __init__(self, pre: dict | None = None) -> None:
        self.meta = dict(pre or {})

    async def get_meta(self, key):
        return self.meta.get(key)

    async def set_meta(self, key, value):
        self.meta[key] = value


class TestStickyResolution:
    async def test_first_use_probes_ollama_and_persists(self, monkeypatch):
        store = _Store()
        probed = []

        async def fake_probe():
            probed.append(1)
            return True  # ollama reachable

        monkeypatch.setattr("loomgraph.embedding.resolve.explicit_provider",
                            lambda: None)
        monkeypatch.setattr("loomgraph.embedding.resolve.probe_ollama", fake_probe)
        cm = await resolve_embedding_client(store)
        async with cm as (client, provider):
            assert provider == "ollama"
        assert store.meta["embedding_provider"] == "ollama"
        assert probed == [1]

    async def test_ollama_absent_falls_to_builtin(self, monkeypatch):
        store = _Store()

        async def fake_probe():
            return False

        built = []

        class FakeBuiltin:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr("loomgraph.embedding.resolve.explicit_provider",
                            lambda: None)
        monkeypatch.setattr("loomgraph.embedding.resolve.probe_ollama", fake_probe)
        monkeypatch.setattr(
            "loomgraph.embedding.resolve.make_builtin_client",
            lambda: built.append(1) or FakeBuiltin())
        cm = await resolve_embedding_client(store)
        async with cm as (client, provider):
            assert provider == "builtin"
        assert store.meta["embedding_provider"] == "builtin"
        assert built == [1]

    async def test_persisted_provider_skips_probe(self, monkeypatch):
        """Stickiness: recorded choice is reused — no re-probe, no flip-flop
        between ollama-up/ollama-down moments (embedding spaces differ)."""
        store = _Store({"embedding_provider": "builtin"})
        probed = []

        async def fake_probe():
            probed.append(1)
            return True  # ollama NOW up — must not win over the record

        built = []

        class FakeBuiltin:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr("loomgraph.embedding.resolve.explicit_provider",
                            lambda: None)
        monkeypatch.setattr("loomgraph.embedding.resolve.probe_ollama", fake_probe)
        monkeypatch.setattr(
            "loomgraph.embedding.resolve.make_builtin_client",
            lambda: built.append(1) or FakeBuiltin())
        cm = await resolve_embedding_client(store)
        async with cm as (client, provider):
            assert provider == "builtin"
        assert probed == []
        assert built == [1]

    async def test_explicit_config_never_probes_or_persists(self, monkeypatch):
        """Explicit provider = user override; no probe, no meta writes."""
        store = _Store()
        probed = []

        async def fake_probe():
            probed.append(1)
            return True

        monkeypatch.setattr("loomgraph.embedding.resolve.probe_ollama", fake_probe)
        monkeypatch.setattr(
            "loomgraph.embedding.resolve.explicit_provider",
            lambda: "ollama")
        cm = await resolve_embedding_client(store)
        async with cm as (client, provider):
            assert provider == "ollama"
        assert probed == []
        assert "embedding_provider" not in store.meta
