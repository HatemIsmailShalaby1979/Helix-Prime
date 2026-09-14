"""Cockpit exclusion tests (P1.7, to be extended in P6).

No cockpit route exists yet — the cockpit module lands in P6. The boundary
that matters today is the permission check itself: an employee, a
contractor, and an external account are denied cockpit.view by the catalog,
so a cockpit router mounted behind require_permission("cockpit.view") in P6
fails closed for them on day one. One probe route is registered here on the
real app_router, exactly as the P1.3 guard tests do, so the dependency is
exercised as production wiring will use it. This module is re-pointed at
the live cockpit routes in P6 (master plan 5.6).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Depends

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import app_router, create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.guard import require_permission
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.permissions import has_permission
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

COCKPIT_ROUTES = (
    "/app/cockpit",
    "/app/cockpit/owner",
    "/app/cockpit/coach",
    "/app/cockpit/parent",
    "/app/cockpit/control-plane",
)


@app_router.get(
    "/cockpit-permission-probe",
    dependencies=[Depends(require_permission("cockpit.view"))],
)
def _probe_cockpit_permission() -> dict[str, str]:
    return {"ok": "true"}


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("a.academy", tenant_id="tenant-a")
    employee = repo.create_account(
        domain.domain_id, "sameh", role_id="employee", password_hash=hash_password("x")
    )
    contractor = repo.create_account(
        domain.domain_id, "tara", role_id="contractor", password_hash=hash_password("x")
    )
    external = repo.create_account(
        domain.domain_id, "vera", role_id="external", password_hash=hash_password("x")
    )
    owner = repo.create_account(
        domain.domain_id, "dalia", role_id="owner", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        employee=employee,
        contractor=contractor,
        external=external,
        owner=owner,
        settings=settings,
        store=store,
    )
    db.close(conn)


def _cookies(ctx, account) -> dict[str, str]:
    token, _session = ctx.store.issue_session(account)
    return {SESSION_COOKIE: token}


def test_no_cockpit_route_is_mounted_yet(ctx) -> None:
    app = create_app(ctx.settings)
    mounted = {getattr(route, "path", None) for route in app.routes}
    for route in COCKPIT_ROUTES:
        assert route not in mounted, f"{route} exists before P6"


def test_employee_session_gets_403_on_cockpit_permission(ctx) -> None:
    assert has_permission(ctx.employee, "cockpit.view") is False
    with TestClient(create_app(ctx.settings)) as client:
        response = client.get("/app/cockpit-permission-probe", cookies=_cookies(ctx, ctx.employee))
        assert response.status_code == 403


def test_contractor_and_external_denied_cockpit_permission(ctx) -> None:
    assert has_permission(ctx.contractor, "cockpit.view") is False
    assert has_permission(ctx.external, "cockpit.view") is False
    with TestClient(create_app(ctx.settings)) as client:
        for account in (ctx.contractor, ctx.external):
            response = client.get("/app/cockpit-permission-probe", cookies=_cookies(ctx, account))
            assert response.status_code == 403


def test_owner_granted_cockpit_permission(ctx) -> None:
    assert has_permission(ctx.owner, "cockpit.view") is True
    with TestClient(create_app(ctx.settings)) as client:
        response = client.get("/app/cockpit-permission-probe", cookies=_cookies(ctx, ctx.owner))
        assert response.status_code == 200


def test_unknown_role_denied_cockpit_permission(ctx) -> None:
    ghost = ctx.repo.create_account(ctx.domain.domain_id, "ghost", password_hash=hash_password("x"))
    assert has_permission(ghost, "cockpit.view") is False
    with TestClient(create_app(ctx.settings)) as client:
        response = client.get("/app/cockpit-permission-probe", cookies=_cookies(ctx, ghost))
        assert response.status_code == 403
