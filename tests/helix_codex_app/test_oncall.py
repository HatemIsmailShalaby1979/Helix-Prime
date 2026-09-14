"""On-call roster tests (P4.2).

Service-level tests prove the on-call invariants: current_oncall returns the
primary for the current window, a coverage gap is reported as a gap rather
than an empty list, next_shifts only lists the account's own upcoming windows,
creating a shift is manager-only and records one governed node, and an
unavailable engine raises EngineUnavailableError instead of degrading. HTTP
tests drive the mounted router through TestClient for the oncall status API,
the fail-closed 503 when the engine cannot be read, the manager-only create
route with CSRF, and the home-screen on-call person.
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
from helix_codex_app.errors import EngineUnavailableError, PermissionDenied
from helix_codex_app.integration.engine_bridge import wfm_coverage
from helix_codex_app.modules.calendar.service import CalendarService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

FROM = "2026-09-01T00:00:00+00:00"
TO = "2026-10-01T00:00:00+00:00"


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
        domain_a.domain_id, "manager", role_id="manager", password_hash=hash_password("x")
    )
    amira = repo.create_account(
        domain_a.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    omar = repo.create_account(
        domain_a.domain_id, "omar", role_id="employee", password_hash=hash_password("x")
    )
    ghada = repo.create_account(
        domain_b.domain_id, "ghada", role_id="employee", password_hash=hash_password("x")
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
        manager=manager,
        amira=amira,
        omar=omar,
        ghada=ghada,
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


def _shift_args(**overrides):
    now = datetime.now(timezone.utc)
    args = {
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
    }
    args.update(overrides)
    return args


def _future_shift_args(**overrides):
    now = datetime.now(timezone.utc)
    args = {
        "starts_at": (now + timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=1, hours=2)).isoformat(),
    }
    args.update(overrides)
    return args


# --- service-level tests ---


def test_create_shift_writes_one_node(ctx):
    before = _node_count(ctx.conn, "oncall_shift")
    shift = ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    assert shift.primary_account_id == ctx.amira.account_id
    assert shift.backup_account_id == ctx.omar.account_id
    assert tuple(shift.roster) == (ctx.amira.account_id, ctx.omar.account_id)
    assert _node_count(ctx.conn, "oncall_shift") == before + 1


def test_create_shift_requires_manager(ctx):
    with pytest.raises(PermissionDenied):
        ctx.service.create_shift(
            ctx.amira,
            **_shift_args(
                primary_account_id=ctx.omar.account_id,
                backup_account_id=ctx.amira.account_id,
            ),
        )


def test_create_shift_requires_distinct_accounts(ctx):
    with pytest.raises(ValueError, match="different accounts"):
        ctx.service.create_shift(
            ctx.manager,
            **_shift_args(
                primary_account_id=ctx.amira.account_id,
                backup_account_id=ctx.amira.account_id,
            ),
        )


def test_create_shift_rejects_unknown_account(ctx):
    with pytest.raises(ValueError, match="unknown account"):
        ctx.service.create_shift(
            ctx.manager,
            **_shift_args(
                primary_account_id=ctx.amira.account_id,
                backup_account_id="account-nobody",
            ),
        )


def test_create_shift_rejects_foreign_account(ctx):
    with pytest.raises(ValueError, match="unknown account"):
        ctx.service.create_shift(
            ctx.manager,
            **_shift_args(
                primary_account_id=ctx.amira.account_id,
                backup_account_id=ctx.ghada.account_id,
            ),
        )


def test_create_shift_rejects_bad_window(ctx):
    with pytest.raises(ValueError, match="end after it starts"):
        ctx.service.create_shift(
            ctx.manager,
            starts_at="2026-09-01T10:00:00+00:00",
            ends_at="2026-09-01T10:00:00+00:00",
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        )


def test_current_oncall_returns_primary(ctx):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    now = datetime.now(timezone.utc).isoformat()
    coverage = ctx.service.current_oncall(ctx.domain_a.tenant_id, now)
    assert coverage.covered is True
    assert coverage.status == "covered"
    assert coverage.shift is not None
    assert coverage.shift.primary_account_id == ctx.amira.account_id


def test_gap_is_reported_as_gap_not_empty(ctx):
    past_start = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    future_start = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    ctx.service.create_shift(
        ctx.manager,
        starts_at=past_start,
        ends_at=(datetime.now(timezone.utc) - timedelta(days=4)).isoformat(),
        primary_account_id=ctx.amira.account_id,
        backup_account_id=ctx.omar.account_id,
    )
    ctx.service.create_shift(
        ctx.manager,
        starts_at=future_start,
        ends_at=(datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
        primary_account_id=ctx.omar.account_id,
        backup_account_id=ctx.amira.account_id,
    )
    coverage = ctx.service.current_oncall(
        ctx.domain_a.tenant_id, datetime.now(timezone.utc).isoformat()
    )
    assert coverage.covered is False
    assert coverage.status == "gap"
    assert coverage.shift is None
    assert coverage.to_dict()["status"] == "gap"


def test_list_shifts_is_tenant_scoped(ctx):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    listed = ctx.service.list_shifts(ctx.amira, FROM, TO)
    assert len(listed) == 1
    assert listed[0].primary_account_id == ctx.amira.account_id


def test_list_shifts_never_mixes_foreign_tenant(ctx):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    assert len(ctx.service.list_shifts(ctx.amira, FROM, TO)) == 1
    listed_for_ghada = ctx.service.list_shifts(ctx.ghada, FROM, TO)
    assert listed_for_ghada == []


def test_next_shifts_only_shows_own_upcoming(ctx):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    ctx.service.create_shift(
        ctx.manager,
        **_future_shift_args(
            primary_account_id=ctx.omar.account_id,
            backup_account_id=ctx.amira.account_id,
        ),
    )
    mine = ctx.service.next_shifts(ctx.amira)
    assert len(mine) == 2
    assert all(
        account_id in (ctx.amira.account_id, ctx.omar.account_id)
        for shift in mine
        for account_id in (shift.primary_account_id, shift.backup_account_id)
    )
    assert any(shift.primary_account_id == ctx.omar.account_id for shift in mine)


def test_next_tenant_shift_returns_earliest_future(ctx):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    ctx.service.create_shift(
        ctx.manager,
        **_future_shift_args(
            primary_account_id=ctx.omar.account_id,
            backup_account_id=ctx.amira.account_id,
        ),
    )
    next_shift = ctx.service.next_tenant_shift(
        ctx.domain_a.tenant_id, datetime.now(timezone.utc).isoformat()
    )
    assert next_shift is not None
    assert next_shift.primary_account_id == ctx.omar.account_id


def test_next_tenant_shift_none_when_no_future(ctx):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    shifted_after = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    assert ctx.service.next_tenant_shift(ctx.domain_a.tenant_id, shifted_after) is None


def test_wfm_coverage_reads_required_agents(ctx, monkeypatch):
    def fake_adapt(**kwargs):
        assert kwargs["owning_role_id"] == "ops_gm"
        assert kwargs["is_sample"] is True
        return SimpleNamespace(
            error=None,
            engine_id="wfm",
            metrics={"optimal_agents": 63, "service_level_achieved": 0.913},
        )

    monkeypatch.setattr("engines.wfm.adapter.adapt", fake_adapt)
    result = wfm_coverage(
        tenant_id="tenant-a",
        client_id="client-a",
        correlation_id="corr-1",
        actor="test",
        from_at="2026-09-01T00:00:00+00:00",
        to_at="2026-09-08T00:00:00+00:00",
    )
    assert result["engine_id"] == "wfm"
    assert result["required_agents"] == 63
    assert result["is_sample"] is True
    assert result["data_mode"] == "sample"
    assert result["basis"] == "canonical WFM sample baseline"


def test_unavailable_engine_raises(ctx, monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "engines.wfm.adapter", None)
    with pytest.raises(EngineUnavailableError, match="unavailable"):
        wfm_coverage(
            tenant_id="tenant-a",
            client_id="client-a",
            correlation_id="corr-1",
            actor="test",
            from_at="2026-09-01T00:00:00+00:00",
            to_at="2026-09-08T00:00:00+00:00",
        )


def test_engine_failure_result_raises(ctx, monkeypatch):
    def fake_adapt(**kwargs):
        return SimpleNamespace(error="engine blew up", metrics=None, engine_id="wfm")

    monkeypatch.setattr("engines.wfm.adapter.adapt", fake_adapt)
    with pytest.raises(EngineUnavailableError, match="could not produce"):
        wfm_coverage(
            tenant_id="tenant-a",
            client_id="client-a",
            correlation_id="corr-1",
            actor="test",
            from_at="2026-09-01T00:00:00+00:00",
            to_at="2026-09-08T00:00:00+00:00",
        )


def test_engine_without_staffing_figure_raises(ctx, monkeypatch):
    def fake_adapt(**kwargs):
        return SimpleNamespace(error=None, metrics={"service_level_achieved": 0.9}, engine_id="wfm")

    monkeypatch.setattr("engines.wfm.adapter.adapt", fake_adapt)
    with pytest.raises(EngineUnavailableError, match="no staffing figure"):
        wfm_coverage(
            tenant_id="tenant-a",
            client_id="client-a",
            correlation_id="corr-1",
            actor="test",
            from_at="2026-09-01T00:00:00+00:00",
            to_at="2026-09-08T00:00:00+00:00",
        )


# --- HTTP tests ---


def test_oncall_status_api_returns_coverage_and_wfm(ctx, client, monkeypatch):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    ctx.service.create_shift(
        ctx.manager,
        **_future_shift_args(
            primary_account_id=ctx.omar.account_id,
            backup_account_id=ctx.amira.account_id,
        ),
    )

    def fake_adapt(**kwargs):
        return SimpleNamespace(
            error=None,
            engine_id="wfm",
            metrics={
                "optimal_agents": 63,
                "service_level_achieved": 0.913,
            },
        )

    monkeypatch.setattr("engines.wfm.adapter.adapt", fake_adapt)
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/api/oncall", cookies=cookies)
    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage"]["status"] == "covered"
    assert payload["coverage"]["shift"]["primary_account_id"] == ctx.amira.account_id
    assert payload["wfm"]["required_agents"] == 63
    assert payload["wfm"]["is_sample"] is True
    assert {s["primary_account_id"] for s in payload["next_shifts"]} == {
        ctx.amira.account_id,
        ctx.omar.account_id,
    }


def test_oncall_status_api_503_when_engine_unavailable(ctx, client, monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "engines.wfm.adapter", None)
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/api/oncall", cookies=cookies)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "engine_unavailable"


def test_create_shift_api_201_and_audits(ctx, client):
    before = _node_count(ctx.conn, "oncall_shift")
    shift_window = _shift_args(
        primary_account_id=ctx.amira.account_id,
        backup_account_id=ctx.omar.account_id,
    )
    cookies, headers = _login(ctx, ctx.manager)
    response = client.post(
        "/app/api/oncall/shifts",
        data={
            "starts_at": shift_window["starts_at"],
            "ends_at": shift_window["ends_at"],
            "primary_account_id": ctx.amira.account_id,
            "backup_account_id": ctx.omar.account_id,
        },
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["primary_account_id"] == ctx.amira.account_id
    assert _node_count(ctx.conn, "oncall_shift") == before + 1


def test_create_shift_api_requires_csrf(ctx, client):
    cookies, _ = _login(ctx, ctx.manager)
    response = client.post(
        "/app/api/oncall/shifts",
        data={
            "starts_at": "2026-09-05T09:00:00+00:00",
            "ends_at": "2026-09-05T10:00:00+00:00",
            "primary_account_id": ctx.amira.account_id,
            "backup_account_id": ctx.omar.account_id,
        },
        cookies=cookies,
    )
    assert response.status_code == 403


def test_create_shift_api_requires_manager(ctx, client):
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/oncall/shifts",
        data={
            "starts_at": "2026-09-05T09:00:00+00:00",
            "ends_at": "2026-09-05T10:00:00+00:00",
            "primary_account_id": ctx.omar.account_id,
            "backup_account_id": ctx.amira.account_id,
        },
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_create_shift_api_rejects_foreign_account(ctx, client):
    cookies, headers = _login(ctx, ctx.manager)
    response = client.post(
        "/app/api/oncall/shifts",
        data={
            "starts_at": "2026-09-05T09:00:00+00:00",
            "ends_at": "2026-09-05T10:00:00+00:00",
            "primary_account_id": ctx.amira.account_id,
            "backup_account_id": ctx.ghada.account_id,
        },
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 400


def test_oncall_route_requires_auth(ctx, client):
    response = client.get("/app/api/oncall")
    assert response.status_code == 401


def test_home_screen_shows_current_oncall_person(ctx, client):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    cookies, _ = _login(ctx, ctx.omar)
    response = client.get("/app/", cookies=cookies)
    assert response.status_code == 200
    assert "amira" in response.text
    assert "on-call primary" in response.text


def test_home_screen_foreign_tenant_shifts_invisible(ctx, client):
    ctx.service.create_shift(
        ctx.manager,
        **_shift_args(
            primary_account_id=ctx.amira.account_id,
            backup_account_id=ctx.omar.account_id,
        ),
    )
    cookies, _ = _login(ctx, ctx.ghada)
    response = client.get("/app/", cookies=cookies)
    assert response.status_code == 200
    assert "amira" not in response.text
