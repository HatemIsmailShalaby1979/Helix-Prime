"""Pydantic request and response models for the messaging API.

The schemas mirror the dataclasses in repository.py. The UI lands in P2.2;
these models are the contract the JSON endpoints will serve, written now so
the wire shape is pinned before a client exists to drift against.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from helix_codex_app.modules.messaging.repository import Conversation, Message


class MessageOut(BaseModel):
    """One message on the wire."""

    message_id: str
    conversation_id: str
    sender_account_id: str
    body: str
    classification: str
    created_at: str
    node_id: str | None = None

    @classmethod
    def from_message(cls, message: Message) -> "MessageOut":
        return cls(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            sender_account_id=message.sender_account_id,
            body=message.body,
            classification=message.classification,
            created_at=message.created_at,
            node_id=message.node_id,
        )


class ConversationOut(BaseModel):
    """One conversation on the wire, with the caller's membership view."""

    conversation_id: str
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

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> "ConversationOut":
        return cls(
            conversation_id=conversation.conversation_id,
            kind=conversation.kind,
            title=conversation.title,
            classification=conversation.classification,
            created_by=conversation.created_by,
            created_at=conversation.created_at,
            correlation_id=conversation.correlation_id,
            member_role=conversation.member_role,
            last_read_at=conversation.last_read_at,
            message_count=conversation.message_count,
            last_message_at=conversation.last_message_at,
            last_message_preview=conversation.last_message_preview,
        )


class MessagePage(BaseModel):
    """A newest-first page of messages plus the cursor for the next one.

    ``next_before`` is an **opaque** cursor: hand it back as the ``before`` query
    parameter unchanged. It is not a timestamp to interpret, and its format may
    grow — it currently carries the row identity as well as the timestamp so that
    a page boundary falling between two messages that share a timestamp does not
    lose one. A bare timestamp is still accepted for older clients.
    """

    messages: list[MessageOut]
    next_before: str | None = None


class SendMessageRequest(BaseModel):
    """The body of a send-message request."""

    body: str = Field(min_length=1, max_length=8000)


class CreateGroupRequest(BaseModel):
    """The body of a create-group request."""

    name: str = Field(min_length=1, max_length=200)
    member_ids: list[str] = Field(default_factory=list, max_length=64)


class CreateDirectRequest(BaseModel):
    """The body of a create-direct request."""

    account_id: str = Field(min_length=1)


class MarkReadRequest(BaseModel):
    """Empty marker for the read-receipt endpoint."""


class AddMemberRequest(BaseModel):
    """The body of an add-member request."""

    account_id: str = Field(min_length=1)
