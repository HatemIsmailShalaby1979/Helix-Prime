"""The write and read surface for conversations and messages.

The service owns the rules the repository cannot express on its own:
create_direct reuses the conversation between the same two accounts, a
group carries a title, and every sent message lands twice — once as a
working-table row and once as a governed node through record_node(), so
chat is in the audit trail like every other write in the app. Tenant and
client ids come from the sender's account record; the request never supplies
them.
"""
from __future__ import annotations

import sqlite3
import uuid

from helix_codex_app.db import record_node
from helix_codex_app.errors import PermissionDenied
from helix_codex_app.modules.messaging.repository import (
    Conversation,
    Message,
    MessagingRepository,
)
from helix_codex_app.modules.notifications.service import NotificationService
from helix_codex_app.security.accounts import Account

PROVENANCE_SOURCE = "helix_codex_app.messaging"
PROVENANCE_DATA_MODE = "app_runtime"
DIRECT_KIND = "direct"
GROUP_KIND = "group"
MAX_GROUP_MEMBERS = 64
MAX_BODY_LENGTH = 8000


class MessagingService:
    """Conversations and messages, with the governance envelope attached."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = MessagingRepository(conn)

    def create_direct(self, a: Account, b: Account) -> Conversation:
        """The direct conversation between two accounts.

        Calling it twice returns the same conversation, in either argument
        order. The two accounts must belong to the same tenant; a
        cross-tenant conversation is denied, not merely unusual.
        """
        if a.tenant_id != b.tenant_id:
            raise PermissionDenied(
                "a direct conversation stays inside one tenant",
                payload={"tenant_a": a.tenant_id, "tenant_b": b.tenant_id},
            )
        if a.account_id == b.account_id:
            raise ValueError("a direct conversation needs two different accounts")
        existing = self.repo.find_direct_conversation(a.account_id, b.account_id)
        if existing is not None:
            return self.repo.get_conversation(existing, a.account_id)
        conversation = self.repo.create_conversation(
            tenant_id=a.tenant_id,
            domain_id=a.domain_id,
            kind=DIRECT_KIND,
            title=None,
            classification="internal",
            created_by=a.account_id,
            correlation_id=self._correlation_id(),
        )
        self.repo.add_member(conversation.conversation_id, a.account_id)
        self.repo.add_member(conversation.conversation_id, b.account_id)
        return self.repo.get_conversation(conversation.conversation_id, a.account_id)

    def create_group(self, creator: Account, name: str, members: list[Account]) -> Conversation:
        """A group conversation with an explicit member list.

        The creator is a member even when the list omits them. Duplicate
        members collapse. A member from another tenant is denied, because
        the conversation carries the creator's tenant and nothing else.
        """
        if not name or not name.strip():
            raise ValueError("a group conversation needs a name")
        roster = [creator] + [member for member in members]
        for member in roster:
            if member.tenant_id != creator.tenant_id:
                raise PermissionDenied(
                    "a group conversation stays inside one tenant",
                    payload={
                        "creator_tenant": creator.tenant_id,
                        "member_tenant": member.tenant_id,
                    },
                )
        unique_ids = {account.account_id for account in roster}
        if len(unique_ids) > MAX_GROUP_MEMBERS:
            raise ValueError(f"a group conversation holds at most {MAX_GROUP_MEMBERS} members")
        conversation = self.repo.create_conversation(
            tenant_id=creator.tenant_id,
            domain_id=creator.domain_id,
            kind=GROUP_KIND,
            title=name.strip(),
            classification="internal",
            created_by=creator.account_id,
            correlation_id=self._correlation_id(),
        )
        for account_id in unique_ids:
            self.repo.add_member(conversation.conversation_id, account_id)
        return self.repo.get_conversation(conversation.conversation_id, creator.account_id)

    def send_message(
        self,
        account: Account,
        conversation_id: str,
        body: str,
    ) -> Message:
        """Store a message from a member and write its governed node.

        The repository has already answered membership by the time this
        runs: get_conversation raises NotFoundError for a non-member, and
        that is the only path to a conversation here. The nodes row is
        written with the conversation's own correlation_id, so a thread
        reads as one story in the audit trail. The row and the node are
        two records of one human action, written in the same call.
        """
        if not body or not body.strip():
            raise ValueError("a message needs a body")
        if len(body) > MAX_BODY_LENGTH:
            raise ValueError(f"a message holds at most {MAX_BODY_LENGTH} characters")
        conversation = self.repo.get_conversation(conversation_id, account.account_id)
        message = self.repo.append_message(
            conversation_id=conversation.conversation_id,
            sender_account_id=account.account_id,
            body=body,
            classification=conversation.classification,
        )
        node_id = record_node(
            self.conn,
            tenant_id=conversation.tenant_id,
            client_id=account.client_id,
            domain_id=conversation.domain_id,
            correlation_id=conversation.correlation_id,
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="message",
            body={
                "message_id": message.message_id,
                "conversation_id": conversation.conversation_id,
                "sender_account_id": account.account_id,
                "body": message.body,
            },
            thread_id=conversation.conversation_id,
        )
        stamped = Message(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            sender_account_id=message.sender_account_id,
            body=message.body,
            classification=message.classification,
            created_at=message.created_at,
            node_id=node_id,
        )
        self.conn.execute(
            "UPDATE messages SET node_id = ? WHERE message_id = ?",
            (node_id, message.message_id),
        )
        self.conn.commit()
        NotificationService(self.conn).notify_message_sent(
            sender=account,
            conversation_id=conversation.conversation_id,
            conversation_tenant_id=conversation.tenant_id,
            conversation_domain_id=conversation.domain_id,
            conversation_kind=conversation.kind,
            conversation_title=conversation.title,
            body=message.body,
            member_ids=self.repo.member_ids(conversation.conversation_id),
        )
        return stamped

    def list_conversations(self, account: Account) -> list[Conversation]:
        """Every conversation the account belongs to."""
        return self.repo.list_conversations(account.account_id)

    def get_conversation(self, account: Account, conversation_id: str) -> Conversation:
        """One conversation, membership enforced."""
        return self.repo.get_conversation(conversation_id, account.account_id)

    def list_messages(
        self,
        account: Account,
        conversation_id: str,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> list[Message]:
        """Messages of one conversation, membership enforced."""
        self.repo.get_conversation(conversation_id, account.account_id)
        return self.repo.list_messages(conversation_id, before=before, limit=limit)

    def add_member(self, actor: Account, conversation_id: str, member: Account) -> None:
        """Add a member to a conversation the actor belongs to."""
        self.repo.get_conversation(conversation_id, actor.account_id)
        if member.tenant_id != actor.tenant_id:
            raise PermissionDenied(
                "membership stays inside the conversation's tenant",
                payload={"actor_tenant": actor.tenant_id, "member_tenant": member.tenant_id},
            )
        self.repo.add_member(conversation_id, member.account_id)

    def remove_member(self, actor: Account, conversation_id: str, member_id: str) -> bool:
        """Remove a member from a conversation the actor belongs to.

        Returns False when the row was already gone. An actor may remove
        themselves; the leave endpoint in P2.2 uses the same path.
        """
        self.repo.get_conversation(conversation_id, actor.account_id)
        return self.repo.remove_member(conversation_id, member_id)

    def mark_read(self, account: Account, conversation_id: str) -> bool:
        """Stamp the caller's read position. Only their own row moves."""
        return self.repo.mark_read(conversation_id, account.account_id)

    @staticmethod
    def _correlation_id() -> str:
        return f"chat-{uuid.uuid4().hex}"
