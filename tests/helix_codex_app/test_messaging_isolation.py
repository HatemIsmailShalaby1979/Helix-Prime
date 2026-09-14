"""Tenant isolation for messaging and notifications (P2.4 close-out).

An account in tenant A must never read, list, or write a conversation,
message, or notification that belongs to tenant B.  The proof is at two
levels: the service raises NotFoundError on every membership-gated read,
and the HTTP surface returns an empty list or a 404.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import NotFoundError
from helix_codex_app.modules.messaging.service import MessagingService
from helix_codex_app.modules.notifications.service import NotificationService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

TestClient = fastapi_testclient.TestClient


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
    bob = repo.create_account(
        domain_b.domain_id, "bob", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
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
        bob=bob,
        settings=settings,
        store=store,
        messaging=messaging,
        notifications=notifications,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _login(ctx, account) -> tuple[dict, dict]:
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


# --- service level: conversations and messages --------------------------------


def test_foreign_conversations_never_appear_in_a_list(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar, ctx.layla])
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "private")
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "team note")
    assert ctx.messaging.list_conversations(ctx.ghada) == []
    assert ctx.messaging.list_conversations(ctx.bob) == []


def test_foreign_conversation_read_raises_not_found(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "private")
    with pytest.raises(NotFoundError):
        ctx.messaging.get_conversation(ctx.ghada, direct.conversation_id)


def test_foreign_message_read_raises_not_found(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "private")
    with pytest.raises(NotFoundError):
        ctx.messaging.list_messages(ctx.ghada, direct.conversation_id)


def test_foreign_account_cannot_write_into_a_foreign_conversation(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    with pytest.raises(NotFoundError):
        ctx.messaging.send_message(ctx.ghada, direct.conversation_id, "intruder")


def test_foreign_read_receipt_is_a_no_op(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    assert ctx.messaging.mark_read(ctx.ghada, direct.conversation_id) is False
    row = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM conversation_members WHERE account_id = ?",
        (ctx.ghada.account_id,),
    ).fetchone()
    assert row["n"] == 0


# --- service level: notifications ----------------------------------------------


def test_foreign_tenant_notifications_are_invisible(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "a direct secret")
    omars = ctx.notifications.list_for(ctx.omar)
    assert len(omars) == 1
    assert ctx.notifications.list_for(ctx.ghada) == []
    assert ctx.notifications.unread_count(ctx.ghada) == 0
    assert ctx.notifications.repo.get(omars[0].notification_id, ctx.ghada.account_id) is None


def test_foreign_account_cannot_mark_foreign_notifications_read(ctx) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "shh")
    note = ctx.notifications.list_for(ctx.omar)[0]
    assert ctx.notifications.mark_read(ctx.ghada, note.notification_id) is False
    fetched = ctx.notifications.repo.get(note.notification_id, ctx.omar.account_id)
    assert fetched is not None
    assert fetched.read_at is None


# --- HTTP level -----------------------------------------------------------------


def test_foreign_tenant_conversation_list_is_empty_on_the_wire(ctx, client) -> None:
    ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar, ctx.layla])
    cookies, _ = _login(ctx, ctx.ghada)
    response = client.get("/app/api/conversations", cookies=cookies)
    assert response.status_code == 200
    assert response.json() == []


def test_foreign_tenant_thread_screen_is_404(ctx, client) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "private")
    cookies, _ = _login(ctx, ctx.ghada)
    response = client.get(f"/app/chat/{direct.conversation_id}", cookies=cookies)
    assert response.status_code == 404


def test_foreign_tenant_messages_api_is_404(ctx, client) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "private")
    cookies, _ = _login(ctx, ctx.ghada)
    response = client.get(
        f"/app/api/conversations/{direct.conversation_id}/messages", cookies=cookies
    )
    assert response.status_code == 404


def test_foreign_tenant_send_message_api_is_404(ctx, client) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    cookies, headers = _login(ctx, ctx.ghada)
    response = client.post(
        f"/app/api/conversations/{direct.conversation_id}/messages",
        json={"body": "let me in"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 404


def test_foreign_tenant_notifications_are_empty_on_the_wire(ctx, client) -> None:
    direct = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    ctx.messaging.send_message(ctx.amira, direct.conversation_id, "shh")
    cookies, _ = _login(ctx, ctx.ghada)
    response = client.get("/app/api/notifications", cookies=cookies)
    assert response.status_code == 200
    assert response.json() == []
    screen = client.get("/app/notifications", cookies=cookies)
    assert screen.status_code == 200
    assert "No notifications yet" in screen.text
