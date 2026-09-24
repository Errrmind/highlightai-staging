"""SQLite knowledge graph sharded by project_id."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app import config


class SqliteGraph:
    def __init__(self, project_id: str, root: Path | None = None) -> None:
        self.project_id = project_id
        self.path = (root or config.GRAPH_DIR) / f"{project_id}.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                  id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL DEFAULT 'record',
                  label TEXT,
                  properties TEXT NOT NULL DEFAULT '{}',
                  project_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edges (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_id TEXT NOT NULL,
                  target_id TEXT NOT NULL,
                  relation TEXT NOT NULL,
                  properties TEXT NOT NULL DEFAULT '{}',
                  project_id TEXT NOT NULL,
                  UNIQUE(source_id, target_id, relation)
                );
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
                """
            )

    def upsert_node(
        self,
        node_id: str,
        kind: str = "record",
        label: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        props = json.dumps(properties or {})
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO nodes(id, kind, label, properties, project_id)
                VALUES(?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  kind=excluded.kind,
                  label=excluded.label,
                  properties=excluded.properties
                """,
                (node_id, kind, label, props, self.project_id),
            )

    def link(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.upsert_node(source_id)
        self.upsert_node(target_id)
        props = json.dumps(properties or {})
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO edges(source_id, target_id, relation, properties, project_id)
                VALUES(?,?,?,?,?)
                ON CONFLICT(source_id, target_id, relation) DO UPDATE SET
                  properties=excluded.properties
                """,
                (source_id, target_id, relation, props, self.project_id),
            )
        return {
            "source_id": source_id,
            "target_id": target_id,
            "relation": relation,
            "project_id": self.project_id,
            "status": "ok",
        }

    def neighbors(self, node_id: str, limit: int = 16) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT source_id, target_id, relation, properties FROM edges
                WHERE source_id=? OR target_id=?
                LIMIT ?
                """,
                (node_id, node_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            other = r["target_id"] if r["source_id"] == node_id else r["source_id"]
            out.append(
                {
                    "node_id": other,
                    "relation": r["relation"],
                    "properties": json.loads(r["properties"] or "{}"),
                    "source_id": r["source_id"],
                    "target_id": r["target_id"],
                }
            )
        return out

    def delete_node(self, node_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM edges WHERE source_id=? OR target_id=?", (node_id, node_id))
            conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))

    def expand(self, seed_ids: list[str], max_hops: int = 1, limit: int = 32) -> list[str]:
        seen = set(seed_ids)
        frontier = list(seed_ids)
        for _ in range(max_hops):
            nxt: list[str] = []
            for nid in frontier:
                for n in self.neighbors(nid, limit=limit):
                    oid = n["node_id"]
                    if oid not in seen:
                        seen.add(oid)
                        nxt.append(oid)
            frontier = nxt
            if not frontier:
                break
        return [i for i in seen if i not in seed_ids]
