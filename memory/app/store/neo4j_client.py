"""Neo4j client stub — live only when NEO4J_URI is set by operator."""
from __future__ import annotations

from typing import Any

from app import config


class Neo4jStore:
    def __init__(self, uri: str | None = None) -> None:
        self.uri = uri if uri is not None else config.NEO4J_URI

    @property
    def configured(self) -> bool:
        return bool(self.uri)

    def link(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {
                "status": "skipped",
                "reason": "neo4j_uri_unset",
                "source_id": source_id,
                "target_id": target_id,
                "relation": relation,
            }
        raise RuntimeError(
            "Live Neo4j write disabled in scaffold; set NEO4J_URI and run via operator."
        )

    def neighbors(self, node_id: str, limit: int = 16) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        raise RuntimeError("Live Neo4j query disabled in scaffold.")

    def delete_node(self, node_id: str) -> dict[str, Any]:
        if not self.configured:
            return {"status": "skipped", "reason": "neo4j_uri_unset"}
        raise RuntimeError("Live Neo4j delete disabled in scaffold.")
