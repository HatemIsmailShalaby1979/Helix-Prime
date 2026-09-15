"""The app database: connection factory, schema bootstrap, and the single writer.

The app owns one SQLite file at settings.db_path, separate from the parent
workflow, audit, and nodes databases. db.py creates the tables the master plan
defines (sections 5.2 and 7) and record_node() is the only function that may
insert into the nodes table. Raw sqlite3 and raw DDL, matching the parent
style. There is no ORM.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from helix_codex_app.config import get_app_settings

CLASSIFICATIONS = frozenset({"public", "internal", "client_confidential", "restricted"})

_SCHEMA_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS nodes (
        node_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        client_id TEXT,
        domain_id TEXT,
        correlation_id TEXT NOT NULL,
        causation_id TEXT,
        classification TEXT NOT NULL,
        nature TEXT NOT NULL,
        kind TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        body TEXT,
        provenance_source TEXT,
        provenance_data_mode TEXT,
        provenance_retrieved_at TEXT,
        parent_node_id TEXT,
        thread_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS domains (
        domain_id TEXT PRIMARY KEY,
        name TEXT UNIQUE,
        tenant_id TEXT NOT NULL,
        client_id TEXT,
        status TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS org_units (
        unit_id TEXT PRIMARY KEY,
        domain_id TEXT,
        parent_unit_id TEXT,
        name TEXT,
        kind TEXT,
        path TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        account_id TEXT PRIMARY KEY,
        domain_id TEXT,
        username TEXT,
        username_normalized TEXT,
        display_name TEXT,
        email TEXT,
        password_hash TEXT,
        password_algo TEXT,
        password_params TEXT,
        role_id TEXT,
        org_unit_id TEXT,
        actor_type TEXT,
        status TEXT,
        must_change_password INTEGER,
        failed_attempts INTEGER,
        locked_until TEXT,
        created_at TEXT,
        updated_at TEXT,
        last_login_at TEXT,
        UNIQUE(domain_id, username_normalized)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        account_id TEXT,
        token_hash TEXT UNIQUE,
        csrf_token TEXT,
        issued_at TEXT,
        expires_at TEXT,
        last_seen_at TEXT,
        ip TEXT,
        user_agent TEXT,
        revoked_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_capabilities (
        account_id TEXT,
        capability_key TEXT,
        enabled INTEGER,
        granted_by TEXT,
        granted_at TEXT,
        PRIMARY KEY(account_id, capability_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_limits (
        account_id TEXT,
        limit_key TEXT,
        limit_value INTEGER,
        window TEXT,
        PRIMARY KEY(account_id, limit_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS login_events (
        event_id TEXT PRIMARY KEY,
        account_id TEXT,
        domain_id TEXT,
        outcome TEXT,
        reason TEXT,
        ip TEXT,
        user_agent TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversations (
        conversation_id TEXT PRIMARY KEY,
        tenant_id TEXT,
        domain_id TEXT,
        kind TEXT,
        title TEXT,
        classification TEXT,
        created_by TEXT,
        created_at TEXT,
        correlation_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_members (
        conversation_id TEXT,
        account_id TEXT,
        member_role TEXT,
        joined_at TEXT,
        last_read_at TEXT,
        PRIMARY KEY(conversation_id, account_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT PRIMARY KEY,
        conversation_id TEXT,
        sender_account_id TEXT,
        body TEXT,
        classification TEXT,
        created_at TEXT,
        edited_at TEXT,
        deleted_at TEXT,
        node_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        tenant_id TEXT,
        domain_id TEXT,
        title TEXT,
        doc_type TEXT,
        owner_account_id TEXT,
        classification TEXT,
        status TEXT,
        current_version INTEGER,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS doc_blocks (
        block_id TEXT PRIMARY KEY,
        document_id TEXT,
        ordinal INTEGER,
        block_type TEXT,
        content TEXT,
        updated_by TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS document_versions (
        version_id TEXT PRIMARY KEY,
        document_id TEXT,
        version_no INTEGER,
        snapshot TEXT,
        created_by TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        tenant_id TEXT,
        domain_id TEXT,
        title TEXT,
        description TEXT,
        status TEXT,
        priority TEXT,
        assignee_account_id TEXT,
        creator_account_id TEXT,
        due_at TEXT,
        completed_at TEXT,
        parent_task_id TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_comments (
        comment_id TEXT PRIMARY KEY,
        task_id TEXT,
        account_id TEXT,
        body TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        tenant_id TEXT,
        domain_id TEXT,
        title TEXT,
        kind TEXT,
        starts_at TEXT,
        ends_at TEXT,
        all_day INTEGER,
        location TEXT,
        room_id TEXT,
        creator_account_id TEXT,
        recurrence_rule TEXT,
        created_at TEXT,
        updated_at TEXT,
        status TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS event_attendees (
        event_id TEXT,
        account_id TEXT,
        response TEXT,
        PRIMARY KEY(event_id, account_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS oncall_shifts (
        shift_id TEXT PRIMARY KEY,
        tenant_id TEXT,
        domain_id TEXT,
        roster TEXT,
        starts_at TEXT,
        ends_at TEXT,
        primary_account_id TEXT,
        backup_account_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        notification_id TEXT PRIMARY KEY,
        account_id TEXT,
        kind TEXT,
        title TEXT,
        body TEXT,
        link TEXT,
        read_at TEXT,
        created_at TEXT,
        correlation_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS punch_records (
        punch_id TEXT PRIMARY KEY,
        account_id TEXT,
        domain_id TEXT,
        tenant_id TEXT,
        punch_type TEXT,
        punched_at TEXT,
        source TEXT,
        geo TEXT,
        note TEXT,
        device_id TEXT,
        correlation_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS files (
        file_id TEXT PRIMARY KEY,
        tenant_id TEXT,
        domain_id TEXT,
        owner_account_id TEXT,
        filename TEXT,
        content_type TEXT,
        size_bytes INTEGER,
        sha256 TEXT,
        storage_path TEXT,
        classification TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_stores (
        store_id TEXT PRIMARY KEY,
        tenant_id TEXT,
        account_id TEXT,
        kind TEXT,
        path TEXT,
        record_count INTEGER,
        chain_head TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS proposals (
        proposal_id TEXT PRIMARY KEY,
        store_id TEXT,
        tenant_id TEXT,
        domain_id TEXT,
        kind TEXT,
        target TEXT,
        state TEXT,
        version INTEGER,
        created_by TEXT,
        role_id TEXT,
        correlation_id TEXT,
        classification TEXT,
        data_mode TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS proposal_reviews (
        review_id TEXT PRIMARY KEY,
        proposal_id TEXT,
        reviewer_account_id TEXT,
        reviewer_role TEXT,
        decision TEXT,
        reason TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS promotions (
        promotion_id TEXT PRIMARY KEY,
        source_store_id TEXT,
        org_store_id TEXT,
        source_proposal_id TEXT,
        state TEXT,
        approved_by TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sections (
        section_id TEXT PRIMARY KEY,
        domain_id TEXT,
        key TEXT,
        label TEXT,
        icon TEXT,
        route TEXT,
        position INTEGER,
        required_capability TEXT,
        enabled INTEGER,
        source_pack TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capability_packs (
        pack_id TEXT PRIMARY KEY,
        name TEXT,
        version TEXT,
        domain TEXT,
        production_readiness TEXT,
        min_core_version TEXT,
        manifest_path TEXT,
        enabled INTEGER,
        registered_at TEXT
    )
    """,
)


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a connection to the app database with the app's pragmas.

    The path defaults to settings.db_path. Row factory, foreign keys, and WAL
    mode are set here, once, so every caller gets the same behaviour.
    """
    path = db_path or get_app_settings().db_path
    parent = pathlib.Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create every table the master plan sections 5.2 and 7 define.

    Each statement is idempotent, so a pre-existing database is left untouched.
    """
    for ddl in _SCHEMA_DDL:
        conn.execute(ddl)
    conn.commit()


