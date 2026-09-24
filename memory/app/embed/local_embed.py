"""Local embeddings — sentence-transformers when available, else hashed bag-of-ngrams.

Never calls external embed APIs.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Sequence

import numpy as np

from app import config

_TOKEN = re.compile(r"[a-z0-9]+", re.I)


class LocalEmbedder:
    """Batch local embedder. Prefers MiniLM on disk; hash fallback is deterministic."""

    def __init__(
        self,
        model_name: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
        force_hash: bool | None = None,
    ) -> None:
        self.model_name = model_name or config.EMBEDDING_MODEL
        self.dimensions = dimensions or config.EMBEDDING_DIMENSIONS
        self.batch_size = batch_size or config.EMBED_BATCH_SIZE
        self.force_hash = config.FORCE_HASH_EMBED if force_hash is None else force_hash
        self._st = None
        self.backend = "hash"
        if not self.force_hash:
            self._try_load_st()

    def _try_load_st(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            cache = str(config.MODEL_CACHE_DIR)
            config.MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._st = SentenceTransformer(self.model_name, cache_folder=cache)
            self.backend = "sentence-transformers"
            # align dims to model
            dim = int(self._st.get_sentence_embedding_dimension())
            self.dimensions = dim
        except Exception:
            self._st = None
            self.backend = "hash"

    @property
    def live(self) -> bool:
        return False  # never external

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._st is not None:
            out: list[list[float]] = []
            for i in range(0, len(texts), self.batch_size):
                batch = list(texts[i : i + self.batch_size])
                vecs = self._st.encode(
                    batch,
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                )
                out.extend(v.tolist() for v in np.asarray(vecs))
            return out
        return [self._hash_embed(t) for t in texts]

    def _hash_embed(self, text: str) -> list[float]:
        """Token-hash embedding: similar bags → similar vectors (fixture-friendly)."""
        dim = self.dimensions
        vec = np.zeros(dim, dtype=np.float64)
        toks = _TOKEN.findall(text.lower())
        if not toks:
            toks = ["empty"]
        for tok in toks:
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            # two buckets per token for stability
            for offset in (0, 8):
                idx = int.from_bytes(h[offset : offset + 4], "little") % dim
                sign = 1.0 if h[offset + 4] % 2 == 0 else -1.0
                vec[idx] += sign
            # bigrams
        for a, b in zip(toks, toks[1:]):
            h = hashlib.sha256(f"{a}_{b}".encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % dim
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += 0.5 * sign
        norm = float(np.linalg.norm(vec)) or 1.0
        vec = vec / norm
        return vec.astype(float).tolist()


# Back-compat alias used by older imports
EmbeddingClient = LocalEmbedder
