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
        # Rows as name-accessible mappings. Safe for existing callers: sqlite3.Row
        # still supports positional indexing (row[0]).
        self.conn.row_factory = sqlite3.Row
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
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_agg_seq ON events(aggregate_id, sequence)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_workflows_corr ON workflows(correlation_id)")
        self._init_governance_schema(cur)
        self.conn.commit()

    def _init_governance_schema(self, cur: sqlite3.Cursor) -> None:
        """
        Governance tables for the enterprise control plane.

        workflow_tasks — active workflow state, one row per governed task.
        audit_events  — append-only transaction ledger, hash-chained and enforced
                        append-only by SQLite triggers (fail-closed, local-first).
        """
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_tasks (
                task_id TEXT PRIMARY KEY,
                workflow_id TEXT,
                correlation_id TEXT NOT NULL,
                tenant_id TEXT,
                client_id TEXT,
                actor_id TEXT NOT NULL,
                actor_role_id TEXT NOT NULL,
                owning_role_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                target_engine TEXT,
                state TEXT NOT NULL,
                estimated_financial_cost REAL NOT NULL DEFAULT 0,
                financial_limit_usd REAL,
                data_classification TEXT NOT NULL,
                confidence_score REAL NOT NULL DEFAULT 1.0,
                reason_code TEXT,
                reason TEXT,
                payload TEXT NOT NULL DEFAULT '{}',
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                schema_version TEXT NOT NULL DEFAULT '1.0'
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_state ON workflow_tasks(state)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_corr ON workflow_tasks(correlation_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_role ON workflow_tasks(actor_role_id)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_role_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason_code TEXT,
                reason TEXT,
                task_id TEXT,
                workflow_id TEXT,
                from_state TEXT,
                to_state TEXT,
                payload TEXT NOT NULL DEFAULT '{}',
                prev_hash TEXT NOT NULL DEFAULT '',
                record_hash TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_corr ON audit_events(correlation_id)")

        # Append-only enforcement: the ledger accepts INSERT only.
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only: UPDATE forbidden');
            END
            """
        )
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only: DELETE forbidden');
            END
            """
        )

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
            cur.execute(
                "SELECT data FROM workflows WHERE idempotency_key = ?", (workflow.idempotency_key,)
            )
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
            cur.execute(
                "SELECT data FROM workflows WHERE idempotency_key = ?", (workflow.idempotency_key,)
            )
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
            (
                data_json,
                workflow.updated_at,
                workflow.correlation.correlation_id,
                workflow.workflow_id,
            ),
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
            cur.execute(
                "SELECT MAX(sequence) FROM events WHERE aggregate_id = ?", (event.aggregate_id,)
            )
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
                (
                    event.event_id,
                    event.aggregate_id,
                    event.sequence,
                    event.correlation_id,
                    data_json,
                    event.timestamp,
                ),
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
        cur.execute(
            "SELECT data FROM events WHERE aggregate_id = ? ORDER BY sequence ASC", (aggregate_id,)
        )
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
        """
        Release every handle this store owns.

        C0: on Windows an un-closed SQLite connection keeps a lock on the file,
        and the next ``shutil.rmtree`` fails with WinError 32 / WinError 267.
        Closing is therefore three deliberate steps, each best-effort:

        1. checkpoint and truncate WAL so no ``-wal``/``-shm`` sidecar survives;
        2. close the connection itself;
        3. drop the reference so a GC cycle cannot resurrect a stale handle.
        """
        conn = getattr(self, "conn", None)
        if conn is None:
            return
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        finally:
            try:
                del self.conn
            except AttributeError:
                pass

    # ── context manager ─────────────────────────────────────────────────────

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Always close, including on exception: a leaked handle here is what
        # makes temporary directories undeletable on Windows.
        self.close()

    @property
    def closed(self) -> bool:
        return not hasattr(self, "conn") or self.conn is None

    def clear_for_tests(self) -> None:
        """
        Danger: clear all mutable data — for tests only.

        audit_events is intentionally NOT cleared: it is the append-only ledger and
        is protected by SQLite triggers.
        """
        cur = self.conn.cursor()
        cur.execute("DELETE FROM events")
        cur.execute("DELETE FROM workflows")
        cur.execute("DELETE FROM workflow_tasks")
        # Existing C2 callers use clear_for_tests() to reset the complete local
        # store between tests. The governance ledger is append-only in production;
        # this explicit test-only escape hatch temporarily removes the triggers,
        # clears rows, then reinstates them before returning.
        cur.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update")
        cur.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete")
        cur.execute("DELETE FROM audit_events")
        self._init_governance_schema(cur)
        self.conn.commit()

    # ── governance: workflow_tasks ─────────────────────────────────────────

    def insert_workflow_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a governed task row. Duplicate task_id fails deterministically."""
        self._require_task_columns(
            task, {"task_id", "correlation_id", "actor_id", "capability", "state"}
        )
        payload_json = json.dumps(task.get("payload") or {}, default=str)
        error_json = (
            json.dumps(task["error"], default=str) if task.get("error") is not None else None
        )
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO workflow_tasks (
                task_id, workflow_id, correlation_id, tenant_id, client_id,
                actor_id, actor_role_id, owning_role_id, capability, target_engine,
                state, estimated_financial_cost, financial_limit_usd, data_classification,
                confidence_score, reason_code, reason, payload, error,
                created_at, updated_at, schema_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task["task_id"],
                task.get("workflow_id"),
                task["correlation_id"],
                task.get("tenant_id"),
                task.get("client_id"),
                task["actor_id"],
                task.get("actor_role_id", ""),
                task.get("owning_role_id", ""),
                task["capability"],
                task.get("target_engine"),
                task["state"],
                float(task.get("estimated_financial_cost") or 0.0),
                task.get("financial_limit_usd"),
                task.get("data_classification", "internal"),
                float(
                    task.get("confidence_score")
                    if task.get("confidence_score") is not None
                    else 1.0
                ),
                task.get("reason_code"),
                task.get("reason"),
                payload_json,
                error_json,
                task.get("created_at", ""),
                task.get("updated_at", ""),
                task.get("schema_version", "1.0"),
            ),
        )
        self.conn.commit()
        return self.get_workflow_task(task["task_id"]) or task

    def update_workflow_task_state(
        self,
        task_id: str,
        new_state: str,
        *,
        updated_at: Optional[str] = None,
        reason_code: Optional[str] = None,
        reason: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update the mutable columns of a task row. Missing task -> ValueError."""
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE workflow_tasks
               SET state = ?, updated_at = ?, reason_code = ?, reason = ?, payload = ?, error = ?
             WHERE task_id = ?
            """,
            (
                new_state,
                updated_at or "",
                reason_code,
                reason,
                json.dumps(payload or {}, default=str),
                json.dumps(error, default=str) if error is not None else None,
                task_id,
            ),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Store.update_workflow_task_state: task {task_id!r} not found")
        self.conn.commit()
        row = self.get_workflow_task(task_id)
        if row is None:  # pragma: no cover - defensive
            raise ValueError(
                f"Store.update_workflow_task_state: task {task_id!r} vanished after update"
            )
        return row

    def get_workflow_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM workflow_tasks WHERE task_id = ?", (task_id,))
        row = cur.fetchone()
        return self._task_row_to_dict(row) if row else None

    def list_workflow_tasks(
        self,
        *,
        state: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        if state and tenant_id:
            cur.execute(
                "SELECT * FROM workflow_tasks WHERE state = ? AND tenant_id = ? ORDER BY created_at DESC LIMIT ?",
                (state, tenant_id, limit),
            )
        elif state:
            cur.execute(
                "SELECT * FROM workflow_tasks WHERE state = ? ORDER BY created_at DESC LIMIT ?",
                (state, limit),
            )
        elif tenant_id:
            cur.execute(
                "SELECT * FROM workflow_tasks WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            )
        else:
            cur.execute("SELECT * FROM workflow_tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        return [self._task_row_to_dict(r) for r in cur.fetchall()]

    # ── governance: audit_events (append-only) ─────────────────────────────

    def append_audit_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Append one ledger row. Duplicate event_id or out-of-chain prev_hash fails."""
        if not event.get("event_id"):
            raise ValueError("Store.append_audit_event: event_id is required")
        if not event.get("record_hash"):
            raise ValueError(
                "Store.append_audit_event: record_hash is required (unsigned events rejected)"
            )
        cur = self.conn.cursor()
        last_hash = self.get_last_audit_hash()
        if event.get("prev_hash", "") != last_hash:
            raise ValueError(
                f"Store.append_audit_event: prev_hash {event.get('prev_hash')!r} does not match "
                f"chain head {last_hash!r} — ledger fork rejected"
            )
        cur.execute(
            """
            INSERT INTO audit_events (
                event_id, occurred_at, correlation_id, actor_id, actor_role_id,
                event_type, decision, reason_code, reason, task_id, workflow_id,
                from_state, to_state, payload, prev_hash, record_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event["event_id"],
                event.get("occurred_at", ""),
                event.get("correlation_id", ""),
                event.get("actor_id", ""),
                event.get("actor_role_id", ""),
                event.get("event_type", ""),
                event.get("decision", ""),
                event.get("reason_code"),
                event.get("reason"),
                event.get("task_id"),
                event.get("workflow_id"),
                event.get("from_state"),
                event.get("to_state"),
                json.dumps(event.get("payload") or {}, default=str),
                event.get("prev_hash", ""),
                event["record_hash"],
            ),
        )
        self.conn.commit()
        return event

    def get_last_audit_hash(self) -> str:
        """Head of the audit hash chain ('' for an empty ledger)."""
        cur = self.conn.cursor()
        cur.execute("SELECT record_hash FROM audit_events ORDER BY rowid DESC LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else ""

    def list_audit_events(
        self,
        *,
        task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        if task_id:
            cur.execute(
                "SELECT * FROM audit_events WHERE task_id = ? ORDER BY rowid ASC LIMIT ?",
                (task_id, limit),
            )
        elif correlation_id:
            cur.execute(
                "SELECT * FROM audit_events WHERE correlation_id = ? ORDER BY rowid ASC LIMIT ?",
                (correlation_id, limit),
            )
        else:
            cur.execute("SELECT * FROM audit_events ORDER BY rowid ASC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        out: List[Dict[str, Any]] = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["payload"] = json.loads(d.get("payload") or "{}")
            out.append(d)
        return out

    def verify_audit_chain(self) -> bool:
        """Re-walk the ledger and confirm every link still hashes to its stored value."""
        import hashlib as _hashlib

        events = self.list_audit_events(limit=100000)
        prev = ""
        for ev in events:
            if ev.get("prev_hash", "") != prev:
                return False
            signing = {
                k: ev.get(k)
                for k in (
                    "event_id",
                    "occurred_at",
                    "correlation_id",
                    "actor_id",
                    "actor_role_id",
                    "event_type",
                    "decision",
                    "reason_code",
                    "reason",
                    "task_id",
                    "workflow_id",
                    "from_state",
                    "to_state",
                    "payload",
                    "prev_hash",
                )
            }
            canonical = json.dumps(
                signing, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
            )
            if _hashlib.sha256(canonical.encode("utf-8")).hexdigest() != ev.get("record_hash"):
                return False
            prev = ev.get("record_hash", "")
        return True

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _require_task_columns(task: Dict[str, Any], required: set) -> None:
        if not isinstance(task, dict):
            raise ValueError(f"Store: task must be dict, got {type(task).__name__}")
        missing = [c for c in required if not task.get(c)]
        if missing:
            raise ValueError(f"Store: task missing required columns {sorted(missing)}")

    @staticmethod
    def _task_row_to_dict(row: Any) -> Dict[str, Any]:
        d = {k: row[k] for k in row.keys()}
        d["payload"] = json.loads(d.get("payload") or "{}")
        if d.get("error"):
            d["error"] = json.loads(d["error"])
        return d