def close(conn: sqlite3.Connection) -> None:
    """Close the handle. Tests call this so Windows releases the file."""
    conn.close()


def record_node(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    correlation_id: str,
    classification: str,
    nature: str,
    created_by: str,
    provenance_source: str,
    provenance_data_mode: str,
    kind: str,
    node_id: str | None = None,
    client_id: str | None = None,
    domain_id: str | None = None,
    causation_id: str | None = None,
    body: dict[str, Any] | None = None,
    provenance_retrieved_at: str | None = None,
    parent_node_id: str | None = None,
    thread_id: str | None = None,
    created_at: str | None = None,
) -> str:
    """Append one node row and return its node_id.

    This is the single writer for the nodes table. The envelope is validated
    here and only here: a blank tenant_id, a blank correlation_id, an unknown
    classification, a missing nature, a missing provenance data_mode, and a
    blank created_by all raise ValueError. A caller cannot skip the envelope.
    """
    if not tenant_id or not tenant_id.strip():
        raise ValueError("record_node: tenant_id must not be blank")
    if not correlation_id or not correlation_id.strip():
        raise ValueError("record_node: correlation_id must not be blank")
    if classification not in CLASSIFICATIONS:
        raise ValueError(
            "record_node: unknown classification "
            f"{classification!r}; expected one of {sorted(CLASSIFICATIONS)}"
        )
    if not nature or not nature.strip():
        raise ValueError("record_node: nature must not be blank")
    if not provenance_data_mode or not provenance_data_mode.strip():
        raise ValueError("record_node: provenance data_mode must not be blank")
    if not created_by or not created_by.strip():
        raise ValueError("record_node: created_by must not be blank")
    if not kind or not kind.strip():
        raise ValueError("record_node: kind must not be blank")

    resolved_node_id = node_id or f"node-{uuid.uuid4().hex}"
    resolved_created_at = created_at or datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO nodes (
            node_id, tenant_id, client_id, domain_id, correlation_id, causation_id,
            classification, nature, kind, created_by, created_at, body,
            provenance_source, provenance_data_mode, provenance_retrieved_at,
            parent_node_id, thread_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resolved_node_id,
            tenant_id,
            client_id,
            domain_id,
            correlation_id,
            causation_id,
            classification,
            nature,
            kind,
            created_by,
            resolved_created_at,
            json.dumps(body) if body is not None else None,
            provenance_source,
            provenance_data_mode,
            provenance_retrieved_at,
            parent_node_id,
            thread_id,
        ),
    )
    conn.commit()
    return resolved_node_id


