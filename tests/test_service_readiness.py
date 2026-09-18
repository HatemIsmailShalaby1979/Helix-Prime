"""
Service readiness tests for the core FastAPI spine.

``/healthz`` is liveness-only and never touches storage. ``/readyz`` fails
closed: a missing, unreadable, or chain-broken audit store answers 503, and
the response names the failed check without exposing paths or internals.

The missing-store test doubles as the can-fail proof for this file: it
asserts the probe leaves the store absent. A probe that recreated the store
would mask runtime loss and this test would fail.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient


@pytest.fixture()
def client(tmp_path):
    from server.app import create_app
    from server.config import Settings

    settings = Settings(
        profile="local",
        db_path=str(tmp_path / "workflow.db"),
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _append_records(db_path: str, count: int = 2) -> None:
    from security.audit import AuditRecord, AuditTrail

    trail = AuditTrail(db_path=db_path)
    try:
        prev = trail.last_hash()
        for _ in range(count):
            rec = AuditRecord.new(
                event_type="readiness-probe",
                actor="readiness-test",
                actor_type="service",
                decision="succeeded",
                previous_hash=prev,
            )
            trail.append(rec)
            prev = rec.current_hash
    finally:
        trail.close()


def _tamper_first_record(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT audit_id, data FROM audit ORDER BY rowid LIMIT 1").fetchone()
        data = json.loads(row[1])
        data["decision"] = "tampered"
        conn.execute(
            "UPDATE audit SET data = ? WHERE audit_id = ?",
            (json.dumps(data), row[0]),
        )
        conn.commit()
    finally:
        conn.close()


def _remove_audit_store(tmp_path) -> None:
    for name in ("audit.db", "audit.db-wal", "audit.db-shm"):
        path = tmp_path / name
        if path.exists():
            path.unlink()


def test_empty_initialized_audit_store_is_ready(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["checks"]["workflow_store"] is True
    assert body["checks"]["audit_chain"] is True


def test_valid_audit_chain_is_ready(client, tmp_path):
    _append_records(str(tmp_path / "audit.db"))
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_missing_audit_database_is_not_ready(client, tmp_path):
    _remove_audit_store(tmp_path)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["checks"]["audit_chain"] is False
    assert body["detail"] == "audit store missing"
    assert not (tmp_path / "audit.db").exists()


def test_unreadable_audit_database_is_not_ready(client, tmp_path):
    (tmp_path / "audit.db").write_bytes(b"not a sqlite database")
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["checks"]["audit_chain"] is False
    assert body["detail"] == "audit store unreadable"


def test_broken_audit_chain_is_not_ready(client, tmp_path):
    _append_records(str(tmp_path / "audit.db"))
    _tamper_first_record(str(tmp_path / "audit.db"))
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["checks"]["audit_chain"] is False
    assert body["detail"] == "audit chain invalid"


def test_liveness_stays_healthy_when_readiness_fails(client, tmp_path):
    _remove_audit_store(tmp_path)
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503


def test_readiness_failure_hides_filesystem_internals(client, tmp_path):
    _remove_audit_store(tmp_path)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert str(tmp_path) not in resp.text
    assert resp.json()["checks"]["audit_chain"] is False
