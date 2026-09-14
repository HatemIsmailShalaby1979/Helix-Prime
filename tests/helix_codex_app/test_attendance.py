"""Attendance tests (P4.3).

Service-level tests prove the punch rules and the manager-trustworthy
summary: punching in while a punch is open raises, punching out with nothing
open raises, the server decides the timestamp, punches are append-only rows
that each carry one governed node sharing the punch correlation_id, an
employee sees only their own records, a manager sees their org unit, and the
summary buckets completed pairs to their punch-in date so a pair crossing
midnight sums correctly. HTTP tests drive the mounted attendance router
through TestClient for the screen, the punch toggle with CSRF, the record and
summary APIs, the HTMX fragment path, and cross-tenant isolation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.modules.attendance import service as attendance_service
from helix_codex_app.modules.attendance.repository import PUNCH_IN, PUNCH_OUT, AttendanceRepository
from helix_codex_app.modules.attendance.service import AttendanceService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore


class _FakeDatetime(datetime):
    """A datetime whose now() is pinned, for deterministic today windows."""

    fake_now = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        if tz is not None:
            return cls.fake_now.astimezone(tz)
        return cls.fake_now


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    coaching = repo.create_org_unit(domain_a.domain_id, "Coaching")
    marketing = repo.create_org_unit(domain_a.domain_id, "Marketing")
    owner = repo.create_account(
        domain_a.domain_id, "owner", role_id="owner", password_hash=hash_password("x")
    )
    layla = repo.create_account(
        domain_a.domain_id,
        "layla",
        role_id="manager",
        org_unit_id=coaching.unit_id,
        password_hash=hash_password("x"),
    )
    amira = repo.create_account(
        domain_a.domain_id,
        "amira",
        role_id="employee",
        org_unit_id=coaching.unit_id,
        password_hash=hash_password("x"),
    )
    omar = repo.create_account(
        domain_a.domain_id,
        "omar",
        role_id="employee",
        org_unit_id=coaching.unit_id,
        password_hash=hash_password("x"),
    )
    tarek = repo.create_account(
        domain_a.domain_id,
        "tarek",
        role_id="employee",
        org_unit_id=marketing.unit_id,
        password_hash=hash_password("x"),
    )
    external = repo.create_account(
        domain_a.domain_id, "ext", role_id="external", password_hash=hash_password("x")
    )
    samira = repo.create_account(
        domain_a.domain_id, "samira", role_id="manager", password_hash=hash_password("x")
    )
    ghada = repo.create_account(
        domain_b.domain_id,
        "ghada",
        role_id="employee",
        password_hash=hash_password("x"),
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    service = AttendanceService(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        coaching=coaching,
        marketing=marketing,
        owner=owner,
        layla=layla,
        amira=amira,
        omar=omar,
        tarek=tarek,
        external=external,
        samira=samira,
        ghada=ghada,
        settings=settings,
        store=store,
        service=service,
        punch_repo=AttendanceRepository(conn),
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


def _punch_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM punch_records").fetchone()[0]


def _seed(ctx, account, punch_type: str, punched_at: str) -> None:
    ctx.punch_repo.insert_punch(
        tenant_id=account.tenant_id,
        domain_id=account.domain_id,
        account_id=account.account_id,
        punch_type=punch_type,
        punched_at=punched_at,
    )


# --- one-open-punch rule ---


def test_punch_in_writes_one_record_and_one_node(ctx):
    before_rows = _punch_count(ctx.conn)
    before_nodes = _node_count(ctx.conn, "punch")
    punch = ctx.service.punch_in(ctx.amira, source="web", device_id="test")
    assert _punch_count(ctx.conn) == before_rows + 1
    assert _node_count(ctx.conn, "punch") == before_nodes + 1
    assert punch.punch_type == PUNCH_IN
    assert punch.account_id == ctx.amira.account_id
    assert punch.source == "web"
    assert punch.device_id == "test"
    assert punch.correlation_id is not None


def test_server_decides_the_timestamp(ctx):
    before = datetime.now(timezone.utc)
    punch = ctx.service.punch_in(ctx.amira)
    after = datetime.now(timezone.utc)
    stamped = datetime.fromisoformat(punch.punched_at)
    assert before <= stamped <= after


def test_double_punch_in_raises(ctx):
    ctx.service.punch_in(ctx.amira)
    with pytest.raises(ValueError, match="already open"):
        ctx.service.punch_in(ctx.amira)


def test_punch_out_with_nothing_open_raises(ctx):
    with pytest.raises(ValueError, match="no punch is open"):
        ctx.service.punch_out(ctx.amira)


def test_punch_in_out_round_trip_closes_the_punch(ctx):
    ctx.service.punch_in(ctx.amira)
    assert ctx.service.current_status(ctx.amira) is not None
    out = ctx.service.punch_out(ctx.amira)
    assert out.punch_type == PUNCH_OUT
    assert ctx.service.current_status(ctx.amira) is None


def test_punch_out_after_out_raises(ctx):
    ctx.service.punch_in(ctx.amira)
    ctx.service.punch_out(ctx.amira)
    with pytest.raises(ValueError, match="no punch is open"):
        ctx.service.punch_out(ctx.amira)


def test_no_punches_means_no_open_punch(ctx):
    assert ctx.service.current_status(ctx.amira) is None


# --- append-only ---


def test_punches_are_append_only_rows(ctx):
    first = ctx.service.punch_in(ctx.amira)
    ctx.service.punch_out(ctx.amira)
    second = ctx.service.punch_in(ctx.amira)
    assert second.punch_id != first.punch_id
    assert _punch_count(ctx.conn) == 3
    assert (
        ctx.service.list_records(
            ctx.amira, "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
        )
        is not None
    )


def test_punch_node_shares_the_punch_correlation_id(ctx):
    punch = ctx.service.punch_in(ctx.amira)
    row = ctx.conn.execute(
        "SELECT correlation_id FROM nodes WHERE kind = 'punch' ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert row["correlation_id"] == punch.correlation_id


def test_repository_has_no_update_or_delete_path(ctx):
    source = "\n".join(AttendanceRepository.__dict__.keys())
    assert "update" not in source
    assert "delete" not in source


# --- visibility ---


def test_employee_sees_only_own_records(ctx):
    ctx.service.punch_in(ctx.amira)
    ctx.service.punch_out(ctx.amira)
    ctx.service.punch_in(ctx.omar)
    records = ctx.service.list_records(
        ctx.amira, "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    assert {r.account_id for r in records} == {ctx.amira.account_id}


def test_manager_sees_their_org_unit(ctx):
    ctx.service.punch_in(ctx.amira)
    ctx.service.punch_out(ctx.amira)
    ctx.service.punch_in(ctx.omar)
    ctx.service.punch_out(ctx.omar)
    ctx.service.punch_in(ctx.tarek)
    records = ctx.service.list_records(
        ctx.layla, "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    assert {r.account_id for r in records} == {ctx.amira.account_id, ctx.omar.account_id}


def test_manager_without_org_unit_sees_only_self(ctx):
    ctx.service.punch_in(ctx.amira)
    records = ctx.service.list_records(
        ctx.samira, "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    assert records == []


def test_owner_sees_whole_domain(ctx):
    ctx.service.punch_in(ctx.amira)
    ctx.service.punch_in(ctx.tarek)
    records = ctx.service.list_records(
        ctx.owner, "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    assert {r.account_id for r in records} == {ctx.amira.account_id, ctx.tarek.account_id}


def test_foreign_tenant_sees_nothing(ctx):
    ctx.service.punch_in(ctx.amira)
    records = ctx.service.list_records(
        ctx.ghada, "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    assert records == []


# --- summary ---


def test_summary_sums_correctly_across_a_day_boundary(ctx):
    _seed(ctx, ctx.amira, PUNCH_IN, "2026-09-14T23:30:00+00:00")
    _seed(ctx, ctx.amira, PUNCH_OUT, "2026-09-15T00:30:00+00:00")
    summary = ctx.service.summary(
        ctx.amira, "2026-09-14T00:00:00+00:00", "2026-09-16T00:00:00+00:00"
    )
    assert summary["days"] == [{"date": "2026-09-14", "minutes": 60}]
    assert summary["total_minutes"] == 60


def test_summary_ignores_punch_outside_the_window(ctx):
    _seed(ctx, ctx.amira, PUNCH_IN, "2026-09-13T23:30:00+00:00")
    _seed(ctx, ctx.amira, PUNCH_OUT, "2026-09-14T00:30:00+00:00")
    summary = ctx.service.summary(
        ctx.amira, "2026-09-14T00:00:00+00:00", "2026-09-16T00:00:00+00:00"
    )
    assert summary["total_minutes"] == 0


def test_summary_open_punch_contributes_zero(ctx):
    _seed(ctx, ctx.amira, PUNCH_IN, "2026-09-14T09:00:00+00:00")
    summary = ctx.service.summary(
        ctx.amira, "2026-09-14T00:00:00+00:00", "2026-09-16T00:00:00+00:00"
    )
    assert summary["days"] == []
    assert summary["total_minutes"] == 0


def test_summary_rejects_inverted_window(ctx):
    with pytest.raises(ValueError, match="end after it starts"):
        ctx.service.summary(ctx.amira, "2026-09-16T00:00:00+00:00", "2026-09-14T00:00:00+00:00")


def test_summary_for_employee_counts_only_self(ctx):
    _seed(ctx, ctx.amira, PUNCH_IN, "2026-09-14T09:00:00+00:00")
    _seed(ctx, ctx.amira, PUNCH_OUT, "2026-09-14T11:00:00+00:00")
    _seed(ctx, ctx.omar, PUNCH_IN, "2026-09-14T09:00:00+00:00")
    _seed(ctx, ctx.omar, PUNCH_OUT, "2026-09-14T10:00:00+00:00")
    own = ctx.service.summary(ctx.amira, "2026-09-14T00:00:00+00:00", "2026-09-15T00:00:00+00:00")
    assert own["total_minutes"] == 120


def test_summary_for_manager_totals_org_unit(ctx):
    _seed(ctx, ctx.amira, PUNCH_IN, "2026-09-14T09:00:00+00:00")
    _seed(ctx, ctx.amira, PUNCH_OUT, "2026-09-14T11:00:00+00:00")
    _seed(ctx, ctx.tarek, PUNCH_IN, "2026-09-14T09:00:00+00:00")
    _seed(ctx, ctx.tarek, PUNCH_OUT, "2026-09-14T10:00:00+00:00")
    unit = ctx.service.summary(ctx.layla, "2026-09-14T00:00:00+00:00", "2026-09-15T00:00:00+00:00")
    assert unit["total_minutes"] == 120


# --- today running total (pinned clock) ---


def test_today_minutes_zero_when_nothing_punched(monkeypatch, ctx):
    monkeypatch.setattr(attendance_service, "datetime", _FakeDatetime)
    assert ctx.service.today_minutes(ctx.amira) == 0


def test_today_minutes_with_closed_pairs(monkeypatch, ctx):
    monkeypatch.setattr(attendance_service, "datetime", _FakeDatetime)
    _seed(ctx, ctx.amira, PUNCH_IN, "2026-09-15T08:00:00+00:00")
    _seed(ctx, ctx.amira, PUNCH_OUT, "2026-09-15T09:00:00+00:00")
    assert ctx.service.today_minutes(ctx.amira) == 60


def test_today_minutes_accrues_the_open_punch(monkeypatch, ctx):
    monkeypatch.setattr(attendance_service, "datetime", _FakeDatetime)
    _seed(ctx, ctx.amira, PUNCH_IN, "2026-09-15T09:00:00+00:00")
    assert ctx.service.today_minutes(ctx.amira) == 60


# --- HTTP ---


def test_attendance_screen_renders(ctx, client):
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/attendance", cookies=cookies)
    assert response.status_code == 200
    assert "Attendance" in response.text
    assert "punch-clock" in response.text
    assert "Punch in" in response.text


def test_attendance_screen_requires_auth(ctx, client):
    response = client.get("/app/attendance")
    assert response.status_code == 401


def test_attendance_screen_denied_for_external(ctx, client):
    cookies, _ = _login(ctx, ctx.external)
    response = client.get("/app/attendance", cookies=cookies)
    assert response.status_code == 403


def test_punch_api_opens_and_audits(ctx, client):
    before_nodes = _node_count(ctx.conn, "punch")
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/attendance/punch",
        data={"action": "in", "source": "web", "device_id": "test"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["punch_type"] == "in"
    assert payload["account_id"] == ctx.amira.account_id
    assert _node_count(ctx.conn, "punch") == before_nodes + 1


def test_punch_api_requires_csrf(ctx, client):
    cookies, _ = _login(ctx, ctx.amira)
    response = client.post("/app/api/attendance/punch", data={"action": "in"}, cookies=cookies)
    assert response.status_code == 403


def test_punch_api_double_in_is_400(ctx, client):
    cookies, headers = _login(ctx, ctx.amira)
    first = client.post(
        "/app/api/attendance/punch", data={"action": "in"}, cookies=cookies, headers=headers
    )
    assert first.status_code == 201
    second = client.post(
        "/app/api/attendance/punch", data={"action": "in"}, cookies=cookies, headers=headers
    )
    assert second.status_code == 400


def test_punch_api_out_with_nothing_open_is_400(ctx, client):
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/attendance/punch", data={"action": "out"}, cookies=cookies, headers=headers
    )
    assert response.status_code == 400


def test_punch_api_omitted_action_toggles_from_state(ctx, client):
    cookies, headers = _login(ctx, ctx.amira)
    opened = client.post("/app/api/attendance/punch", data={}, cookies=cookies, headers=headers)
    assert opened.status_code == 201
    assert opened.json()["punch_type"] == "in"
    closed = client.post("/app/api/attendance/punch", data={}, cookies=cookies, headers=headers)
    assert closed.status_code == 201
    assert closed.json()["punch_type"] == "out"


def test_punch_api_htmx_fragment_updates_label(ctx, client):
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/attendance/punch",
        data={"action": "in"},
        cookies=cookies,
        headers={**headers, "hx-request": "true"},
    )
    assert response.status_code == 200
    assert 'id="punch-clock"' in response.text
    assert "Punch out" in response.text
    assert "punch-clock__status--on" in response.text


def test_records_api_returns_visible_records(ctx, client):
    ctx.service.punch_in(ctx.amira)
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(
        "/app/api/attendance/records",
        params={"from": "2026-01-01T00:00:00+00:00", "to": "2027-01-01T00:00:00+00:00"},
        cookies=cookies,
    )
    assert response.status_code == 200
    payload = response.json()
    assert {r["account_id"] for r in payload["records"]} == {ctx.amira.account_id}


def test_records_api_requires_both_range_edges(ctx, client):
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(
        "/app/api/attendance/records", params={"from": "2026-09-14T00:00:00+00:00"}, cookies=cookies
    )
    assert response.status_code == 400


def test_summary_api_route_shape(ctx, client):
    _seed(ctx, ctx.amira, PUNCH_IN, "2026-09-14T09:00:00+00:00")
    _seed(ctx, ctx.amira, PUNCH_OUT, "2026-09-14T10:00:00+00:00")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(
        "/app/api/attendance/summary",
        params={"from": "2026-09-14T00:00:00+00:00", "to": "2026-09-15T00:00:00+00:00"},
        cookies=cookies,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_minutes"] == 60
    assert payload["days"] == [{"date": "2026-09-14", "minutes": 60}]


def test_summary_api_inverted_range_is_400(ctx, client):
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(
        "/app/api/attendance/summary",
        params={"from": "2026-09-15T00:00:00+00:00", "to": "2026-09-14T00:00:00+00:00"},
        cookies=cookies,
    )
    assert response.status_code == 400


def test_manager_records_api_scopes_to_org_unit(ctx, client):
    ctx.service.punch_in(ctx.tarek)
    cookies, _ = _login(ctx, ctx.layla)
    response = client.get(
        "/app/api/attendance/records",
        params={"from": "2000-01-01T00:00:00+00:00", "to": "2100-01-01T00:00:00+00:00"},
        cookies=cookies,
    )
    assert response.status_code == 200
    assert response.json()["records"] == []
