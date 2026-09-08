"""Node storage for the super-app.

Provides CRUD operations on Nodes with tenant isolation.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from server.models.node import Node, NodeKind


class NodeStore:
    """SQLite-backed node store with tenant isolation."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Connect to the database."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        """Initialize the schema."""
        if self._conn is None:
            raise RuntimeError("Not connected")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                client_id TEXT,
                correlation_id TEXT NOT NULL,
                causation_id TEXT,
                classification TEXT NOT NULL,
                nature TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                provenance_source TEXT,
                provenance_data_mode TEXT,
                provenance_retrieved_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nodes_tenant
            ON nodes(tenant_id, created_at DESC)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nodes_correlation
            ON nodes(correlation_id)
        """)
        self._conn.commit()

    def create(self, node: Node) -> Node:
        """Create a new node."""
        if self._conn is None:
            raise RuntimeError("Not connected")

        self._conn.execute(
            """
            INSERT OR REPLACE INTO nodes (
                node_id, tenant_id, client_id, correlation_id, causation_id,
                classification, nature, created_by, created_at, kind, body,
                provenance_source, provenance_data_mode, provenance_retrieved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.envelope.node_id,
                node.envelope.tenant_id,
                node.envelope.client_id,
                node.envelope.correlation_id,
                node.envelope.causation_id,
                node.envelope.classification.value,
                node.envelope.nature.value,
                node.envelope.created_by,
                node.envelope.created_at,
                node.kind.value,
                json.dumps(node.body),
                node.envelope.provenance.source,
                node.envelope.provenance.data_mode,
                node.envelope.provenance.retrieved_at,
            ),
        )
        self._conn.commit()
        return node

    def get(self, node_id: str, tenant_id: str) -> Node | None:
        """Get a node by ID with tenant isolation."""
        if self._conn is None:
            raise RuntimeError("Not connected")

        row = self._conn.execute(
            "SELECT * FROM nodes WHERE node_id = ? AND tenant_id = ?",
            (node_id, tenant_id),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_node(row)

    def list_by_tenant(
        self,
        tenant_id: str,
        kind: NodeKind | None = None,
        limit: int = 100,
    ) -> Sequence[Node]:
        """List nodes for a tenant with optional kind filter."""
        if self._conn is None:
            raise RuntimeError("Not connected")

        query = "SELECT * FROM nodes WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]

        if kind:
            query += " AND kind = ?"
            params.append(kind.value)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_node(row) for row in rows]

    def list_by_correlation(
        self,
        correlation_id: str,
        tenant_id: str,
    ) -> Sequence[Node]:
        """List nodes by correlation ID (for conversation threads)."""
        if self._conn is None:
            raise RuntimeError("Not connected")

        rows = self._conn.execute(
            """
            SELECT * FROM nodes
            WHERE correlation_id = ? AND tenant_id = ?
            ORDER BY created_at ASC
            """,
            (correlation_id, tenant_id),
        ).fetchall()

        return [self._row_to_node(row) for row in rows]

    def _row_to_node(self, row: sqlite3.Row) -> Node:
        """Convert a database row to a Node."""
        from server.models.node import (
            NodeEnvelope,
            NodeKind,
            Nature,
            Classification,
            Provenance,
        )

        envelope = NodeEnvelope(
            node_id=row["node_id"],
            tenant_id=row["tenant_id"],
            client_id=row["client_id"],
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
            classification=Classification(row["classification"]),
            nature=Nature(row["nature"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
            provenance=Provenance(
                source=row["provenance_source"] or "unknown",
                data_mode=row["provenance_data_mode"] or "simulated_realistic",
                retrieved_at=row["provenance_retrieved_at"] or "",
            ),
        )

        kind = NodeKind(row["kind"])
        body = json.loads(row["body"]) if row["body"] else {}

        return Node(envelope=envelope, kind=kind, body=body)
