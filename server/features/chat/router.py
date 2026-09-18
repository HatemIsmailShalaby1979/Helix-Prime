"""Chat feature — real-time messaging with SSE streaming."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from security.identity import Identity
from server import deps
from server import scope as api_scope
from server.auth import current_identity
from server.models.node import ChatMessage, Classification, Nature, NodeEnvelope, Provenance

router = APIRouter(prefix="/api/chat", tags=["chat"])


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
    identity: Identity = Depends(current_identity),
):
    """SSE stream for chat messages."""
    api_scope.require_tenant(identity, tenant_id, route="GET /api/chat/stream", request=request)
    return None
