"""The owner cockpit (P6.3).

The cockpit is read-only, and the numbers on it must be the pack's numbers — not
a re-implementation that could drift. So one test proves the bridge returns
exactly what a direct call to the pack's compute function returns, and the others
prove the gate holds and the tenant scoping is real.
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
from helix_codex_app.modules.cockpit.service import owner_cards
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

AS_OF = "2026-09-15T00:00:00Z"
COCKPIT_ROUTES = (
    "/app/cockpit",
    "/app/cockpit/owner",
    "/app/api/cockpit/summary",
)
FIVE_LABELS = (
    "Active athletes",
    "MRR (USD)",
    "Attendance (7d)",
    "At-risk athletes",
    "Facility utilisation",
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


def _login(ctx, account) -> dict:
    token, _session = ctx.store.issue_session(account)
    return {SESSION_COOKIE: token}


# --- the gate ----------------------------------------------------------------
def test_an_employee_is_refused_every_cockpit_route(client, ctx):
    cookies = _login(ctx, ctx.employee)
    for route in COCKPIT_ROUTES:
        response = client.get(route, cookies=cookies)
        assert response.status_code == 403, f"{route} returned {response.status_code}"


def test_a_manager_can_open_the_cockpit(client, ctx):
    cookies = _login(ctx, ctx.manager)
    response = client.get("/app/cockpit", cookies=cookies)
    assert response.status_code == 200
    assert "The Cockpit" in response.text


def test_an_owner_can_open_the_owner_board(client, ctx):
    cookies = _login(ctx, ctx.owner)
    response = client.get("/app/cockpit/owner", cookies=cookies)
    assert response.status_code == 200


# --- the numbers are the pack's numbers --------------------------------------
def test_the_bridge_returns_exactly_what_a_direct_compute_returns(ctx):
    """No re-implementation: the bridge calls the pack's own compute function."""
    from capabilities.sports_academy import build_synthetic_academy
    from capabilities.sports_academy.cockpit_views.owner_dashboard import (
        compute_owner_dashboard,
    )
    from capabilities.sports_academy.contracts import build_academy_connectors
    from connectors.contracts import ConnectorContext

    account = ctx.owner
    context = ConnectorContext(
        account.tenant_id,
        account.domain_id,
        account.client_id,
        actor="direct",
        correlation_id="direct",
        data_mode="simulated_realistic",
    )
    fixtures = build_synthetic_academy(account.tenant_id, account.client_id, AS_OF)
    direct = compute_owner_dashboard(context, build_academy_connectors(context, fixtures), AS_OF)

    served = cockpit_bridge.owner_summary(account, as_of=AS_OF)

    assert served["kpis"] == direct["kpis"]
    assert served["attendance_7d"] == direct["attendance_7d"]
    assert served["at_risk_athletes"] == direct["at_risk_athletes"]
    assert served["sessions_total"] == direct["sessions_total"]


def test_the_owner_board_shows_five_cards(ctx):
    cards = owner_cards(cockpit_bridge.owner_summary(ctx.owner, as_of=AS_OF))
    assert len(cards) == 5
    assert tuple(card["label"] for card in cards) == FIVE_LABELS
    assert all(card["value"] not in (None, "") for card in cards)


def test_the_served_page_carries_all_five_numbers(client, ctx):
    cookies = _login(ctx, ctx.owner)
    response = client.get("/app/cockpit/owner", cookies=cookies)
    assert response.status_code == 200
    for label in FIVE_LABELS:
        assert label in response.text
    assert "simulated_realistic" in response.text


def test_the_summary_api_serves_the_same_numbers_as_the_bridge(client, ctx):
    cookies = _login(ctx, ctx.owner)
    served = client.get("/app/api/cockpit/summary", cookies=cookies).json()
    assert set(served["kpis"]) >= {"active_athletes", "mrr", "facility_utilization"}
    assert served["data_mode"] == "simulated_realistic"


# --- the tenant boundary -----------------------------------------------------
def test_a_foreign_tenant_owner_does_not_see_another_tenants_queue(client, ctx):
    """The approval queue is tenant-scoped, so a foreign owner sees an empty one."""
    token, _session = ctx.store.issue_session(ctx.manager)
    session = ctx.store.verify(token)
    assert session is not None
    manager_cookies = {SESSION_COOKIE: token}
    manager_headers = {"X-CSRF-Token": session.csrf_token}

    submitted = client.post(
        "/app/api/ops/workflows",
        json={"capability": "wfm_forecast"},
        cookies=manager_cookies,
        headers=manager_headers,
    )
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_id"]

    own_view = client.get("/app/cockpit/owner", cookies=manager_cookies)
    assert workflow_id in own_view.text

    outsider_cookies = _login(ctx, ctx.outsider)
    foreign_view = client.get("/app/cockpit/owner", cookies=outsider_cookies)
    assert foreign_view.status_code == 200
    assert workflow_id not in foreign_view.text


def test_the_cockpit_refuses_an_account_with_no_tenant(ctx):
    from helix_codex_app.errors import EngineUnavailableError

    stripped = SimpleNamespace(**{**ctx.owner.__dict__, "tenant_id": ""})
    with pytest.raises(EngineUnavailableError):
        cockpit_bridge.owner_summary(stripped, as_of=AS_OF)
