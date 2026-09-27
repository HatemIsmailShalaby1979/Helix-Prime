"""Fixed-window rate limits for the routes a stranger can reach.

The public front door is the only part of the app reachable from outside, so its
routes are the ones worth bounding. The enterprise sign-in path already has limits
of its own (``LoginThrottle``) and is deliberately not touched here.

Buckets are keyed on the resolved client address (see ``client_ip``) **and** the
route name, so one visitor exhausting the WFM submit ceiling cannot lock another
visitor out of the demo screen, and cannot lock anyone out of the sign-in routes.

The fixed-window counter below mirrors ``LoginThrottle`` rather than sharing code
with it. Sharing would mean editing the enterprise login path's implementation,
which was explicitly out of scope for this step; a behaviour-preserving refactor of
a working security control is not worth doing as a side effect of adding a new one.
Unifying the two is a reasonable follow-up in its own right.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Request

from helix_codex_app.db import close, connect
from helix_codex_app.errors import LimitExceeded
from helix_codex_app.security.client_ip import client_ip


@dataclass(frozen=True)
class RouteLimit:
    """One route's ceiling and window."""

    name: str
    max_requests: int
    window_seconds: int


SUPABASE_LOGIN = RouteLimit("auth.supabase_login", 30, 60)
SUPABASE_CALLBACK = RouteLimit("auth.supabase_callback", 30, 60)
PASSWORDLESS_DEMO = RouteLimit("auth.passwordless_demo", 10, 60)
WFM_DEMO_SCREEN = RouteLimit("ops.wfm_demo_screen", 60, 60)
WFM_DEMO_SUBMIT = RouteLimit("ops.wfm_demo_submit", 10, 60)

ALL_LIMITS: tuple[RouteLimit, ...] = (
    SUPABASE_LOGIN,
    SUPABASE_CALLBACK,
    PASSWORDLESS_DEMO,
    WFM_DEMO_SCREEN,
    WFM_DEMO_SUBMIT,
)

UNKNOWN_CLIENT = "unknown"


class RouteThrottle:
    """Fixed-window counters over the route_throttle table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def check(self, limit: RouteLimit, client: str) -> None:
        """Count this request against its window, or refuse it with a 429."""
        self._prune()
        bucket = _bucket(limit, client)
        if self.count(bucket) >= limit.max_requests:
            raise LimitExceeded(
                "Too many requests. Try again in a minute.",
                payload={
                    "limit": limit.name,
                    "window_seconds": limit.window_seconds,
                    "max_requests": limit.max_requests,
                },
            )
        self._hit(bucket, limit.window_seconds)

    def count(self, bucket: str) -> int:
        """Requests recorded in a live window for one bucket, else zero."""
        row = self.conn.execute(
            "SELECT attempts FROM route_throttle WHERE bucket = ?", (bucket,)
        ).fetchone()
        return int(row["attempts"]) if row is not None else 0

    def _hit(self, bucket: str, window_seconds: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = self.conn.execute(
            "SELECT attempts, window_start FROM route_throttle WHERE bucket = ?",
            (bucket,),
        ).fetchone()
        if row is None or _expired(row["window_start"], window_seconds):
            self.conn.execute(
                """
                INSERT OR REPLACE INTO route_throttle (bucket, attempts, window_start)
                VALUES (?, 1, ?)
                """,
                (bucket, now),
            )
        else:
            self.conn.execute(
                "UPDATE route_throttle SET attempts = attempts + 1 WHERE bucket = ?",
                (bucket,),
            )
        self.conn.commit()

    def _prune(self) -> None:
        """Drop rows older than the longest window any route declares.

        Pruning on the longest window rather than the calling route's own means a
        shorter-window bucket is never deleted while a longer one is still live.
        """
        cutoff = (datetime.now(timezone.utc) - _longest_window()).isoformat()
        self.conn.execute("DELETE FROM route_throttle WHERE window_start < ?", (cutoff,))
        self.conn.commit()


def limit_route(limit: RouteLimit) -> Callable[[Request], None]:
    """Build a FastAPI dependency that bounds one route."""

    def dependency(request: Request) -> None:
        settings = request.app.state.settings
        conn = connect(db_path=settings.db_path)
        try:
            RouteThrottle(conn).check(limit, client_ip(request) or UNKNOWN_CLIENT)
        finally:
            close(conn)

    return dependency


def _bucket(limit: RouteLimit, client: str) -> str:
    return f"route:{limit.name}:ip:{client.strip()}"


def _longest_window() -> timedelta:
    return timedelta(seconds=max(limit.window_seconds for limit in ALL_LIMITS))


def _expired(window_start: str | None, window_seconds: int) -> bool:
    try:
        started = datetime.fromisoformat(window_start)
    except (TypeError, ValueError):
        return True
    return datetime.now(timezone.utc) - started > timedelta(seconds=window_seconds)
