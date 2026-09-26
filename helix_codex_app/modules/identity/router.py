"""Auth routes: the sign-in screen, sign-out, the identity fragment, and the password screen.

The login form is public, because there is no session yet and a person must be
able to reach it before they are signed in. Everything here answers with a
classic redirect, a full page, or an HTMX fragment — never a JSON-only
endpoint. Credential failures re-render the login page with the service's one
shared message; the machine-readable code stays in login_events, never in the
page, so a caller cannot distinguish a bad domain from a bad password.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from helix_codex_app.db import close, connect
from helix_codex_app.errors import AuthError
from helix_codex_app.modules.identity.service import LoginService
from helix_codex_app.modules.identity.supabase import (
    SupabaseAuthError,
    authorize_url,
    exchange_code,
)
from helix_codex_app.security.accounts import AccountRepository, ensure_demo_account
from helix_codex_app.security.guard import current_account, require_csrf
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore, set_session_cookie
from helix_codex_app.templating import render

identity_router = APIRouter(prefix="/app/auth")

passwordless_demo_router = APIRouter(prefix="/app/auth")

LOGIN_REDIRECT = "/app/"


@passwordless_demo_router.get("/demo", response_model=None)
def demo_entry(request: Request) -> RedirectResponse:
    """Create the scoped demo identity on first use and issue a session.

    A development and test fixture, not a public entry point: it mints a session
    for the shared demo identity with no password and no identity-provider round
    trip. `create_app` mounts this router only when
    `settings.enable_passwordless_demo` is true, so a deployed instance has no
    such route at all rather than a refused one. GitHub sign-in through Supabase
    is the one public flow.
    """
    settings = request.app.state.settings
    conn = connect(db_path=settings.db_path)
    try:
        account = ensure_demo_account(
            AccountRepository(conn),
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        token, _session = SessionStore(conn, settings).issue_session(
            account,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    finally:
        close(conn)
    response = RedirectResponse("/app/ops", status_code=303)
    set_session_cookie(response, token, settings)
    return response


@identity_router.get("/supabase/login", response_model=None)
def supabase_login(request: Request) -> RedirectResponse | JSONResponse:
    """Start the GitHub OAuth PKCE flow through Supabase Auth.

    Supabase does not forward this app's `state` to the callback. It only
    preserves the query string already present on `redirect_to` and appends its
    own `code`, so `state` must travel inside `redirect_to` itself.
    """
    settings = request.app.state.settings
    if not settings.supabase_url or not settings.supabase_anon_key or not settings.supabase_redirect_uri:
        return JSONResponse({"error": "supabase_auth_not_configured"}, status_code=503)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = hashlib.sha256(verifier.encode()).digest()
    encoded = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode()
    redirect_uri = f"{settings.supabase_redirect_uri}?state={quote(state)}"
    response = RedirectResponse(
        authorize_url(settings.supabase_url, redirect_uri, state=state, challenge=encoded),
        status_code=303,
    )
    response.set_cookie("supabase_oauth_state", state, secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.set_cookie("supabase_oauth_verifier", verifier, secure=settings.cookie_secure, httponly=True, samesite="lax")
    return response


@identity_router.get("/supabase/callback", response_model=None)
async def supabase_callback(request: Request) -> RedirectResponse | HTMLResponse:
    """Verify the Supabase user and bridge it to the scoped demo session."""
    query = request.query_params
    state = request.cookies.get("supabase_oauth_state")
    verifier = request.cookies.get("supabase_oauth_verifier")
    settings = request.app.state.settings
    if query.get("error") or not state or state != query.get("state") or not verifier:
        return HTMLResponse("Sign-in could not be verified.", status_code=400)
    try:
        user = await exchange_code(settings.supabase_url or "", settings.supabase_anon_key or "", query.get("code", ""), verifier)
    except SupabaseAuthError as exc:
        print({"event_type": "supabase_auth_error", "status": exc.status, "detail": exc.detail}, flush=True)
        return HTMLResponse("Sign-in could not be verified.", status_code=401)
    conn = connect(db_path=settings.db_path)
    try:
        repo = AccountRepository(conn)
        email = str(user.get("email"))
        account = ensure_demo_account(repo, password_hash=hash_password(secrets.token_urlsafe(32)), display_name=email)
        if account.email != email:
            account = repo.update_account(account.account_id, email=email, display_name=email)
        token, _session = SessionStore(conn, settings).issue_session(account, ip=_client_ip(request), user_agent=request.headers.get("user-agent"))
    finally:
        close(conn)
    response = RedirectResponse("/app/ops", status_code=303)
    set_session_cookie(response, token, settings)
    response.delete_cookie("supabase_oauth_state")
    response.delete_cookie("supabase_oauth_verifier")
    return response


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
