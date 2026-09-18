"""Domain login, lockout, logout, and password-screen tests for the app.

Service-level tests drive LoginService against a throwaway database. The
HTTP tests drive the real router through TestClient, so the public login
form, the guarded logout/password routes, the CSRF header requirement, and
the cookie round-trip are exercised exactly as the app wiring uses them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.modules.identity.service import (
    BAD_CREDENTIALS_MESSAGE,
    LoginResult,
    LoginService,
)
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password, verify_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore


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
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    service = LoginService(conn, settings)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        amira=amira,
        settings=settings,
        service=service,
        store=store,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _cookie(token: str) -> dict[str, str]:
    return {SESSION_COOKIE: token}


def _login(ctx, client, *, username="amira", domain="a.academy", password):
    resp = client.post(
        "/app/auth/login",
        data={"domain": domain, "username": username, "password": password},
    )
    assert resp.status_code == 303, resp.text
    return _session_token(resp.headers["set-cookie"])


def _session_token(set_cookie: str) -> str:
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith(f"{SESSION_COOKIE}="):
            return part.split("=", 1)[1]
    raise AssertionError("no session cookie in header")


def _set_must_change(ctx, account_id: str) -> None:
    ctx.conn.execute(
        "UPDATE accounts SET must_change_password = 1 WHERE account_id = ?", (account_id,)
    )
    ctx.conn.commit()


def test_login_success_sets_session_cookie(ctx, client) -> None:
    resp = client.post(
        "/app/auth/login",
        data={"domain": "a.academy", "username": "amira", "password": "your-password"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/"
    cookie = " ".join(resp.headers["set-cookie"].lower().split())
    assert cookie.startswith("helix_session=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    rows = ctx.conn.execute(
        "SELECT outcome, reason FROM login_events WHERE account_id = ?", (ctx.amira.account_id,)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "success"
    session_count = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM sessions WHERE account_id = ?", (ctx.amira.account_id,)
    ).fetchone()["n"]
    assert session_count == 1


def test_login_form_is_public_and_plain(client) -> None:
    assert client.get("/app/").status_code == 401
    resp = client.get("/app/auth/login")
    assert resp.status_code == 200
    assert "Sign in" in resp.text
    assert "Authenticate" not in resp.text


def test_login_form_redirects_authenticated_user(ctx, client) -> None:
    token, _session = ctx.store.issue_session(ctx.amira)
    resp = client.get("/app/auth/login", cookies=_cookie(token))
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/"


def test_wrong_password_returns_form_error_and_increments(ctx, client) -> None:
    resp = client.post(
        "/app/auth/login",
        data={"domain": "a.academy", "username": "amira", "password": "nope1234"},
    )
    assert resp.status_code == 200
    assert "The sign-in details did not match" in resp.text
    account = ctx.repo.get_account_by_id(ctx.amira.account_id)
    assert account.failed_attempts == 1
    assert account.status == "active"
    reason = ctx.conn.execute(
        "SELECT reason FROM login_events WHERE account_id = ?", (ctx.amira.account_id,)
    ).fetchone()["reason"]
    assert reason == "bad_password"


def test_sixth_attempt_is_locked_and_lock_is_recorded(ctx, client) -> None:
    for _ in range(5):
        client.post(
            "/app/auth/login",
            data={"domain": "a.academy", "username": "amira", "password": "nope1234"},
        )
    account = ctx.repo.get_account_by_id(ctx.amira.account_id)
    assert account.failed_attempts == 5
    assert account.status == "locked"
    assert account.locked_until is not None
    resp = client.post(
        "/app/auth/login",
        data={"domain": "a.academy", "username": "amira", "password": "your-password"},
    )
    assert resp.status_code == 200
    assert "Too many failed attempts" in resp.text
    reasons = [
        row["reason"]
        for row in ctx.conn.execute(
            "SELECT reason FROM login_events WHERE account_id = ?", (ctx.amira.account_id,)
        ).fetchall()
    ]
    assert reasons.count("bad_password") == 4
    assert reasons.count("locked") == 2
    assert ctx.repo.get_account_by_id(ctx.amira.account_id).failed_attempts == 5


def test_locked_account_cannot_login_even_with_right_password(ctx, client) -> None:
    ctx.repo.lock_account(ctx.amira.account_id)
    resp = client.post(
        "/app/auth/login",
        data={"domain": "a.academy", "username": "amira", "password": "your-password"},
    )
    assert resp.status_code == 200
    assert "Too many failed attempts" in resp.text
    assert resp.headers.get("set-cookie") is None
    session_count = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM sessions WHERE account_id = ?", (ctx.amira.account_id,)
    ).fetchone()["n"]
    assert session_count == 0


def test_logout_revokes_the_session(ctx, client) -> None:
    token = _login(ctx, client, password="your-password")
    session = ctx.store.verify(token)
    assert session is not None
    assert client.get("/app/", cookies=_cookie(token)).status_code == 200
    resp = client.post(
        "/app/auth/logout",
        cookies=_cookie(token),
        headers={"X-CSRF-Token": session.csrf_token},
    )
    assert resp.status_code == 200
    assert ctx.store.verify(token) is None
    assert client.get("/app/", cookies=_cookie(token)).status_code == 401


def test_logout_without_csrf_is_rejected(ctx, client) -> None:
    token = _login(ctx, client, password="your-password")
    resp = client.post("/app/auth/logout", cookies=_cookie(token))
    assert resp.status_code == 403


def test_must_change_password_redirects_to_password_screen(ctx, client) -> None:
    _set_must_change(ctx, ctx.amira.account_id)
    resp = client.post(
        "/app/auth/login",
        data={"domain": "a.academy", "username": "amira", "password": "your-password"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/auth/password"


def test_password_screen_and_change_flow(ctx, client) -> None:
    _set_must_change(ctx, ctx.amira.account_id)
    token = _login(ctx, client, password="your-password")
    session = ctx.store.verify(token)
    resp = client.get("/app/auth/password", cookies=_cookie(token))
    assert resp.status_code == 200
    assert "Set a new password" in resp.text
    resp = client.post(
        "/app/auth/password",
        cookies=_cookie(token),
        headers={"X-CSRF-Token": session.csrf_token},
        data={"old_password": "your-password", "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/"
    account = ctx.repo.get_account_by_id(ctx.amira.account_id)
    assert account.must_change_password is False
    assert verify_password("brand-new-pass", account.password_hash)
    assert ctx.store.verify(token) is None
    fresh_token = _login(ctx, client, password="brand-new-pass")
    fresh_session = ctx.store.verify(fresh_token)
    resp = client.post(
        "/app/auth/password",
        cookies=_cookie(fresh_token),
        headers={"X-CSRF-Token": fresh_session.csrf_token},
        data={"old_password": "wrong", "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 200
    assert "current password is incorrect" in resp.text


def test_password_change_without_csrf_is_rejected(ctx, client) -> None:
    token = _login(ctx, client, password="your-password")
    resp = client.post(
        "/app/auth/password",
        cookies=_cookie(token),
        data={"old_password": "your-password", "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 403


def test_me_fragment_shows_display_name_and_role(ctx, client) -> None:
    token = _login(ctx, client, password="your-password")
    resp = client.get("/app/auth/me", cookies=_cookie(token))
    assert resp.status_code == 200
    assert "Amira K." in resp.text
    assert "manager" in resp.text


def test_home_greets_signed_in_user(ctx, client) -> None:
    token = _login(ctx, client, password="your-password")
    resp = client.get("/app/", cookies=_cookie(token))
    assert resp.status_code == 200
    assert "Hello, Amira K." in resp.text
    assert "manager" in resp.text


def test_public_home_keeps_generic_greeting(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Hello, operator." in resp.text


def test_unknown_domain_is_recorded_without_enumeration(ctx) -> None:
    mishit = ctx.service.login("ghost.academy", "amira", "whatever", ip="127.0.0.1")
    assert mishit.ok is False
    assert mishit.error == BAD_CREDENTIALS_MESSAGE
    rows = ctx.conn.execute("SELECT account_id, domain_id, reason FROM login_events").fetchall()
    assert len(rows) == 1
    assert rows[0]["reason"] == "no_such_domain"
    assert rows[0]["account_id"] is None
    assert rows[0]["domain_id"] is None
    wrong_password = ctx.service.login("a.academy", "amira", "wrong-pass", ip="127.0.0.1")
    assert wrong_password.ok is False
    assert wrong_password.error == mishit.error
    assert wrong_password.code != mishit.code


def test_successful_service_login_resets_failed_attempts(ctx) -> None:
    ctx.service.login("a.academy", "amira", "nope1234", ip="127.0.0.1")
    ctx.service.login("a.academy", "amira", "nope1234", ip="127.0.0.1")
    result = ctx.service.login("a.academy", "amira", "your-password", ip="127.0.0.1")
    assert result.ok is True
    assert isinstance(result, LoginResult)
    assert result.token is not None
    assert result.must_change_password is False
    account = ctx.repo.get_account_by_id(ctx.amira.account_id)
    assert account.failed_attempts == 0
    assert account.status == "active"
    assert account.last_login_at is not None
    assert ctx.store.verify(result.token) is not None


def test_expired_lock_allows_login_again(ctx) -> None:
    past = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    ctx.conn.execute(
        "UPDATE accounts SET status = 'locked', locked_until = ? WHERE account_id = ?",
        (past, ctx.amira.account_id),
    )
    ctx.conn.commit()
    result = ctx.service.login("a.academy", "amira", "your-password", ip="127.0.0.1")
    assert result.ok is True
    account = ctx.repo.get_account_by_id(ctx.amira.account_id)
    assert account.status == "active"
    assert account.locked_until is None


def test_short_new_password_is_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.change_password(ctx.amira, "your-password", "short")


def test_change_password_clears_must_change_flag(ctx) -> None:
    _set_must_change(ctx, ctx.amira.account_id)
    account = ctx.repo.get_account_by_id(ctx.amira.account_id)
    assert account.must_change_password is True
    updated = ctx.service.change_password(account, "your-password", "brand-new-pass")
    assert updated.must_change_password is False
    assert verify_password("brand-new-pass", updated.password_hash)


def test_change_password_rejects_wrong_current(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.change_password(ctx.amira, "not-the-password", "brand-new-pass")
