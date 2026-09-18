"""
Chat SSE stream tests for the headless FastAPI surface.

``GET /api/chat/stream/{correlation_id}`` is a tenant-scoped EventSource:
the subscription key carries tenant and correlation id, frames are filtered
to the caller scope, idle connections get keep-alive comments, and disconnect
unsubscribes. Unknown correlations answer 404 and foreign tenants 403.

The foreign-frame test is the can-fail proof for the per-frame filter: it
publishes a foreign-tenant payload to the caller key directly, so removing
the filter lets it through and the test fails.
"""
from __future__ import annotations

import asyncio
import secrets
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from security.identity import Identity
from server.errors import NotFound

TOKEN = secrets.token_urlsafe(24)
TENANT_A = "tenant-chat-a"
TENANT_B = "tenant-chat-b"
CLIENT_A = "client-chat-a"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", TOKEN)
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", "sami")
    monkeypatch.setenv("HELIX_API_TOKEN_TENANT_ID", TENANT_A)
    monkeypatch.setenv("HELIX_API_TOKEN_CLIENT_ID", CLIENT_A)
    monkeypatch.delenv("HELIX_API_ALLOW_GLOBAL_OPERATOR", raising=False)
    from server.app import create_app
    from server.config import Settings

    settings = Settings(
        profile="local",
        db_path=str(tmp_path / "workflow.db"),
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _identity():
    return Identity(
        actor="sami",
        actor_type="service",
        tenant_id=TENANT_A,
        client_id=CLIENT_A,
        role_id="sami",
    )


class _FakeRequest:
    def __init__(self) -> None:
        self.disconnected = False
        self.state = SimpleNamespace(correlation_id="test-correlation")

    async def is_disconnected(self) -> bool:
        return self.disconnected


def _inbox() -> str:
    return f"chat_{TENANT_A}"


def _key(tenant: str, correlation: str) -> str:
    return f"chat:{tenant}:{correlation}"


def test_stream_response_content_type(client):
    from server.features.chat.router import stream_messages

    resp = asyncio.run(stream_messages(_inbox(), _FakeRequest(), identity=_identity()))
    assert resp.status_code == 200
    assert resp.media_type == "text/event-stream"
    assert resp.headers["Cache-Control"] == "no-cache"
    assert resp.headers["Connection"] == "keep-alive"
    assert resp.headers["X-Accel-Buffering"] == "no"


def test_authorized_stream_receives_its_own_event():
    from server.features.chat.router import chat_event_stream
    from server.sse import get_bus

    async def collect() -> list[str]:
        bus = get_bus()
        request = _FakeRequest()
        frames: list[str] = []
        loop = asyncio.get_running_loop()
        loop.call_later(
            0.05,
            bus.publish,
            _key(TENANT_A, _inbox()),
            "chat_message",
            {"tenant_id": TENANT_A, "client_id": CLIENT_A, "body": "hello"},
        )
        async for frame in chat_event_stream(request, TENANT_A, CLIENT_A, _inbox()):
            frames.append(frame)
            request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames, "the stream emitted nothing"
    assert frames[0].startswith("event: chat_message")
    assert TENANT_A in frames[0]
    assert get_bus().subscriber_count(_key(TENANT_A, _inbox())) == 0


def test_created_message_reaches_the_tenant_stream(client):
    from server.sse import get_bus

    async def collect() -> dict:
        bus = get_bus()
        queue = bus.subscribe(_key(TENANT_A, _inbox()))
        try:

            def _post() -> None:
                resp = client.post(
                    "/api/chat/messages",
                    params={"message": "hello-bus"},
                    headers=_auth(),
                )
                assert resp.status_code == 200

            await asyncio.to_thread(_post)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 5.0
            while True:
                try:
                    return queue.get_nowait()
                except asyncio.QueueEmpty:
                    if loop.time() > deadline:
                        raise AssertionError(
                            "no chat frame published for the created message"
                        ) from None
                    await asyncio.sleep(0.01)
        finally:
            bus.unsubscribe(_key(TENANT_A, _inbox()), queue)

    frame = asyncio.run(collect())
    assert frame["event"] == "chat_message"
    assert frame["data"]["tenant_id"] == TENANT_A
    assert frame["data"]["body"]["content"] == "hello-bus"


def test_foreign_tenant_event_is_never_emitted(monkeypatch):
    import server.features.chat.router as chat_router
    from server.features.chat.router import chat_event_stream
    from server.sse import get_bus

    monkeypatch.setattr(chat_router, "_HEARTBEAT_SECONDS", 0.02)

    async def collect() -> list[str]:
        bus = get_bus()
        request = _FakeRequest()
        frames: list[str] = []
        loop = asyncio.get_running_loop()
        loop.call_later(
            0.05,
            bus.publish,
            _key(TENANT_B, f"chat_{TENANT_B}"),
            "chat_message",
            {"tenant_id": TENANT_B, "body": "foreign"},
        )
        async for frame in chat_event_stream(request, TENANT_A, CLIENT_A, _inbox()):
            frames.append(frame)
            if len(frames) >= 2:
                request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames
    assert TENANT_B not in "".join(frames)
    assert get_bus().subscriber_count(_key(TENANT_A, _inbox())) == 0


def test_stream_skips_frames_from_another_tenant(monkeypatch):
    import server.features.chat.router as chat_router
    from server.features.chat.router import chat_event_stream
    from server.sse import get_bus

    monkeypatch.setattr(chat_router, "_HEARTBEAT_SECONDS", 0.02)

    async def collect() -> list[str]:
        bus = get_bus()
        request = _FakeRequest()
        frames: list[str] = []
        loop = asyncio.get_running_loop()
        loop.call_later(
            0.05,
            bus.publish,
            _key(TENANT_A, _inbox()),
            "chat_message",
            {"tenant_id": TENANT_B, "body": "smuggled"},
        )
        async for frame in chat_event_stream(request, TENANT_A, CLIENT_A, _inbox()):
            frames.append(frame)
            if len(frames) >= 2:
                request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames
    assert all(frame == ": keep-alive\n\n" for frame in frames)


def test_unauthorized_stream_is_rejected(client):
    from server.features.chat.router import stream_messages

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            stream_messages(_inbox(), _FakeRequest(), tenant_id=TENANT_B, identity=_identity())
        )
    assert exc.value.status_code == 403


