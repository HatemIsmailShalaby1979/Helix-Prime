"""Control-plane baseline schema, reproduced verbatim from control_plane/store.py.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-12

This migration reproduces the schema that control_plane/store.py applies via
_init_schema() + _init_governance_schema() — the same statements in the same
order — so a database created by Store and a database created by
``alembic upgrade head`` have identical sqlite_master contents modulo
indentation, and an existing Store database can be stamped to head as a no-op.
CI enforces agreement in both directions via scripts/check_migration_drift.py.
"""
from __future__ import annotations

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
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
    op.execute(
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_agg_seq ON events(aggregate_id, sequence)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_workflows_corr ON workflows(correlation_id)")

    op.execute(
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_state ON workflow_tasks(state)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_corr ON workflow_tasks(correlation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_role ON workflow_tasks(actor_role_id)")

    op.execute(
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_corr ON audit_events(correlation_id)")

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_update
        BEFORE UPDATE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit_events is append-only: UPDATE forbidden');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_delete
        BEFORE DELETE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit_events is append-only: DELETE forbidden');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update")
    op.execute("DROP INDEX IF EXISTS idx_audit_corr")
    op.execute("DROP INDEX IF EXISTS idx_audit_task")
    op.execute("DROP TABLE IF EXISTS audit_events")
    op.execute("DROP INDEX IF EXISTS idx_tasks_role")
    op.execute("DROP INDEX IF EXISTS idx_tasks_corr")
    op.execute("DROP INDEX IF EXISTS idx_tasks_state")
    op.execute("DROP TABLE IF EXISTS workflow_tasks")
    op.execute("DROP INDEX IF EXISTS idx_workflows_corr")
    op.execute("DROP INDEX IF EXISTS idx_events_agg_seq")
    op.execute("DROP TABLE IF EXISTS events")
    op.execute("DROP TABLE IF EXISTS workflows")
