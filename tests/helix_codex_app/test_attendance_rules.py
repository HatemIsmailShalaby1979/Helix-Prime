"""Attendance rule tests (P4.4 close-out).

Prove the attendance phase rules in one place: exactly one open punch per
account, punches are append-only rows with no update or delete path, and
visibility is manager-logical (an owner sees the whole domain, a manager
sees their org unit or just themselves when they have none, everyone else
sees only themselves). The one-open rule is per account: one account's open
punch never blocks another account. Service-level tests pass through
AttendanceService; HTTP tests drive the records API through TestClient.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.modules.attendance.repository import PUNCH_IN, AttendanceRepository
from helix_codex_app.modules.attendance.service import AttendanceService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

FROM = "2000-01-01T00:00:00+00:00"
TO = "2100-01-01T00:00:00+00:00"


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


def _punch_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM punch_records").fetchone()[0]


def _seed_open(ctx, account, punched_at: str) -> None:
    ctx.punch_repo.insert_punch(
        tenant_id=account.tenant_id,
        domain_id=account.domain_id,
        account_id=account.account_id,
        punch_type=PUNCH_IN,
        punched_at=punched_at,
    )


def _close(ctx, account, punched_at: str) -> None:
    ctx.punch_repo.insert_punch(
        tenant_id=account.tenant_id,
        domain_id=account.domain_id,
        account_id=account.account_id,
        punch_type="out",
        punched_at=punched_at,
    )


# --- rule: exactly one open punch per account ---


def test_a_punch_in_right_after_an_open_one_raises(ctx):
    ctx.service.punch_in(ctx.amira)
    with pytest.raises(ValueError, match="already open"):
        ctx.service.punch_in(ctx.amira)


def test_a_punch_out_with_nothing_open_raises(ctx):
    with pytest.raises(ValueError, match="no punch is open"):
        ctx.service.punch_out(ctx.amira)


def test_the_rule_is_per_account_not_global(ctx):
    ctx.service.punch_in(ctx.amira)
    ctx.service.punch_in(ctx.omar)
    assert ctx.service.current_status(ctx.amira) is not None
    assert ctx.service.current_status(ctx.omar) is not None


def test_an_open_punch_only_closes_for_its_owner(ctx):
    ctx.service.punch_in(ctx.amira)
    with pytest.raises(ValueError, match="no punch is open"):
        ctx.service.punch_out(ctx.omar)
    closed = ctx.service.punch_out(ctx.amira)
    assert closed.punch_type == "out"
    assert ctx.service.current_status(ctx.amira) is None


def test_a_closed_punch_allows_a_new_one(ctx):
    ctx.service.punch_in(ctx.amira)
    ctx.service.punch_out(ctx.amira)
    reopened = ctx.service.punch_in(ctx.amira)
    assert reopened.punch_type == PUNCH_IN


# --- rule: append-only ---


def test_every_punch_is_a_new_row(ctx):
    first = ctx.service.punch_in(ctx.amira)
    ctx.service.punch_out(ctx.amira)
    second = ctx.service.punch_in(ctx.amira)
    assert _punch_count(ctx.conn) == 3
    assert second.punch_id != first.punch_id


def test_the_repository_has_no_update_or_delete_method(ctx):
    names = set(AttendanceRepository.__dict__)
    assert not any("update" in name for name in names)
    assert "delete" not in names
    assert _punch_count(ctx.conn) == 0


def test_closing_keeps_the_open_row(ctx):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    rows = ctx.conn.execute("SELECT punch_type FROM punch_records").fetchall()
    assert [row["punch_type"] for row in rows] == ["in", "out"]
    assert _punch_count(ctx.conn) == 2


# --- rule: manager org-unit visibility ---


def test_open_punches_seed_the_org_units(ctx):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    _seed_open(ctx, ctx.omar, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.omar, "2026-09-14T12:00:00+00:00")
    _seed_open(ctx, ctx.tarek, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.tarek, "2026-09-14T12:00:00+00:00")
    visible = ctx.service.list_records(ctx.layla, FROM, TO)
    assert {r.account_id for r in visible} == {ctx.amira.account_id, ctx.omar.account_id}


def test_manager_does_not_see_the_other_org_unit(ctx):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    _seed_open(ctx, ctx.tarek, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.tarek, "2026-09-14T12:00:00+00:00")
    visible = ctx.service.list_records(ctx.layla, FROM, TO)
    assert ctx.tarek.account_id not in {r.account_id for r in visible}


def test_a_manager_with_no_org_unit_sees_only_self(ctx):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    _seed_open(ctx, ctx.samira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.samira, "2026-09-14T12:00:00+00:00")
    visible = ctx.service.list_records(ctx.samira, FROM, TO)
    assert {r.account_id for r in visible} == {ctx.samira.account_id}


def test_owner_sees_the_whole_domain(ctx):
    for account in (ctx.amira, ctx.omar, ctx.tarek):
        _seed_open(ctx, account, "2026-09-14T09:00:00+00:00")
        _close(ctx, account, "2026-09-14T12:00:00+00:00")
    visible = ctx.service.list_records(ctx.owner, FROM, TO)
    assert {r.account_id for r in visible} == {
        ctx.amira.account_id,
        ctx.omar.account_id,
        ctx.tarek.account_id,
    }


def test_employee_sees_only_self(ctx):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    _seed_open(ctx, ctx.omar, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.omar, "2026-09-14T12:00:00+00:00")
    visible = ctx.service.list_records(ctx.amira, FROM, TO)
    assert {r.account_id for r in visible} == {ctx.amira.account_id}


def test_foreign_tenant_sees_nothing(ctx):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    visible = ctx.service.list_records(ctx.ghada, FROM, TO)
    assert visible == []


def test_manager_summary_totals_only_the_org_unit(ctx):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    _seed_open(ctx, ctx.omar, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.omar, "2026-09-14T09:30:00+00:00")
    _seed_open(ctx, ctx.tarek, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.tarek, "2026-09-14T18:00:00+00:00")
    summary = ctx.service.summary(
        ctx.layla, "2026-09-14T00:00:00+00:00", "2026-09-15T00:00:00+00:00"
    )
    assert summary["total_minutes"] == 210


# --- HTTP scope is the same rule ---


def test_records_api_scopes_to_the_managers_org_unit(ctx, client):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    _seed_open(ctx, ctx.tarek, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.tarek, "2026-09-14T12:00:00+00:00")
    cookies, _ = _login(ctx, ctx.layla)
    response = client.get(
        "/app/api/attendance/records", params={"from": FROM, "to": TO}, cookies=cookies
    )
    assert response.status_code == 200
    payload = response.json()
    assert {r["account_id"] for r in payload["records"]} == {ctx.amira.account_id}


def test_records_api_foreign_tenant_is_empty(ctx, client):
    _seed_open(ctx, ctx.amira, "2026-09-14T09:00:00+00:00")
    _close(ctx, ctx.amira, "2026-09-14T12:00:00+00:00")
    cookies, _ = _login(ctx, ctx.ghada)
    response = client.get(
        "/app/api/attendance/records", params={"from": FROM, "to": TO}, cookies=cookies
    )
    assert response.status_code == 200
    assert response.json()["records"] == []
