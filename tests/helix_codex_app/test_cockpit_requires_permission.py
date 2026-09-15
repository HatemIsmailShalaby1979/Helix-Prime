"""Cockpit permission enforcement, end to end (P6.5).

The cockpit is a manager-and-owner surface. These tests hit every cockpit route
through the real app with a real session for each app role, so the claim "an
employee never sees it" is about HTTP, not about a function somebody remembered
to call. The contractor and external roles matter as much as the employee: they
are real accounts a tenant can create, and each one must get the same refusal.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

COCKPIT_ROUTES = (
    "/app/cockpit",
    "/app/cockpit/owner",
    "/app/cockpit/coach",
    "/app/cockpit/parent",
    "/app/cockpit/control-plane",
    "/app/api/cockpit/summary",
)
REFUSED_ROLES = ("employee", "contractor", "external")
ALLOWED_ROLES = ("manager", "owner")


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("academy.test", tenant_id="tenant-a", client_id="client-a")
    accounts = {
        role: repo.create_account(
            domain.domain_id, role, role_id=role, password_hash=hash_password("x")
        )
        for role in REFUSED_ROLES + ALLOWED_ROLES
    }
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        accounts=accounts,
        settings=settings,
        store=store,
        tmp_path=tmp_path,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx, monkeypatch):
    monkeypatch.setenv("HELIX_DB_PATH", str(ctx.tmp_path / "workflow.db"))
    monkeypatch.setenv("HELIX_AUDIT_DB_PATH", str(ctx.tmp_path / "audit.db"))
    monkeypatch.setenv("HELIX_LOG_PATH", str(ctx.tmp_path / "logs.jsonl"))
    from server.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def _cookies(ctx, account) -> dict:
    token, _session = ctx.store.issue_session(account)
    assert ctx.store.verify(token) is not None
    return {SESSION_COOKIE: token}


def test_every_refused_role_gets_403_on_every_cockpit_route(client, ctx):
    for role in REFUSED_ROLES:
        cookies = _cookies(ctx, ctx.accounts[role])
        for route in COCKPIT_ROUTES:
            response = client.get(route, cookies=cookies)
            assert response.status_code == 403, (
                f"{role} on {route} returned {response.status_code}, expected 403"
            )


def test_every_allowed_role_gets_200_on_every_cockpit_route(client, ctx):
    for role in ALLOWED_ROLES:
        cookies = _cookies(ctx, ctx.accounts[role])
        for route in COCKPIT_ROUTES:
            response = client.get(route, cookies=cookies)
            assert response.status_code == 200, (
                f"{role} on {route} returned {response.status_code}, expected 200"
            )


def test_a_refused_role_cannot_reach_the_cockpit_even_with_a_guessable_id(client, ctx):
    """A role without cockpit.view gets the same refusal on every path shape.

    An id that would select a specific resource if the route were open must not
    change the answer: the gate runs before any lookup, so there is nothing to
    probe with.
    """
    cookies = _cookies(ctx, ctx.accounts["employee"])
    probe_routes = (
        "/app/cockpit/owner",
        "/app/cockpit/coach?coach_id=coach-1",
        "/app/cockpit/parent?family_id=fam-01",
        "/app/cockpit/control-plane",
        "/app/api/cockpit/summary",
    )
    for route in probe_routes:
        response = client.get(route, cookies=cookies)
        assert response.status_code == 403, f"{route} returned {response.status_code}"


def test_a_refused_role_gets_403_without_a_session_too(client):
    for route in COCKPIT_ROUTES:
        response = client.get(route)
        assert response.status_code in (401, 403), f"{route} returned {response.status_code}"
