"""Notification service tests (P2.3).

These tests exercise the NotificationService and its integration with
messaging.send_message directly, without an HTTP layer.  The three
key properties the prompt names are pinned here:
1. A message with @username in a group creates exactly one mention
   notification for the named account (and none for the sender).
2. A direct message creates one dm notification for the other member
   (and none for the sender).
3. unread_count matches the number of unread notification rows.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.modules.messaging.service import MessagingService
from helix_codex_app.modules.notifications.schemas import NotificationOut
from helix_codex_app.modules.notifications.service import NotificationService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    amira = repo.create_account(
        domain.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    omar = repo.create_account(
        domain.domain_id, "omar", role_id="employee", password_hash=hash_password("x")
    )
    layla = repo.create_account(
        domain.domain_id, "layla", role_id="employee", password_hash=hash_password("x")
    )
    messaging = MessagingService(conn)
    notifications = NotificationService(conn)
    yield SimpleNamespace(
        conn=conn,
        domain=domain,
        amira=amira,
        omar=omar,
        layla=layla,
        messaging=messaging,
        notifications=notifications,
    )
    db.close(conn)


# --- properties the prompt names --------------------------------------------


def test_mention_creates_one_notification_for_the_named_account(ctx) -> None:
    """@omar in a group message fires one mention notification."""
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar, ctx.layla])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "hello @omar")
    omar_notes = ctx.notifications.list_for(ctx.omar)
    assert len(omar_notes) == 1
    assert omar_notes[0].kind == "mention"
    assert "hello @omar" in omar_notes[0].body
    assert ctx.notifications.unread_count(ctx.omar) == 1


def test_sender_is_never_notified_of_own_message(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "just chatting")
    assert ctx.notifications.list_for(ctx.amira) == []
    assert ctx.notifications.unread_count(ctx.amira) == 0


def test_dm_creates_notification_for_the_other_member(ctx) -> None:
    """A direct message creates a dm notification for the recipient."""
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "hi there")
    omar_notes = ctx.notifications.list_for(ctx.omar)
    assert len(omar_notes) == 1
    assert omar_notes[0].kind == "dm"
    assert "hi there" in omar_notes[0].body
    assert ctx.notifications.unread_count(ctx.omar) == 1
    # sender is not notified
    assert ctx.notifications.list_for(ctx.amira) == []


def test_unread_count_matches_row_count(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar, ctx.layla])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "ping @omar @layla")
    omar_notes = ctx.notifications.list_for(ctx.omar)
    layla_notes = ctx.notifications.list_for(ctx.layla)
    assert len(omar_notes) == 1
    assert len(layla_notes) == 1
    assert ctx.notifications.unread_count(ctx.omar) == 1
    assert ctx.notifications.unread_count(ctx.layla) == 1
    # mark omar's read
    ctx.notifications.mark_read(ctx.omar, omar_notes[0].notification_id)
    assert ctx.notifications.unread_count(ctx.omar) == 0
    assert ctx.notifications.unread_count(ctx.layla) == 1


# --- idempotent mark_read --------------------------------------------------


def test_mark_read_is_idempotent(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "yo @omar")
    note = ctx.notifications.list_for(ctx.omar)[0]
    assert note.read_at is None
    # first call stamps it
    assert ctx.notifications.mark_read(ctx.omar, note.notification_id) is True
    # second call is a no-op
    assert ctx.notifications.mark_read(ctx.omar, note.notification_id) is False
    # still readable
    fetched = ctx.notifications.repo.get(note.notification_id, ctx.omar.account_id)
    assert fetched is not None
    assert fetched.read_at is not None


# --- cross-account isolation -------------------------------------------------


def test_notifications_are_isolated_between_accounts(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "mention @omar")
    omar_notes = ctx.notifications.list_for(ctx.omar)
    assert len(omar_notes) == 1
    # amira cannot read omar's notification
    assert ctx.notifications.repo.get(omar_notes[0].notification_id, ctx.amira.account_id) is None


# --- schema round-trip -------------------------------------------------------


def test_notification_out_round_trips(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "test @omar")
    note = ctx.notifications.list_for(ctx.omar)[0]
    out = NotificationOut.from_notification(note)
    assert out.notification_id == note.notification_id
    assert out.kind == "mention"
    assert out.read_at is None


# --- governed node envelope --------------------------------------------------


def test_notification_creates_governed_node(ctx) -> None:
    """Each notification row has a matching nodes row with the right envelope."""
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "hi @omar")
    note = ctx.notifications.list_for(ctx.omar)[0]
    node = ctx.conn.execute(
        "SELECT kind, nature, classification, provenance_source, provenance_data_mode"
        " FROM nodes WHERE correlation_id = ? AND kind = 'notification'",
        (note.correlation_id,),
    ).fetchone()
    assert node is not None
    assert node["nature"] == "system_event"
    assert node["classification"] == "internal"
    assert node["provenance_source"] == "helix_codex_app.notifications"
    assert node["provenance_data_mode"] == "app_runtime"


# --- mention with no @ in a group message produces nothing -------------------


def test_group_message_without_mentions_creates_no_notifications(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "no mentions here")
    assert ctx.notifications.list_for(ctx.omar) == []
    assert ctx.notifications.list_for(ctx.amira) == []


# --- mention of self is skipped ----------------------------------------------


def test_mention_of_self_does_not_notify(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "ping @amira")
    assert ctx.notifications.list_for(ctx.amira) == []


# --- mark_all_read -----------------------------------------------------------


def test_mark_all_read(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "msg 1 @omar")
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "msg 2 @omar")
    assert ctx.notifications.unread_count(ctx.omar) == 2
    count = ctx.notifications.mark_all_read(ctx.omar)
    assert count == 2
    assert ctx.notifications.unread_count(ctx.omar) == 0
    # second call is a no-op
    assert ctx.notifications.mark_all_read(ctx.omar) == 0


# --- empty body mention produces no notifications ----------------------------


def test_empty_body_mention_produces_nothing(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    # Mention pattern alone (e.g. @) in a longer body, but no match
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "just @")
    assert ctx.notifications.list_for(ctx.omar) == []
