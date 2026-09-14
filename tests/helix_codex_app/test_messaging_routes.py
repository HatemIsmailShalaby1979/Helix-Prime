"""Chat screen, messaging API, and SSE stream tests (P2.2).

HTTP tests drive the mounted messaging router through TestClient, covering
the screens, the JSON contract, the HTMX fragment path, and CSRF. The SSE
tests follow the parent stream suite: a test client cannot stream an
infinite response to completion, so conversation_event_stream is driven
directly and the stream route is pinned with the fast, deterministic cases
(open headers, non-member 403).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.integration.sse_bridge import publish, subscriber_count
from helix_codex_app.modules.messaging.router import conversation_event_stream
from helix_codex_app.modules.messaging.service import MessagingService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

_MESSAGE_PAYLOAD = {
    "message_id": "msg-x",
    "conversation_id": "conv-x",
    "sender_account_id": "account-x",
    "body": "hello from the stream",
    "classification": "internal",
    "created_at": "2026-09-01T10:00:00+00:00",
    "node_id": "node-x",
}


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
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    service = MessagingService(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        amira=amira,
        omar=omar,
        layla=layla,
        ghada=ghada,
        settings=settings,
        store=store,
        service=service,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _login(ctx, account) -> tuple[dict, dict]:
    """Return (cookies, headers) for one account: cookie + CSRF header."""
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _stream_url(conversation_id: str) -> str:
    return f"/app/api/conversations/{conversation_id}/stream"


class _FakeRequest:
    def __init__(self, disconnected: bool = False) -> None:
        self.disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self.disconnected


# --- screens ----------------------------------------------------------------


def test_chat_list_screen_renders_peers_and_no_conversations(ctx, client) -> None:
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/chat", cookies=cookies)
    assert response.status_code == 200
    assert "New chat" in response.text
    assert ctx.omar.account_id in response.text
    assert "No conversations yet" in response.text


def test_thread_screen_renders_messages_oldest_first(ctx, client) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    ctx.service.send_message(ctx.amira, conversation.conversation_id, "first")
    ctx.service.send_message(ctx.omar, conversation.conversation_id, "second")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(f"/app/chat/{conversation.conversation_id}", cookies=cookies)
    assert response.status_code == 200
    assert response.text.index("first") < response.text.index("second")
    assert f'data-conversation-id="{conversation.conversation_id}"' in response.text
    assert 'data-self="' + ctx.amira.account_id + '"' in response.text


def test_thread_screen_is_404_for_a_non_member(ctx, client) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    cookies, _ = _login(ctx, ctx.layla)
    response = client.get(f"/app/chat/{conversation.conversation_id}", cookies=cookies)
    assert response.status_code == 404


def test_chat_list_requires_authentication(client) -> None:
    response = client.get("/app/chat")
    assert response.status_code == 401


# --- conversations -----------------------------------------------------------


def test_create_direct_route_is_idempotent(ctx, client) -> None:
    cookies, headers = _login(ctx, ctx.amira)
    url = "/app/api/conversations"
    first = client.post(
        url, json={"account_id": ctx.omar.account_id}, cookies=cookies, headers=headers
    )
    second = client.post(
        url, json={"account_id": ctx.omar.account_id}, cookies=cookies, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["conversation_id"] == second.json()["conversation_id"]
    assert first.json()["kind"] == "direct"


def test_create_direct_route_rejects_an_unknown_account(ctx, client) -> None:
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/conversations",
        json={"account_id": "account-nobody"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 404


def test_create_direct_hx_fragment_returns_the_list(ctx, client) -> None:
    cookies, headers = _login(ctx, ctx.amira)
    headers["HX-Request"] = "true"
    response = client.post(
        "/app/api/conversations",
        data={"account_id": ctx.omar.account_id},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200
    assert 'id="chat-section"' in response.text
    assert response.text.index(ctx.omar.username) < response.text.index("Conversations")


def test_create_group_route(ctx, client) -> None:
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/conversations",
        json={"name": "Ops", "member_ids": [ctx.omar.account_id, ctx.layla.account_id]},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "group"
    assert body["title"] == "Ops"
    group_id = body["conversation_id"]
    for account in (ctx.amira, ctx.omar, ctx.layla):
        assert ctx.service.get_conversation(account, group_id)


def test_create_conversation_requires_csrf(ctx, client) -> None:
    cookies, _ = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/conversations", json={"account_id": ctx.omar.account_id}, cookies=cookies
    )
    assert response.status_code == 403


# --- messages ----------------------------------------------------------------


def test_send_message_route_json_writes_and_audits(ctx, client) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    cookies, headers = _login(ctx, ctx.amira)
    before = ctx.conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]
    response = client.post(
        f"/app/api/conversations/{conversation.conversation_id}/messages",
        json={"body": "a ruled message"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["conversation_id"] == conversation.conversation_id
    assert body["sender_account_id"] == ctx.amira.account_id
    after = ctx.conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]
    assert after == before + 1
    stored = ctx.conn.execute(
        "SELECT node_id FROM messages WHERE message_id = ?", (body["message_id"],)
    ).fetchone()
    assert stored["node_id"] == body["node_id"]


def test_send_message_hx_fragment_returns_one_bubble(ctx, client) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    cookies, headers = _login(ctx, ctx.amira)
    headers["HX-Request"] = "true"
    response = client.post(
        f"/app/api/conversations/{conversation.conversation_id}/messages",
        data={"body": "via the composer"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200
    assert "chat-bubble--me" in response.text
    assert "via the composer" in response.text
    assert 'data-message-id="' in response.text


def test_send_message_route_is_404_for_a_non_member(ctx, client) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    cookies, headers = _login(ctx, ctx.layla)
    response = client.post(
        f"/app/api/conversations/{conversation.conversation_id}/messages",
        json={"body": "let me in"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 404


def test_list_messages_route_pages_with_a_cursor(ctx, client) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    sent = [
        ctx.service.send_message(ctx.amira, conversation.conversation_id, f"note {index}")
        for index in range(4)
    ]
    cookies, _ = _login(ctx, ctx.amira)
    first = client.get(
        f"/app/api/conversations/{conversation.conversation_id}/messages?limit=2", cookies=cookies
    )
    assert first.status_code == 200
    page = first.json()
    assert [m["message_id"] for m in page["messages"]] == [sent[3].message_id, sent[2].message_id]
    cursor = page["next_before"]
    second = client.get(
        f"/app/api/conversations/{conversation.conversation_id}/messages?limit=2&before={cursor}",
        cookies=cookies,
    )
    assert [m["message_id"] for m in second.json()["messages"]] == [
        sent[1].message_id,
        sent[0].message_id,
    ]


def test_mark_read_route_stamps_only_the_caller(ctx, client) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/conversations/{conversation.conversation_id}/read",
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    row = ctx.conn.execute(
        "SELECT last_read_at FROM conversation_members"
        " WHERE conversation_id = ? AND account_id = ?",
        (conversation.conversation_id, ctx.amira.account_id),
    ).fetchone()
    assert row["last_read_at"] is not None


def test_list_messages_route_is_404_for_a_non_member(ctx, client) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    ctx.service.send_message(ctx.amira, conversation.conversation_id, "private")
    cookies, _ = _login(ctx, ctx.layla)
    response = client.get(
        f"/app/api/conversations/{conversation.conversation_id}/messages", cookies=cookies
    )
    assert response.status_code == 404


# --- the SSE stream ----------------------------------------------------------


def test_conversation_stream_route_returns_streaming_response(ctx) -> None:
    import asyncio

    from fastapi.responses import StreamingResponse

    from helix_codex_app.modules.messaging.router import conversation_stream

    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)

    class _State:
        account = ctx.amira

    class _App:
        state = SimpleNamespace(settings=ctx.settings)

    class _FakeRequest:
        app = _App()
        state = _State()

    async def run():
        response = await conversation_stream(  # type: ignore[arg-type]
            _FakeRequest(), conversation.conversation_id
        )
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"

    asyncio.run(run())


@pytest.mark.parametrize("outsider", ["layla", "ghada"])
def test_stream_is_403_for_any_non_member(ctx, client, outsider) -> None:
    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    account = getattr(ctx, outsider)
    cookies, _ = _login(ctx, account)
    response = client.get(_stream_url(conversation.conversation_id), cookies=cookies)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_conversation_event_stream_emits_a_posted_message(ctx) -> None:
    import asyncio

    conversation = ctx.service.create_direct(ctx.amira, ctx.omar)
    conversation_id = conversation.conversation_id

    async def collect() -> list[str]:
        request = _FakeRequest()
        frames: list[str] = []
        payload = dict(_MESSAGE_PAYLOAD, conversation_id=conversation_id)
        # Publish shortly after the generator starts: publish() delivers to
        # the subscribers that exist at that moment, and the generator only
        # subscribes once iteration begins. The route publishes the same
        # shape immediately after send_message, so this is the posted frame.
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, publish, conversation_id, "message", payload)
        async for frame in conversation_event_stream(request, conversation_id):  # type: ignore[arg-type]
            frames.append(frame)
            request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames, "the stream emitted nothing"
    assert "event: message" in frames[0]
    assert "msg-x" in frames[0]
    assert "hello from the stream" in frames[0]
    assert subscriber_count(conversation_id) == 0, "unsubscribe was not called"


def test_conversation_event_stream_closes_cleanly_on_disconnect(ctx) -> None:
    import asyncio

    conversation_id = ctx.service.create_direct(ctx.amira, ctx.omar).conversation_id

    async def run() -> list[str]:
        frames: list[str] = []
        async for frame in conversation_event_stream(
            _FakeRequest(disconnected=True), conversation_id
        ):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert frames == []
    assert subscriber_count(conversation_id) == 0, "disconnect left a subscriber behind"
