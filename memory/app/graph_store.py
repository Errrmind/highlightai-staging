"""SQLite WAL graph store — WAVE1-1.2."""
from __future__ import annotations

import json
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any


class GraphStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
              id TEXT PRIMARY KEY,
              type TEXT NOT NULL DEFAULT 'record',
              properties TEXT NOT NULL DEFAULT '{}',
              project_id TEXT,
              created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS edges (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_id TEXT NOT NULL,
              target_id TEXT NOT NULL,
              relation TEXT NOT NULL,
              properties TEXT NOT NULL DEFAULT '{}',
              project_id TEXT,
              UNIQUE(source_id, target_id, relation)
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
            CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project_id);
            CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_rel ON edges(relation);
            """
        )
        self._conn.commit()

    def add_node(
        self,
        node_id: str,
        node_type: str = "record",
        properties: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> None:
        props = json.dumps(properties or {})
        self._conn.execute(
            """
            INSERT INTO nodes(id, type, properties, project_id)
            VALUES(?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              type=excluded.type,
              properties=excluded.properties,
              project_id=COALESCE(excluded.project_id, nodes.project_id)
            """,
            (node_id, node_type, props, project_id),
        )
        self._conn.commit()

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> None:
        if not self.get_node(source_id):
            self.add_node(source_id, project_id=project_id)
        if not self.get_node(target_id):
            self.add_node(target_id, project_id=project_id)
        props = json.dumps(properties or {})
        self._conn.execute(
            """
            INSERT INTO edges(source_id, target_id, relation, properties, project_id)
            VALUES(?,?,?,?,?)
            ON CONFLICT(source_id, target_id, relation) DO UPDATE SET
              properties=excluded.properties
            """,
            (source_id, target_id, relation, props, project_id),
        )
        self._conn.commit()

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "type": row["type"],
            "properties": json.loads(row["properties"] or "{}"),
            "project_id": row["project_id"],
            "created_at": row["created_at"],
        }

    def get_edges_from(self, node_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE source_id=?", (node_id,)
        ).fetchall()
        return [self._edge_row(r) for r in rows]

    def get_edges_to(self, node_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE target_id=?", (node_id,)
        ).fetchall()
        return [self._edge_row(r) for r in rows]

    def _edge_row(self, r: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": r["id"],
            "source_id": r["source_id"],
            "target_id": r["target_id"],
            "relation": r["relation"],
            "properties": json.loads(r["properties"] or "{}"),
            "project_id": r["project_id"],
        }

    def expand(
        self,
        seed_ids: list[str],
        max_depth: int = 2,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """BFS expand from seeds; returns neighbor edge records up to limit."""
        seen_nodes = set(seed_ids)
        seen_edges: list[dict[str, Any]] = []
        q: deque[tuple[str, int]] = deque((s, 0) for s in seed_ids)
        while q and len(seen_edges) < limit:
            nid, depth = q.popleft()
            if depth >= max_depth:
                continue
            for e in self.get_edges_from(nid) + self.get_edges_to(nid):
                if len(seen_edges) >= limit:
                    break
                eid = (e["source_id"], e["target_id"], e["relation"])
                if any(
                    (x["source_id"], x["target_id"], x["relation"]) == eid for x in seen_edges
                ):
                    continue
                seen_edges.append(e)
                other = e["target_id"] if e["source_id"] == nid else e["source_id"]
                if other not in seen_nodes:
                    seen_nodes.add(other)
                    q.append((other, depth + 1))
        return seen_edges

    def get_neighbors_by_type(self, node_id: str, node_type: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for e in self.get_edges_from(node_id) + self.get_edges_to(node_id):
            other = e["target_id"] if e["source_id"] == node_id else e["source_id"]
            node = self.get_node(other)
            if node and node.get("type") == node_type:
                out.append({"node": node, "edge": e})
        return out

    def count(self) -> dict[str, int]:
        n = self._conn.execute("SELECT COUNT(*) AS c FROM nodes").fetchone()["c"]
        e = self._conn.execute("SELECT COUNT(*) AS c FROM edges").fetchone()["c"]
        return {"nodes": int(n), "edges": int(e)}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore
