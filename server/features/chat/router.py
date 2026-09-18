"""Chat feature — real-time messaging with SSE streaming."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from security.identity import Identity
from server import deps
from server import scope as api_scope
from server.auth import current_identity
from server.errors import NotFound
from server.models.node import ChatMessage, Classification, Nature, NodeEnvelope, Provenance
from server.sse import encode, get_bus

router = APIRouter(prefix="/api/chat", tags=["chat"])

_HEARTBEAT_SECONDS = 15


def _stream_key(tenant: str, correlation_id: str) -> str:
    return f"chat:{tenant}:{correlation_id}"


def _inbox_correlation(tenant: str) -> str:
    return f"chat_{tenant}"


async def chat_event_stream(request: Request, tenant: str, client: str | None, correlation_id: str):
    """
    Yield SSE frames for one chat correlation until the client goes away.

    Split out from the route so it can be driven directly in tests: an
    ASGI test client cannot stream an infinite response to completion.
    """
    bus = get_bus()
    key = _stream_key(tenant, correlation_id)
    queue = bus.subscribe(key)
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            data = frame.get("data") if isinstance(frame, dict) else None
            if not isinstance(data, dict) or data.get("tenant_id") != tenant:
                continue
            if client is not None and data.get("client_id") != client:
                continue
            yield encode(frame.get("event", "chat_message"), data)
    finally:
        bus.unsubscribe(key, queue)


@router.post("/messages")
async def create_message(
    message: str,
    request: Request,
    tenant_id: str | None = None,
    client_id: str | None = None,
    identity: Identity = Depends(current_identity),
) -> dict:
    """Create a new chat message."""
    tenant = api_scope.require_tenant(
        identity, tenant_id, route="POST /api/chat/messages", request=request
    )
    if tenant is None:
        tenant = "default"
    client = api_scope.require_client(identity, client_id)
    with deps.node_store() as store:
        node = ChatMessage(
            envelope=NodeEnvelope(
                node_id=f"msg_{len(store.list_by_tenant(tenant))}",
                tenant_id=tenant,
                client_id=client,
                correlation_id=f"chat_{tenant}",
                causation_id=None,
                classification=Classification.INTERNAL,
                provenance=Provenance(
                    source="user",
                    data_mode="simulated_realistic",
                    retrieved_at="",
                ),
                nature=Nature.USER_CLAIM,
                created_by="user",
                created_at="",
            ),
            body={"content": message},
        )
        store.create(node)

    get_bus().publish(
        _stream_key(tenant, node.envelope.correlation_id),
        "chat_message",
        node.to_dict(),
    )

    return {"status": "ok", "node_id": node.envelope.node_id}


@router.get("/messages")
async def list_messages(
    request: Request,
    tenant_id: str | None = None,
    limit: int = 50,
    identity: Identity = Depends(current_identity),
) -> list[dict]:
    """List chat messages for a tenant."""
    tenant = api_scope.require_tenant(
        identity, tenant_id, route="GET /api/chat/messages", request=request
    )
    if tenant is None:
        tenant = "default"
    with deps.node_store() as store:
        nodes = store.list_by_tenant(tenant, limit=limit)

    return [node.to_dict() for node in nodes]


@router.get("/stream/{correlation_id}")
async def stream_messages(
    correlation_id: str,
    request: Request,
    tenant_id: str | None = None,
    client_id: str | None = None,
    identity: Identity = Depends(current_identity),
) -> StreamingResponse:
    """SSE stream for one chat correlation inside the caller scope."""
    tenant = api_scope.require_tenant(
        identity, tenant_id, route="GET /api/chat/stream", request=request
    )
    if tenant is None:
        tenant = "default"
    client = api_scope.require_client(identity, client_id)
    if correlation_id != _inbox_correlation(tenant) and not _has_history(tenant, correlation_id):
        raise NotFound(f"no chat stream for correlation {correlation_id!r}")
    return StreamingResponse(
        chat_event_stream(request, tenant, client, correlation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _has_history(tenant: str, correlation_id: str) -> bool:
    with deps.node_store() as store:
        return len(store.list_by_correlation(correlation_id, tenant)) > 0
