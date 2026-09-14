"""Wire contracts for the notification API.

The shape is pinned before any client exists, so it cannot drift without
a schema-level error surfacing in tests.
"""
from __future__ import annotations

from pydantic import BaseModel

from helix_codex_app.modules.notifications.repository import Notification


class NotificationOut(BaseModel):
    """One notification on the wire."""

    notification_id: str
    account_id: str
    kind: str
    title: str
    body: str
    link: str | None = None
    read_at: str | None = None
    created_at: str
    correlation_id: str

    @classmethod
    def from_notification(cls, notification: Notification) -> NotificationOut:
        return cls(
            notification_id=notification.notification_id,
            account_id=notification.account_id,
            kind=notification.kind,
            title=notification.title,
            body=notification.body,
            link=notification.link,
            read_at=notification.read_at,
            created_at=notification.created_at,
            correlation_id=notification.correlation_id,
        )
