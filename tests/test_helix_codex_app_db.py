"""Tests for helix_codex_app/db.py: the app database and the single node writer.

The node envelope is validated inside record_node, so every test here asserts
that a skipped or bad field raises ValueError. Fail closed, never silently.
"""
from __future__ import annotations

import pytest

from helix_codex_app import db

VALID_ENVELOPE = dict(
    tenant_id="tenant-academy-1",
    correlation_id="corr-p1-001",
    classification="internal",
    nature="verified_fact",
    created_by="account-owner-1",
    provenance_source="app",
    provenance_data_mode="simulated_realistic",
    kind="decision",
)


def _store(tmp_path):
    conn = db.connect(db_path=str(tmp_path / "app.db"))
    db._init_schema(conn)
    return conn


def test_schema_creates_every_planned_table(tmp_path):
    conn = _store(tmp_path)
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        db.close(conn)
    assert {
        "nodes",
        "domains",
        "org_units",
        "accounts",
        "sessions",
        "account_capabilities",
        "account_limits",
        "login_events",
        "conversations",
        "conversation_members",
        "messages",
        "documents",
        "doc_blocks",
        "document_versions",
        "tasks",
        "task_comments",
        "events",
        "event_attendees",
        "oncall_shifts",
        "notifications",
        "punch_records",
        "files",
        "memory_stores",
        "proposals",
        "proposal_reviews",
        "promotions",
        "sections",
        "capability_packs",
    } <= tables


def test_record_node_rejects_blank_tenant_id(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["tenant_id"] = "   "
        with pytest.raises(ValueError, match="tenant_id"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_blank_correlation_id(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["correlation_id"] = ""
        with pytest.raises(ValueError, match="correlation_id"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_unknown_classification(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["classification"] = "top_secret_paranoia"
        with pytest.raises(ValueError, match="classification"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_missing_nature(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["nature"] = ""
        with pytest.raises(ValueError, match="nature"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_missing_provenance_data_mode(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["provenance_data_mode"] = ""
        with pytest.raises(ValueError, match="data_mode"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_blank_created_by(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["created_by"] = "   "
        with pytest.raises(ValueError, match="created_by"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_writes_the_full_envelope(tmp_path):
    conn = _store(tmp_path)
    try:
        node_id = db.record_node(conn, **VALID_ENVELOPE)
        rows = conn.execute(
            "SELECT node_id, tenant_id, correlation_id, classification, nature,"
            " kind, created_by, provenance_source, provenance_data_mode,"
            " provenance_retrieved_at FROM nodes WHERE node_id = ?",
            (node_id,),
        ).fetchall()
    finally:
        db.close(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["node_id"] == node_id
    assert row["tenant_id"] == "tenant-academy-1"
    assert row["correlation_id"] == "corr-p1-001"
    assert row["classification"] == "internal"
    assert row["nature"] == "verified_fact"
    assert row["kind"] == "decision"
    assert row["created_by"] == "account-owner-1"
    assert row["provenance_source"] == "app"
    assert row["provenance_data_mode"] == "simulated_realistic"
