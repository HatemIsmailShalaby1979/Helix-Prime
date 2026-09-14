"""The request guard: who is calling, and what they may do.

current_account reads the helix_session cookie, verifies the session against
the sessions table, refreshes the idle timestamp, loads the account, and
attaches session and account to request.state. It is installed once at the
/app router boundary, so a handler can never skip it. require_csrf guards
every mutating /app route by comparing the X-CSRF-Token header with the
session's stored CSRF token using compare_digest. require_scope,
require_capability, and require_permission (checked against the app
permission catalog) gate the finer actions; an unknown permission key is
denied, never allowed.
"""
from __future__ import annotations

import hmac
from collections.abc import Callable

from fastapi import Depends, Request

from helix_codex_app.db import close, connect
from helix_codex_app.errors import AuthError, PermissionDenied
from helix_codex_app.security.accounts import Account, AccountRepository
from helix_codex_app.security.permissions import has_permission
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore


def current_account(request: Request) -> Account:
    """Authenticate the caller and refresh the session, or raise AuthError.

    A fresh database handle is opened and closed here, per request, so a
    guard never outlives the call. request.state.account and
    request.state.session are set for handlers and the render layer.
    """
    settings = request.app.state.settings
    token = request.cookies.get(SESSION_COOKIE, "")
    conn = connect(db_path=settings.db_path)
    try:
        store = SessionStore(conn, settings)
        session = store.verify(token)
        if session is None:
            raise AuthError("no valid session")
        store.touch(session.session_id)
        account = AccountRepository(conn).get_account_by_id(session.account_id)
        if account is None or account.status != "active":
            raise AuthError("account unavailable")
    finally:
        close(conn)
    request.state.session = session
    request.state.account = account
    return account


def require_csrf(request: Request, _caller: Account = Depends(current_account)) -> None:
    """Reject a mutating request whose CSRF token does not match its session."""
    session = getattr(request.state, "session", None)
    if session is None:
        raise PermissionDenied("csrf: no active session")
    header = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(header, session.csrf_token):
        raise PermissionDenied("csrf: token mismatch")


def require_permission(key: str) -> Callable[[Request, Account], None]:
    """Return a dependency granting the route only for a granted permission.

    has_permission resolves the account's role against the app permission
    catalog and then unions the account's enabled capability rows, so an
    admin grant or revoke is effective on the very next request. An unknown
    key or unknown role denies, never allows.
    """

    def dependency(request: Request, account: Account = Depends(current_account)) -> None:
        settings = request.app.state.settings
        conn = connect(db_path=settings.db_path)
        try:
            granted = has_permission(account, key, conn)
        finally:
            close(conn)
        if not granted:
            raise PermissionDenied(
                f"permission {key!r} not granted",
                payload={"account_id": account.account_id, "permission_key": key},
            )

    return dependency


def require_capability(key: str) -> Callable[[Request, Account], None]:
    """Return a dependency granting the route only for an enabled capability."""

    def dependency(request: Request, account: Account = Depends(current_account)) -> None:
        settings = request.app.state.settings
        conn = connect(db_path=settings.db_path)
        try:
            row = conn.execute(
                """
                SELECT enabled FROM account_capabilities
                WHERE account_id = ? AND capability_key = ?
                """,
                (account.account_id, key),
            ).fetchone()
        finally:
            close(conn)
        if row is None or not row["enabled"]:
            raise PermissionDenied(
                f"capability {key!r} not granted",
                payload={"account_id": account.account_id, "capability_key": key},
            )

    return dependency


def require_scope(tenant_id: str) -> Callable[[Account], None]:
    """Return a dependency rejecting any caller outside the given tenant."""

    def dependency(account: Account = Depends(current_account)) -> None:
        if account.tenant_id != tenant_id:
            raise PermissionDenied(
                f"scope {tenant_id!r} is not the caller's own tenant",
                payload={
                    "account_id": account.account_id,
                    "tenant_id": account.tenant_id,
                    "requested_scope": tenant_id,
                },
            )

    return dependency
