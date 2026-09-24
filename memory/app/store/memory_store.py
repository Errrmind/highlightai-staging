"""Filesystem memory store + local npy index + SQLite graph (CORE-BUILD-V1)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app import config
from app.models import Chunk
from app.retention.policy import RetentionPolicy
from app.store.npy_index import NpyVectorIndex
from app.store.sqlite_graph import SqliteGraph


class MemoryStore:
    def __init__(
        self,
        root: Path | None = None,
        project_id: str | None = None,
        retention: RetentionPolicy | None = None,
    ) -> None:
        self.project_id = project_id or config.PROJECT_ID
        self.root = root or config.STORE_DIR
        self.chunks_path = self.root / "chunks.jsonl"
        self.index_path = self.root / "index.json"
        self.retention = retention or RetentionPolicy()
        self.vector_index = NpyVectorIndex(self.project_id)
        self.graph = SqliteGraph(self.project_id)

    def _ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.index_path.write_text("{}\n", encoding="utf-8")

    def upsert_chunks(self, chunks: list[Chunk]) -> int:
        self._ensure()
        with self.chunks_path.open("a", encoding="utf-8") as fh:
            for chunk in chunks:
                fh.write(chunk.model_dump_json() + "\n")
        items = []
        for c in chunks:
            payload = c.model_dump(mode="json", exclude={"embedding"})
            items.append((c.embedding or [], payload))
            self.graph.upsert_node(
                c.record_id,
                kind="record",
                label=c.text[:80],
                properties={"project_id": c.project_id},
            )
            self.graph.upsert_node(
                c.chunk_id,
                kind="chunk",
                label=c.text[:80],
                properties={"record_id": c.record_id, "project_id": c.project_id},
            )
            self.graph.link(c.record_id, c.chunk_id, "has_chunk")
        self.vector_index.upsert(items)
        self._reindex()
        return len(chunks)

    def get_by_id(self, record_or_chunk_id: str, project_id: str | None = None) -> list[dict]:
        out: list[dict] = []
        for row in self._iter_chunks():
            if project_id and row.get("project_id") != project_id:
                continue
            if row.get("chunk_id") == record_or_chunk_id or row.get("record_id") == record_or_chunk_id:
                exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
                if not self.retention.is_expired(exp):
                    out.append(row)
        return out

    def all_chunks(self, project_id: str | None = None) -> list[dict]:
        rows = list(self._iter_chunks())
        kept, _ = self.retention.purge_expired(rows)
        if project_id:
            kept = [r for r in kept if r.get("project_id") == project_id]
        return kept

    def delete(self, id_: str, project_id: str | None = None, hard: bool = False) -> int:
        self._ensure()
        rows = list(self._iter_chunks())
        kept: list[dict] = []
        removed = 0
        remove_ids: set[str] = set()
        for row in rows:
            match = row.get("chunk_id") == id_ or row.get("record_id") == id_
            if project_id and row.get("project_id") != project_id:
                kept.append(row)
                continue
            if match:
                removed += 1
                remove_ids.add(row.get("chunk_id") or "")
                remove_ids.add(row.get("record_id") or "")
                if not hard:
                    row = dict(row)
                    row["expires_at"] = "1970-01-01T00:00:00+00:00"
                    kept.append(row)
            else:
                kept.append(row)
        self._rewrite_chunks(kept)
        self.vector_index.delete_ids({x for x in remove_ids if x})
        self.graph.delete_node(id_)
        self._reindex()
        return removed

    def link(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        project_id: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        g = SqliteGraph(project_id)
        return g.link(source_id, target_id, relation, properties)

    def links_for(self, node_id: str) -> list[dict]:
        return self.graph.neighbors(node_id)

    def export(self, project_id: str, dest: Path, fmt: str = "jsonl") -> Path:
        self._ensure()
        dest.parent.mkdir(parents=True, exist_ok=True)
        rows = self.all_chunks(project_id=project_id)
        if fmt == "json":
            dest.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        else:
            with dest.open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row) + "\n")
        return dest

    def _iter_chunks(self):
        if not self.chunks_path.exists():
            return
        with self.chunks_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def _rewrite_chunks(self, rows: list[dict]) -> None:
        self._ensure()
        with self.chunks_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def _reindex(self) -> None:
        self._ensure()
        index: dict[str, list[str]] = {}
        for row in self._iter_chunks():
            rid = row.get("record_id")
            cid = row.get("chunk_id")
            if rid and cid:
                index.setdefault(rid, []).append(cid)
        self.index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
