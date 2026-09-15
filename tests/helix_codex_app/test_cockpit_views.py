"""The coach, parent, and control-plane views (P6.4).

Two of these views are the same shape as the owner board and are checked the same
way. The control plane is the interesting one: it shows the halt state and the
audit trail, so the tests are about what it refuses to do and about the audit
rows being this workspace's and nobody else's.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.integration import engine_bridge
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

NEW_ROUTES = (
    "/app/cockpit/coach",
    "/app/cockpit/parent",
    "/app/cockpit/control-plane",
)
WRITE_MARKERS = (
    "hx-post",
    "<form",
    "/halt/engage",
    "/halt/release",
    "/api/ops/workflows",
)


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    owner = repo.create_account(
        domain_a.domain_id, "owner", role_id="owner", password_hash=hash_password("x")
    )
    manager = repo.create_account(
        domain_a.domain_id, "layla", role_id="manager", password_hash=hash_password("x")
    )
    employee = repo.create_account(
        domain_a.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    outsider = repo.create_account(
        domain_b.domain_id, "outsider", role_id="owner", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        owner=owner,
        manager=manager,
        employee=employee,
        outsider=outsider,
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
        json={"capability": "wfm_forecast"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _submit_and_approve(client, ctx) -> dict:
    """Drive a workflow far enough that the core has audited it.

    A submit alone leaves the workflow at the gate and writes nothing to the
    audit ledger; the audit rows appear once the decision is taken.
    """
    card = _submit(client, ctx, ctx.manager)
    cookies, headers = _session(ctx, ctx.owner)
    decided = client.post(
        f"/app/api/ops/workflows/{card['workflow_id']}/approve",
        json={"decision": "approve"},
        cookies=cookies,
        headers=headers,
    )
    assert decided.status_code == 200, decided.text
    return card


# --- the gate, on every new view ---------------------------------------------
def test_an_employee_is_refused_every_new_view(client, ctx):
    cookies, _ = _session(ctx, ctx.employee)
    for route in NEW_ROUTES:
        response = client.get(route, cookies=cookies)
        assert response.status_code == 403, f"{route} returned {response.status_code}"


def test_a_manager_can_open_every_new_view(client, ctx):
    cookies, _ = _session(ctx, ctx.manager)
    for route in NEW_ROUTES:
        response = client.get(route, cookies=cookies)
        assert response.status_code == 200, f"{route} returned {response.status_code}"


# --- the coach and parent views ----------------------------------------------
def test_the_coach_view_shows_a_coach_and_their_day(client, ctx):
    cookies, _ = _session(ctx, ctx.owner)
    response = client.get("/app/cockpit/coach", cookies=cookies)
    assert response.status_code == 200
    assert "Coach board" in response.text
    assert "Today's sessions" in response.text
    assert "simulated_realistic" in response.text


def test_the_coach_view_accepts_an_explicit_coach(client, ctx):
    from helix_codex_app.integration import cockpit_bridge

    options = cockpit_bridge.picker_options(ctx.owner)["coaches"]
    assert options
    cookies, _ = _session(ctx, ctx.owner)
    response = client.get(f"/app/cockpit/coach?coach_id={options[-1]['id']}", cookies=cookies)
    assert response.status_code == 200
    assert options[-1]["label"] in response.text


def test_the_coach_view_reports_an_unknown_coach(client, ctx):
    cookies, _ = _session(ctx, ctx.owner)
    response = client.get("/app/cockpit/coach?coach_id=not-a-coach", cookies=cookies)
    assert response.status_code == 404


def test_the_parent_view_shows_a_family(client, ctx):
    cookies, _ = _session(ctx, ctx.owner)
    response = client.get("/app/cockpit/parent", cookies=cookies)
    assert response.status_code == 200
    assert "Family view" in response.text
    assert "Schedule" in response.text
    assert "Fees" in response.text


def test_the_parent_view_reports_an_unknown_family(client, ctx):
    cookies, _ = _session(ctx, ctx.owner)
    response = client.get("/app/cockpit/parent?family_id=not-a-family", cookies=cookies)
    assert response.status_code == 404


# --- the control plane is read-only ------------------------------------------
def test_the_control_plane_offers_no_write_action(client, ctx):
    cookies, _ = _session(ctx, ctx.owner)
    response = client.get("/app/cockpit/control-plane", cookies=cookies)
    assert response.status_code == 200
    for marker in WRITE_MARKERS:
        assert marker not in response.text, f"the control plane exposes {marker!r}"


def test_the_control_plane_has_no_post_route(client):
    posted = client.post("/app/cockpit/control-plane")
    assert posted.status_code == 405


def test_the_control_plane_calls_the_bridge_policy_gate(ctx, monkeypatch):
    from helix_codex_app.modules.cockpit.service import CockpitService

    called = {"value": False}

    def _gate(account):
        called["value"] = account.account_id == ctx.owner.account_id

    monkeypatch.setattr(engine_bridge, "authorize_read", _gate)
    monkeypatch.setattr(engine_bridge, "list_workflows", lambda account, limit=200: [])
    monkeypatch.setattr(engine_bridge, "recent_audit_entries", lambda limit=500: [])
    monkeypatch.setattr(engine_bridge, "list_engines", lambda: [])
    monkeypatch.setattr(engine_bridge, "kill_switch_status", lambda tenant_id: {"engaged": False})
    monkeypatch.setattr(engine_bridge, "audit_chain_verified", lambda: True)
    CockpitService().control_plane(ctx.owner)
    assert called["value"] is True


def test_the_control_plane_shows_engine_status_and_the_halt_state(client, ctx):
    cookies, _ = _session(ctx, ctx.owner)
    response = client.get("/app/cockpit/control-plane", cookies=cookies)
    assert "Engines" in response.text
    assert "Halt state" in response.text
    assert "Audit chain" in response.text
    # all six engines are named
    for engine in engine_bridge.list_engines():
        assert engine["name"] in response.text


# --- the audit panel ---------------------------------------------------------
def test_the_audit_panel_shows_this_workspaces_rows(client, ctx):
    card = _submit_and_approve(client, ctx)
    correlation = card["correlation_id"]

    recorded = [
        row
        for row in engine_bridge.recent_audit_entries(limit=200)
        if row.get("correlation_id") == correlation
    ]
    assert recorded, (
        f"no audit row for {correlation}; "
        f"rows={[r.get('correlation_id') for r in engine_bridge.recent_audit_entries(limit=50)]}"
    )

    cookies, _ = _session(ctx, ctx.owner)
    response = client.get("/app/cockpit/control-plane", cookies=cookies)
    assert response.status_code == 200
    assert correlation in response.text


def test_a_foreign_tenant_does_not_see_another_workspaces_audit_rows(client, ctx):
    card = _submit_and_approve(client, ctx)

    outsider_cookies, _ = _session(ctx, ctx.outsider)
    foreign = client.get("/app/cockpit/control-plane", cookies=outsider_cookies)
    assert foreign.status_code == 200
    assert card["correlation_id"] not in foreign.text
