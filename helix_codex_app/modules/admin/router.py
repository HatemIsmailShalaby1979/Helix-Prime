"""Admin routes: the screens for users, domains, org units, and limits.

Every route here is owner-and-manager only. The permission is checked once
at the router boundary — the router is included with
require_permission("admin.users") — and again inside the service before any
write. Pages render the admin templates; forms post back with the CSRF
header and answer with a redirect, so a phone browser and an HTMX request
both behave the same way.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from helix_codex_app.db import close, connect
from helix_codex_app.errors import NotFoundError, PermissionDenied
from helix_codex_app.modules.admin.evidence import build_evidence_zip
from helix_codex_app.modules.admin.service import AdminService
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import require_csrf, require_permission
from helix_codex_app.templating import render

admin_router = APIRouter(
    prefix="/app/admin",
    dependencies=[Depends(require_permission("admin.users"))],
)

USERS_URL = "/app/admin/users"


@admin_router.get("", response_model=None)
def admin_home(request: Request) -> HTMLResponse:
    """The admin landing screen: links to the three admin screens."""
    return render(
        request, "admin/index.html", {"active_nav": "admin", "account": _account(request)}
    )


@admin_router.get("/users", response_model=None)
def users_screen(request: Request) -> HTMLResponse:
    """The account list with search and the create form."""
    account = _account(request)
    query = (request.query_params.get("q") or "").strip().lower()
    flash = request.query_params.get("flash")
    conn = _conn(request)
    try:
        service = AdminService(conn)
        org_units = service.list_org_units(account)
        accounts = service.list_users(account)
    finally:
        close(conn)
    if query:
        accounts = [
            a
            for a in accounts
            if query in a.username.lower()
            or query in (a.display_name or "").lower()
            or query in (a.email or "").lower()
        ]
    return render(
        request,
        "admin/users.html",
        {
            "active_nav": "admin",
            "account": account,
            "accounts": accounts,
            "org_units": org_units,
            "query": request.query_params.get("q", ""),
            "flash": flash,
        },
    )


@admin_router.post("/users", response_model=None, dependencies=[Depends(require_csrf)])
async def create_user(request: Request) -> HTMLResponse | RedirectResponse:
    """Create an account from the admin form."""
    account = _account(request)
    form = await request.form()
    conn = _conn(request)
    try:
        service = AdminService(conn)
        service.create_user(
            account,
            username=str(form.get("username") or "").strip(),
            password=str(form.get("password") or ""),
            domain_id=str(form.get("domain_id") or account.domain_id),
            display_name=str(form.get("display_name") or "").strip() or None,
            email=str(form.get("email") or "").strip() or None,
            role_id=str(form.get("role_id") or "employee"),
            org_unit_id=str(form.get("org_unit_id") or "").strip() or None,
        )
    except ValueError as exc:
        return _back_with_error(request, str(exc), role_id=str(form.get("role_id") or ""))
    finally:
        close(conn)
    return RedirectResponse(f"{USERS_URL}?flash=created", status_code=303)


@admin_router.get("/users/{account_id}", response_model=None)
def user_detail_screen(request: Request, account_id: str) -> HTMLResponse:
    """One account: status, role, capabilities, and limits."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = AdminService(conn)
        target = service.get_managed_user(account, account_id)
        capabilities = service.capabilities_of(target)
        limits = service.limits_of(target)
    except NotFoundError as exc:
        return _not_found(request, str(exc))
    finally:
        close(conn)
    return render(
        request,
        "admin/user_detail.html",
        {
            "active_nav": "admin",
            "account": account,
            "target": target,
            "capabilities": capabilities,
            "limits": limits,
            "flash": request.query_params.get("flash"),
        },
    )


@admin_router.patch(
    "/users/{account_id}", response_model=None, dependencies=[Depends(require_csrf)]
)
async def update_user(request: Request, account_id: str) -> HTMLResponse | RedirectResponse:
    """Update profile fields, role, org unit, or status from the detail form."""
    account = _account(request)
    form = await request.form()
    conn = _conn(request)
    try:
        service = AdminService(conn)
        status = str(form.get("status") or "").strip()
        service.update_user(
            account,
            account_id,
            display_name=str(form.get("display_name") or "").strip() or None,
            email=str(form.get("email") or "").strip() or None,
            role_id=str(form.get("role_id") or "").strip() or None,
            org_unit_id=str(form.get("org_unit_id") or "").strip() or None,
        )
        if status:
            service.set_user_status(account, account_id, status)
    except (ValueError, PermissionDenied) as exc:
        return _back_with_error(request, str(exc), account_id=account_id)
    finally:
        close(conn)
    return RedirectResponse(f"/app/admin/users/{account_id}?flash=saved", status_code=303)


