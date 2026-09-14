"""Notification screens, JSON API, and SSE stream tests (P2.3).

HTTP tests drive the mounted notifications router through TestClient,
covering the screens, the JSON contract, CSRF, and SSE header-level
checks.  The SSE stream is driven directly so the infinite body does
not hang the test client.
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
from helix_codex_app.integration.sse_bridge import subscriber_count
from helix_codex_app.modules.messaging.service import MessagingService
from helix_codex_app.modules.notifications.router import (
    notification_event_stream,
    notification_stream,
)
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
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    messaging = MessagingService(conn)
    notifications = NotificationService(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        amira=amira,
        omar=omar,
        layla=layla,
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
    """Return (cookies, headers) for one account: cookie + CSRF header."""
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


# --- screens ------------------------------------------------------------------


def test_notifications_screen_renders_empty(ctx, client) -> None:
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/notifications", cookies=cookies)
    assert response.status_code == 200
    assert "No notifications yet" in response.text


def test_notifications_screen_lists_items(ctx, client) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "hi @omar")
    cookies, _ = _login(ctx, ctx.omar)
    response = client.get("/app/notifications", cookies=cookies)
    assert response.status_code == 200
    assert "Mention in Team" in response.text


def test_notifications_screen_requires_auth(client) -> None:
    response = client.get("/app/notifications")
    assert response.status_code == 401


# --- JSON API -----------------------------------------------------------------


def test_list_notifications_returns_own_items(ctx, client) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "hello @omar")
    cookies, _ = _login(ctx, ctx.omar)
    response = client.get("/app/api/notifications", cookies=cookies)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["kind"] == "mention"
    assert items[0]["read_at"] is None


def test_list_notifications_isolation(ctx, client) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "hi @omar")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/api/notifications", cookies=cookies)
    assert response.json() == []


# --- mark_read ----------------------------------------------------------------


def test_mark_read_is_idempotent(ctx, client) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "ping @omar")
    note = ctx.notifications.list_for(ctx.omar)[0]
    cookies, headers = _login(ctx, ctx.omar)
    first = client.post(
        f"/app/api/notifications/{note.notification_id}/read",
        cookies=cookies,
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json() == {"ok": True}
    second = client.post(
        f"/app/api/notifications/{note.notification_id}/read",
        cookies=cookies,
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json() == {"ok": True}


def test_mark_read_404_for_another_account(ctx, client) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "ping @omar")
    note = ctx.notifications.list_for(ctx.omar)[0]
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/notifications/{note.notification_id}/read",
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 404


def test_mark_read_requires_csrf(ctx, client) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "x @omar")
    note = ctx.notifications.list_for(ctx.omar)[0]
    cookies, _ = _login(ctx, ctx.omar)
    response = client.post(
        f"/app/api/notifications/{note.notification_id}/read",
        cookies=cookies,
    )
    assert response.status_code == 403


# --- mark_all_read -----------------------------------------------------------


def test_mark_all_read(ctx, client) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "a @omar")
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "b @omar")
    assert ctx.notifications.unread_count(ctx.omar) == 2
    cookies, headers = _login(ctx, ctx.omar)
    response = client.post(
        "/app/api/notifications/read-all",
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert ctx.notifications.unread_count(ctx.omar) == 0


# --- SSE stream ---------------------------------------------------------------


def test_notification_stream_returns_streaming_response(ctx) -> None:
    import asyncio

    from fastapi.responses import StreamingResponse

    class _State:
        account = ctx.amira

    class _App:
        state = SimpleNamespace(settings=ctx.settings)

    class _Request:
        app = _App()
        state = _State()

    async def run():
        response = await notification_stream(_Request())  # type: ignore[arg-type]
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"

    asyncio.run(run())


def test_notification_event_stream_emits_initial_count(ctx) -> None:
    group = ctx.messaging.create_group(ctx.amira, "Team", [ctx.omar])
    ctx.messaging.send_message(ctx.amira, group.conversation_id, "ping @omar")

    async def collect() -> list[str]:
        request = _FakeRequest()
        frames: list[str] = []
        async for frame in notification_event_stream(request, ctx.omar.account_id, 1):
            frames.append(frame)
            request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames, "the stream emitted nothing"
    assert "event: unread_count" in frames[0]
    assert '"unread": 1' in frames[0]


def test_notification_event_stream_emits_bus_frame(ctx) -> None:
    from helix_codex_app.integration.sse_bridge import publish

    account_id = ctx.omar.account_id

    async def collect() -> list[str]:
        request = _FakeRequest()
        frames: list[str] = []
        loop = asyncio.get_running_loop()
        loop.call_later(
            0.05,
            publish,
            account_id,
            "notification",
            {"notification_id": "notif-x", "kind": "dm"},
        )
        async for frame in notification_event_stream(request, account_id, 0):
            frames.append(frame)
            if len(frames) >= 2:
                request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert len(frames) >= 2
    assert "event: unread_count" in frames[0]
    assert "event: notification" in frames[1]


def test_notification_stream_cleans_up_on_disconnect(ctx) -> None:
    async def run() -> list[str]:
        frames: list[str] = []
        async for frame in notification_event_stream(
            _FakeRequest(disconnected=True), ctx.omar.account_id, 0
        ):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    # The initial unread_count frame is always emitted before the disconnect
    # check, so one frame is expected.  What matters is the subscriber is
    # cleaned up.
    assert len(frames) == 1
    assert "event: unread_count" in frames[0]
    assert subscriber_count(ctx.omar.account_id) == 0


class _FakeRequest:
    def __init__(self, disconnected: bool = False) -> None:
        self.disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self.disconnected
