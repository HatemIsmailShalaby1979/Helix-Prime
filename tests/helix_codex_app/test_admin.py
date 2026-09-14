"""Admin service and admin route tests: users, domains, org units, limits.

Service-level tests drive AdminService against a throwaway database with a
real owner, a real manager scoped to one org unit, and a real employee.
HTTP tests drive the mounted admin router through TestClient, so the
router-boundary permission check, the CSRF requirement, and the employee
403 on every admin route are exercised exactly as the app wiring uses them.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import LimitExceeded, NotFoundError, PermissionDenied
from helix_codex_app.modules.admin.service import AdminService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.limits import check_and_consume, load_limits
from helix_codex_app.security.passwords import hash_password, verify_password
from helix_codex_app.security.permissions import has_permission
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

ADMIN_ROUTES_GET = (
    "/app/admin",
    "/app/admin/users",
    "/app/admin/domains",
    "/app/admin/org-units",
)
ADMIN_ROUTES_MUTATING = (
    "/app/admin/users",
    "/app/admin/domains",
    "/app/admin/org-units",
)


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    units = repo.create_org_unit(domain.domain_id, "Floor")
    owner = repo.create_account(
        domain.domain_id,
        "dalia",
        display_name="Dalia O.",
        role_id="owner",
        password_hash=hash_password("owner-password"),
    )
    manager = repo.create_account(
        domain.domain_id,
        "amira",
        display_name="Amira K.",
        role_id="manager",
        org_unit_id=units.unit_id,
        password_hash=hash_password("manager-password"),
    )
    employee = repo.create_account(
        domain.domain_id,
        "sameh",
        display_name="Sameh R.",
        role_id="employee",
        org_unit_id=units.unit_id,
        password_hash=hash_password("employee-password"),
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    service = AdminService(conn)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        units=units,
        owner=owner,
        manager=manager,
        employee=employee,
        settings=settings,
        service=service,
        store=store,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _token(ctx, account) -> str:
    token, _session = ctx.store.issue_session(account)
    return token


def _cookies(ctx, account, token: str | None = None) -> dict[str, str]:
    return {SESSION_COOKIE: token or _token(ctx, account)}


def _csrf(ctx, account, token: str) -> dict[str, str]:
    session = ctx.store.verify(token)
    assert session is not None
    return {"X-CSRF-Token": session.csrf_token}


def _node_count(ctx) -> int:
    return ctx.conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]


def test_owner_creates_user_in_own_domain(ctx) -> None:
    before = _node_count(ctx)
    created = ctx.service.create_user(
        ctx.owner,
        username="noura",
        password="your-password",
        domain_id=ctx.domain.domain_id,
        display_name="Noura S.",
        role_id="employee",
        org_unit_id=ctx.units.unit_id,
    )
    assert created.username == "noura"
    assert created.status == "active"
    assert created.role_id == "employee"
    assert verify_password("your-password", created.password_hash)
    assert _node_count(ctx) == before + 1
    row = ctx.conn.execute(
        "SELECT tenant_id, classification, nature, kind, created_by FROM nodes"
    ).fetchone()
    assert row["tenant_id"] == "tenant-a"
    assert row["classification"] == "internal"
    assert row["kind"] == "admin"
    assert row["created_by"] == ctx.owner.account_id


def test_created_user_can_sign_in(ctx, client) -> None:
    ctx.service.create_user(
        ctx.owner,
        username="noura",
        password="your-password",
        domain_id=ctx.domain.domain_id,
    )
    resp = client.post(
        "/app/auth/login",
        data={"domain": "a.academy", "username": "noura", "password": "your-password"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/"
    token = _session_token(resp.headers["set-cookie"])
    assert client.get("/app/", cookies={SESSION_COOKIE: token}).status_code == 200


def test_manager_creates_user_only_inside_own_org_unit(ctx) -> None:
    other_unit = ctx.repo.create_org_unit(ctx.domain.domain_id, "Office")
    created = ctx.service.create_user(
        ctx.manager,
        username="mona",
        password="your-password",
        domain_id=ctx.domain.domain_id,
        org_unit_id=ctx.units.unit_id,
    )
    assert created.org_unit_id == ctx.units.unit_id
    with pytest.raises(PermissionDenied):
        ctx.service.create_user(
            ctx.manager,
            username="hana",
            password="your-password",
            domain_id=ctx.domain.domain_id,
            org_unit_id=other_unit.unit_id,
        )
    with pytest.raises(PermissionDenied):
        ctx.service.create_user(
            ctx.manager,
            username="rana",
            password="your-password",
            domain_id=ctx.domain.domain_id,
            org_unit_id=None,
        )


def test_manager_cannot_act_outside_own_org_unit(ctx) -> None:
    outside = ctx.repo.create_account(
        ctx.domain.domain_id,
        "farida",
        role_id="employee",
        password_hash=hash_password("employee-password"),
    )
    with pytest.raises(PermissionDenied):
        ctx.service.update_user(ctx.manager, outside.account_id, display_name="X")
    with pytest.raises(PermissionDenied):
        ctx.service.set_user_status(ctx.manager, outside.account_id, "disabled")
    with pytest.raises(PermissionDenied):
        ctx.service.grant_capability(ctx.manager, outside.account_id, "docs.write")
    with pytest.raises(PermissionDenied):
        ctx.service.set_limit(ctx.manager, outside.account_id, "storage_mb", 10)
    with pytest.raises(PermissionDenied):
        ctx.service.create_domain(ctx.manager, name="b.academy", tenant_id="tenant-b")


def test_manager_cannot_manage_the_owner(ctx) -> None:
    with pytest.raises(PermissionDenied):
        ctx.service.set_user_status(ctx.manager, ctx.owner.account_id, "disabled")


def test_manager_without_org_unit_manages_nothing(ctx) -> None:
    free = ctx.repo.create_account(
        ctx.domain.domain_id,
        "layla",
        role_id="manager",
        password_hash=hash_password("manager-password"),
    )
    with pytest.raises(PermissionDenied):
        ctx.service.list_users(free)
    with pytest.raises(PermissionDenied):
        ctx.service.create_user(
            free,
            username="mona",
            password="your-password",
            domain_id=ctx.domain.domain_id,
        )


def test_manager_lists_only_own_unit(ctx) -> None:
    ctx.repo.create_account(
        ctx.domain.domain_id,
        "farida",
        role_id="employee",
        password_hash=hash_password("employee-password"),
    )
    visible = ctx.service.list_users(ctx.manager)
    assert {a.username for a in visible} == {"amira", "sameh"}
    visible_owner = ctx.service.list_users(ctx.owner)
    assert {a.username for a in visible_owner} == {"dalia", "amira", "sameh", "farida"}


def test_employee_403_on_every_admin_route(ctx, client) -> None:
    cookies = _cookies(ctx, ctx.employee)
    headers = _csrf(ctx, ctx.employee, _token(ctx, ctx.employee))
    for path in ADMIN_ROUTES_GET:
        assert client.get(path, cookies=cookies).status_code == 403, path
    for path in ADMIN_ROUTES_MUTATING:
        resp = client.post(
            path,
            cookies=cookies,
            headers=headers,
            data={"username": "x", "password": "12345678", "name": "x", "tenant_id": "t"},
        )
        assert resp.status_code == 403, path
    assert (
        client.patch(
            f"/app/admin/users/{ctx.employee.account_id}",
            cookies=cookies,
            headers=headers,
            data={"display_name": "X"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/app/admin/users/{ctx.employee.account_id}/capabilities",
            cookies=cookies,
            headers=headers,
            data={"capability_key": "admin.users", "action": "grant"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/app/admin/users/{ctx.employee.account_id}/limits",
            cookies=cookies,
            headers=headers,
            data={"limit_key": "storage_mb", "limit_value": "1"},
        ).status_code
        == 403
    )


def test_owner_gets_admin_screens(ctx, client) -> None:
    cookies = _cookies(ctx, ctx.owner)
    for path in ADMIN_ROUTES_GET:
        resp = client.get(path, cookies=cookies)
        assert resp.status_code == 200, path
        assert "Helix Codex" in resp.text
    resp = client.get("/app/admin/users", cookies=cookies)
    assert "amira" in resp.text
    assert "sameh" in resp.text


def test_user_detail_screen_shows_status_role_capabilities_limits(ctx, client) -> None:
    ctx.service.grant_capability(ctx.owner, ctx.employee.account_id, "docs.write")
    ctx.service.set_limit(ctx.owner, ctx.employee.account_id, "storage_mb", 250)
    resp = client.get(
        f"/app/admin/users/{ctx.employee.account_id}",
        cookies=_cookies(ctx, ctx.owner),
    )
    assert resp.status_code == 200
    assert "sameh" in resp.text
    assert "docs.write" in resp.text
    assert "storage_mb" in resp.text
    assert "250" in resp.text


def test_granted_capability_is_reflected_in_has_permission_immediately(ctx) -> None:
    key = "packs.manage"
    assert has_permission(ctx.employee, key) is False
    assert has_permission(ctx.employee, key, ctx.conn) is False
    ctx.service.grant_capability(ctx.owner, ctx.employee.account_id, key)
    fresh = ctx.repo.get_account_by_id(ctx.employee.account_id)
    assert has_permission(fresh, key) is False
    assert has_permission(fresh, key, ctx.conn) is True
    ctx.service.revoke_capability(ctx.owner, ctx.employee.account_id, key)
    fresh = ctx.repo.get_account_by_id(ctx.employee.account_id)
    assert has_permission(fresh, key, ctx.conn) is False


def test_grant_widens_route_access_immediately(ctx, client) -> None:
    assert has_permission(ctx.employee, "admin.users", ctx.conn) is False
    cookies = _cookies(ctx, ctx.employee)
    assert client.get("/app/admin/users", cookies=cookies).status_code == 403
    ctx.service.grant_capability(ctx.owner, ctx.employee.account_id, "admin.users")
    assert client.get("/app/admin/users", cookies=cookies).status_code == 200


def test_self_grant_and_self_role_change_are_denied(ctx) -> None:
    with pytest.raises(PermissionDenied):
        ctx.service.grant_capability(ctx.owner, ctx.owner.account_id, "packs.manage")
    with pytest.raises(PermissionDenied):
        ctx.service.revoke_capability(ctx.owner, ctx.owner.account_id, "packs.manage")
    with pytest.raises(PermissionDenied):
        ctx.service.update_user(ctx.owner, ctx.owner.account_id, role_id="employee")
    with pytest.raises(PermissionDenied):
        ctx.service.set_user_status(ctx.owner, ctx.owner.account_id, "disabled")


def test_account_cannot_move_its_own_org_unit(ctx) -> None:
    other_unit = ctx.repo.create_org_unit(ctx.domain.domain_id, "Office")
    with pytest.raises(PermissionDenied):
        ctx.service.update_user(ctx.manager, ctx.manager.account_id, org_unit_id=other_unit.unit_id)


def test_set_user_status_revokes_sessions_and_audits(ctx) -> None:
    token, _session = ctx.store.issue_session(ctx.employee)
    assert ctx.store.verify(token) is not None
    updated = ctx.service.set_user_status(ctx.owner, ctx.employee.account_id, "disabled")
    assert updated.status == "disabled"
    assert ctx.store.verify(token) is None
    row = ctx.conn.execute(
        "SELECT body FROM nodes WHERE kind = 'admin' ORDER BY created_at DESC"
    ).fetchone()
    assert '"set_user_status"' in row["body"]
    assert '"disabled"' in row["body"]
    reactivated = ctx.service.set_user_status(ctx.owner, ctx.employee.account_id, "active")
    assert reactivated.status == "active"


def test_unknown_status_is_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.set_user_status(ctx.owner, ctx.employee.account_id, "frozen")


def test_set_limit_below_current_usage_does_not_crash(ctx) -> None:
    ctx.service.set_limit(ctx.owner, ctx.employee.account_id, "storage_mb", 500)
    target = ctx.repo.get_account_by_id(ctx.employee.account_id)
    loaded = load_limits(ctx.conn, target)
    assert loaded.limits["storage_mb"] == 500
    check_and_consume(loaded, "storage_mb", 400)
    updated = ctx.service.set_limit(ctx.owner, ctx.employee.account_id, "storage_mb", 50)
    assert updated.limits["storage_mb"] == 50
    check_and_consume(updated, "storage_mb", 40)
    with pytest.raises(LimitExceeded):
        check_and_consume(updated, "storage_mb", 20)


def test_negative_limit_is_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.set_limit(ctx.owner, ctx.employee.account_id, "storage_mb", -1)


def test_create_domain_owner_only_and_audited(ctx) -> None:
    domain = ctx.service.create_domain(ctx.owner, name="b.academy", tenant_id="tenant-b")
    assert domain.tenant_id == "tenant-b"
    row = ctx.conn.execute(
        "SELECT body FROM nodes WHERE kind = 'admin' ORDER BY created_at DESC"
    ).fetchone()
    assert '"create_domain"' in row["body"]
    with pytest.raises(PermissionDenied):
        ctx.service.create_domain(ctx.manager, name="c.academy", tenant_id="tenant-c")


def test_duplicate_domain_name_is_rejected_plainly(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.create_domain(ctx.owner, name="a.academy", tenant_id="tenant-a")


def test_create_org_unit_scoped_to_own_domain(ctx) -> None:
    other_domain = ctx.service.create_domain(ctx.owner, name="b.academy", tenant_id="tenant-b")
    unit = ctx.service.create_org_unit(ctx.manager, domain_id=ctx.domain.domain_id, name="Evening")
    assert unit.domain_id == ctx.domain.domain_id
    assert unit.path == "/Evening"
    with pytest.raises(PermissionDenied):
        ctx.service.create_org_unit(ctx.manager, domain_id=other_domain.domain_id, name="Foreign")


def test_cross_domain_target_is_not_found(ctx) -> None:
    other_domain = ctx.repo.create_domain("b.academy", tenant_id="tenant-b")
    stranger = ctx.repo.create_account(
        other_domain.domain_id,
        "ghada",
        role_id="employee",
        password_hash=hash_password("employee-password"),
    )
    with pytest.raises(NotFoundError):
        ctx.service.update_user(ctx.owner, stranger.account_id, display_name="X")


def test_weak_password_is_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.create_user(
            ctx.owner,
            username="noura",
            password="short",
            domain_id=ctx.domain.domain_id,
        )


def test_unknown_role_is_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.create_user(
            ctx.owner,
            username="noura",
            password="your-password",
            domain_id=ctx.domain.domain_id,
            role_id="superuser",
        )


def test_admin_post_requires_csrf(ctx, client) -> None:
    resp = client.post(
        "/app/admin/users",
        cookies=_cookies(ctx, ctx.owner),
        data={"username": "noura", "password": "your-password", "domain_id": ctx.domain.domain_id},
    )
    assert resp.status_code == 403


def test_owner_creates_user_through_the_ui(ctx, client) -> None:
    token = _token(ctx, ctx.owner)
    resp = client.post(
        "/app/admin/users",
        cookies=_cookies(ctx, ctx.owner, token),
        headers=_csrf(ctx, ctx.owner, token),
        data={
            "username": "noura",
            "password": "your-password",
            "display_name": "Noura S.",
            "role_id": "employee",
            "org_unit_id": ctx.units.unit_id,
            "domain_id": ctx.domain.domain_id,
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/admin/users?flash=created"
    login = client.post(
        "/app/auth/login",
        data={"domain": "a.academy", "username": "noura", "password": "your-password"},
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/app/"
    set_cookie = login.headers["set-cookie"]
    assert set_cookie.startswith("helix_session=")
    token = _session_token(set_cookie)
    assert client.get("/app/", cookies={SESSION_COOKIE: token}).status_code == 200
    assert "Noura S." in client.get("/app/", cookies={SESSION_COOKIE: token}).text


def _session_token(set_cookie: str) -> str:
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith(f"{SESSION_COOKIE}="):
            return part.split("=", 1)[1]
    raise AssertionError("no session cookie in header")
