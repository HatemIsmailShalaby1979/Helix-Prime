"""The write and read surface for the notification centre.

The service owns two jobs:
1. CRUD on notification rows (delegated to the repository) plus the
   governed envelope (record_node) and a bus publish so the live badge
   updates instantly.
2. The trigger hooks that messaging calls after a message is committed:
   direct messages produce a "dm" notification for every other member,
   group messages produce a "mention" notification for each @username
   that resolves to an account in the same domain.
"""
from __future__ import annotations

import re
import sqlite3
import uuid

from helix_codex_app.db import record_node
from helix_codex_app.integration.sse_bridge import publish
from helix_codex_app.modules.notifications.repository import Notification, NotificationRepository
from helix_codex_app.security.accounts import Account, AccountRepository

MENTION_RE = re.compile(r"@([A-Za-z0-9_]+)")
PROVENANCE_SOURCE = "helix_codex_app.notifications"
PROVENANCE_DATA_MODE = "app_runtime"
MAX_PREVIEW = 120
DIRECT_KIND = "direct"


class NotificationService:
    """Notifications, with the governance envelope and live badge publish."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = NotificationRepository(conn)
        self.accounts = AccountRepository(conn)

    def create(
        self,
        *,
        account_id: str,
        tenant_id: str,
        client_id: str | None,
        domain_id: str | None,
        kind: str,
        title: str,
        body: str,
        link: str | None,
        created_by: str,
        correlation_id: str,
    ) -> Notification:
        """Store one notification, write its governed node, and publish
        a live badge frame to the account's subscribers."""
        notification = self.repo.create(
            account_id=account_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            correlation_id=correlation_id,
        )
        record_node(
            self.conn,
            tenant_id=tenant_id,
            client_id=client_id,
            domain_id=domain_id,
            correlation_id=correlation_id,
            classification="internal",
            nature="system_event",
            created_by=created_by,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="notification",
            body={
                "notification_id": notification.notification_id,
                "account_id": account_id,
                "kind": kind,
                "title": title,
                "link": link,
            },
        )
        self._publish_badge(account_id)
        return notification

    def list_for(self, account: Account, *, limit: int = 50) -> list[Notification]:
        """Newest-first list scoped to one account."""
        return self.repo.list_for(account.account_id, limit=limit)

    def unread_count(self, account: Account) -> int:
        """How many notifications are unread for this account."""
        return self.repo.unread_count(account.account_id)

    def mark_read(self, account: Account, notification_id: str) -> bool:
        """Stamp one notification read. Idempotent: returns False when
        the row was already read or does not belong to the account."""
        return self.repo.mark_read(notification_id, account.account_id)

    def mark_all_read(self, account: Account) -> int:
        """Stamp every unread notification for the account read.
        Publishes a zero-count badge frame only when at least one row
        was newly stamped, so a second call is a no-op on the bus too."""
        count = self.repo.mark_all_read(account.account_id)
        if count > 0:
            self._publish_badge(account.account_id)
        return count

    def notify_message_sent(
        self,
        sender: Account,
        conversation_id: str,
        conversation_tenant_id: str,
        conversation_domain_id: str | None,
        conversation_kind: str,
        conversation_title: str | None,
        body: str,
        member_ids: list[str],
    ) -> list[Notification]:
        """Triggered by messaging.send_message after the commit.

        Direct conversations produce one "dm" notification for every
        other member.  Group conversations produce one "mention"
        notification for each @username that resolves to an account in the
        same domain.  The sender is never notified.
        """
        correlation_id = f"notif-{uuid.uuid4().hex}"
        link = f"/app/chat/{conversation_id}"
        created: list[Notification] = []
        if conversation_kind == DIRECT_KIND:
            for recipient_id in member_ids:
                if recipient_id == sender.account_id:
                    continue
                created.append(
                    self.create(
                        account_id=recipient_id,
                        tenant_id=conversation_tenant_id,
                        client_id=sender.client_id,
                        domain_id=conversation_domain_id,
                        kind="dm",
                        title=f"Direct message from {sender.username}",
                        body=body[:MAX_PREVIEW],
                        link=link,
                        created_by=sender.account_id,
                        correlation_id=correlation_id,
                    )
                )
        else:
            for account in self._mentioned_accounts(conversation_domain_id, body):
                if account.account_id == sender.account_id:
                    continue
                created.append(
                    self.create(
                        account_id=account.account_id,
                        tenant_id=conversation_tenant_id,
                        client_id=sender.client_id,
                        domain_id=conversation_domain_id,
                        kind="mention",
                        title=f"Mention in {conversation_title or 'a chat'}",
                        body=body[:MAX_PREVIEW],
                        link=link,
                        created_by=sender.account_id,
                        correlation_id=correlation_id,
                    )
                )
        return created

    def _mentioned_accounts(self, domain_id: str | None, body: str) -> list[Account]:
        """Accounts whose username appears as @name in the message body."""
        if not domain_id or not body:
            return []
        names = {m.group(1).lower() for m in MENTION_RE.finditer(body)}
        if not names:
            return []
        accounts = self.accounts.list_accounts(domain_id)
        by_normalized = {a.username_normalized: a for a in accounts}
        return [by_normalized[n] for n in names if n in by_normalized]

    def _publish_badge(self, account_id: str) -> None:
        """Push the latest unread count to the account's badge subscribers."""
        count = self.repo.unread_count(account_id)
        publish(account_id, "unread_count", {"unread": count})
