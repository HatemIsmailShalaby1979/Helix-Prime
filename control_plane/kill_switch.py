"""
Emergency stop (kill switch) for the control plane (H1.5, G18).

A platform whose value proposition is provable restraint must be able to halt
itself. This module implements a persisted, fail-closed halt flag honoured by
control_plane.engine.Engine before every committal action (submit, approve,
execute):

* engage(reason, actor) halts the whole platform; engage(..., tenant_id=...)
  halts one tenant only — the platform is multi-tenant by design, so an
  incident in one tenant must not stop the others.
* release(actor, ...) lifts the halt. Releasing a scope that is not halted is
  a no-op that is still audited.
* is_engaged() fails CLOSED: if the flag cannot be read, the platform behaves
  as halted. Deny-and-raise is the only failure mode; this module never
  silently skips.

The flag is a row in the control-plane SQLite store (same database as the
workflows; no new dependency, no Redis). Every engage, release, and halted
denial appends a record to the tamper-evident audit trail — the halt itself
is auditable, and auditing still works while halted because the audit trail
is a separate, append-only path that the halt never gates.

Engine.cancel is deliberately NOT gated: cancelling stops work, it never
starts it, and an operator must always be able to stop in-flight work,
especially while halted.
"""
from __future__ import annotations

import contextlib
import datetime
import sqlite3
from typing import Any, Dict, Optional

from security.audit import AuditRecord, AuditTrail

GLOBAL_SCOPE = "*"
DEFAULT_DB_PATH = "control_plane/workflow.db"
DEFAULT_AUDIT_DB_PATH = "security/audit.db"