@admin_router.post(
    "/users/{account_id}/capabilities",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def set_capability(request: Request, account_id: str) -> HTMLResponse | RedirectResponse:
    """Grant or revoke one capability from the detail form."""
    account = _account(request)
    form = await request.form()
    capability_key = str(form.get("capability_key") or "").strip()
    action = str(form.get("action") or "").strip()
    if not capability_key:
        return _back_with_error(request, "Pick a capability first.", account_id=account_id)
    conn = _conn(request)
    try:
        service = AdminService(conn)
        if action == "revoke":
            service.revoke_capability(account, account_id, capability_key)
        else:
            service.grant_capability(account, account_id, capability_key)
    except (NotFoundError, PermissionDenied, ValueError) as exc:
        return _back_with_error(request, str(exc), account_id=account_id)
    finally:
        close(conn)
    return RedirectResponse(f"/app/admin/users/{account_id}?flash=capability", status_code=303)


@admin_router.post(
    "/users/{account_id}/limits",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def set_limit(request: Request, account_id: str) -> HTMLResponse | RedirectResponse:
    """Set one limit value from the detail form."""
    account = _account(request)
    form = await request.form()
    limit_key = str(form.get("limit_key") or "").strip()
    if not limit_key:
        return _back_with_error(request, "Pick a limit first.", account_id=account_id)
    try:
        limit_value = int(str(form.get("limit_value") or "0"))
    except ValueError:
        return _back_with_error(request, "The limit must be a number.", account_id=account_id)
    conn = _conn(request)
    try:
        service = AdminService(conn)
        service.set_limit(
            account,
            account_id,
            limit_key,
            limit_value,
            window=str(form.get("window") or "day"),
        )
    except (NotFoundError, PermissionDenied, ValueError) as exc:
        return _back_with_error(request, str(exc), account_id=account_id)
    finally:
        close(conn)
    return RedirectResponse(f"/app/admin/users/{account_id}?flash=limit", status_code=303)


@admin_router.get("/domains", response_model=None)
def domains_screen(request: Request) -> HTMLResponse:
    """List domains in the caller's tenant and create one (owner only)."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = AdminService(conn)
        domains = service.list_domains(account)
    finally:
        close(conn)
    return render(
        request,
        "admin/domains.html",
        {
            "active_nav": "admin",
            "account": account,
            "domains": domains,
            "is_owner": account.role_id == "owner",
            "flash": request.query_params.get("flash"),
        },
    )


@admin_router.post("/domains", response_model=None, dependencies=[Depends(require_csrf)])
async def create_domain(request: Request) -> HTMLResponse | RedirectResponse:
    """Create a domain (owner only)."""
    account = _account(request)
    form = await request.form()
    name = str(form.get("name") or "").strip()
    tenant_id = str(form.get("tenant_id") or "").strip()
    if not name or not tenant_id:
        return _back_with_error(request, "A domain needs a name and a tenant.")
    conn = _conn(request)
    try:
        service = AdminService(conn)
        service.create_domain(account, name=name, tenant_id=tenant_id)
    except (PermissionDenied, ValueError) as exc:
        return _back_with_error(request, str(exc))
    finally:
        close(conn)
    return RedirectResponse("/app/admin/domains?flash=created", status_code=303)


@admin_router.get("/org-units", response_model=None)
def org_units_screen(request: Request) -> HTMLResponse:
    """List org units in the caller's domain and create one."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = AdminService(conn)
        units = service.list_org_units(account)
    finally:
        close(conn)
    return render(
        request,
        "admin/org_units.html",
        {
            "active_nav": "admin",
            "account": account,
            "units": units,
            "flash": request.query_params.get("flash"),
        },
    )


@admin_router.post("/org-units", response_model=None, dependencies=[Depends(require_csrf)])
async def create_org_unit(request: Request) -> HTMLResponse | RedirectResponse:
    """Create an org unit inside the caller's domain."""
    account = _account(request)
    form = await request.form()
    name = str(form.get("name") or "").strip()
    if not name:
        return _back_with_error(request, "An org unit needs a name.")
    conn = _conn(request)
    try:
        service = AdminService(conn)
        service.create_org_unit(
            account,
            domain_id=account.domain_id,
            name=name,
            parent_unit_id=str(form.get("parent_unit_id") or "").strip() or None,
            kind=str(form.get("kind") or "team").strip() or "team",
        )
    except (PermissionDenied, NotFoundError, ValueError) as exc:
        return _back_with_error(request, str(exc))
    finally:
        close(conn)
    return RedirectResponse("/app/admin/org-units?flash=created", status_code=303)


@admin_router.get("/evidence/export", response_model=None)
def evidence_export(request: Request) -> Response:
    """Download the tenant's evidence dossier as a zip.

    Owner-only: the export contains the whole governed audit trail for the
    tenant, node counts by kind, every registered memory store's chain
    verification, and the release manifest. A manager can administer users
    but cannot read the full dossier.
    """
    account = _account(request)
    if account.role_id != "owner":
        raise PermissionDenied(
            "only an owner may export the evidence pack",
            payload={"account_id": account.account_id},
        )
    conn = _conn(request)
    try:
        payload = build_evidence_zip(
            conn,
            tenant_id=account.tenant_id,
            db_path=request.app.state.settings.db_path,
        )
    finally:
        close(conn)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="evidence-export.zip"'},
    )


def _account(request: Request) -> Account:
    return request.state.account


def _conn(request: Request):
    return connect(db_path=request.app.state.settings.db_path)


def _back_with_error(
    request: Request,
    message: str,
    **extra: str,
) -> HTMLResponse:
    params = {"error": message, **extra}
    target = request.headers.get("referer") or USERS_URL
    return RedirectResponse(_url_with(target, params), status_code=303)


def _url_with(url: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in url else "?"
    encoded = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{url}{separator}{encoded}"


def _not_found(request: Request, message: str) -> HTMLResponse:
    return render(
        request,
        "admin/user_detail.html",
        {"active_nav": "admin", "account": _account(request), "error": message},
        status_code=404,
    )
