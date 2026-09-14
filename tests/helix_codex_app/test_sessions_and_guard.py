"""Sessions, cookie, and CSRF guard tests for the app scaffold.

Probe routes are registered once, at module import, on the real app_router
and csrf_router objects, so the guard is exercised exactly as the production
wiring uses it. The fixture builds a throwaway app database under tmp_path
and points both the app and the parent engine at temp files, keeping the
suite hermetic.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import Depends
from starlette.responses import Response as StarletteResponse

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import app_router, create_app, csrf_router
from helix_codex_app.config import AppSettings
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.guard import (
    current_account,
    require_capability,
    require_permission,
    require_scope,
)
from helix_codex_app.security.sessions import (
    SESSION_COOKIE,
    SessionStore,
    set_session_cookie,
)
from server.config import get_settings as get_server_settings


@app_router.get("/whoami")
def _probe_whoami(account=Depends(current_account)) -> dict[str, str]:
    return {"account_id": account.account_id, "tenant_id": account.tenant_id}


@app_router.get(
    "/capability-punch",
    dependencies=[Depends(require_capability("test.punch"))],
)
def _probe_capability_punch() -> dict[str, str]:
    return {"ok": "true"}


@app_router.get(
    "/capability-denied",
    dependencies=[Depends(require_capability("test.denied"))],
)
def _probe_capability_denied() -> dict[str, str]:
    return {"ok": "true"}


@app_router.get(
    "/permission-punch",
    dependencies=[Depends(require_permission("test.punch"))],
)
def _probe_permission_punch() -> dict[str, str]:
    return {"ok": "true"}


@app_router.get("/scope-tenant-a", dependencies=[Depends(require_scope("tenant-a"))])
def _probe_scope_tenant_a() -> dict[str, str]:
    return {"ok": "true"}


@csrf_router.post("/csrf-probe")
def _probe_csrf() -> dict[str, str]:
    return {"ok": "true"}


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    server_dir = tmp_path / "server"
    for name in ("HELIX_DB_PATH", "HELIX_AUDIT_DB_PATH", "HELIX_LOG_PATH"):
        monkeypatch.setenv(name, str(server_dir / name))
    get_server_settings.cache_clear()

    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    amira = repo.create_account(domain_a.domain_id, "amira", role_id="manager")
    omar = repo.create_account(domain_b.domain_id, "omar", role_id="owner")
    conn.execute(
        """
        INSERT OR REPLACE INTO account_capabilities (
            account_id, capability_key, enabled, granted_by, granted_at
        ) VALUES (?, 'test.punch', 1, 'system', ?)
        """,
        (amira.account_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    settings = AppSettings(db_path=db_path)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        settings=settings,
        store=store,
        amira=amira,
        omar=omar,
    )
    get_server_settings.cache_clear()
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings)) as test_client:
        yield test_client


def _cookie(token: str) -> dict[str, str]:
    return {SESSION_COOKIE: token}


def test_no_cookie_returns_401(client) -> None:
    resp = client.get("/app/whoami")
    assert resp.status_code == 401


def test_valid_cookie_returns_200(ctx, client) -> None:
    token, _session = ctx.store.issue_session(ctx.amira, ip="127.0.0.1", user_agent="pytest")
    resp = client.get("/app/whoami", cookies=_cookie(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == ctx.amira.account_id
    assert body["tenant_id"] == "tenant-a"


def test_public_routes_do_not_need_session(client) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/app/healthz").status_code == 200


def test_non_get_without_csrf_returns_403(ctx, client) -> None:
    token, _session = ctx.store.issue_session(ctx.amira)
    resp = client.post("/app/csrf-probe", cookies=_cookie(token))
    assert resp.status_code == 403


def test_non_get_with_wrong_csrf_returns_403(ctx, client) -> None:
    token, _session = ctx.store.issue_session(ctx.amira)
    resp = client.post(
        "/app/csrf-probe",
        cookies=_cookie(token),
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert resp.status_code == 403


def test_non_get_with_correct_csrf_returns_200(ctx, client) -> None:
    token, session = ctx.store.issue_session(ctx.amira)
    resp = client.post(
        "/app/csrf-probe",
        cookies=_cookie(token),
        headers={"X-CSRF-Token": session.csrf_token},
    )
    assert resp.status_code == 200


def test_revoked_session_fails_next_request(ctx, client) -> None:
    token, session = ctx.store.issue_session(ctx.amira)
    ctx.store.revoke(session.session_id)
    resp = client.get("/app/whoami", cookies=_cookie(token))
    assert resp.status_code == 401


def test_revoked_session_fails_at_verify(ctx) -> None:
    token, session = ctx.store.issue_session(ctx.amira)
    assert ctx.store.verify(token) is not None
    ctx.store.revoke(session.session_id)
    assert ctx.store.verify(token) is None


def test_expired_session_returns_401(ctx, client) -> None:
    token, session = ctx.store.issue_session(ctx.amira)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ctx.conn.execute(
        "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
        (past, session.session_id),
    )
    ctx.conn.commit()
    resp = client.get("/app/whoami", cookies=_cookie(token))
    assert resp.status_code == 401


def test_idle_session_returns_401(ctx, client) -> None:
    token, session = ctx.store.issue_session(ctx.amira)
    stale = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    ctx.conn.execute(
        "UPDATE sessions SET last_seen_at = ? WHERE session_id = ?",
        (stale, session.session_id),
    )
    ctx.conn.commit()
    resp = client.get("/app/whoami", cookies=_cookie(token))
    assert resp.status_code == 401


def test_touch_refreshes_idle_timestamp(ctx) -> None:
    token, session = ctx.store.issue_session(ctx.amira)
    stale = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    ctx.conn.execute(
        "UPDATE sessions SET last_seen_at = ? WHERE session_id = ?",
        (stale, session.session_id),
    )
    ctx.conn.commit()
    assert ctx.store.verify(token) is None
    ctx.store.touch(session.session_id)
    assert ctx.store.verify(token) is not None


def test_revoke_all_for_account(ctx) -> None:
    token_a, _ = ctx.store.issue_session(ctx.amira)
    token_b, _ = ctx.store.issue_session(ctx.amira)
    assert ctx.store.revoke_all_for(ctx.amira.account_id) == 2
    assert ctx.store.verify(token_a) is None
    assert ctx.store.verify(token_b) is None


def test_only_token_hash_is_stored(ctx) -> None:
    token, session = ctx.store.issue_session(ctx.amira)
    row = ctx.conn.execute(
        "SELECT token_hash, csrf_token FROM sessions WHERE session_id = ?",
        (session.session_id,),
    ).fetchone()
    assert row["token_hash"] == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert row["token_hash"] != token


def test_cookie_flags(ctx) -> None:
    response = StarletteResponse()
    set_session_cookie(response, "dummy-token", ctx.settings)
    header = response.headers["set-cookie"].lower()
    assert "helix_session=dummy-token" in header
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/" in header
    assert "secure" in header


def test_cookie_secure_flag_off_for_plain_http() -> None:
    settings = AppSettings(db_path="unused.db", cookie_secure=False)
    response = StarletteResponse()
    set_session_cookie(response, "dummy-token", settings)
    header = response.headers["set-cookie"].lower()
    assert "secure" not in header


def test_cross_tenant_scope_denied(ctx, client) -> None:
    token_b, _session = ctx.store.issue_session(ctx.omar)
    resp = client.get("/app/scope-tenant-a", cookies=_cookie(token_b))
    assert resp.status_code == 403


def test_own_tenant_scope_allowed(ctx, client) -> None:
    token_a, _session = ctx.store.issue_session(ctx.amira)
    resp = client.get("/app/scope-tenant-a", cookies=_cookie(token_a))
    assert resp.status_code == 200


def test_capability_granted_for_seeded_account(ctx, client) -> None:
    token_a, _session = ctx.store.issue_session(ctx.amira)
    resp = client.get("/app/capability-punch", cookies=_cookie(token_a))
    assert resp.status_code == 200


def test_capability_denied_for_missing_grant(ctx, client) -> None:
    token_a, _session = ctx.store.issue_session(ctx.amira)
    resp = client.get("/app/capability-denied", cookies=_cookie(token_a))
    assert resp.status_code == 403


def test_capability_denied_for_other_account(ctx, client) -> None:
    token_b, _session = ctx.store.issue_session(ctx.omar)
    resp = client.get("/app/capability-punch", cookies=_cookie(token_b))
    assert resp.status_code == 403


def test_permission_gate_denies_until_catalog(ctx, client) -> None:
    token_b, _session = ctx.store.issue_session(ctx.omar)
    resp = client.get("/app/permission-punch", cookies=_cookie(token_b))
    assert resp.status_code == 403


def test_locked_account_cannot_use_session(ctx, client) -> None:
    liya = ctx.repo.create_account(
        ctx.repo.get_domain_by_name("a.academy").domain_id, "liya", role_id="employee"
    )
    token, _session = ctx.store.issue_session(liya)
    ctx.repo.lock_account(liya.account_id)
    resp = client.get("/app/whoami", cookies=_cookie(token))
    assert resp.status_code == 401


def test_issue_session_rejects_non_active_account(ctx) -> None:
    liya = ctx.repo.create_account(
        ctx.repo.get_domain_by_name("a.academy").domain_id, "sara", role_id="employee"
    )
    ctx.repo.set_status(liya.account_id, "disabled")
    disabled = ctx.repo.get_account_by_id(liya.account_id)
    with pytest.raises(ValueError):
        ctx.store.issue_session(disabled)
