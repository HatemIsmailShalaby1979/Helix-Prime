"""Cockpit cross-tenant isolation (P6.5).

The pack's synthetic numbers are seeded from a fixed RNG, so tenant A and
tenant B produce the same aggregates by design. That means "the numbers differ"
cannot be the proof here, and pretending it was would be a test that passes for
the wrong reason. What is genuinely per-tenant is the workspace state the
cockpit reads alongside the numbers: the approval queue, the audit rows, and the
context the numbers are computed under. These tests pin all three.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.integration import cockpit_bridge
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

CAPABILITY = "wfm_forecast"


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    manager_a = repo.create_account(
        domain_a.domain_id, "layla", role_id="manager", password_hash=hash_password("x")
    )
    owner_a = repo.create_account(
        domain_a.domain_id, "owna", role_id="owner", password_hash=hash_password("x")
    )
    owner_b = repo.create_account(
        domain_b.domain_id, "ownb", role_id="owner", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        manager_a=manager_a,
        owner_a=owner_a,
        owner_b=owner_b,
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


def _session(ctx, account) -> tuple[dict, dict]:
    token, _issued = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _submit(client, ctx, account) -> dict:
    cookies, headers = _session(ctx, account)
    response = client.post(
        "/app/api/ops/workflows",
        json={"capability": CAPABILITY},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client, ctx, account, workflow_id: str) -> dict:
    cookies, headers = _session(ctx, account)
    response = client.post(
        f"/app/api/ops/workflows/{workflow_id}/approve",
        json={"decision": "approve", "reason": "approved for the isolation test"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_numbers_are_computed_under_the_callers_own_tenant(ctx, monkeypatch):
    """The connector context is built from the account, so the cockpit cannot
    be pointed at another tenant by any request the app accepts."""
    seen = []
    real_context = cockpit_bridge._context

    def _capturing_context(account, *, as_of, pack):
        context, connectors, extra = real_context(account, as_of=as_of, pack=pack)
        seen.append((account.account_id, context.tenant_id, context.client_id))
        return context, connectors, extra

    monkeypatch.setattr(cockpit_bridge, "_context", _capturing_context)
    cockpit_bridge.owner_summary(ctx.owner_a, as_of="2026-09-15T00:00:00Z")
    cockpit_bridge.owner_summary(ctx.owner_b, as_of="2026-09-15T00:00:00Z")
    assert seen == [
        (ctx.owner_a.account_id, ctx.owner_a.tenant_id, ctx.owner_a.client_id),
        (ctx.owner_b.account_id, ctx.owner_b.tenant_id, ctx.owner_b.client_id),
    ]


def test_a_foreign_owner_sees_an_empty_approval_queue(client, ctx):
    """Tenant A's open request never appears on tenant B's owner board."""
    card = _submit(client, ctx, ctx.manager_a)

    cookies, _ = _session(ctx, ctx.owner_a)
    own_view = client.get("/app/cockpit/owner", cookies=cookies)
    assert own_view.status_code == 200
    assert card["workflow_id"] in own_view.text

    foreign_cookies, _ = _session(ctx, ctx.owner_b)
    foreign_view = client.get("/app/cockpit/owner", cookies=foreign_cookies)
    assert foreign_view.status_code == 200
    assert card["workflow_id"] not in foreign_view.text


def test_a_foreign_owner_cannot_fetch_another_tenants_workflow(client, ctx):
    """The workflow detail route scopes by tenant: a foreign id is NotFound."""
    card = _submit(client, ctx, ctx.manager_a)
    foreign_cookies, _ = _session(ctx, ctx.owner_b)
    response = client.get(
        f"/app/api/ops/workflows/{card['workflow_id']}", cookies=foreign_cookies
    )
    assert response.status_code == 404


def test_a_foreign_owner_sees_no_foreign_audit_rows(client, ctx):
    """The control-plane audit panel is filtered by tenant id."""
    card = _submit(client, ctx, ctx.manager_a)
    _approve(client, ctx, ctx.owner_a, card["workflow_id"])

    own_cookies, _ = _session(ctx, ctx.owner_a)
    own_panel = client.get("/app/cockpit/control-plane", cookies=own_cookies)
    assert own_panel.status_code == 200
    assert card["correlation_id"] in own_panel.text

    foreign_cookies, _ = _session(ctx, ctx.owner_b)
    foreign_panel = client.get("/app/cockpit/control-plane", cookies=foreign_cookies)
    assert foreign_panel.status_code == 200
    assert card["correlation_id"] not in foreign_panel.text