class KillSwitchEngaged(RuntimeError):
    """A committal action was refused because the kill switch is engaged."""


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _require_non_empty(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: must be a non-empty string, got {value!r}")
    return value.strip()


def _scope_for(tenant_id: Optional[str]) -> str:
    if tenant_id is None:
        return GLOBAL_SCOPE
    tenant_id = _require_non_empty(tenant_id, "KillSwitch: tenant_id")
    if tenant_id == GLOBAL_SCOPE:
        raise ValueError('KillSwitch: tenant_id "*" is reserved for the global halt')
    return tenant_id


class KillSwitch:
    """Persisted halt flag. Shares the engine's store connection when given one."""

    def __init__(
        self,
        store: Any = None,
        db_path: Optional[str] = None,
        audit_db_path: str = DEFAULT_AUDIT_DB_PATH,
    ) -> None:
        if store is not None and db_path is not None:
            raise ValueError("KillSwitch: pass store or db_path, not both")
        self._store = store
        self._db_path = db_path or getattr(store, "db_path", None) or DEFAULT_DB_PATH
        self.audit_db_path = audit_db_path or DEFAULT_AUDIT_DB_PATH
        if store is not None:
            self._init_schema(store.conn)

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS halt_state (
                scope TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                actor TEXT NOT NULL,
                engaged_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    @contextlib.contextmanager
    def _connection(self):
        if self._store is not None:
            yield self._store.conn
            return
        import pathlib

        pathlib.Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(
            sqlite3.connect(self._db_path, check_same_thread=False, isolation_level=None)
        ) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            self._init_schema(conn)
            yield conn

    def _append_halt_event(
        self,
        event_type: str,
        actor: str,
        decision: str,
        tenant_id: Optional[str],
        detail: Optional[str],
    ) -> None:
        trail = AuditTrail(db_path=self.audit_db_path)
        try:
            prev_hash = trail.last_hash()
            record = AuditRecord.new(
                event_type=event_type,
                actor=actor,
                actor_type="human",
                decision=decision,
                tenant_id=tenant_id,
                input_ref=detail,
                previous_hash=prev_hash,
            )
            try:
                trail.append(record)
            except ValueError:
                prev_hash = trail.last_hash()
                record = AuditRecord.new(
                    event_type=event_type,
                    actor=actor,
                    actor_type="human",
                    decision=decision,
                    tenant_id=tenant_id,
                    input_ref=detail,
                    previous_hash=prev_hash,
                )
                trail.append(record)
        finally:
            trail.close()

    def active_halt(self, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if tenant_id is not None:
            tenant_id = _require_non_empty(tenant_id, "KillSwitch.active_halt: tenant_id")
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT scope, reason, actor, engaged_at FROM halt_state WHERE scope = ?",
                (GLOBAL_SCOPE,),
            )
            row = cur.fetchone()
            if row is not None:
                return {
                    "engaged": True,
                    "scope": "global",
                    "reason": row[1],
                    "actor": row[2],
                    "engaged_at": row[3],
                }
            if tenant_id is not None:
                cur.execute(
                    "SELECT scope, reason, actor, engaged_at FROM halt_state WHERE scope = ?",
                    (tenant_id,),
                )
                row = cur.fetchone()
                if row is not None:
                    return {
                        "engaged": True,
                        "scope": f"tenant:{tenant_id}",
                        "reason": row[1],
                        "actor": row[2],
                        "engaged_at": row[3],
                    }
            return None

    def is_engaged(self, tenant_id: Optional[str] = None) -> bool:
        try:
            return self.active_halt(tenant_id=tenant_id) is not None
        except Exception:
            return True

    def engage(
        self, reason: str, actor: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        reason = _require_non_empty(reason, "KillSwitch.engage: reason")
        actor = _require_non_empty(actor, "KillSwitch.engage: actor")
        scope = _scope_for(tenant_id)
        self._append_halt_event(
            "kill_switch_engaged",
            actor=actor,
            decision="engaged",
            tenant_id=tenant_id,
            detail=reason,
        )
        with self._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO halt_state (scope, reason, actor, engaged_at)"
                " VALUES (?, ?, ?, ?)",
                (scope, reason, actor, _now_iso()),
            )
            conn.commit()
        return self.status(tenant_id=tenant_id)

    def release(self, actor: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        actor = _require_non_empty(actor, "KillSwitch.release: actor")
        scope = _scope_for(tenant_id)
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM halt_state WHERE scope = ?", (scope,))
            was_engaged = cur.rowcount > 0
            conn.commit()
        self._append_halt_event(
            "kill_switch_released",
            actor=actor,
            decision="released",
            tenant_id=tenant_id,
            detail=f"was_engaged={was_engaged}",
        )
        return self.status(tenant_id=tenant_id)

    def status(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT scope, reason, actor, engaged_at FROM halt_state ORDER BY scope"
            ).fetchall()
        halts = [row[0] for row in rows]
        effective = self.active_halt(tenant_id=tenant_id)
        return {
            "engaged": effective is not None,
            "scope": effective["scope"] if effective else "none",
            "reason": effective["reason"] if effective else None,
            "actor": effective["actor"] if effective else None,
            "engaged_at": effective["engaged_at"] if effective else None,
            "tenants": sorted(scope for scope in halts if scope != GLOBAL_SCOPE),
        }


def engage(
    reason: str,
    actor: str,
    tenant_id: Optional[str] = None,
    db_path: Optional[str] = None,
    audit_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    return KillSwitch(
        db_path=db_path or DEFAULT_DB_PATH,
        audit_db_path=audit_db_path or DEFAULT_AUDIT_DB_PATH,
    ).engage(reason, actor, tenant_id=tenant_id)


def release(
    actor: str,
    tenant_id: Optional[str] = None,
    db_path: Optional[str] = None,
    audit_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    return KillSwitch(
        db_path=db_path or DEFAULT_DB_PATH,
        audit_db_path=audit_db_path or DEFAULT_AUDIT_DB_PATH,
    ).release(actor, tenant_id=tenant_id)


def is_engaged(
    tenant_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    return KillSwitch(db_path=db_path or DEFAULT_DB_PATH).is_engaged(tenant_id=tenant_id)


def status(
    tenant_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    return KillSwitch(db_path=db_path or DEFAULT_DB_PATH).status(tenant_id=tenant_id)
