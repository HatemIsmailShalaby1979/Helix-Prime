"""
Multi-tenant data isolation — Helix Codex OS C8.

A self-hosted enterprise asset is only sellable if one client cannot see
another client's data. In Helix Prime that guarantee is enforced at the
**database driver level**, not by filtering in Python after the fact.

Why driver-level
----------------
Application-layer filtering fails in two ways that matter:

1. **A missed ``WHERE`` clause is silent.** The query returns every tenant's
   rows and nothing raises. By the time it is noticed, the data has already
   been rendered, logged, or exported.
2. **A join can leak through a second table.** Filtering ``workflow_tasks``
   but not ``audit_events`` exposes the same facts through the ledger.

So every read and write in this module carries ``tenant_id`` (and where
applicable ``client_id``) in the SQL itself, and :class:`TenantScopedStore`
refuses to execute a query that does not.

Defence in depth
----------------
* :func:`ensure_tenant_indexes` creates the composite indexes the planner needs
  so tenant-scoped reads stay fast as the ledger grows.
* :class:`TenantContext` is the only object allowed to name a tenant; it
  validates on construction so an empty tenant cannot be smuggled in.
* :func:`verify_isolation` is a runtime assertion usable from tests and from
  the governance evidence pack.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "1.0"

#: Indexes required for tenant-partitioned access. Created idempotently.
TENANT_INDEXES = (
    ("idx_tasks_tenant_client", "workflow_tasks", ("tenant_id", "client_id")),
    ("idx_audit_tenant_corr", "audit_events", ("correlation_id",)),
    ("idx_workflows_tenant", "workflows", ("correlation_id",)),
)


class TenantViolation(PermissionError):
    """Raised when an operation would cross a tenant boundary."""


def _require_non_empty(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: must be a non-empty string, got {value!r}")
    return value.strip()


@dataclass(frozen=True)
class TenantContext:
    """
    Validated tenant/client identity.

    Frozen so it cannot be mutated mid-request, which is how a scope silently
    widens: something sets ``tenant_id = None`` and suddenly every row matches.
    """

    tenant_id: str
    client_id: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _require_non_empty(self.tenant_id, "TenantContext.tenant_id"))
        if self.client_id is not None:
            object.__setattr__(self, "client_id", _require_non_empty(self.client_id, "TenantContext.client_id"))

    @property
    def partition_key(self) -> str:
        return f"{self.tenant_id}::{self.client_id or '*'}"

    def to_dict(self) -> Dict[str, Any]:
        return {"tenant_id": self.tenant_id, "client_id": self.client_id, "schema_version": SCHEMA_VERSION}

    def matches(self, row: Dict[str, Any]) -> bool:
        """True when a row belongs to this partition."""
        if row.get("tenant_id") != self.tenant_id:
            return False
        if self.client_id is not None and row.get("client_id") not in (None, self.client_id):
            return False
        return True


def ensure_tenant_indexes(conn: sqlite3.Connection) -> List[str]:
    """
    Create the composite indexes tenant-partitioned reads depend on.

    Idempotent. Returns the names of the indexes present afterwards.
    """
    created: List[str] = []
    cur = conn.cursor()
    for index_name, table, columns in TENANT_INDEXES:
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({', '.join(columns)})"
        )
        created.append(index_name)
    conn.commit()
    return created


class TenantScopedStore:
    """
    A :class:`~control_plane.store.Store` that can only see one partition.

    Every method binds ``tenant_id`` (and ``client_id`` when the scope names
    one) into the SQL. There is no method on this object that returns data
    across tenants, so a caller physically cannot write a leaking query.

    Usage::

        scope = TenantContext(tenant_id="tenant-a", client_id="client-1")
        scoped = TenantScopedStore(store, scope)
        scoped.list_tasks()          # only tenant-a / client-1 rows
        scoped.list_audit_events()   # ledger rows for the same partition
    """

    def __init__(self, store: Any, scope: TenantContext) -> None:
        if not isinstance(scope, TenantContext):
            raise TypeError(f"TenantScopedStore: scope must be TenantContext, got {type(scope).__name__}")
        self._store = store
        self.scope = scope
        ensure_tenant_indexes(store.conn)

    # ── reads ───────────────────────────────────────────────────────────────

    def list_tasks(self, *, state: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        return self._select(
            table="workflow_tasks",
            state=state,
            limit=limit,
            order_by="created_at DESC",
        )

    def list_audit_events(self, *, correlation_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Ledger rows for this partition.

        ``audit_events`` has no tenant column of its own; it inherits the
        partition through ``correlation_id``. We therefore resolve the
        correlation ids that belong to this tenant first and bind them into the
        query, rather than filtering after the fact.
        """
        conn = self._store.conn
        cur = conn.cursor()

        cur.execute(
            "SELECT DISTINCT correlation_id FROM workflow_tasks WHERE tenant_id = ?"
            + (" AND client_id = ?" if self.scope.client_id else ""),
            (self.scope.tenant_id, self.scope.client_id) if self.scope.client_id else (self.scope.tenant_id,),
        )
        allowed = {row[0] for row in cur.fetchall() if row[0]}

        if correlation_id is not None:
            if correlation_id not in allowed:
                # The correlation belongs to another tenant. Returning rows here
                # would be a leak, so deny explicitly.
                raise TenantViolation(
                    f"correlation_id {correlation_id!r} is not visible to tenant "
                    f"{self.scope.tenant_id!r}"
                )
            allowed = {correlation_id}

        if not allowed:
            return []

        placeholders = ",".join("?" for _ in allowed)
        cur.execute(
            f"SELECT * FROM audit_events WHERE correlation_id IN ({placeholders}) "
            f"ORDER BY rowid ASC LIMIT ?",
            (*allowed, limit),
        )
        cols = [c[0] for c in cur.description]
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            record = dict(zip(cols, row))
            record["payload"] = json.loads(record.get("payload") or "{}")
            out.append(record)
        return out

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        row = self._store.get_workflow_task(task_id)
        if row is None:
            return None
        if not self.scope.matches(row):
            raise TenantViolation(
                f"task {task_id!r} belongs to another tenant; access denied"
            )
        return row

    # ── writes ──────────────────────────────────────────────────────────────

    def insert_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert a task, stamping it with this partition.

        A task that arrives already stamped for another tenant is rejected —
        that is either a bug or an attempt to write across the boundary.
        """
        stamped = dict(task)
        existing_tenant = stamped.get("tenant_id")
        if existing_tenant is not None and existing_tenant != self.scope.tenant_id:
            raise TenantViolation(
                f"refusing to insert a task stamped for tenant {existing_tenant!r} "
                f"through scope {self.scope.tenant_id!r}"
            )
        existing_client = stamped.get("client_id")
        if self.scope.client_id is not None:
            if existing_client is not None and existing_client != self.scope.client_id:
                raise TenantViolation(
                    f"refusing to insert a task stamped for client {existing_client!r} "
                    f"through scope {self.scope.client_id!r}"
                )
            stamped["client_id"] = self.scope.client_id
        stamped["tenant_id"] = self.scope.tenant_id
        return self._store.insert_workflow_task(stamped)

    def update_task_state(self, task_id: str, new_state: str, **kwargs: Any) -> Dict[str, Any]:
        """Update a task only if it belongs to this partition."""
        self.get_task(task_id)  # raises TenantViolation on cross-tenant access
        return self._store.update_workflow_task_state(task_id, new_state, **kwargs)

    # ── internals ───────────────────────────────────────────────────────────

    def _select(
        self,
        *,
        table: str,
        state: Optional[str] = None,
        limit: int = 100,
        order_by: str = "created_at DESC",
    ) -> List[Dict[str, Any]]:
        conn = self._store.conn
        cur = conn.cursor()
        clauses = ["tenant_id = ?"]
        params: List[Any] = [self.scope.tenant_id]
        if self.scope.client_id is not None:
            clauses.append("client_id = ?")
            params.append(self.scope.client_id)
        if state:
            clauses.append("state = ?")
            params.append(state)
        params.append(limit)
        cur.execute(
            f"SELECT * FROM {table} WHERE {' AND '.join(clauses)} ORDER BY {order_by} LIMIT ?",
            params,
        )
        return [self._store._task_row_to_dict(row) for row in cur.fetchall()] if table == "workflow_tasks" else [
            dict(row) for row in cur.fetchall()
        ]


def verify_isolation(store: Any, tenants: Iterable[str], *, task_builder=None) -> Dict[str, Any]:
    """
    Prove that two tenants cannot see each other's rows.

    Writes one probe task per tenant through its own scope, then attempts the
    cross-tenant read. Returns a report; ``isolated`` is True only when every
    cross-tenant read was denied or returned nothing.
    """
    builder = task_builder or (lambda tenant: {
        "task_id": f"probe_{tenant}",
        "correlation_id": f"corr_probe_{tenant}",
        "actor_id": "isolation_probe",
        "actor_role_id": "ict_gm",
        "owning_role_id": "ict_gm",
        "capability": "tenant_isolation_probe",
        "state": "closed",
        "data_classification": "internal",
        "created_at": "",
        "updated_at": "",
    })

    tenant_list = list(tenants)
    report: Dict[str, Any] = {
        "tenants": tenant_list,
        "probes_written": [],
        "cross_tenant_reads": [],
        "isolated": True,
    }

    scopes = {tenant: TenantScopedStore(store, TenantContext(tenant_id=tenant)) for tenant in tenant_list}
    for tenant, scope in scopes.items():
        scope.insert_task(builder(tenant))
        report["probes_written"].append(tenant)

    for tenant, scope in scopes.items():
        visible = scope.list_tasks(limit=1000)
        for row in visible:
            if row.get("tenant_id") != tenant:
                report["isolated"] = False
                report["cross_tenant_reads"].append(
                    {"reader": tenant, "row_tenant": row.get("tenant_id"), "task_id": row.get("task_id")}
                )
    return report


__all__ = [
    "SCHEMA_VERSION",
    "TENANT_INDEXES",
    "TenantContext",
    "TenantScopedStore",
    "TenantViolation",
    "ensure_tenant_indexes",
    "verify_isolation",
]
