"""Qdrant client stub — live only when QDRANT_URL is set by operator."""
from __future__ import annotations

from typing import Any

from app import config


class QdrantStore:
    def __init__(self, url: str | None = None) -> None:
        self.url = url if url is not None else config.QDRANT_URL

    @property
    def configured(self) -> bool:
        return bool(self.url)

    def upsert(self, points: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.configured:
            return {"status": "skipped", "reason": "qdrant_url_unset", "count": len(points)}
        raise RuntimeError(
            "Live Qdrant upsert disabled in scaffold; set QDRANT_URL and run via operator."
        )

    def search(self, vector: list[float], top_k: int = 8, project_id: str | None = None) -> list[dict]:
        if not self.configured:
            return []
        raise RuntimeError("Live Qdrant search disabled in scaffold.")

    def delete(self, ids: list[str]) -> dict[str, Any]:
        if not self.configured:
            return {"status": "skipped", "reason": "qdrant_url_unset"}
        raise RuntimeError("Live Qdrant delete disabled in scaffold.")