def store_id_for(*, path: str) -> str:
    """The stable id for one governed memory store.

    Keyed on the resolved path, which is derived from the server-generated
    domain id. Two domains can therefore never collide on one index row, and
    registering the same store twice updates that row instead of adding one.
    """
    return f"store::{path}"


def register_store(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    account_id: str | None,
    kind: str,
    path: str,
) -> str:
    """Record a memory store in the index, creating the row or refreshing it.

    kind is "account" for a person's own store and "org" for the tenant's
    shared store. The record count and chain head start empty and are kept
    current by touch_store().
    """
    if not tenant_id or not tenant_id.strip():
        raise ValueError("register_store: tenant_id must not be blank")
    if not path or not path.strip():
        raise ValueError("register_store: path must not be blank")
    store_id = store_id_for(path=path)
    conn.execute(
        """
        INSERT INTO memory_stores (
            store_id, tenant_id, account_id, kind, path, record_count, chain_head, updated_at
        ) VALUES (?, ?, ?, ?, ?, 0, NULL, ?)
        ON CONFLICT(store_id) DO UPDATE SET
            kind = excluded.kind,
            path = excluded.path,
            updated_at = excluded.updated_at
        """,
        (
            store_id,
            tenant_id,
            account_id,
            kind,
            path,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return store_id


def touch_store(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    record_count: int,
    chain_head: str | None,
) -> None:
    """Refresh a store's record count and chain head after a write."""
    conn.execute(
        """
        UPDATE memory_stores
           SET record_count = ?, chain_head = ?, updated_at = ?
         WHERE store_id = ?
        """,
        (int(record_count), chain_head, datetime.now(timezone.utc).isoformat(), store_id),
    )
    conn.commit()


def list_stores(conn: sqlite3.Connection, tenant_id: str) -> list[sqlite3.Row]:
    """Every memory store registered for one tenant. A blank tenant is rejected."""
    if not tenant_id or not tenant_id.strip():
        raise ValueError("list_stores: tenant_id is required")
    return list(
        conn.execute(
            "SELECT * FROM memory_stores WHERE tenant_id = ? ORDER BY store_id",
            (tenant_id,),
        ).fetchall()
    )


def get_store(conn: sqlite3.Connection, store_id: str) -> sqlite3.Row | None:
    """One store index row, or None."""
    return conn.execute("SELECT * FROM memory_stores WHERE store_id = ?", (store_id,)).fetchone()
