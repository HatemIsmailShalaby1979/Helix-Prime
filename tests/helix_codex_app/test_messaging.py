"""Messaging repository and service tests (P2.1).

The four properties the prompt names are pinned here: a non-member cannot
read or post, create_direct is idempotent for a pair, sending a message
creates exactly one nodes row, and list_messages pages correctly. The
fixtures build two tenants so the tenant rules are exercised with real
data, not stubs.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.errors import NotFoundError, PermissionDenied
from helix_codex_app.modules.messaging.repository import MessagingRepository
from helix_codex_app.modules.messaging.schemas import MessageOut
from helix_codex_app.modules.messaging.service import MessagingService
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
    service = MessagingService(conn)
    messaging_repo = MessagingRepository(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        amira=amira,
        omar=omar,
        layla=layla,
        ghada=ghada,
        service=service,
        messaging_repo=messaging_repo,
    )
    db.close(conn)


def _node_rows(ctx, conversation_id: str):
    return ctx.conn.execute(
        "SELECT node_id, kind, correlation_id, tenant_id FROM nodes WHERE thread_id = ?",
        (conversation_id,),
    ).fetchall()


def test_non_member_cannot_read_or_post(ctx) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    with pytest.raises(NotFoundError):
        ctx.service.get_conversation(ctx.layla, conversation.conversation_id)
    with pytest.raises(NotFoundError):
        ctx.service.list_messages(ctx.layla, conversation.conversation_id)
    with pytest.raises(NotFoundError):
        ctx.service.send_message(ctx.layla, conversation.conversation_id, "let me in")
    with pytest.raises(NotFoundError):
        ctx.service.add_member(ctx.layla, conversation.conversation_id, ctx.layla)
    with pytest.raises(NotFoundError):
        ctx.service.remove_member(ctx.layla, conversation.conversation_id, ctx.amira.account_id)
    listed = ctx.service.list_conversations(ctx.layla)
    assert listed == []


def test_create_direct_twice_returns_the_same_conversation(ctx) -> None:
    first = ctx.service.create_direct(ctx.amira, ctx.omar)
    second = ctx.service.create_direct(ctx.amira, ctx.omar)
    reversed_pair = ctx.service.create_direct(ctx.omar, ctx.amira)
    assert first.conversation_id == second.conversation_id
    assert first.conversation_id == reversed_pair.conversation_id
    members = ctx.messaging_repo.member_ids(first.conversation_id)
    assert set(members) == {ctx.amira.account_id, ctx.omar.account_id}
    kind = ctx.conn.execute(
        "SELECT kind FROM conversations WHERE conversation_id = ?",
        (first.conversation_id,),
    ).fetchone()["kind"]
    assert kind == "direct"
    total = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM conversations WHERE kind = 'direct'"
    ).fetchone()["n"]
    assert total == 1


def test_direct_conversation_is_one_pair_not_one_channel(ctx) -> None:
    first_pair = ctx.service.create_direct(ctx.amira, ctx.omar)
    other_pair = ctx.service.create_direct(ctx.amira, ctx.layla)
    assert first_pair.conversation_id != other_pair.conversation_id
    counts = ctx.conn.execute(
        "SELECT conversation_id, COUNT(*) AS n FROM conversation_members"
        " GROUP BY conversation_id"
    ).fetchall()
    by_id = {row["conversation_id"]: row["n"] for row in counts}
    assert by_id[first_pair.conversation_id] == 2
    assert by_id[other_pair.conversation_id] == 2


def test_send_message_creates_exactly_one_nodes_row(ctx) -> None:
    """One message row, one message node, plus one notification node for the
    direct-recipient trigger (P2.3).  The message node is always first."""
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    before = ctx.conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]
    message = ctx.service.send_message(ctx.amira, conversation.conversation_id, "first shift note")
    after = ctx.conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]
    assert after == before + 2
    row = ctx.conn.execute(
        "SELECT node_id, kind, classification, nature, tenant_id, correlation_id,"
        " created_by, thread_id, provenance_source, provenance_data_mode"
        " FROM nodes WHERE kind = 'message'"
    ).fetchone()
    assert row["node_id"] == message.node_id
    assert row["kind"] == "message"
    assert row["classification"] == "internal"
    assert row["nature"] == "user_claim"
    assert row["tenant_id"] == "tenant-a"
    assert row["correlation_id"] == conversation.correlation_id
    assert row["created_by"] == ctx.amira.account_id
    assert row["thread_id"] == conversation.conversation_id
    assert row["provenance_source"] == "helix_codex_app.messaging"
    assert row["provenance_data_mode"] == "app_runtime"
    stored = ctx.conn.execute(
        "SELECT node_id FROM messages WHERE message_id = ?", (message.message_id,)
    ).fetchone()
    assert stored["node_id"] == message.node_id


def test_nodes_row_carries_the_conversation_correlation_id(ctx) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    group = ctx.service.create_group(ctx.amira, "Floor crew", [ctx.omar])
    ctx.service.send_message(ctx.amira, conversation.conversation_id, "in the pair")
    ctx.service.send_message(ctx.amira, group.conversation_id, "in the group")
    correlations = {
        row["thread_id"]: row["correlation_id"]
        for row in ctx.conn.execute(
            "SELECT thread_id, correlation_id FROM nodes WHERE kind = 'message'"
        ).fetchall()
    }
    assert correlations[conversation.conversation_id] == conversation.correlation_id
    assert correlations[group.conversation_id] == group.correlation_id
    assert conversation.correlation_id != group.correlation_id


def test_list_messages_paginates_correctly(ctx) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    sent = [
        ctx.service.send_message(ctx.amira, conversation.conversation_id, f"note {index}")
        for index in range(5)
    ]
    page_one = ctx.service.list_messages(ctx.amira, conversation.conversation_id, limit=3)
    assert [m.message_id for m in page_one] == [
        sent[4].message_id,
        sent[3].message_id,
        sent[2].message_id,
    ]
    oldest_held = page_one[-1].created_at
    page_two = ctx.service.list_messages(
        ctx.amira, conversation.conversation_id, before=oldest_held, limit=3
    )
    assert [m.message_id for m in page_two] == [sent[1].message_id, sent[0].message_id]
    beyond = ctx.service.list_messages(
        ctx.amira, conversation.conversation_id, before=page_two[-1].created_at, limit=3
    )
    assert beyond == []


def test_list_messages_is_newest_first_and_member_scoped(ctx) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    ctx.service.send_message(ctx.amira, conversation.conversation_id, "one")
    ctx.service.send_message(ctx.omar, conversation.conversation_id, "two")
    messages = ctx.service.list_messages(ctx.omar, conversation.conversation_id)
    assert [m.body for m in messages] == ["two", "one"]
    with pytest.raises(NotFoundError):
        ctx.service.list_messages(ctx.layla, conversation.conversation_id)


def test_list_messages_orders_a_timestamp_tie_newest_first(ctx) -> None:
    """A wall clock cannot order two messages sent back to back.

    The clock ticks every 15.6 ms on Windows, so consecutive timestamps are
    equal and a created_at-only sort hands the pair back oldest-first. The tie
    is forced here so the regression is catchable on every platform, not only
    on the one whose clock happens to be coarse.
    """
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    ctx.service.send_message(ctx.amira, conversation.conversation_id, "one")
    ctx.service.send_message(ctx.omar, conversation.conversation_id, "two")
    ctx.conn.execute(
        "UPDATE messages SET created_at = ? WHERE conversation_id = ?",
        ("2026-01-01T00:00:00Z", conversation.conversation_id),
    )
    ctx.conn.commit()

    messages = ctx.service.list_messages(ctx.omar, conversation.conversation_id)
    assert [m.body for m in messages] == ["two", "one"]


def test_group_conversation_shape(ctx) -> None:
    group = ctx.service.create_group(ctx.amira, "Floor crew", [ctx.omar, ctx.layla])
    assert group.kind == "group"
    assert group.title == "Floor crew"
    members = set(ctx.messaging_repo.member_ids(group.conversation_id))
    assert members == {
        ctx.amira.account_id,
        ctx.omar.account_id,
        ctx.layla.account_id,
    }
    reseeded = ctx.service.create_group(ctx.amira, "Again", [ctx.omar, ctx.omar, ctx.amira])
    assert set(ctx.messaging_repo.member_ids(reseeded.conversation_id)) == {
        ctx.amira.account_id,
        ctx.omar.account_id,
    }


def test_cross_tenant_membership_is_denied(ctx) -> None:
    with pytest.raises(PermissionDenied):
        ctx.service.create_direct(ctx.amira, ctx.ghada)
    with pytest.raises(PermissionDenied):
        ctx.service.create_group(ctx.amira, "Mixed", [ctx.ghada])
    group = ctx.service.create_group(ctx.amira, "Own tenant", [ctx.omar])
    with pytest.raises(PermissionDenied):
        ctx.service.add_member(ctx.amira, group.conversation_id, ctx.ghada)


def test_cross_tenant_conversation_is_invisible_even_with_an_id(ctx) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    fetched = ctx.conn.execute(
        "SELECT tenant_id FROM conversations WHERE conversation_id = ?",
        (conversation.conversation_id,),
    ).fetchone()
    assert fetched["tenant_id"] == "tenant-a"
    with pytest.raises(NotFoundError):
        ctx.service.get_conversation(ctx.ghada, conversation.conversation_id)


def test_same_tenant_different_domain_stays_possible(ctx) -> None:
    second_domain = ctx.repo.create_domain("c.academy", tenant_id="tenant-a")
    colleague = ctx.repo.create_account(
        second_domain.domain_id, "nadia", role_id="employee", password_hash=hash_password("x")
    )
    conversation = ctx.service.create_direct(ctx.amira, colleague)
    assert conversation.tenant_id == "tenant-a"
    message = ctx.service.send_message(ctx.amira, conversation.conversation_id, "cross-domain ok")
    assert message.node_id is not None


def test_remove_member_and_mark_read(ctx) -> None:
    group = ctx.service.create_group(ctx.amira, "Floor crew", [ctx.omar, ctx.layla])
    ctx.service.send_message(ctx.amira, group.conversation_id, "hello team")
    assert ctx.service.mark_read(ctx.omar, group.conversation_id) is True
    row = ctx.conn.execute(
        "SELECT last_read_at FROM conversation_members"
        " WHERE conversation_id = ? AND account_id = ?",
        (group.conversation_id, ctx.omar.account_id),
    ).fetchone()
    assert row["last_read_at"] is not None
    assert ctx.service.remove_member(ctx.amira, group.conversation_id, ctx.layla.account_id)
    with pytest.raises(NotFoundError):
        ctx.service.get_conversation(ctx.layla, group.conversation_id)
    assert ctx.service.mark_read(ctx.layla, group.conversation_id) is False


def test_empty_and_oversized_messages_are_rejected(ctx) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    with pytest.raises(ValueError):
        ctx.service.send_message(ctx.amira, conversation.conversation_id, "   ")
    with pytest.raises(ValueError):
        ctx.service.send_message(ctx.amira, conversation.conversation_id, "x" * 8001)


def test_group_without_a_name_is_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.create_group(ctx.amira, "   ", [ctx.omar])


def test_direct_with_self_is_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.create_direct(ctx.amira, ctx.amira)


def test_no_edit_or_delete_write_paths_exist(ctx) -> None:
    columns = {row["name"] for row in ctx.conn.execute("PRAGMA table_info(messages)")}
    assert {"edited_at", "deleted_at"} <= columns
    service_names = {name for name in dir(MessagingService) if not name.startswith("_")}
    assert "edit_message" not in service_names
    assert "delete_message" not in service_names


def test_schemas_round_trip_a_message(ctx) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    message = ctx.service.send_message(ctx.amira, conversation.conversation_id, "wire shape")
    out = MessageOut.from_message(message)
    assert out.message_id == message.message_id
    assert out.body == "wire shape"
    assert out.node_id == message.node_id


def test_list_conversations_orders_by_latest_activity(ctx) -> None:
    quiet = ctx.service.create_direct(ctx.amira, ctx.omar)
    busy = ctx.service.create_direct(ctx.amira, ctx.layla)
    ctx.service.send_message(ctx.amira, busy.conversation_id, "activity here")
    listed = ctx.service.list_conversations(ctx.amira)
    assert [c.conversation_id for c in listed] == [busy.conversation_id, quiet.conversation_id]
    assert listed[0].message_count == 1
    assert listed[0].last_message_preview == "activity here"
    assert listed[1].message_count == 0
