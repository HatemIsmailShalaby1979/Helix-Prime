"""The storage layer for conversations, memberships, and messages.

Every read here resolves the account's membership first. A conversation
that the caller does not belong to is not filtered out of a list; it is
absent from every query, because the membership join is part of the SQL.
Tenant scope comes from the account record, never from a request parameter.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from helix_codex_app.errors import NotFoundError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Conversation:
    """One conversation, as the member sees it."""

    conversation_id: str
    tenant_id: str
    domain_id: str | None
    kind: str
    title: str | None
    classification: str
    created_by: str
    created_at: str
    correlation_id: str
    member_role: str | None = None
    last_read_at: str | None = None
    message_count: int = 0
    last_message_at: str | None = None
    last_message_preview: str | None = None


@dataclass(frozen=True)
class Message:
    """One stored message."""

    message_id: str
    conversation_id: str
    sender_account_id: str
    body: str
    classification: str
    created_at: str
    node_id: str | None = None


class MessagingRepository:
    """The read and write surface for the messaging tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_conversation(
        self,
        *,
        tenant_id: str,
        domain_id: str | None,
        kind: str,
        title: str | None,
        classification: str,
        created_by: str,
        correlation_id: str,
    ) -> Conversation:
        """Insert one conversation row and return it. The caller seeds the
        membership rows separately, so a conversation never exists without
        members."""
        conversation_id = _new_id("conv")
        created_at = _now()
        self.conn.execute(
            """
            INSERT INTO conversations (
                conversation_id, tenant_id, domain_id, kind, title,
                classification, created_by, created_at, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                tenant_id,
                domain_id,
                kind,
                title,
                classification,
                created_by,
                created_at,
                correlation_id,
            ),
        )
        self.conn.commit()
        return Conversation(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            kind=kind,
            title=title,
            classification=classification,
            created_by=created_by,
            created_at=created_at,
            correlation_id=correlation_id,
        )

    def add_member(
        self,
        conversation_id: str,
        account_id: str,
        *,
        member_role: str = "member",
    ) -> None:
        """Add one member. Inserting a duplicate is a no-op, so seeding a
        group from a list that repeats an account cannot fail the call."""
        self.conn.execute(
            """
            INSERT OR IGNORE INTO conversation_members (
                conversation_id, account_id, member_role, joined_at, last_read_at
            ) VALUES (?, ?, ?, ?, NULL)
            """,
            (conversation_id, account_id, member_role, _now()),
        )
        self.conn.commit()

    def remove_member(self, conversation_id: str, account_id: str) -> bool:
        """Remove one member. Returns False when the row was already gone,
        which is also what happens when the account was never a member."""
        cursor = self.conn.execute(
            "DELETE FROM conversation_members WHERE conversation_id = ? AND account_id = ?",
            (conversation_id, account_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_membership(self, conversation_id: str, account_id: str) -> sqlite3.Row | None:
        """The membership row for one account, or None."""
        return self.conn.execute(
            """
            SELECT conversation_id, account_id, member_role, joined_at, last_read_at
            FROM conversation_members
            WHERE conversation_id = ? AND account_id = ?
            """,
            (conversation_id, account_id),
        ).fetchone()

    def get_conversation(self, conversation_id: str, account_id: str) -> Conversation:
        """Load one conversation the account belongs to.

        Raises NotFoundError when the conversation does not exist, when the
        account is not a member, or when the conversation belongs to another
        tenant — one message shape for three cases, so the caller cannot
        learn which part was wrong.
        """
        row = self.conn.execute(
            """
            SELECT c.conversation_id, c.tenant_id, c.domain_id, c.kind, c.title,
                   c.classification, c.created_by, c.created_at, c.correlation_id,
                   m.member_role, m.last_read_at
            FROM conversations c
            JOIN conversation_members m
              ON m.conversation_id = c.conversation_id AND m.account_id = ?
            WHERE c.conversation_id = ?
            """,
            (account_id, conversation_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no conversation {conversation_id!r} for this account")
        return _conversation_from_row(row)

    def list_conversations(self, account_id: str) -> list[Conversation]:
        """Every conversation the account belongs to, newest activity first.

        Activity is the newest message timestamp, falling back to the
        conversation's own creation for a conversation with no messages yet.
        """
        rows = self.conn.execute(
            """
            SELECT c.conversation_id, c.tenant_id, c.domain_id, c.kind, c.title,
                   c.classification, c.created_by, c.created_at, c.correlation_id,
                   m.member_role, m.last_read_at,
                   (SELECT COUNT(*) FROM messages msg
                     WHERE msg.conversation_id = c.conversation_id) AS message_count,
                   (SELECT MAX(created_at) FROM messages msg
                     WHERE msg.conversation_id = c.conversation_id) AS last_message_at,
                   (SELECT body FROM messages msg
                     WHERE msg.conversation_id = c.conversation_id
                     ORDER BY msg.created_at DESC LIMIT 1) AS last_message_preview
            FROM conversations c
            JOIN conversation_members m
              ON m.conversation_id = c.conversation_id AND m.account_id = ?
            ORDER BY last_message_at DESC, c.created_at DESC
            """,
            (account_id,),
        ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def find_direct_conversation(self, account_a: str, account_b: str) -> str | None:
        """The id of the existing direct conversation between two accounts.

        A direct conversation is kind='direct' with exactly two members. The
        pair is unordered: (a, b) and (b, a) find the same row.
        """
        row = self.conn.execute(
            """
            SELECT c.conversation_id
            FROM conversations c
            JOIN conversation_members m1
              ON m1.conversation_id = c.conversation_id AND m1.account_id = ?
            JOIN conversation_members m2
              ON m2.conversation_id = c.conversation_id AND m2.account_id = ?
            WHERE c.kind = 'direct'
              AND (SELECT COUNT(*) FROM conversation_members m
                    WHERE m.conversation_id = c.conversation_id) = 2
            LIMIT 1
            """,
            (account_a, account_b),
        ).fetchone()
        return row["conversation_id"] if row else None

    def append_message(
        self,
        *,
        conversation_id: str,
        sender_account_id: str,
        body: str,
        classification: str,
        node_id: str | None = None,
    ) -> Message:
        """Insert one message row and return it."""
        message_id = _new_id("msg")
        created_at = _now()
        self.conn.execute(
            """
            INSERT INTO messages (
                message_id, conversation_id, sender_account_id, body,
                classification, created_at, node_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                sender_account_id,
                body,
                classification,
                created_at,
                node_id,
            ),
        )
        self.conn.commit()
        return Message(
            message_id=message_id,
            conversation_id=conversation_id,
            sender_account_id=sender_account_id,
            body=body,
            classification=classification,
            created_at=created_at,
            node_id=node_id,
        )

    def list_messages(
        self,
        conversation_id: str,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> list[Message]:
        """Messages newest-first, optionally starting below a given
        created_at timestamp. The caller pages by passing the oldest
        timestamp of the page it already holds."""
        sql = """
            SELECT message_id, conversation_id, sender_account_id, body,
                   classification, created_at, node_id
            FROM messages
            WHERE conversation_id = ?
        """
        params: list[Any] = [conversation_id]
        if before is not None:
            sql += " AND created_at < ?"
            params.append(before)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(_bounded_limit(limit))
        rows = self.conn.execute(sql, params).fetchall()
        return [_message_from_row(row) for row in rows]

    def mark_read(self, conversation_id: str, account_id: str) -> bool:
        """Stamp last_read_at with now. Returns False when the account is
        not a member, so a read receipt never creates membership."""
        cursor = self.conn.execute(
            """
            UPDATE conversation_members
            SET last_read_at = ?
            WHERE conversation_id = ? AND account_id = ?
            """,
            (_now(), conversation_id, account_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def member_ids(self, conversation_id: str) -> list[str]:
        """The member accounts of a conversation, in join order."""
        rows = self.conn.execute(
            "SELECT account_id FROM conversation_members"
            " WHERE conversation_id = ? ORDER BY joined_at",
            (conversation_id,),
        ).fetchall()
        return [row["account_id"] for row in rows]


def _bounded_limit(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > 200:
        return 200
    return limit


def _conversation_from_row(row: sqlite3.Row) -> Conversation:
    return Conversation(
        conversation_id=row["conversation_id"],
        tenant_id=row["tenant_id"],
        domain_id=row["domain_id"],
        kind=row["kind"],
        title=row["title"],
        classification=row["classification"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        correlation_id=row["correlation_id"],
        member_role=row["member_role"] if "member_role" in row.keys() else None,
        last_read_at=row["last_read_at"] if "last_read_at" in row.keys() else None,
        message_count=row["message_count"] if "message_count" in row.keys() else 0,
        last_message_at=row["last_message_at"] if "last_message_at" in row.keys() else None,
        last_message_preview=(
            row["last_message_preview"] if "last_message_preview" in row.keys() else None
        ),
    )


def _message_from_row(row: sqlite3.Row) -> Message:
    return Message(
        message_id=row["message_id"],
        conversation_id=row["conversation_id"],
        sender_account_id=row["sender_account_id"],
        body=row["body"],
        classification=row["classification"],
        created_at=row["created_at"],
        node_id=row["node_id"],
    )
