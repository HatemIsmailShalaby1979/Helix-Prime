"""SSE stream isolation for conversations and notifications (P2.4 close-out).

A conversation stream refuses any non-member — same-tenant outsider or
foreign-tenant account — with a 403.  A notification stream only delivers
frames for the owning account: other accounts' publishes on the same bus
are invisible.

The conversation stream is driven directly because a test client cannot
drain an infinite body.  The pattern is identical to P2.2 and P2.3.
"""
from __future__ import annotations

import asyncio
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
from helix_codex_app.modules.notifications.router import notification_event_stream
from helix_codex_app.modules.notifications.service import NotificationService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore


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


def _stream_url(conversation_id: str) -> str:
    return f"/app/api/conversations/{conversation_id}/stream"


class _FakeRequest:
    def __init__(self, disconnected: bool = False) -> None:
        self.disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self.disconnected


# --- conversation stream: non-member 403 ------------------------------------


@pytest.mark.parametrize("outsider", ["layla", "ghada"])
def test_conversation_stream_is_403_for_any_non_member(ctx, client, outsider) -> None:
    conversation = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    account = getattr(ctx, outsider)
    cookies, _ = _login(ctx, account)
    response = client.get(_stream_url(conversation.conversation_id), cookies=cookies)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


# --- conversation stream: member-open ----------------------------------------


def test_conversation_stream_opens_for_a_member(ctx) -> None:
    from fastapi.responses import StreamingResponse

    from helix_codex_app.modules.messaging.router import conversation_stream

    conversation = ctx.messaging.create_direct(ctx.amira, ctx.omar)

    class _State:
        account = ctx.amira

    class _App:
        state = SimpleNamespace(settings=ctx.settings)

    class _Request:
        app = _App()
        state = _State()

    async def run():
        response = await conversation_stream(  # type: ignore[arg-type]
            _Request(), conversation.conversation_id
        )
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"

    asyncio.run(run())


# --- conversation stream: per-key isolation ----------------------------------


def test_conversation_stream_relays_only_its_own_conversation(ctx) -> None:
    conversation = ctx.messaging.create_direct(ctx.amira, ctx.omar)
    own_id = conversation.conversation_id
    other_conv = ctx.messaging.create_direct(ctx.amira, ctx.layla)
    other_id = other_conv.conversation_id

    async def collect() -> list[str]:
        request = _FakeRequest()
        frames: list[str] = []
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, publish, other_id, "message", {"body": "from another thread"})
        loop.call_later(0.10, publish, own_id, "message", {"body": "mine"})
        async for frame in conversation_event_stream(request, own_id):
            frames.append(frame)
            request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames, "the stream emitted nothing"
    assert "mine" in frames[0]
    assert "from another thread" not in frames[0]
    assert subscriber_count(own_id) == 0


# --- notification stream: owner-only frames ----------------------------------


def test_notification_stream_relays_only_the_owning_accounts_frames(ctx) -> None:
    omar_id = ctx.omar.account_id
    layla_id = ctx.layla.account_id

    async def collect() -> list[str]:
        request = _FakeRequest()
        frames: list[str] = []
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, publish, layla_id, "notification", {"source": "layla"})
        loop.call_later(0.10, publish, omar_id, "notification", {"source": "omar"})
        async for frame in notification_event_stream(request, omar_id, 0):
            frames.append(frame)
            if len(frames) >= 2:
                request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert len(frames) >= 2
    assert "event: unread_count" in frames[0]
    assert "event: notification" in frames[1]
    assert "omar" in frames[1]
    notification_frames = [f for f in frames if "event: notification" in f]
    assert len(notification_frames) == 1
    assert "layla" not in str(notification_frames)
    assert subscriber_count(omar_id) == 0


# --- notification stream: owner-scoped initial count -------------------------


def test_notification_stream_initial_count_is_the_owning_accounts(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "ping @omar")
    omar_unread = ctx.notifications.unread_count(ctx.omar)

    async def collect() -> list[str]:
        request = _FakeRequest()
        frames: list[str] = []
        async for frame in notification_event_stream(request, ctx.omar.account_id, omar_unread):
            frames.append(frame)
            request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames, "the stream emitted nothing"
    assert "event: unread_count" in frames[0]
    assert f'"unread": {omar_unread}' in frames[0]
