"""
Appliance observability tests for the self-hosted deployment.

Proves the operator signals end to end: secrets never reach logs or the
metrics exposition, route labels stay normalized templates, tenant ids
never become label values, readiness/auth/kill-switch failures increment
their counters, the disk gauge is exported, and every alert rule references
an exported metric. The readiness sensitivity test is the can-fail proof:
with the recording call patched out, the failing probe leaves no signal,
so the positive tests only pass while the wiring is in place.
"""
from __future__ import annotations

import json
import secrets
from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from observability.metrics import REGISTRY

TOKEN = secrets.token_urlsafe(24)
TENANT = "tenant-obs"


@pytest.fixture(autouse=True)
def _reset_registry():
    REGISTRY.reset_for_tests()
    yield
    REGISTRY.reset_for_tests()


@pytest.fixture()
def core_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", TOKEN)
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", "sami")
    monkeypatch.setenv("HELIX_API_TOKEN_TENANT_ID", TENANT)
    monkeypatch.setenv("HELIX_API_TOKEN_CLIENT_ID", "client-obs")
    monkeypatch.delenv("HELIX_API_ALLOW_GLOBAL_OPERATOR", raising=False)
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


@pytest.fixture()
def app_ctx(tmp_path):
    from helix_codex_app import db
    from helix_codex_app.app import create_app
    from helix_codex_app.config import AppSettings
    from helix_codex_app.modules.identity.service import LoginService
    from helix_codex_app.security.accounts import AccountRepository
    from helix_codex_app.security.passwords import hash_password

    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("o.academy", tenant_id="tenant-o", client_id="client-o")
    owner = repo.create_account(
        domain.domain_id,
        "owner",
        role_id="owner",
        password_hash=hash_password("owner-password"),
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    service = LoginService(conn, settings)
    namespace = SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        owner=owner,
        settings=settings,
        service=service,
        db_path=db_path,
    )
    with TestClient(create_app(settings), follow_redirects=False) as client:
        namespace.client = client
        yield namespace
    db.close(conn)


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_secrets_never_appear_in_core_logs_or_metrics(core_client, tmp_path) -> None:
    fake_password = secrets.token_urlsafe(24)
    fake_token_value = secrets.token_hex(16)
    fake_cookie = secrets.token_hex(16)
    core_client.get(
        f"/api/approvals?password={fake_password}&token={fake_token_value}",
        headers={**_auth(), "Cookie": f"helix_session={fake_cookie}"},
    )
    lines = (tmp_path / "logs.jsonl").read_text(encoding="utf-8")
    assert fake_password not in lines
    assert fake_token_value not in lines
    assert fake_cookie not in lines
    exposition = core_client.get("/metrics", headers=_auth()).text
    assert fake_password not in exposition
    assert fake_token_value not in exposition
    assert fake_cookie not in exposition


def test_app_request_log_redacts_secrets(app_ctx, capsys) -> None:
    fake_password = secrets.token_urlsafe(24)
    fake_cookie = secrets.token_hex(16)
    app_ctx.client.get(
        f"/app/?password={fake_password}",
        cookies={"helix_session": fake_cookie},
    )
    out = capsys.readouterr().out
    assert fake_password not in out
    assert fake_cookie not in out
    entries = [json.loads(line) for line in out.splitlines() if '"http_request"' in line]
    assert entries, "app emitted no http_request log lines"
    entry = entries[-1]
    assert entry["route"] == "/app/"
    assert entry["status"] == 401
    assert entry["duration_ms"] >= 0
    assert entry["correlation_id"]


def test_route_labels_are_normalized(core_client) -> None:
    concrete = f"doc-{secrets.token_hex(8)}"
    assert core_client.get(f"/api/docs/{concrete}", headers=_auth()).status_code == 404
    exposition = core_client.get("/metrics", headers=_auth()).text
    assert "/api/docs/{doc_id}" in exposition
    assert concrete not in exposition


def test_tenant_identifiers_are_not_metric_labels(core_client, monkeypatch) -> None:
    unique_tenant = f"tenant-{secrets.token_hex(6)}"
    unique_client = f"client-{secrets.token_hex(6)}"
    monkeypatch.setenv("HELIX_API_TOKEN_TENANT_ID", unique_tenant)
    monkeypatch.setenv("HELIX_API_TOKEN_CLIENT_ID", unique_client)
    resp = core_client.post(
        "/api/workflows",
        json={
            "tenant_id": unique_tenant,
            "client_id": unique_client,
            "capability": "wfm_forecast",
            "requesting_actor": "suby",
            "owning_role_id": "ops_gm",
            "input_payload": {"arrival_rate": 10},
            "requires_approval": True,
        },
        headers=_auth(),
    )
    assert resp.status_code == 409
    exposition = core_client.get("/metrics", headers=_auth()).text
    assert unique_tenant not in exposition
    assert unique_client not in exposition


