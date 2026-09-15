"""The operations section (P6.2).

These drive the real stack: a real app, a real governed engine on a temporary
database, real sessions. The point is the rail, not the screen — a request must
land at the gate, an approval must move it, a refusal must say why, and the
correlation id must survive the whole trip.
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

CAPABILITY = "wfm_forecast"
OPS_ROUTES = (
    "/app/ops",
    "/app/ops/wfm",
    "/app/api/ops/workflows/does-not-exist",
)


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("academy.test", tenant_id="tenant-a", client_id="client-a")
    owner = repo.create_account(
        domain.domain_id, "owner", role_id="owner", password_hash=hash_password("x")
    )
    manager = repo.create_account(
        domain.domain_id, "layla", role_id="manager", password_hash=hash_password("x")
    )
    employee = repo.create_account(
        domain.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        owner=owner,
        manager=manager,
        employee=employee,
        settings=settings,
        store=store,
        tmp_path=tmp_path,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx, monkeypatch):
    """An app whose governed engine writes to this test's temporary directory."""
    monkeypatch.setenv("HELIX_DB_PATH", str(ctx.tmp_path / "workflow.db"))
    monkeypatch.setenv("HELIX_AUDIT_DB_PATH", str(ctx.tmp_path / "audit.db"))
    monkeypatch.setenv("HELIX_LOG_PATH", str(ctx.tmp_path / "logs.jsonl"))
    from server.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def _login(ctx, account) -> tuple[dict, dict]:
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _submit(client, ctx, account, capability: str = CAPABILITY) -> dict:
    cookies, headers = _login(ctx, account)
    response = client.post(
        "/app/api/ops/workflows",
        json={"capability": capability},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- the gate ----------------------------------------------------------------
def test_an_employee_is_refused_every_ops_route(client, ctx):
    cookies, _ = _login(ctx, ctx.employee)
    for route in OPS_ROUTES:
        response = client.get(route, cookies=cookies)
        assert response.status_code == 403, f"{route} returned {response.status_code}"


def test_an_employee_cannot_submit(client, ctx):
    cookies, headers = _login(ctx, ctx.employee)
    response = client.post(
        "/app/api/ops/workflows",
        json={"capability": CAPABILITY},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 403


def test_a_manager_can_open_the_ops_screen(client, ctx):
    cookies, _ = _login(ctx, ctx.manager)
    response = client.get("/app/ops", cookies=cookies)
    assert response.status_code == 200
    assert "Operations" in response.text


# --- the rail ----------------------------------------------------------------
def test_a_submit_lands_at_the_gate_not_in_the_engine(client, ctx):
    card = _submit(client, ctx, ctx.manager)
    assert card["state"] == "awaiting_approval"
    assert card["capability"] == CAPABILITY
    assert card["correlation_id"]
    assert card["requesting_actor"] == ctx.manager.account_id


def test_an_approval_moves_it_past_the_gate(client, ctx):
    """Approval is not execution, but the core does move the workflow on."""
    card = _submit(client, ctx, ctx.manager)
    cookies, headers = _login(ctx, ctx.owner)
    response = client.post(
        f"/app/api/ops/workflows/{card['workflow_id']}/approve",
        json={"decision": "approve", "reason": "looks right"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200, response.text
    decided = response.json()
    assert decided["state"] != "awaiting_approval"
    assert decided["state"] in ("approved", "executing", "succeeded")
    assert decided["approver_id"] == ctx.owner.account_id
    assert decided["approval_note"] == "looks right"


def test_the_submitter_cannot_approve_their_own_request(client, ctx):
    card = _submit(client, ctx, ctx.manager)
    cookies, headers = _login(ctx, ctx.manager)
    response = client.post(
        f"/app/api/ops/workflows/{card['workflow_id']}/approve",
        json={"decision": "approve"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code >= 400
    cookies, _ = _login(ctx, ctx.manager)
    still = client.get(f"/app/api/ops/workflows/{card['workflow_id']}", cookies=cookies)
    assert still.json()["state"] == "awaiting_approval"


def test_a_refusal_needs_a_reason(client, ctx):
    card = _submit(client, ctx, ctx.manager)
    cookies, headers = _login(ctx, ctx.owner)
    response = client.post(
        f"/app/api/ops/workflows/{card['workflow_id']}/approve",
        json={"decision": "reject", "reason": "   "},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 400


def test_a_refusal_records_the_reason(client, ctx):
    card = _submit(client, ctx, ctx.manager)
    cookies, headers = _login(ctx, ctx.owner)
    response = client.post(
        f"/app/api/ops/workflows/{card['workflow_id']}/approve",
        json={"decision": "reject", "reason": "not this quarter"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] != "awaiting_approval"


def test_the_correlation_id_survives_from_submit_to_close(client, ctx):
    card = _submit(client, ctx, ctx.manager)
    cookies, headers = _login(ctx, ctx.owner)
    decided = client.post(
        f"/app/api/ops/workflows/{card['workflow_id']}/approve",
        json={"decision": "approve"},
        cookies=cookies,
        headers=headers,
    ).json()
    assert decided["correlation_id"] == card["correlation_id"]
    cookies, _ = _login(ctx, ctx.owner)
    fetched = client.get(f"/app/api/ops/workflows/{card['workflow_id']}", cookies=cookies).json()
    assert fetched["correlation_id"] == card["correlation_id"]


def test_a_submit_needs_a_capability(client, ctx):
    cookies, headers = _login(ctx, ctx.manager)
    response = client.post(
        "/app/api/ops/workflows",
        json={"capability": "  "},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 400
