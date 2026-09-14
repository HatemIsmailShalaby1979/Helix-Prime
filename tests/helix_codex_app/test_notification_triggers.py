"""Once-only notification triggers (P2.4 close-out).

Each wired trigger fires once and only once per relevant recipient.
The proof: every assertion checks the notification count, not just
the shape.  The tests go through MessagingService.send_message —
the only wired trigger path — so they pin the integration boundary
without duplicating the service tests in test_notifications.py.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.modules.messaging.service import MessagingService
from helix_codex_app.modules.notifications.service import NotificationService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    amira = repo.create_account(
        domain_a.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    omar = repo.create_account(
        domain_a.domain_id, "omar", role_id="employee", password_hash=hash_password("x")
    )
    layla = repo.create_account(
        domain_a.domain_id, "layla", role_id="employee", password_hash=hash_password("x")
    )
    ghada = repo.create_account(
        domain_b.domain_id, "ghada", role_id="employee", password_hash=hash_password("x")
    )
    messaging = MessagingService(conn)
    notifications = NotificationService(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        amira=amira,
        omar=omar,
        layla=layla,
        ghada=ghada,
        messaging=messaging,
        notifications=notifications,
    )
    db.close(conn)


# --- direct message triggers -------------------------------------------------


def test_one_direct_message_fires_one_dm(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "hi")
    assert ctx.notifications.unread_count(ctx.omar) == 1
    assert ctx.notifications.list_for(ctx.omar)[0].kind == "dm"


def test_each_direct_message_fires_its_own_dm(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "first")
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "second")
    assert ctx.notifications.unread_count(ctx.omar) == 2
    notes = ctx.notifications.list_for(ctx.omar)
    assert all(n.kind == "dm" for n in notes)


# --- mention triggers --------------------------------------------------------


def test_one_mention_fires_exactly_one_notification(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "@omar @omar and again @omar")
    assert ctx.notifications.unread_count(ctx.omar) == 1
    assert ctx.notifications.list_for(ctx.omar)[0].kind == "mention"


def test_a_mention_notifies_each_named_account_once(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar, ctx.layla])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "@omar @layla")
    assert ctx.notifications.unread_count(ctx.omar) == 1
    assert ctx.notifications.unread_count(ctx.layla) == 1


def test_a_mention_of_an_unknown_username_fires_nothing(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "hello @nobody")
    assert ctx.notifications.unread_count(ctx.omar) == 0
    assert ctx.notifications.list_for(ctx.omar) == []


def test_a_group_message_without_a_mention_fires_nothing(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "just chatting")
    assert ctx.notifications.list_for(ctx.omar) == []


def test_a_mention_of_a_foreign_domain_account_fires_nothing(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "hi @ghada")
    assert ctx.notifications.unread_count(ctx.omar) == 0
    assert ctx.notifications.list_for(ctx.ghada) == []


def test_a_direct_message_never_fires_a_mention_for_an_at_username(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "hey @omar")
    notes = ctx.notifications.list_for(ctx.omar)
    assert len(notes) == 1
    assert notes[0].kind == "dm"


def test_sender_is_never_notified(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "hello @amira")
    assert ctx.notifications.list_for(ctx.amira) == []
    assert ctx.notifications.unread_count(ctx.amira) == 0
