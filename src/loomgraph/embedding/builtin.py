"""BuiltinEmbeddingClient — zero-config local embedding via ONNX int8 (#158).

CodeRankEmbed-137M (MIT, 768-dim, code-specialized). Heavy deps
(``onnxruntime`` + ``tokenizers``) live in the ``loomgraph[embed]`` extra —
importing them without the extra fails loud with the install hint (#142
philosophy), never silently degrades.

Query semantics (upstream model card): queries MUST carry the task prefix
``Represent this query for searching relevant code: ``; documents (code /
descriptions) embed bare. ``embed`` = documents, ``embed_query`` = prefixed
query — the search command uses the latter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loomgraph.embedding.base import EmbeddingClient, EmbeddingResult

QUERY_PREFIX = "Represent this query for searching relevant code: "
MAX_LENGTH = 512


class BuiltinEmbeddingError(RuntimeError):
    """Built-in embedding unavailable (missing extra / model / inference)."""


def _import_deps() -> tuple[Any, Any, Any]:
    try:
        import numpy as np  # noqa: PLC0415
        import onnxruntime as ort  # noqa: PLC0415
        from tokenizers import Tokenizer  # noqa: PLC0415
    except ImportError as ex:
        raise BuiltinEmbeddingError(
            f"built-in embedding needs the [embed] extra ({ex}). "
            "Install with: pipx install loomgraph[embed] "
            "(or: uv pip install 'loomgraph[embed]')"
        ) from ex
    return ort, Tokenizer, np


class BuiltinEmbeddingClient(EmbeddingClient):
    """Local CPU embedding client; model auto-downloaded on first use."""

    def __init__(self, model_dir: Path | None = None) -> None:
        from loomgraph.embedding.model_source import resolve_model_dir

        try:
            ort, tokenizer_cls, _np = _import_deps()
        except BuiltinEmbeddingError:
            raise
        except ImportError as ex:
            raise BuiltinEmbeddingError(
                f"built-in embedding needs the [embed] extra ({ex}). "
                "Install with: pipx install loomgraph[embed]"
            ) from ex
        self._dir = model_dir or resolve_model_dir()
        opts = ort.SessionOptions()
        self._sess = ort.InferenceSession(
            str(self._dir / "model.onnx"), sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._tok = tokenizer_cls.from_file(str(self._dir / "tokenizer.json"))
        self._tok.enable_truncation(max_length=MAX_LENGTH)
        self._tok.enable_padding(length=None)

    @property
    def dimension(self) -> int:
        return 768

    @property
    def max_length(self) -> int:
        return MAX_LENGTH

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        vecs = self._run(texts)
        return EmbeddingResult(embeddings=vecs, model="coderankembed-int8")

    async def embed_query(self, text: str) -> list[float]:
        """Query embedding — carries the required task-instruction prefix."""
        return self._run([QUERY_PREFIX + text])[0]

    async def embed_single(self, text: str) -> list[float]:
        return self._run([text])[0]

    def _run(self, texts: list[str]) -> list[list[float]]:
        _, _, np = _import_deps()
        enc = self._tok.encode_batch(texts)
        input_ids = np.array([e.ids for e in enc], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        outputs = self._sess.run(
            None,
            {"input_ids": input_ids, "attention_mask": attention_mask},
        )
        # sentence_embedding is the second output [B,768] — but this export
        # is NOT pre-normalized (measured norm ~24.7; the community README's
        # "L2-normalized" claim doesn't hold), so normalize here: vec0 KNN
        # uses L2 distance, where unnormalized inputs wreck ranking scores.
        # Pure-python normalize (no numpy ops) — keeps the mock surface tiny.
        import math

        result: list[list[float]] = []
        for row in outputs[1]:
            vals = [float(x) for x in row]
            norm = math.sqrt(sum(v * v for v in vals)) or 1.0
            result.append([v / norm for v in vals])
        return result
