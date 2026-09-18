"""Helix Codex App baseline schema, reproduced verbatim from helix_codex_app/db.py.

Revision ID: 0001_codex_app_baseline
Revises:
Create Date: 2026-09-14

This migration reproduces the schema that helix_codex_app/db.py applies via
_init_schema(), using raw op.execute DDL in the parent style. A database
created by db.py and a database created by ``alembic upgrade head`` have
identical sqlite_master contents modulo indentation, so an existing app
database can be stamped to head as a no-op. CI enforces agreement in both
directions via helix_codex_app/scripts/check_app_migration_drift.py.
"""
from __future__ import annotations

from alembic import op

revision = "0001_codex_app_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
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
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS domains (
        domain_id TEXT PRIMARY KEY,
        name TEXT UNIQUE,
        tenant_id TEXT NOT NULL,
        client_id TEXT,
        status TEXT,
        created_at TEXT
    )
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS account_capabilities (
        account_id TEXT,
        capability_key TEXT,
        enabled INTEGER,
        granted_by TEXT,
        granted_at TEXT,
        PRIMARY KEY(account_id, capability_key)
    )
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS account_limits (
        account_id TEXT,
        limit_key TEXT,
        limit_value INTEGER,
        window TEXT,
        PRIMARY KEY(account_id, limit_key)
    )
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS login_throttle (
        bucket TEXT PRIMARY KEY,
        attempts INTEGER,
        window_start TEXT
    )
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS conversation_members (
        conversation_id TEXT,
        account_id TEXT,
        member_role TEXT,
        joined_at TEXT,
        last_read_at TEXT,
        PRIMARY KEY(conversation_id, account_id)
    )
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS document_versions (
        version_id TEXT PRIMARY KEY,
        document_id TEXT,
        version_no INTEGER,
        snapshot TEXT,
        created_by TEXT,
        created_at TEXT
    )
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS task_comments (
        comment_id TEXT PRIMARY KEY,
        task_id TEXT,
        account_id TEXT,
        body TEXT,
        created_at TEXT
    )
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS event_attendees (
        event_id TEXT,
        account_id TEXT,
        response TEXT,
        PRIMARY KEY(event_id, account_id)
    )
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS promotions (
        promotion_id TEXT PRIMARY KEY,
        source_store_id TEXT,
        org_store_id TEXT,
        source_proposal_id TEXT,
        state TEXT,
        approved_by TEXT,
        created_at TEXT,
        updated_at TEXT,
        org_proposal_id TEXT
    )
    
    """
    )

    op.execute(
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
    
    """
    )

    op.execute(
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
    
    """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS capability_packs")
    op.execute("DROP TABLE IF EXISTS sections")
    op.execute("DROP TABLE IF EXISTS promotions")
    op.execute("DROP TABLE IF EXISTS proposal_reviews")
    op.execute("DROP TABLE IF EXISTS proposals")
    op.execute("DROP TABLE IF EXISTS memory_stores")
    op.execute("DROP TABLE IF EXISTS files")
    op.execute("DROP TABLE IF EXISTS punch_records")
    op.execute("DROP TABLE IF EXISTS notifications")
    op.execute("DROP TABLE IF EXISTS oncall_shifts")
    op.execute("DROP TABLE IF EXISTS event_attendees")
    op.execute("DROP TABLE IF EXISTS events")
    op.execute("DROP TABLE IF EXISTS task_comments")
    op.execute("DROP TABLE IF EXISTS tasks")
    op.execute("DROP TABLE IF EXISTS document_versions")
    op.execute("DROP TABLE IF EXISTS doc_blocks")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversation_members")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP TABLE IF EXISTS login_events")
    op.execute("DROP TABLE IF EXISTS login_throttle")
    op.execute("DROP TABLE IF EXISTS account_limits")
    op.execute("DROP TABLE IF EXISTS account_capabilities")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS accounts")
    op.execute("DROP TABLE IF EXISTS org_units")
    op.execute("DROP TABLE IF EXISTS domains")
    op.execute("DROP TABLE IF EXISTS nodes")
