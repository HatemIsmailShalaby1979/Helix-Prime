"""Authentication-boundary hardening tests for the app.

Covers what the per-feature suites do not pin in one place: login
throttling by source address and login name (SQLite-backed, bounded),
session revocation on password change, production-safe cookie flags, a
route-by-route CSRF sweep over every mutating /app route, router-boundary
permission markers for admin and cockpit, and redaction of unhandled
errors. The throttling tests are the can-fail proof for the LoginThrottle
wiring: without it the spray below answers bad_password, never throttled.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.modules.identity.service import (
    THROTTLED_MESSAGE,
    LoginService,
)
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore
from helix_codex_app.security.throttle import (
    MAX_ATTEMPTS_PER_IP,
    MAX_ATTEMPTS_PER_LOGIN,
    LoginThrottle,
    login_bucket,
)


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    amira = repo.create_account(
        domain.domain_id,
        "amira",
        display_name="Amira K.",
        role_id="manager",
        password_hash=hash_password("your-password"),
    )
    omar = repo.create_account(
        domain.domain_id,
        "omar",
        display_name="Omar B.",
        role_id="employee",
        password_hash=hash_password("your-password"),
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    service = LoginService(conn, settings)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        amira=amira,
        omar=omar,
        settings=settings,
        service=service,
        store=store,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _spray(service, *, domain="a.academy", username="ghost", ip="10.9.0.1", count):
    last = None
    for _ in range(count):
        last = service.login(domain, username, "wrong-password", ip=ip)
    return last


def test_unknown_login_name_is_throttled(ctx) -> None:
    last = _spray(ctx.service, count=MAX_ATTEMPTS_PER_LOGIN + 1)
    assert last.ok is False
    assert last.code == "throttled"
    assert last.error == THROTTLED_MESSAGE


def test_source_address_is_throttled_across_names(ctx) -> None:
    for i in range(MAX_ATTEMPTS_PER_IP):
        result = ctx.service.login("a.academy", f"ghost-{i}", "wrong-password", ip="10.9.0.2")
        assert result.code != "throttled"
    throttled = ctx.service.login("a.academy", "ghost-final", "wrong-password", ip="10.9.0.2")
    assert throttled.ok is False
    assert throttled.code == "throttled"
    assert throttled.error == THROTTLED_MESSAGE


def test_throttle_message_does_not_enumerate(ctx) -> None:
    unknown = _spray(ctx.service, username="ghost", count=MAX_ATTEMPTS_PER_LOGIN + 1)
    assert unknown.code == "throttled"
    for i in range(MAX_ATTEMPTS_PER_IP):
        ctx.service.login("a.academy", f"probe-{i}", "wrong-password", ip="10.9.0.5")
    known = ctx.service.login("a.academy", "amira", "your-password", ip="10.9.0.5")
    assert known.ok is False
    assert known.code == "throttled"
    assert known.error == unknown.error == THROTTLED_MESSAGE


def test_successful_login_clears_throttle_counters(ctx) -> None:
    _spray(ctx.service, username="amira", ip="10.9.0.4", count=4)
    ok = ctx.service.login("a.academy", "amira", "your-password", ip="10.9.0.4")
    assert ok.ok is True
    throttle = LoginThrottle(ctx.conn)
    assert throttle._count(login_bucket("a.academy", "amira")) == 0
    assert throttle._count("ip:10.9.0.4") == 0


def test_throttle_table_stays_bounded(ctx) -> None:
    for i in range(40):
        ctx.service.login("a.academy", f"ghost-{i}", "wrong-password", ip=f"10.9.1.{i}")
    rows = ctx.conn.execute("SELECT COUNT(*) AS n FROM login_throttle").fetchone()
    assert rows["n"] <= 80


def test_http_login_spray_answers_429(ctx, client) -> None:
    last = None
    for _ in range(MAX_ATTEMPTS_PER_LOGIN + 1):
        last = client.post(
            "/app/auth/login",
            data={"domain": "a.academy", "username": "ghost", "password": "wrong-password"},
        )
    assert last.status_code == 429
    assert THROTTLED_MESSAGE in last.text


def test_password_change_revokes_every_session(ctx, client) -> None:
    issued = [ctx.store.issue_session(ctx.amira) for _ in range(2)]
    tokens = [token for token, _session in issued]
    sessions = [ctx.store.verify(token) for token in tokens]
    assert all(session is not None for session in sessions)
    csrf = sessions[0].csrf_token
    resp = client.post(
        "/app/auth/password",
        data={"old_password": "your-password", "new_password": "a-new-password"},
        cookies={SESSION_COOKIE: tokens[0]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 303
    assert all(ctx.store.verify(token) is None for token in tokens)
    fresh = ctx.service.login("a.academy", "amira", "a-new-password")
    assert fresh.ok is True


def test_secure_cookie_flag_follows_settings(ctx, tmp_path) -> None:
    secure_settings = AppSettings(db_path=ctx.settings.db_path, cookie_secure=True)
    with TestClient(create_app(secure_settings), follow_redirects=False) as secure_client:
        resp = secure_client.post(
            "/app/auth/login",
            data={"domain": "a.academy", "username": "amira", "password": "your-password"},
        )
        assert resp.status_code == 303
        cookie = resp.headers["set-cookie"].lower()
        assert "secure" in cookie
        assert "httponly" in cookie
        assert "samesite=lax" in cookie


def test_logout_clears_the_cookie_with_matching_flags(ctx, client) -> None:
    token, session = ctx.store.issue_session(ctx.amira)
    resp = client.post(
        "/app/auth/logout",
        cookies={SESSION_COOKIE: token},
        headers={"X-CSRF-Token": session.csrf_token},
    )
    assert resp.status_code == 200
    cleared = resp.headers["set-cookie"].lower()
    assert "httponly" in cleared
    assert "samesite=lax" in cleared
    assert ctx.store.verify(token) is None


def test_every_mutating_app_route_requires_csrf(ctx) -> None:
    app = create_app(ctx.settings)
    mutating = {"POST", "PUT", "PATCH", "DELETE"}
    unguarded = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/app"):
            continue
        if path == "/app/auth/login":
            continue
        methods = set(getattr(route, "methods", set()) or set())
        if not methods & mutating:
            continue
        dependant = getattr(route, "dependant", None)
        names = {
            getattr(getattr(d, "call", None), "__name__", "")
            for d in getattr(dependant, "dependencies", [])
        }
        if "require_csrf" not in names:
            unguarded.append(f"{sorted(methods & mutating)} {path}")
    assert not unguarded, f"mutating routes without CSRF: {unguarded}"


def test_admin_and_cockpit_routers_gate_at_the_boundary() -> None:
    from helix_codex_app.modules.admin.router import admin_router
    from helix_codex_app.modules.cockpit.router import cockpit_router

    def permission_keys(router) -> set[str]:
        keys = set()
        for dependency in router.dependencies:
            marker = getattr(dependency.dependency, "_permission_key", None)
            if marker is not None:
                keys.add(marker)
        return keys

    assert permission_keys(admin_router) == {"admin.users"}
    assert permission_keys(cockpit_router) == {"cockpit.view"}


def test_employee_is_denied_admin_and_cockpit(ctx, client) -> None:
    token, _session = ctx.store.issue_session(ctx.omar)
    assert client.get("/app/admin", cookies={SESSION_COOKIE: token}).status_code == 403
    assert client.get("/app/cockpit", cookies={SESSION_COOKIE: token}).status_code == 403


def test_disabled_locked_and_revoked_accounts_fail_immediately(ctx, client) -> None:
    token, _session = ctx.store.issue_session(ctx.amira)
    assert ctx.store.verify(token) is not None
    ctx.repo.set_status(ctx.amira.account_id, "disabled")
    assert ctx.store.verify(token) is None
    assert client.get("/app/", cookies={SESSION_COOKIE: token}).status_code == 401
    ctx.repo.set_status(ctx.amira.account_id, "active")
    token2, _session2 = ctx.store.issue_session(ctx.repo.get_account_by_id(ctx.amira.account_id))
    ctx.store.revoke_all_for(ctx.amira.account_id)
    assert ctx.store.verify(token2) is None
    locked = ctx.repo.lock_account(ctx.amira.account_id)
    assert locked.status == "locked"
    with pytest.raises(ValueError):
        ctx.store.issue_session(ctx.repo.get_account_by_id(ctx.amira.account_id))
    denied = ctx.service.login("a.academy", "amira", "your-password")
    assert denied.ok is False


def test_unhandled_errors_are_redacted(ctx, monkeypatch) -> None:
    import helix_codex_app.modules.identity.router as identity_router

    leaked_token = "redact-me-token-value"
    leaked_path = "C:\\secrets\\app.db"

    def _boom(*args, **kwargs):
        raise RuntimeError(f"boom {leaked_token} at {leaked_path}")

    monkeypatch.setattr(identity_router, "render", _boom)
    with TestClient(
        create_app(ctx.settings), follow_redirects=False, raise_server_exceptions=False
    ) as quiet:
        resp = quiet.get("/app/auth/login")
    assert resp.status_code == 500
    assert leaked_token not in resp.text
    assert "secrets" not in resp.text
    assert "Traceback" not in resp.text
    assert resp.json()["error"]["code"] == "internal_error"