def test_unknown_stream_is_not_found(client):
    from server.features.chat.router import stream_messages

    with pytest.raises(NotFound) as exc:
        asyncio.run(stream_messages("no-such-correlation", _FakeRequest(), identity=_identity()))
    assert exc.value.http_status == 404


def test_keep_alive_frames_flow_while_idle(monkeypatch):
    import server.features.chat.router as chat_router
    from server.features.chat.router import chat_event_stream
    from server.sse import get_bus

    monkeypatch.setattr(chat_router, "_HEARTBEAT_SECONDS", 0.02)

    async def collect() -> list[str]:
        request = _FakeRequest()
        frames: list[str] = []
        async for frame in chat_event_stream(request, TENANT_A, CLIENT_A, _inbox()):
            frames.append(frame)
            request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames == [": keep-alive\n\n"]
    assert get_bus().subscriber_count(_key(TENANT_A, _inbox())) == 0


def test_message_list_and_create_are_tenant_isolated(client, monkeypatch):
    created = client.post("/api/chat/messages", params={"message": "scoped"}, headers=_auth())
    assert created.status_code == 200
    mine = client.get("/api/chat/messages", headers=_auth()).json()
    assert any(n["body"]["content"] == "scoped" for n in mine)
    monkeypatch.setenv("HELIX_API_TOKEN_TENANT_ID", TENANT_B)
    assert client.get("/api/chat/messages", headers=_auth()).json() == []
    assert (
        client.post(
            "/api/chat/messages",
            params={"message": "x", "tenant_id": TENANT_A},
            headers=_auth(),
        ).status_code
        == 403
    )
