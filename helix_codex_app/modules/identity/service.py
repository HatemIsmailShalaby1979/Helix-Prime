"""Domain login, logout, and password change for the app.

login() is the one place a username and password become a session. Every
outcome — a success, a wrong password, a missing domain, a missing account, a
locked account — writes a login_events row so the attempts and the lockout are
auditable. Credential failures share one message: the code names the
underlying cause for the audit row, but the router only ever prints the same
user-facing sentence, so a caller cannot learn whether the domain, the
username, or the password was the wrong part.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from helix_codex_app.config import AppSettings, get_app_settings
from helix_codex_app.security.accounts import Account, AccountRepository
from helix_codex_app.security.passwords import hash_password, verify_password
from helix_codex_app.security.sessions import Session, SessionStore
from helix_codex_app.security.throttle import LoginThrottle, login_bucket

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
MIN_PASSWORD_LENGTH = 8

BAD_CREDENTIALS_MESSAGE = "The sign-in details did not match."
LOCKED_MESSAGE = "Too many failed attempts. Try again in 15 minutes."
THROTTLED_MESSAGE = "Too many sign-in attempts. Try again in a few minutes."

_CREDENTIAL_FAILURES = frozenset({"no_such_domain", "no_such_account", "bad_password"})


@dataclass(frozen=True)
class LoginResult:
    """The outcome of one login attempt.

    ok and code drive the router; error is the one message the page may show.
    For a credential failure the code names the audit cause while error stays
    the shared sentence, so the divergence between the two is intentional.
    """

    ok: bool
    code: str | None = None
    error: str | None = None
    token: str | None = None
    session: Session | None = None
    account: Account | None = None
    must_change_password: bool = False


class LoginService:
    """The write surface for signing in and out and for password changes."""

    def __init__(self, conn: sqlite3.Connection, settings: AppSettings | None = None) -> None:
        self.conn = conn
        self.settings = settings or get_app_settings()
        self.repo = AccountRepository(conn)
        self.sessions = SessionStore(conn, self.settings)
        self.throttle = LoginThrottle(conn)

    def login(
        self,
        domain_name: str,
        username: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResult:
        """Resolve username@domain and turn a verified password into a session.

        A missing domain or account returns the same generic failure as a
        wrong password, and the single rule stated here is also the unit that
        proves it: every path in _CREDENTIAL_FAILURES renders error equal to
        BAD_CREDENTIALS_MESSAGE. A source address or login name that fails too
        often in a short window is throttled with a 429-shaped result before
        any account is touched. Lockout counts real accounts only; after
        MAX_FAILED_ATTEMPTS consecutive failures the account is locked for
        LOCK_MINUTES and the lock itself is recorded in login_events.
        """
        domain = self.repo.get_domain_by_name(domain_name)
        account = self.repo.get_account_by_login(domain_name, username) if domain else None
        bucket = login_bucket(domain_name, username)
        if self.throttle.throttled(login_key=bucket, ip=ip) is not None:
            self._record("throttled", None, domain.domain_id if domain else None, ip, user_agent)
            return LoginResult(ok=False, code="throttled", error=THROTTLED_MESSAGE)
        if domain is None:
            self.throttle.record(login_key=bucket, ip=ip)
            self._record("no_such_domain", None, None, ip, user_agent)
            return LoginResult(ok=False, code="no_such_domain", error=BAD_CREDENTIALS_MESSAGE)
        if account is None:
            self.throttle.record(login_key=bucket, ip=ip)
            self._record("no_such_account", None, domain.domain_id, ip, user_agent)
            return LoginResult(ok=False, code="no_such_account", error=BAD_CREDENTIALS_MESSAGE)
        if self._is_locked(account):
            self._record("locked", account.account_id, domain.domain_id, ip, user_agent)
            return LoginResult(ok=False, code="locked", error=LOCKED_MESSAGE)
        if account.status == "locked":
            self.repo.reset_failed_attempts(account.account_id)
            self.repo.set_status(account.account_id, "active")
            account = self.repo.get_account_by_id(account.account_id)
        if account.status != "active":
            self._record("unusable_account", account.account_id, domain.domain_id, ip, user_agent)
            return LoginResult(ok=False, code="unusable_account", error=BAD_CREDENTIALS_MESSAGE)
        if not account.password_hash or not verify_password(password, account.password_hash):
            self.throttle.record(login_key=login_bucket(domain_name, username), ip=ip)
            updated = self.repo.record_failed_attempt(account.account_id)
            if updated.failed_attempts >= MAX_FAILED_ATTEMPTS:
                until = (datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)).isoformat()
                self.repo.lock_account(account.account_id, until=until)
                self._record("locked", account.account_id, domain.domain_id, ip, user_agent)
                return LoginResult(ok=False, code="locked", error=LOCKED_MESSAGE)
            self._record("bad_password", account.account_id, domain.domain_id, ip, user_agent)
            return LoginResult(ok=False, code="bad_password", error=BAD_CREDENTIALS_MESSAGE)
        self.repo.reset_failed_attempts(account.account_id)
        self.throttle.clear(login_key=login_bucket(domain_name, username), ip=ip)
        self.conn.execute(
            "UPDATE accounts SET last_login_at = ? WHERE account_id = ?",
            (_now(), account.account_id),
        )
        self.conn.commit()
        fresh = self.repo.get_account_by_id(account.account_id)
        token, session = self.sessions.issue_session(fresh, ip=ip, user_agent=user_agent)
        self._record("success", fresh.account_id, domain.domain_id, ip, user_agent)
        return LoginResult(
            **{
                "ok": True,
                "code": "success",
                "token": token,
                "session": session,
                "account": fresh,
                "must_change_password": fresh.must_change_password,
            }
        )

    def logout(self, session_id: str) -> None:
        """Revoke one session; its very next verify fails."""
        self.sessions.revoke(session_id)

    def change_password(self, account: Account, old: str, new: str) -> Account:
        """Verify the old password, store a new hash, clear must_change_password."""
        if not account.password_hash or not verify_password(old, account.password_hash):
            raise ValueError("The current password is incorrect.")
        if len(new) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"The new password must be at least {MIN_PASSWORD_LENGTH} characters long."
            )
        updated = self.repo.set_password(account.account_id, hash_password(new))
        self.sessions.revoke_all_for(account.account_id)
        return updated

    def _is_locked(self, account: Account) -> bool:
        if account.status != "locked":
            return False
        if account.locked_until is None:
            return True
        try:
            return datetime.fromisoformat(account.locked_until) > datetime.now(timezone.utc)
        except (TypeError, ValueError):
            return True

    def _record(
        self,
        reason: str,
        account_id: str | None,
        domain_id: str | None,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        event_id = f"event-{uuid.uuid4().hex}"
        self.conn.execute(
            """
            INSERT INTO login_events (
                event_id, account_id, domain_id, outcome, reason, ip, user_agent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                account_id,
                domain_id,
                "success" if reason == "success" else "fail",
                reason,
                ip,
                user_agent,
                _now(),
            ),
        )
        self.conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
