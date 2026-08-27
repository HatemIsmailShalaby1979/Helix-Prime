"""
Durable local store for Helix Prime Codex C2.

SQLite-backed, local-first. Supports append/read/replay, idempotency,
duplicate/out-of-order detection, and persistence across process restart.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Any, Dict, List, Optional

from control_plane.events import Event
from control_plane.workflow import Workflow

DEFAULT_DB_PATH = "control_plane/workflow.db"


class Store:
    """
    Durable store with SQLite. Smallest safe local-first implementation.

    - Workflows keyed by workflow_id and idempotency_key (unique)
    - Events keyed by event_id (unique) and per-aggregate sequence (unique)
    - Append is atomic; duplicate event_id or out-of-order sequence fails deterministically
    - Idempotent workflow creation: same idempotency_key returns existing workflow
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        # Ensure directory exists
        pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE,
                correlation_id TEXT,
                data TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                aggregate_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                correlation_id TEXT,
                data TEXT NOT NULL,
                timestamp TEXT,
                UNIQUE(aggregate_id, sequence)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_agg_seq ON events(aggregate_id, sequence)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_workflows_corr ON workflows(correlation_id)")
        self.conn.commit()

    # ── workflows ────────────────────────────────────────────────────────────

    def create_workflow(self, workflow: Workflow) -> Workflow:
        """
        Idempotent creation: if idempotency_key already exists, return existing workflow.
        Otherwise insert new workflow and emit workflow_created event via caller (not here).
        Uses BEGIN IMMEDIATE for safe concurrent check-then-insert.
        """
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE")
            # Check idempotency inside transaction
            cur.execute("SELECT data FROM workflows WHERE idempotency_key = ?", (workflow.idempotency_key,))
            row = cur.fetchone()
            if row is not None:
                self.conn.execute("ROLLBACK")
                data = json.loads(row[0])
                return Workflow.from_dict(data)
            # Insert new
            data_json = json.dumps(workflow.to_dict(), default=str)
            cur.execute(
                "INSERT INTO workflows (workflow_id, idempotency_key, correlation_id, data, updated_at) VALUES (?, ?, ?, ?, ?)",
                (
                    workflow.workflow_id,
                    workflow.idempotency_key,
                    workflow.correlation.correlation_id,
                    data_json,
                    workflow.updated_at,
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            # Race: another insert with same idempotency_key succeeded
            cur.execute("SELECT data FROM workflows WHERE idempotency_key = ?", (workflow.idempotency_key,))
            row = cur.fetchone()
            if row is not None:
                data = json.loads(row[0])
                return Workflow.from_dict(data)
            raise ValueError(f"Store.create_workflow integrity error: {e}") from e
        except Exception:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        cur = self.conn.cursor()
        cur.execute("SELECT data FROM workflows WHERE workflow_id = ?", (workflow_id,))
        row = cur.fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return Workflow.from_dict(data)

    def get_workflow_by_idempotency(self, idempotency_key: str) -> Optional[Workflow]:
        cur = self.conn.cursor()
        cur.execute("SELECT data FROM workflows WHERE idempotency_key = ?", (idempotency_key,))
        row = cur.fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return Workflow.from_dict(data)

    def update_workflow(self, workflow: Workflow) -> None:
        data_json = json.dumps(workflow.to_dict(), default=str)
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE workflows SET data = ?, updated_at = ?, correlation_id = ? WHERE workflow_id = ?",
            (data_json, workflow.updated_at, workflow.correlation.correlation_id, workflow.workflow_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Store.update_workflow: workflow {workflow.workflow_id!r} not found")
        self.conn.commit()

    def list_workflows(self, limit: int = 100) -> List[Workflow]:
        cur = self.conn.cursor()
        cur.execute("SELECT data FROM workflows ORDER BY updated_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        return [Workflow.from_dict(json.loads(r[0])) for r in rows]

    # ── events ───────────────────────────────────────────────────────────────

    def append_event(self, event: Event) -> Event:
        """
        Append event. Enforces:
        - event_id unique
        - per-aggregate sequence must be exactly next (0,1,2...) — detects duplicate/out-of-order
        - idempotency: if same event_id already exists, return existing (idempotent)
        Uses BEGIN IMMEDIATE for safe per-aggregate sequence enforcement.
        """
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE")
            # Idempotency: if event_id already exists, return existing
            cur.execute("SELECT data FROM events WHERE event_id = ?", (event.event_id,))
            row = cur.fetchone()
            if row is not None:
                self.conn.execute("ROLLBACK")
                data = json.loads(row[0])
                return Event.from_dict(data)

            # Check sequence: must be next for this aggregate
            cur.execute("SELECT MAX(sequence) FROM events WHERE aggregate_id = ?", (event.aggregate_id,))
            row = cur.fetchone()
            max_seq = row[0] if row[0] is not None else -1
            expected = max_seq + 1
            if event.sequence != expected:
                self.conn.execute("ROLLBACK")
                raise ValueError(
                    f"Store.append_event: out-of-order sequence for {event.aggregate_id!r}: "
                    f"expected {expected}, got {event.sequence} (max existing {max_seq})"
                )

            data_json = json.dumps(event.to_dict(), default=str)
            cur.execute(
                "INSERT INTO events (event_id, aggregate_id, sequence, correlation_id, data, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (event.event_id, event.aggregate_id, event.sequence, event.correlation_id, data_json, event.timestamp),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            # Check if it's duplicate event_id
            cur.execute("SELECT data FROM events WHERE event_id = ?", (event.event_id,))
            row = cur.fetchone()
            if row is not None:
                data = json.loads(row[0])
                return Event.from_dict(data)
            raise ValueError(f"Store.append_event integrity error: {e}") from e
        except Exception:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        return event

    def get_events(self, aggregate_id: str) -> List[Event]:
        cur = self.conn.cursor()
        cur.execute("SELECT data FROM events WHERE aggregate_id = ? ORDER BY sequence ASC", (aggregate_id,))
        rows = cur.fetchall()
        return [Event.from_dict(json.loads(r[0])) for r in rows]

    def get_next_sequence(self, aggregate_id: str) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT MAX(sequence) FROM events WHERE aggregate_id = ?", (aggregate_id,))
        row = cur.fetchone()
        max_seq = row[0] if row[0] is not None else -1
        return max_seq + 1

    def replay(self, aggregate_id: str) -> List[Event]:
        """Alias for get_events — replay in order."""
        return self.get_events(aggregate_id)

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def clear_for_tests(self) -> None:
        """Danger: clear all data — for tests only."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM events")
        cur.execute("DELETE FROM workflows")
        self.conn.commit()
