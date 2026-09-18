"""SQLite-backed login throttling for the app sign-in surface.

Two fixed-window buckets bound abuse without keeping anything in memory:
one per source address and one per login name. Every check first deletes
buckets whose window has expired, so the table holds only live windows and
stays small no matter how long the app runs. Buckets never distinguish a
known account from an unknown one: the login-name bucket is keyed on the
supplied domain and username, so throttling cannot be used to enumerate
accounts.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

THROTTLE_WINDOW_MINUTES = 10
MAX_ATTEMPTS_PER_IP = 20
MAX_ATTEMPTS_PER_LOGIN = 10


def login_bucket(domain_name: str, username: str) -> str:
    return f"login:{domain_name.strip().lower()}:{(username or '').strip().lower()}"


def ip_bucket(ip: str) -> str:
    return f"ip:{ip.strip()}"


class LoginThrottle:
    """Fixed-window counters over the login_throttle table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def throttled(self, *, login_key: str, ip: str | None) -> str | None:
        """Return the tripped bucket kind, or None when the attempt may proceed."""
        self._prune()
        if ip is not None and self._count(ip_bucket(ip)) >= MAX_ATTEMPTS_PER_IP:
            return "ip"
        if self._count(login_key) >= MAX_ATTEMPTS_PER_LOGIN:
            return "login"
        return None

    def record(self, *, login_key: str, ip: str | None) -> None:
        """Count one failed attempt in the current window for each bucket."""
        if ip is not None:
            self._hit(ip_bucket(ip))
        self._hit(login_key)
        self.conn.commit()

    def clear(self, *, login_key: str, ip: str | None) -> None:
        """Forget a login name and address after a successful sign-in."""
        if ip is not None:
            self.conn.execute("DELETE FROM login_throttle WHERE bucket = ?", (ip_bucket(ip),))
        self.conn.execute("DELETE FROM login_throttle WHERE bucket = ?", (login_key,))
        self.conn.commit()

    def _count(self, bucket: str) -> int:
        row = self.conn.execute(
            "SELECT attempts FROM login_throttle WHERE bucket = ?", (bucket,)
        ).fetchone()
        return int(row["attempts"]) if row is not None else 0

    def _hit(self, bucket: str) -> None:
        now = _now()
        row = self.conn.execute(
            "SELECT attempts, window_start FROM login_throttle WHERE bucket = ?",
            (bucket,),
        ).fetchone()
        if row is None or _expired(row["window_start"]):
            self.conn.execute(
                """
                INSERT OR REPLACE INTO login_throttle (bucket, attempts, window_start)
                VALUES (?, 1, ?)
                """,
                (bucket, now),
            )
        else:
            self.conn.execute(
                "UPDATE login_throttle SET attempts = attempts + 1 WHERE bucket = ?",
                (bucket,),
            )

    def _prune(self) -> None:
        cutoff = (datetime.now(timezone.utc) - _window()).isoformat()
        self.conn.execute("DELETE FROM login_throttle WHERE window_start < ?", (cutoff,))
        self.conn.commit()


def _window() -> timedelta:
    return timedelta(minutes=THROTTLE_WINDOW_MINUTES)


def _expired(window_start: str | None) -> bool:
    try:
        started = datetime.fromisoformat(window_start)
    except (TypeError, ValueError):
        return True
    return datetime.now(timezone.utc) - started > _window()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
