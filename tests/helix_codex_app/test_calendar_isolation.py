"""Calendar isolation tests (P4.4 close-out).

Events and on-call shifts never cross tenants. Prove the whole phase rule
in one place: an event or shift written in tenant A is unreadable,
unupdatable, and unrespondable from tenant B; every tenant B list is empty;
tenant B coverage is a gap, not a leaked roster; and a shift cannot be
created naming a foreign account. Service-level tests pass through
CalendarService; HTTP tests drive the mounted router through TestClient.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import NotFoundError
from helix_codex_app.modules.calendar.service import CalendarService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

FROM = "2026-09-01T00:00:00+00:00"
TO = "2026-10-01T00:00:00+00:00"
WINDOW = "2026-09-10T12:00:00+00:00"


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
    amira = repo.create_account(
        domain_a.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    ghada = repo.create_account(
        domain_b.domain_id, "ghada", role_id="employee", password_hash=hash_password("x")
    )
    huda = repo.create_account(
        domain_b.domain_id, "huda", role_id="manager", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    service = CalendarService(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        owner=owner,
        amira=amira,
        ghada=ghada,
        huda=huda,
        settings=settings,
        store=store,
        service=service,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _login(ctx, account) -> tuple[dict, dict]:
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _node_count(conn, kind: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM nodes WHERE kind = ?", (kind,)).fetchone()[0]


def _make_event(ctx) -> str:
    event = ctx.service.create_event(
        ctx.amira,
        title="Intake meeting",
        starts_at="2026-09-01T09:00:00+00:00",
        ends_at="2026-09-01T10:00:00+00:00",
    )
    return event.event_id


def _make_shift(ctx) -> str:
    shift = ctx.service.create_shift(
        ctx.owner,
        starts_at="2026-09-10T09:00:00+00:00",
        ends_at="2026-09-10T17:00:00+00:00",
        primary_account_id=ctx.amira.account_id,
        backup_account_id=ctx.owner.account_id,
    )
    return shift.shift_id


# --- events never cross tenants ---


def test_foreign_event_read_is_not_found(ctx):
    event_id = _make_event(ctx)
    with pytest.raises(NotFoundError):
        ctx.service.get_event(ctx.ghada, event_id)


def test_foreign_event_list_is_empty(ctx):
    _make_event(ctx)
    assert ctx.service.list_events(ctx.ghada, FROM, TO) == []


def test_foreign_event_update_is_not_found(ctx):
    event_id = _make_event(ctx)
    with pytest.raises(NotFoundError):
        ctx.service.update_event(ctx.ghada, event_id, title="hijacked")


def test_foreign_event_cancel_is_not_found(ctx):
    event_id = _make_event(ctx)
    with pytest.raises(NotFoundError):
        ctx.service.cancel_event(ctx.ghada, event_id)


def test_foreign_event_respond_is_not_found(ctx):
    event_id = _make_event(ctx)
    with pytest.raises(NotFoundError):
        ctx.service.respond(ctx.ghada, event_id, "yes")


def test_event_write_from_ghada_writes_a_tenant_b_row(ctx):
    ghada_event = ctx.service.create_event(
        ctx.ghada,
        title="Tenant B sync",
        starts_at="2026-09-02T09:00:00+00:00",
        ends_at="2026-09-02T10:00:00+00:00",
    )
    assert ghada_event.tenant_id == "tenant-b"
    row = ctx.conn.execute(
        "SELECT tenant_id FROM events WHERE event_id = ?", (ghada_event.event_id,)
    ).fetchone()
    assert row["tenant_id"] == "tenant-b"
    node = ctx.conn.execute(
        "SELECT tenant_id FROM nodes WHERE kind = 'event' ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert node["tenant_id"] == "tenant-b"


def test_tenant_b_sees_only_its_own_events(ctx):
    ctx.service.create_event(
        ctx.amira,
        title="Tenant A meeting",
        starts_at="2026-09-02T09:00:00+00:00",
        ends_at="2026-09-02T10:00:00+00:00",
    )
    ghada_event = ctx.service.create_event(
        ctx.ghada,
        title="Tenant B sync",
        starts_at="2026-09-02T11:00:00+00:00",
        ends_at="2026-09-02T12:00:00+00:00",
    )
    listed = ctx.service.list_events(ctx.ghada, FROM, TO)
    assert len(listed) == 1
    assert listed[0].event_id == ghada_event.event_id
    assert listed[0].title == "Tenant B sync"


# --- on-call shifts never cross tenants ---


def test_foreign_shift_list_is_empty(ctx):
    _make_shift(ctx)
    assert ctx.service.list_shifts(ctx.ghada, FROM, TO) == []


def test_foreign_tenant_coverage_is_a_gap(ctx):
    _make_shift(ctx)
    coverage = ctx.service.current_oncall("tenant-b", WINDOW)
    assert coverage.covered is False
    assert coverage.status == "gap"
    assert coverage.shift is None


def test_foreign_tenant_next_shift_is_none(ctx):
    _make_shift(ctx)
    assert ctx.service.next_tenant_shift("tenant-b", "2026-09-01T00:00:00+00:00") is None


def test_shift_cannot_name_a_foreign_account(ctx):
    with pytest.raises(ValueError, match="unknown account"):
        ctx.service.create_shift(
            ctx.owner,
            starts_at="2026-09-10T09:00:00+00:00",
            ends_at="2026-09-10T17:00:00+00:00",
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.ghada.account_id,
        )


def test_shift_row_and_node_stay_in_tenant_a(ctx):
    shift_id = _make_shift(ctx)
    row = ctx.conn.execute(
        "SELECT tenant_id FROM oncall_shifts WHERE shift_id = ?", (shift_id,)
    ).fetchone()
    assert row["tenant_id"] == "tenant-a"
    node = ctx.conn.execute(
        "SELECT tenant_id FROM nodes WHERE kind = 'oncall_shift' ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert node["tenant_id"] == "tenant-a"


def test_tenant_b_can_roster_its_own_shifts(ctx):
    shift = ctx.service.create_shift(
        ctx.huda,
        starts_at="2026-09-12T09:00:00+00:00",
        ends_at="2026-09-12T17:00:00+00:00",
        primary_account_id=ctx.huda.account_id,
        backup_account_id=ctx.ghada.account_id,
    )
    assert shift.tenant_id == "tenant-b"


# --- HTTP never leaks across tenants ---


def test_events_api_is_empty_for_foreign_tenant(ctx, client):
    _make_event(ctx)
    cookies, _ = _login(ctx, ctx.ghada)
    response = client.get("/app/api/events", params={"from": FROM, "to": TO}, cookies=cookies)
    assert response.status_code == 200
    assert response.json()["events"] == []


def test_foreign_event_cancel_via_put_is_404(ctx, client):
    event_id = _make_event(ctx)
    cookies, headers = _login(ctx, ctx.ghada)
    response = client.put(
        f"/app/api/events/{event_id}",
        data={"status": "cancelled"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 404


def test_oncall_api_for_foreign_tenant_shows_a_gap(ctx, client, monkeypatch):
    from types import SimpleNamespace as NS

    _make_shift(ctx)

    def fake_adapt(**kwargs):
        return NS(
            error=None,
            engine_id="wfm",
            metrics={"optimal_agents": 63, "service_level_achieved": 0.913},
        )

    monkeypatch.setattr("engines.wfm.adapter.adapt", fake_adapt)
    cookies, _ = _login(ctx, ctx.ghada)
    response = client.get("/app/api/oncall", cookies=cookies)
    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage"]["status"] == "gap"
    assert payload["coverage"]["covered"] is False
    assert payload["next_shifts"] == []
