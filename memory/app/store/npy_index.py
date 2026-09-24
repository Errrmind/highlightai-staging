"""Numpy .npy + JSON metadata vector index under artifacts/memory/index/{project_id}/."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app import config


class NpyVectorIndex:
    def __init__(self, project_id: str, root: Path | None = None) -> None:
        self.project_id = project_id
        self.dir = (root or config.INDEX_DIR) / project_id
        self.vectors_path = self.dir / "vectors.npy"
        self.meta_path = self.dir / "meta.json"

    def _ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> tuple[np.ndarray, list[dict[str, Any]]]:
        self._ensure()
        if not self.vectors_path.exists() or not self.meta_path.exists():
            return np.zeros((0, config.EMBEDDING_DIMENSIONS), dtype=np.float32), []
        vecs = np.load(self.vectors_path)
        meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        return vecs, meta

    def _save(self, vecs: np.ndarray, meta: list[dict[str, Any]]) -> None:
        self._ensure()
        np.save(self.vectors_path, vecs.astype(np.float32))
        self.meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    def upsert(self, items: list[tuple[list[float], dict[str, Any]]]) -> int:
        if not items:
            return 0
        vecs, meta = self._load()
        by_id = {m.get("chunk_id"): i for i, m in enumerate(meta)}
        for emb, payload in items:
            arr = np.asarray(emb, dtype=np.float32)
            cid = payload.get("chunk_id")
            if cid in by_id:
                i = by_id[cid]
                if vecs.shape[0] == 0:
                    vecs = arr.reshape(1, -1)
                else:
                    if arr.shape[0] != vecs.shape[1]:
                        # rebuild dim if needed
                        new = np.zeros((len(meta), arr.shape[0]), dtype=np.float32)
                        new[: vecs.shape[0], : min(vecs.shape[1], arr.shape[0])] = vecs[
                            :, : min(vecs.shape[1], arr.shape[0])
                        ]
                        vecs = new
                    vecs[i] = arr
                meta[i] = payload
            else:
                if vecs.shape[0] == 0:
                    vecs = arr.reshape(1, -1)
                else:
                    if arr.shape[0] != vecs.shape[1]:
                        new = np.zeros((vecs.shape[0], arr.shape[0]), dtype=np.float32)
                        new[:, : vecs.shape[1]] = vecs
                        vecs = new
                    vecs = np.vstack([vecs, arr.reshape(1, -1)])
                meta.append(payload)
                by_id[cid] = len(meta) - 1
        self._save(vecs, meta)
        return len(items)

    def search(
        self,
        query_vec: list[float],
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        vecs, meta = self._load()
        if vecs.shape[0] == 0:
            return []
        q = np.asarray(query_vec, dtype=np.float32)
        if q.shape[0] != vecs.shape[1]:
            # pad/truncate
            qq = np.zeros(vecs.shape[1], dtype=np.float32)
            n = min(q.shape[0], vecs.shape[1])
            qq[:n] = q[:n]
            q = qq
        # cosine
        qn = q / (np.linalg.norm(q) or 1.0)
        norms = np.linalg.norm(vecs, axis=1)
        norms[norms == 0] = 1.0
        scores = (vecs @ qn) / norms
        order = np.argsort(-scores)
        out: list[dict[str, Any]] = []
        for i in order:
            row = dict(meta[int(i)])
            if filters:
                if "project_id" in filters and row.get("project_id") != filters["project_id"]:
                    continue
                if filters.get("pii_flag") is False and row.get("pii_flag"):
                    continue
            row["score"] = float(scores[int(i)])
            out.append(row)
            if len(out) >= top_k:
                break
        return out

    def delete_ids(self, ids: set[str]) -> int:
        vecs, meta = self._load()
        if not meta:
            return 0
        keep_idx = [i for i, m in enumerate(meta) if m.get("chunk_id") not in ids and m.get("record_id") not in ids]
        removed = len(meta) - len(keep_idx)
        if removed == 0:
            return 0
        new_meta = [meta[i] for i in keep_idx]
        new_vecs = vecs[keep_idx] if keep_idx else np.zeros((0, vecs.shape[1] if vecs.ndim == 2 else config.EMBEDDING_DIMENSIONS), dtype=np.float32)
        self._save(new_vecs, new_meta)
        return removed
