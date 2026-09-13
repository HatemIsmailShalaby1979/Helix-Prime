"""Opaque, revocable cookie sessions.

A session's public face is an unguessable token kept only in the browser
cookie. The store keeps just its SHA-256 hash plus a separate CSRF token for
double-submit protection, so a database leak does not hand over live
sessions. verify() also joins the account row, so a disabled, locked, or
terminated account invalidates its sessions on the very next request.
Timeouts come from AppSettings: the idle window from session_idle_minutes and
the hard ceiling from session_absolute_days.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from starlette.responses import Response

from helix_codex_app.config import AppSettings, get_app_settings
from helix_codex_app.security.accounts import Account

SESSION_COOKIE = "helix_session"


@dataclass(frozen=True)
class Session:
    """One live session, as loaded from the sessions table.

    csrf_token is the double-submit token a mutating request must echo back
    in the X-CSRF-Token header. account_status mirrors the account row at
    verify time, so a session can be told apart from an account that was
    disabled after the session was issued.
    """

    session_id: str
    account_id: str
    csrf_token: str
    issued_at: str
    expires_at: str
    last_seen_at: str
    ip: str | None = None
    user_agent: str | None = None
    revoked_at: str | None = None
    account_status: str | None = None


class SessionStore:
    """The read and write surface for the sessions table."""

    def __init__(self, conn: sqlite3.Connection, settings: AppSettings | None = None) -> None:
        self.conn = conn
        self.settings = settings or get_app_settings()

    def issue_session(
        self,
        account: Account,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, Session]:
        """Create a session and return (token, session). Only the token hash
        and the CSRF token are stored; the token itself is handed to the
        caller exactly once, to be set as the cookie value."""
        if account.status != "active":
            raise ValueError(f"issue_session: account {account.account_id} is not active")
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=f"session-{uuid.uuid4().hex}",
            account_id=account.account_id,
            csrf_token=secrets.token_urlsafe(32),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(days=self.settings.session_absolute_days)).isoformat(),
            last_seen_at=now.isoformat(),
            ip=ip,
            user_agent=user_agent,
            account_status=account.status,
        )
        self.conn.execute(
            """
            INSERT INTO sessions (
                session_id, account_id, token_hash, csrf_token, issued_at,
                expires_at, last_seen_at, ip, user_agent, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                session.session_id,
                session.account_id,
                _hash_token(token),
                session.csrf_token,
                session.issued_at,
                session.expires_at,
                session.last_seen_at,
                session.ip,
                session.user_agent,
            ),
        )
        self.conn.commit()
        return token, session

    def verify(self, token: str) -> Session | None:
        """Return the session for a token, or None.

        Missing, revoked, expired, idle-expired, and locked-account sessions
        all fail closed: each returns None, never a session.
        """
        if not token or not token.strip():
            return None
        row = self.conn.execute(
            """
            SELECT s.session_id, s.account_id, s.csrf_token, s.issued_at,
                   s.expires_at, s.last_seen_at, s.ip, s.user_agent,
                   s.revoked_at, a.status AS account_status
            FROM sessions s
            JOIN accounts a ON a.account_id = s.account_id
            WHERE s.token_hash = ?
            """,
            (_hash_token(token),),
        ).fetchone()
        if row is None:
            return None
        session = _session_from_row(row)
        if session.revoked_at is not None:
            return None
        if session.account_status != "active":
            return None
        now = datetime.now(timezone.utc)
        expires = _parse_iso(session.expires_at)
        if expires is None or now > expires:
            return None
        last_seen = _parse_iso(session.last_seen_at)
        idle_window = timedelta(minutes=self.settings.session_idle_minutes)
        if last_seen is None or now - last_seen > idle_window:
            return None
        return session

    def touch(self, session_id: str) -> None:
        """Refresh the idle timestamp. Call after a successful verify."""
        self.conn.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE session_id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        self.conn.commit()

    def revoke(self, session_id: str) -> None:
        """Revoke one session; the very next verify of its token fails."""
        self.conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE session_id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        self.conn.commit()

    def revoke_all_for(self, account_id: str) -> int:
        """Revoke every live session for an account; returns how many."""
        cursor = self.conn.execute(
            """
            UPDATE sessions SET revoked_at = ?
            WHERE account_id = ? AND revoked_at IS NULL
            """,
            (datetime.now(timezone.utc).isoformat(), account_id),
        )
        self.conn.commit()
        return cursor.rowcount


def set_session_cookie(
    response: Response,
    token: str,
    settings: AppSettings | None = None,
) -> None:
    """Write the session cookie with the app's fixed attributes.

    HttpOnly, SameSite=Lax, and path=/ are unconditional. Secure follows
    settings.cookie_secure so plain-HTTP local development can disable it.
    """
    resolved = settings or get_app_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=resolved.session_absolute_days * 86_400,
        path="/",
        secure=resolved.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _session_from_row(row: sqlite3.Row) -> Session:
    return Session(
        session_id=row["session_id"],
        account_id=row["account_id"],
        csrf_token=row["csrf_token"],
        issued_at=row["issued_at"],
        expires_at=row["expires_at"],
        last_seen_at=row["last_seen_at"],
        ip=row["ip"],
        user_agent=row["user_agent"],
        revoked_at=row["revoked_at"],
        account_status=row["account_status"],
    )
