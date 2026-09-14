"""The storage layer for per-account notifications.

A notification is a lightweight row: who it belongs to, what happened, and
whether it has been read. The service layer adds the governed envelope
(record_node) and the bus publish for the live badge; the repository is
pure storage.  Membership or cross-account access is not scoped here —
that is a router-level gate that passes an account_id from the session.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Notification:
    """One alert belonging to one account."""

    notification_id: str
    account_id: str
    kind: str
    title: str
    body: str
    link: str | None
    read_at: str | None
    created_at: str
    correlation_id: str


class NotificationRepository:
    """The read and write surface for the notifications table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(
        self,
        *,
        account_id: str,
        kind: str,
        title: str,
        body: str,
        link: str | None = None,
        correlation_id: str,
    ) -> Notification:
        """Insert one notification row and return it."""
        notification_id = _new_id("notif")
        created_at = _now()
        self.conn.execute(
            """
            INSERT INTO notifications (
                notification_id, account_id, kind, title, body, link,
                read_at, created_at, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (notification_id, account_id, kind, title, body, link, created_at, correlation_id),
        )
        self.conn.commit()
        return Notification(
            notification_id=notification_id,
            account_id=account_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            read_at=None,
            created_at=created_at,
            correlation_id=correlation_id,
        )

    def get(self, notification_id: str, account_id: str) -> Notification | None:
        """One notification owned by the account, or None."""
        row = self.conn.execute(
            """
            SELECT notification_id, account_id, kind, title, body, link,
                   read_at, created_at, correlation_id
            FROM notifications
            WHERE notification_id = ? AND account_id = ?
            """,
            (notification_id, account_id),
        ).fetchone()
        return _from_row(row) if row else None

    def list_for(self, account_id: str, *, limit: int = 50) -> list[Notification]:
        """Newest-first list of one account's notifications."""
        limit = max(1, min(limit, 200))
        rows = self.conn.execute(
            """
            SELECT notification_id, account_id, kind, title, body, link,
                   read_at, created_at, correlation_id
            FROM notifications
            WHERE account_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (account_id, limit),
        ).fetchall()
        return [_from_row(row) for row in rows]

    def unread_count(self, account_id: str) -> int:
        """How many notifications have not yet been read."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM notifications" " WHERE account_id = ? AND read_at IS NULL",
            (account_id,),
        ).fetchone()
        return row["n"] or 0

    def mark_read(self, notification_id: str, account_id: str) -> bool:
        """Stamp read_at. Idempotent: returns False when the row is already
        read or belongs to someone else."""
        cursor = self.conn.execute(
            """
            UPDATE notifications
            SET read_at = ?
            WHERE notification_id = ? AND account_id = ? AND read_at IS NULL
            """,
            (_now(), notification_id, account_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def mark_all_read(self, account_id: str) -> int:
        """Stamp every unread notification for the account.
        Returns the number of rows newly stamped."""
        cursor = self.conn.execute(
            """
            UPDATE notifications
            SET read_at = ?
            WHERE account_id = ? AND read_at IS NULL
            """,
            (_now(), account_id),
        )
        self.conn.commit()
        return cursor.rowcount


def _from_row(row: sqlite3.Row) -> Notification:
    return Notification(
        notification_id=row["notification_id"],
        account_id=row["account_id"],
        kind=row["kind"],
        title=row["title"],
        body=row["body"],
        link=row["link"],
        read_at=row["read_at"],
        created_at=row["created_at"],
        correlation_id=row["correlation_id"],
    )
