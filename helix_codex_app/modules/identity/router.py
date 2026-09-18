"""Auth routes: the sign-in screen, sign-out, the identity fragment, and the password screen.

The login form is public, because there is no session yet and a person must be
able to reach it before they are signed in. Everything here answers with a
classic redirect, a full page, or an HTMX fragment — never a JSON-only
endpoint. Credential failures re-render the login page with the service's one
shared message; the machine-readable code stays in login_events, never in the
page, so a caller cannot distinguish a bad domain from a bad password.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from helix_codex_app.db import close, connect
from helix_codex_app.errors import AuthError
from helix_codex_app.modules.identity.service import LoginService
from helix_codex_app.security.guard import current_account, require_csrf
from helix_codex_app.security.sessions import SESSION_COOKIE, set_session_cookie
from helix_codex_app.templating import render

identity_router = APIRouter(prefix="/app/auth")

LOGIN_REDIRECT = "/app/"


@identity_router.get("/login", response_model=None)
def login_form(request: Request) -> HTMLResponse | RedirectResponse:
    """Show the sign-in form, or send an already-signed-in person to the app."""
    try:
        current_account(request)
    except AuthError:
        return render(request, "auth/login.html")
    return RedirectResponse(LOGIN_REDIRECT, status_code=303)


@identity_router.post("/login", response_model=None)
async def login_submit(request: Request) -> HTMLResponse | RedirectResponse:
    """Sign in with domain + username + password and set the session cookie."""
    form = await request.form()
    domain_name = (form.get("domain") or "").strip()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    settings = request.app.state.settings
    conn = connect(db_path=settings.db_path)
    try:
        result = LoginService(conn, settings).login(
            domain_name,
            username,
            password,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    finally:
        close(conn)
    if result.ok:
        target = "/app/auth/password" if result.must_change_password else LOGIN_REDIRECT
        response = RedirectResponse(target, status_code=303)
        set_session_cookie(response, result.token, settings)
        return response
    if result.code == "throttled":
        return render(
            request,
            "auth/login.html",
            {"error": result.error, "domain": domain_name, "username": username},
            status_code=429,
        )
    return render(
        request,
        "auth/login.html",
        {"error": result.error, "domain": domain_name, "username": username},
    )


@identity_router.get("/me", dependencies=[Depends(current_account)])
def me(request: Request) -> HTMLResponse:
    """The signed-in identity fragment: display name and role."""
    return render(request, "auth/me.html", {"account": request.state.account})


@identity_router.post(
    "/logout",
    dependencies=[Depends(current_account), Depends(require_csrf)],
)
def logout(request: Request) -> HTMLResponse:
    """Revoke this session and clear the cookie."""
    session = request.state.session
    settings = request.app.state.settings
    conn = connect(db_path=settings.db_path)
    try:
        LoginService(conn, settings).logout(session.session_id)
    finally:
        close(conn)
    response = HTMLResponse("")
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    if request.headers.get("hx-request") == "true":
        response.headers["HX-Redirect"] = "/app/auth/login"
    return response


@identity_router.get("/password", dependencies=[Depends(current_account)])
def password_form(request: Request) -> HTMLResponse:
    """The set-a-new-password screen."""
    return render(request, "auth/password.html", {"account": request.state.account})


@identity_router.post(
    "/password",
    dependencies=[Depends(current_account), Depends(require_csrf)],
    response_model=None,
)
async def password_submit(request: Request) -> HTMLResponse | RedirectResponse:
    """Change the password; a bad current password re-renders with an error."""
    account = request.state.account
    settings = request.app.state.settings
    form = await request.form()
    old = form.get("old_password") or ""
    new = form.get("new_password") or ""
    rendered = None
    conn = connect(db_path=settings.db_path)
    try:
        try:
            LoginService(conn, settings).change_password(account, old, new)
        except ValueError as exc:
            rendered = render(
                request, "auth/password.html", {"account": account, "error": str(exc)}
            )
    finally:
        close(conn)
    if rendered is not None:
        return rendered
    if request.headers.get("hx-request") == "true":
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = LOGIN_REDIRECT
        return response
    return RedirectResponse(LOGIN_REDIRECT, status_code=303)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None
