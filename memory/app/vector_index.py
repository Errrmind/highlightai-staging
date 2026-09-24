"""Numpy memmap vector index — WAVE1-1.2."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_DIM = 384
REBUILD_DELETED_RATIO = 0.30


class VectorIndex:
    """Cosine vector index backed by memmap vectors.npy + metadata.jsonl + chunk_ids.json."""

    def __init__(self, root: Path | str, dim: int = DEFAULT_DIM) -> None:
        self.root = Path(root)
        self.dim = int(dim)
        self.vectors_path = self.root / "vectors.npy"
        self.metadata_path = self.root / "metadata.jsonl"
        self.chunk_ids_path = self.root / "chunk_ids.json"
        self._meta: list[dict[str, Any]] = []
        self._ids: list[str] = []
        self._deleted: list[bool] = []
        self._vectors: np.memmap | np.ndarray | None = None
        self._capacity = 0
        self.root.mkdir(parents=True, exist_ok=True)
        if self.vectors_path.exists() and self.chunk_ids_path.exists():
            self.load()
        else:
            self._init_empty()

    def _init_empty(self) -> None:
        self._capacity = 1024
        self._vectors = np.memmap(
            self.vectors_path, dtype=np.float32, mode="w+", shape=(self._capacity, self.dim)
        )
        self._vectors[:] = 0
        self._vectors.flush()
        self._meta = []
        self._ids = []
        self._deleted = []
        self.save()

    def __len__(self) -> int:
        return sum(1 for d in self._deleted if not d)

    @property
    def deleted_ratio(self) -> float:
        if not self._deleted:
            return 0.0
        return sum(1 for d in self._deleted if d) / len(self._deleted)

    def _ensure_capacity(self, need: int) -> None:
        assert self._vectors is not None
        if need <= self._capacity:
            return
        new_cap = max(self._capacity * 2, need, 1024)
        # grow via rewrite (memmap cannot easily expand in-place portably)
        old = np.asarray(self._vectors[: len(self._ids)], dtype=np.float32).copy()
        del self._vectors
        self._vectors = np.memmap(
            self.vectors_path, dtype=np.float32, mode="w+", shape=(new_cap, self.dim)
        )
        self._vectors[:] = 0
        if old.size:
            self._vectors[: old.shape[0]] = old
        self._vectors.flush()
        self._capacity = new_cap

    def add(
        self,
        chunk_id: str,
        vector: np.ndarray | list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        if vec.shape[0] != self.dim:
            raise ValueError(f"expected dim={self.dim}, got {vec.shape[0]}")
        # upsert: soft-delete old then append (rebuild later)
        if chunk_id in self._ids:
            idx = self._ids.index(chunk_id)
            if not self._deleted[idx]:
                self._deleted[idx] = True
        n = len(self._ids)
        self._ensure_capacity(n + 1)
        assert self._vectors is not None
        self._vectors[n] = vec
        self._vectors.flush()
        meta = dict(metadata or {})
        meta["chunk_id"] = chunk_id
        self._meta.append(meta)
        self._ids.append(chunk_id)
        self._deleted.append(False)
        if self.deleted_ratio > REBUILD_DELETED_RATIO:
            self.rebuild()

    def delete(self, chunk_id: str) -> bool:
        found = False
        for i, cid in enumerate(self._ids):
            if cid == chunk_id and not self._deleted[i]:
                self._deleted[i] = True
                found = True
        if found and self.deleted_ratio > REBUILD_DELETED_RATIO:
            self.rebuild()
        return found

    def search(
        self,
        query: np.ndarray | list[float],
        top_k: int = 8,
        *,
        project_id: str | None = None,
        min_highlight_score: float | None = None,
        source_type: str | None = None,
        exclude_redacted: bool = True,
    ) -> list[dict[str, Any]]:
        t0 = time.perf_counter()
        if not self._ids or self._vectors is None:
            return []
        q = np.asarray(query, dtype=np.float32).reshape(-1)
        if q.shape[0] != self.dim:
            qq = np.zeros(self.dim, dtype=np.float32)
            n = min(q.shape[0], self.dim)
            qq[:n] = q[:n]
            q = qq
        qn = float(np.linalg.norm(q)) or 1.0
        q = q / qn
        n = len(self._ids)
        mat = np.asarray(self._vectors[:n], dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1)
        norms[norms == 0] = 1.0
        sims = (mat @ q) / norms
        hits: list[dict[str, Any]] = []
        order = np.argsort(-sims)
        for i in order:
            i = int(i)
            if self._deleted[i]:
                continue
            meta = dict(self._meta[i])
            if project_id is not None and meta.get("project_id") != project_id:
                continue
            if exclude_redacted and meta.get("redaction_flag") is True:
                continue
            if min_highlight_score is not None:
                hs = float(meta.get("highlight_score") or 0.0)
                if hs < min_highlight_score:
                    continue
            if source_type is not None and meta.get("source_type") != source_type:
                continue
            hits.append(
                {
                    "chunk_id": self._ids[i],
                    "score": float(sims[i]),
                    "similarity": float(sims[i]),
                    "metadata": meta,
                    "text": meta.get("text") or "",
                    "highlight_score": float(meta.get("highlight_score") or 0.0),
                    "record_id": meta.get("record_id") or self._ids[i],
                    "project_id": meta.get("project_id"),
                }
            )
            if len(hits) >= top_k:
                break
        _ = (time.perf_counter() - t0) * 1000  # latency budget tracked by callers/tests
        return hits

    def rebuild(self) -> int:
        keep_idx = [i for i, d in enumerate(self._deleted) if not d]
        if self._vectors is None:
            return 0
        kept_vecs = np.asarray(self._vectors[keep_idx], dtype=np.float32) if keep_idx else np.zeros(
            (0, self.dim), dtype=np.float32
        )
        kept_meta = [self._meta[i] for i in keep_idx]
        kept_ids = [self._ids[i] for i in keep_idx]
        del self._vectors
        self._capacity = max(1024, len(kept_ids) * 2, 1024)
        self._vectors = np.memmap(
            self.vectors_path, dtype=np.float32, mode="w+", shape=(self._capacity, self.dim)
        )
        self._vectors[:] = 0
        if kept_vecs.shape[0]:
            self._vectors[: kept_vecs.shape[0]] = kept_vecs
        self._vectors.flush()
        self._meta = kept_meta
        self._ids = kept_ids
        self._deleted = [False] * len(kept_ids)
        self.save()
        return len(kept_ids)

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self._vectors is not None:
            self._vectors.flush()
        with self.metadata_path.open("w", encoding="utf-8") as fh:
            for i, meta in enumerate(self._meta):
                row = dict(meta)
                row["_deleted"] = bool(self._deleted[i]) if i < len(self._deleted) else False
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.chunk_ids_path.write_text(
            json.dumps(
                {"ids": self._ids, "deleted": self._deleted, "dim": self.dim, "capacity": self._capacity},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def load(self) -> None:
        data = json.loads(self.chunk_ids_path.read_text(encoding="utf-8"))
        self._ids = list(data.get("ids") or [])
        self._deleted = list(data.get("deleted") or [False] * len(self._ids))
        self.dim = int(data.get("dim") or self.dim)
        self._capacity = int(data.get("capacity") or max(1024, len(self._ids)))
        self._meta = []
        if self.metadata_path.exists():
            with self.metadata_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    row.pop("_deleted", None)
                    self._meta.append(row)
        while len(self._meta) < len(self._ids):
            self._meta.append({"chunk_id": self._ids[len(self._meta)]})
        if self.vectors_path.exists():
            self._vectors = np.memmap(
                self.vectors_path, dtype=np.float32, mode="r+", shape=(self._capacity, self.dim)
            )
        else:
            self._init_empty()

    def get(self, chunk_id: str) -> dict[str, Any] | None:
        for i, cid in enumerate(self._ids):
            if cid == chunk_id and not self._deleted[i]:
                return dict(self._meta[i])
        return None
