"""Self-hosted model acquisition for the built-in embedding provider (#158).

Resolution order (dreamlinx decision, loomgraph #158):
  1. env ``LOOMGRAPH_EMBED_MODEL_URL`` (advanced escape hatch — one URL,
     served verbatim; tokenizer.json is fetched from the same directory)
  2. GitHub Releases asset (self-hosted, primary — no LFS quota, CDN-backed)
  3. ModelScope mirror (direct reachability from CN networks)
  4. HuggingFace community repo (fallback of last resort)

The model is CodeRankEmbed-137M dynamic-int8 ONNX (MIT), 139 MB, 768-dim.
SHA256 pins the v2 quantization (``reduce_range=True`` — v1 produced
degenerate embeddings on pre-VNNI AVX2 CPUs; see upstream README).
"""

from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from collections.abc import Iterator
from pathlib import Path

MODEL_NAME = "coderankembed-int8"
# v2 quantization per mrsladoje/CodeRankEmbed-onnx-int8 README (MIT).
EXPECTED_SHA256 = (
    "4eae31d09b1843103a1ebd5e2b2e24b5a5cad441a33906b35b12b1e2ed91d1db"
)

# GitHub asset is uploaded at release time (embed-v1); until then 404s fall
# through to the next source — the resolver degrades naturally.
MODEL_SOURCES = [
    "https://github.com/dreamlx/LoomGraph/releases/download/embed-v1/coderankembed-int8.onnx",
    "https://modelscope.cn/models/dreamlx/LoomGraph-embed/resolve/master/coderankembed-int8.onnx",
    "https://huggingface.co/mrsladoje/CodeRankEmbed-onnx-int8/resolve/main/onnx/model.onnx",
]
TOKENIZER_SOURCES = [
    "https://github.com/dreamlx/LoomGraph/releases/download/embed-v1/tokenizer.json",
    "https://modelscope.cn/models/dreamlx/LoomGraph-embed/resolve/master/tokenizer.json",
    "https://huggingface.co/mrsladoje/CodeRankEmbed-onnx-int8/resolve/main/tokenizer.json",
]

_CHUNK = 1 << 16


class ModelDownloadError(RuntimeError):
    """Model acquisition failed — no source reachable or checksum mismatch."""


def source_urls() -> list[str]:
    env = os.environ.get("LOOMGRAPH_EMBED_MODEL_URL")
    if env:
        return [env]
    return list(MODEL_SOURCES)


def tokenizer_urls() -> list[str]:
    env = os.environ.get("LOOMGRAPH_EMBED_MODEL_URL")
    if env:
        return [env.rsplit("/", 1)[0] + "/tokenizer.json"]
    return list(TOKENIZER_SOURCES)


def _stream_url(url: str, chunk: int = _CHUNK) -> Iterator[bytes]:
    with urllib.request.urlopen(url, timeout=30) as resp:
        while True:
            b = resp.read(chunk)
            if not b:
                return
            yield b


def default_cache_root() -> Path:
    return Path.home() / ".loomgraph" / "models" / MODEL_NAME


def download_model(cache_root: Path | None = None) -> Path:
    """Fetch model.onnx + tokenizer.json into the cache dir, sha256-verified.

    Falls through sources in order; writes atomically (tmp + rename).
    """
    root = cache_root or default_cache_root()
    root.mkdir(parents=True, exist_ok=True)

    model_path = root / "model.onnx"
    last_err: Exception | None = None
    for url in source_urls():
        try:
            h = hashlib.sha256()
            tmp = root / "model.onnx.tmp"
            with tmp.open("wb") as fh:
                for chunk in _stream_url(url):
                    fh.write(chunk)
                    h.update(chunk)
            digest = h.hexdigest()
            if digest != EXPECTED_SHA256:
                tmp.unlink(missing_ok=True)
                raise ModelDownloadError(
                    f"sha256 mismatch for {url}: got {digest}, want {EXPECTED_SHA256}"
                )
            tmp.replace(model_path)
            break
        except Exception as ex:  # noqa: BLE001 — fall through to next source
            last_err = ex
            print(f"[loomgraph] model source failed ({url}): {ex}", file=sys.stderr)
    else:
        raise ModelDownloadError(f"all model sources failed: {last_err}")

    tok_path = root / "tokenizer.json"
    if not tok_path.exists():
        for url in tokenizer_urls():
            try:
                tmp = root / "tokenizer.json.tmp"
                with tmp.open("wb") as fh:
                    for chunk in _stream_url(url):
                        fh.write(chunk)
                tmp.replace(tok_path)
                break
            except Exception as ex:  # noqa: BLE001
                last_err = ex
                print(f"[loomgraph] tokenizer source failed ({url}): {ex}",
                      file=sys.stderr)
        else:
            raise ModelDownloadError(f"all tokenizer sources failed: {last_err}")

    return root


def resolve_model_dir(cache_root: Path | None = None) -> Path:
    """Return the cache dir with model+tokenizer present, downloading once."""
    root = cache_root or default_cache_root()
    if (root / "model.onnx").exists() and (root / "tokenizer.json").exists():
        return root
    return download_model(cache_root=root)
