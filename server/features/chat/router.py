"""Chat feature — real-time messaging with SSE streaming."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.models.node import ChatMessage, NodeEnvelope, Nature, Classification, Provenance
from server.models.store import NodeStore
from server import deps

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/messages")
async def create_message(
    message: str,
    tenant_id: str = "default",
    client_id: str | None = None,
) -> dict:
    """Create a new chat message."""
    store = deps.get_store()
    engine = deps.get_engine()

    # Create node
    node = ChatMessage(
        envelope=NodeEnvelope(
            node_id=f"msg_{len(store.list_by_tenant(tenant_id))}",
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=f"chat_{tenant_id}",
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
    tenant_id: str = "default",
    limit: int = 50,
) -> list[dict]:
    """List chat messages for a tenant."""
    store = deps.get_store()
    nodes = store.list_by_tenant(tenant_id, limit=limit)

    return [node.to_dict() for node in nodes]


@router.get("/stream/{correlation_id}")
async def stream_messages(
    correlation_id: str,
    tenant_id: str = "default",
):
    """SSE stream for chat messages."""
    # TODO: Implement SSE streaming
    pass
