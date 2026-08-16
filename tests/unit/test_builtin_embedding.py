"""
Unit tests for #158 built-in embedding: model source resolver + client.
Download and ONNX inference are mocked — a real-model smoke lives separately.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from loomgraph.embedding.model_source import (
    MODEL_SOURCES,
    download_model,
    resolve_model_dir,
)

# Two bytes that "hash" to whatever we declare: downloader verifies sha256
# against EXPECTED_SHA256 — tests craft files matching a patched constant.


class TestSourceOrder:
    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("LOOMGRAPH_EMBED_MODEL_URL", "https://x/y.onnx")
        from loomgraph.embedding import model_source
        assert model_source.source_urls()[0] == "https://x/y.onnx"

    def test_default_order_selfhost_first_hf_last(self):
        urls = list(MODEL_SOURCES)
        assert urls[0].startswith("https://github.com/dreamlx/LoomGraph/releases/")
        assert any("modelscope" in u for u in urls)
        assert urls[-1].startswith("https://huggingface.co/")


class TestDownload:
    def _fake_model_bytes(self) -> bytes:
        return b"onnx-model-bytes"

    def test_download_writes_and_verifies(self, tmp_path, monkeypatch):
        from loomgraph.embedding import model_source

        monkeypatch.setattr(model_source, "EXPECTED_SHA256",
                            hashlib.sha256(self._fake_model_bytes()).hexdigest())
        monkeypatch.setattr(model_source, "EXPECTED_TOKENIZER_SHA256",
                            hashlib.sha256(b'{"tokenizer":"json"}').hexdigest())
        # tokenizer is small; serve both from one fake source
        def fake_stream(url, chunk=1 << 16):
            data = (self._fake_model_bytes() if url.endswith(".onnx")
                    else b'{"tokenizer":"json"}')
            for i in range(0, len(data), chunk):
                yield data[i:i + chunk]

        monkeypatch.setattr(model_source, "_stream_url", fake_stream)
        d = download_model(cache_root=tmp_path)
        assert (d / "model.onnx").read_bytes() == self._fake_model_bytes()
        assert (d / "tokenizer.json").exists()

    def test_bad_sha_fails_loud(self, tmp_path, monkeypatch):
        from loomgraph.embedding import model_source

        monkeypatch.setattr(model_source, "EXPECTED_SHA256", "0" * 64)

        def fake_stream(url, chunk=1 << 16):
            yield self._fake_model_bytes()

        monkeypatch.setattr(model_source, "_stream_url", fake_stream)
        with pytest.raises(model_source.ModelDownloadError, match="sha256"):
            download_model(cache_root=tmp_path)

    def test_resolve_skips_download_when_cached(self, tmp_path, monkeypatch):
        from loomgraph.embedding import model_source

        called = []
        monkeypatch.setattr(model_source, "download_model",
                            lambda cache_root: called.append(1) or tmp_path)
        # pre-populate files whose shas match the patched pins
        # (cached files are re-verified, BOTH artifacts — re-review C2-1)
        mdata, tdata = b"cached-model", b"cached-tokenizer"
        (tmp_path / "model.onnx").write_bytes(mdata)
        (tmp_path / "tokenizer.json").write_bytes(tdata)
        monkeypatch.setattr(model_source, "EXPECTED_SHA256",
                            hashlib.sha256(mdata).hexdigest())
        monkeypatch.setattr(model_source, "EXPECTED_TOKENIZER_SHA256",
                            hashlib.sha256(tdata).hexdigest())
        d = resolve_model_dir(cache_root=tmp_path)
        assert d == tmp_path
        assert not called



class _FakeNP:
    """Minimal numpy shim (array + dtypes) so the mocked-inference tests run
    in CI without the [embed] extra — normalization is pure-python now."""

    float32 = "float32"
    int64 = "int64"

    @staticmethod
    def array(x, dtype=None):
        return x


class TestBuiltinClient:
    def test_missing_extra_fails_loud_with_hint(self, monkeypatch):
        from loomgraph.embedding import builtin

        def boom(name):
            raise ImportError(f"No module named {name!r}")

        monkeypatch.setattr(
            builtin, "_import_deps",
            lambda: (_ for _ in ()).throw(ImportError("No module named 'onnxruntime'")))
        with pytest.raises(builtin.BuiltinEmbeddingError, match=r"loomgraph\[embed\]"):
            builtin.BuiltinEmbeddingClient(model_dir=Path("/tmp"))

    def test_embed_adds_no_prefix_for_documents(self, tmp_path, monkeypatch):
        """Documents (entity descriptions) embed WITHOUT the query prefix."""
        from loomgraph.embedding import builtin

        captured = {}

        class _Enc:
            def __init__(self, ids, mask):
                self.ids, self.attention_mask = ids, mask

        class FakeTok:
            def encode_batch(self, texts):
                captured["docs"] = list(texts)
                return [_Enc([1, 2], [1, 1]) for _ in texts]

        class FakeSess:
            def run(self, _, feeds):
                n = len(feeds["input_ids"])
                return [None, [[0.1, 0.2, 0.3]] * n]

        c = builtin.BuiltinEmbeddingClient.__new__(builtin.BuiltinEmbeddingClient)
        monkeypatch.setattr(builtin, "_import_deps",
                            lambda: (None, None, _FakeNP))
        c._tok = FakeTok()
        c._sess = FakeSess()
        import asyncio
        res = asyncio.run(c.embed(["def foo(): pass"]))
        assert captured["docs"] == ["def foo(): pass"]
        # L2-normalized (unnormalized-ONNX fix): [0.1,0.2,0.3] / |.|
        n = (0.01 + 0.04 + 0.09) ** 0.5
        assert res.embeddings[0] == pytest.approx(
            [0.1 / n, 0.2 / n, 0.3 / n])

    def test_embed_query_adds_prefix(self, tmp_path, monkeypatch):
        from loomgraph.embedding import builtin

        captured = {}

        class _Enc:
            def __init__(self, ids, mask):
                self.ids, self.attention_mask = ids, mask

        class FakeTok:
            def encode_batch(self, texts):
                captured["docs"] = list(texts)
                return [_Enc([1], [1]) for _ in texts]

        class FakeSess:
            def run(self, _, feeds):
                n = len(feeds["input_ids"])
                return [None, [[0.3, 0.2, 0.1]] * n]

        c = builtin.BuiltinEmbeddingClient.__new__(builtin.BuiltinEmbeddingClient)
        monkeypatch.setattr(builtin, "_import_deps",
                            lambda: (None, None, _FakeNP))
        c._tok = FakeTok()
        c._sess = FakeSess()
        import asyncio
        vec = asyncio.run(c.embed_query("where are hotspots computed"))
        assert captured["docs"] == [builtin.QUERY_PREFIX + "where are hotspots computed"]
        n = (0.09 + 0.04 + 0.01) ** 0.5
        assert vec == pytest.approx([0.3 / n, 0.2 / n, 0.1 / n])