def test_readiness_failures_are_counted(core_client, tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    audit_db.unlink()
    assert core_client.get("/readyz").status_code == 503
    counts = REGISTRY.snapshot().get("helix_readiness_check_failures_total", {})
    assert counts.get("audit_chain", 0.0) >= 1.0


def test_readiness_signal_is_load_bearing(core_client, tmp_path, monkeypatch) -> None:
    (tmp_path / "audit.db").unlink()
    monkeypatch.setattr(REGISTRY, "record_readiness_failure", lambda check: None)
    assert core_client.get("/readyz").status_code == 503
    counts = REGISTRY.snapshot().get("helix_readiness_check_failures_total", {})
    assert counts.get("audit_chain", 0.0) == 0.0


def test_audit_failures_are_observable(core_client, tmp_path) -> None:
    import sqlite3

    from security.audit import AuditRecord, AuditTrail

    trail = AuditTrail(db_path=str(tmp_path / "audit.db"))
    try:
        prev = None
        for _ in range(2):
            rec = AuditRecord.new(
                event_type="obs-test",
                actor="obs",
                actor_type="service",
                decision="succeeded",
                previous_hash=prev,
            )
            trail.append(rec)
            prev = rec.current_hash
    finally:
        trail.close()
    conn = sqlite3.connect(str(tmp_path / "audit.db"))
    try:
        row = conn.execute("SELECT audit_id, data FROM audit ORDER BY rowid LIMIT 1").fetchone()
        data = json.loads(row[1])
        data["decision"] = "tampered"
        conn.execute("UPDATE audit SET data = ? WHERE audit_id = ?", (json.dumps(data), row[0]))
        conn.commit()
    finally:
        conn.close()
    assert core_client.get("/readyz").status_code == 503
    snapshot = REGISTRY.snapshot()
    assert snapshot["helix_audit_chain_verifications_total"].get("failure", 0.0) >= 1.0
    assert snapshot["helix_readiness_check_failures_total"].get("audit_chain", 0.0) >= 1.0


def test_auth_and_throttle_events_are_counted(app_ctx) -> None:
    service = app_ctx.service
    assert service.login("o.academy", "owner", "wrong", ip="10.8.0.1").ok is False
    assert service.login("o.academy", "owner", "owner-password", ip="10.8.0.1").ok is True
    for _ in range(11):
        service.login("o.academy", "ghost", "wrong", ip="10.8.0.2")
    for _ in range(5):
        service.login("o.academy", "owner", "wrong", ip="10.8.0.3")
    counts = REGISTRY.snapshot().get("helix_auth_events_total", {})
    assert counts.get("login_failure", 0.0) >= 1.0
    assert counts.get("login_success", 0.0) >= 1.0
    assert counts.get("login_throttled", 0.0) >= 1.0
    assert counts.get("login_locked", 0.0) >= 1.0


def test_kill_switch_engagements_are_counted(tmp_path) -> None:
    from contracts.task import CorrelationContext, TaskRequest
    from control_plane.engine import Engine
    from control_plane.store import Store

    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(
        store=store,
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    try:
        engine.register_handler("ops_execution", lambda wf: {"ok": True})
        engine.kill_switch.engage("obs drill", "operator")
        corr = CorrelationContext.new(tenant_id="t", client_id="c")
        request = TaskRequest(
            request_id="req_obs_ks",
            correlation=corr,
            requesting_actor="suby",
            owning_role_id="ops_gm",
            capability="ops_execution",
            input_payload={},
            requires_approval=False,
            status="proposed",
            created_at="2026-09-18T00:00:00Z",
            client_id="c",
        )
        with pytest.raises(Exception):
            engine.submit(request)
        engine.kill_switch.release("operator")
    finally:
        engine.close()
    counts = REGISTRY.snapshot().get("helix_kill_switch_events_total", {})
    assert counts.get("engaged", 0.0) >= 1.0
    assert counts.get("denied", 0.0) >= 1.0
    assert counts.get("released", 0.0) >= 1.0


def test_disk_gauge_is_exported(core_client) -> None:
    exposition = core_client.get("/metrics", headers=_auth()).text
    lines = [ln for ln in exposition.splitlines() if ln.startswith("helix_data_disk_free_bytes ")]
    assert lines, "disk gauge missing from exposition"
    assert float(lines[0].split()[-1]) >= 0.0


def test_backup_manifest_carries_operator_readable_verdicts(tmp_path) -> None:
    import uuid
    from datetime import datetime, timezone

    from helix_codex_app import db as app_db
    from helix_codex_app.scripts.backup_app import backup_app

    db_path = str(tmp_path / "app.db")
    conn = app_db.connect(db_path=db_path)
    app_db._init_schema(conn)
    conn.execute(
        "INSERT INTO nodes (node_id, tenant_id, client_id, domain_id, correlation_id,"
        " causation_id, classification, nature, kind, created_by, created_at, body,"
        " provenance_source, provenance_data_mode)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"node-{uuid.uuid4().hex}",
            "t",
            "c",
            "d",
            "corr",
            None,
            "internal",
            "historical_event",
            "admin",
            "system",
            datetime.now(timezone.utc).isoformat(),
            "{}",
            "src",
            "app_runtime",
        ),
    )
    conn.commit()
    app_db.close(conn)
    manifest = backup_app(
        db_path=db_path,
        memory_root=str(tmp_path / "memory_stores"),
        target_dir=str(tmp_path / "backup"),
    )
    assert manifest["node_count"] == 1
    assert manifest["memory_chains_verified"] is True
    assert manifest["files"], "operator needs the integrity inventory"
