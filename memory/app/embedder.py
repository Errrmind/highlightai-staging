"""Local embedder — all-MiniLM-L6-v2 (384-d, L2-normalized).

WAVE2-2.0: default loads sentence-transformers. Hash only when force_hash=True
(tests) or when ST load fails AND allow_hash_fallback=True (explicit blocker path).
"""
from __future__ import annotations

import hashlib
import re
import sys
from typing import Sequence

import numpy as np

DIM = 384
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_TOKEN = re.compile(r"[a-z0-9]+", re.I)


class EmbedderLoadError(RuntimeError):
    """Raised when MiniLM cannot load and hash fallback is not allowed."""


class Embedder:
    """embed_one / embed_batch → L2-normalized float32 vectors of dim 384."""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        force_hash: bool = False,
        cache_folder: str | None = None,
        allow_hash_fallback: bool = False,
    ) -> None:
        self.model_name = model_name
        self.dim = DIM
        self.backend = "hash"
        self._st = None
        self.load_error: str | None = None

        if force_hash:
            self.backend = "hash"
            self.dim = DIM
            print(
                f"[embedder] model={self.model_name} backend=hash (force_hash=True) dim={self.dim}",
                flush=True,
            )
            return

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            kwargs = {}
            if cache_folder:
                kwargs["cache_folder"] = cache_folder
            import os as _os

            rev = _os.getenv("EMBEDDING_REVISION")  # RW-1: pinned model commit (set in Dockerfile)
            if rev:
                kwargs["revision"] = rev
            self._st = SentenceTransformer(model_name, **kwargs)
            self.dim = int(self._st.get_embedding_dimension() if hasattr(self._st, "get_embedding_dimension") else self._st.get_sentence_embedding_dimension())
            self.backend = "sentence-transformers"
            print(
                f"[embedder] model={self.model_name} backend=sentence-transformers dim={self.dim}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._st = None
            self.load_error = f"{type(exc).__name__}: {exc}"
            self.backend = "hash"
            self.dim = DIM
            msg = (
                f"[embedder] BLOCKER: failed to load {model_name}: {self.load_error}. "
                f"backend=hash (fallback)"
            )
            print(msg, file=sys.stderr, flush=True)
            if not allow_hash_fallback:
                raise EmbedderLoadError(msg) from exc
            print(
                f"[embedder] model={self.model_name} backend=hash dim={self.dim} "
                f"(explicit fallback after ST failure)",
                flush=True,
            )

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        if self._st is not None:
            vecs = self._st.encode(
                list(texts),
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return np.asarray(vecs, dtype=np.float32)
        return np.stack([self._hash_embed(t) for t in texts], axis=0)

    def _hash_embed(self, text: str) -> np.ndarray:
        dim = self.dim
        vec = np.zeros(dim, dtype=np.float64)
        toks = _TOKEN.findall((text or "").lower()) or ["empty"]
        for tok in toks:
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            for offset in (0, 8):
                idx = int.from_bytes(h[offset : offset + 4], "little") % dim
                sign = 1.0 if h[offset + 4] % 2 == 0 else -1.0
                vec[idx] += sign
        for a, b in zip(toks, toks[1:]):
            h = hashlib.sha256(f"{a}_{b}".encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % dim
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += 0.5 * sign
        norm = float(np.linalg.norm(vec)) or 1.0
        return (vec / norm).astype(np.float32)
