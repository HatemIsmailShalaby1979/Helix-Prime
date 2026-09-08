"""Document feature — document storage and retrieval."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.models.node import DocumentNode, NodeEnvelope, Nature, Classification, Provenance
from server.models.store import NodeStore
from server import deps

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.post("/")
async def create_document(
    title: str,
    content: str = "",
    tenant_id: str = "default",
) -> dict:
    """Create a new document."""
    store = deps.get_store()

    node = DocumentNode(
        envelope=NodeEnvelope(
            node_id=f"doc_{len(store.list_by_tenant(tenant_id))}",
            tenant_id=tenant_id,
            client_id=None,
            correlation_id=f"docs_{tenant_id}",
            causation_id=None,
            classification=Classification.CLIENT_CONFIDENTIAL,
            provenance=Provenance(
                source="user",
                data_mode="simulated_realistic",
                retrieved_at="",
            ),
            nature=Nature.USER_CLAIM,
            created_by="user",
            created_at="",
        ),
        body={"title": title, "content": content},
    )

    store.create(node)

    return {"status": "ok", "node_id": node.envelope.node_id}


@router.get("/")
async def list_documents(
    tenant_id: str = "default",
    limit: int = 100,
) -> list[dict]:
    """List documents for a tenant."""
    store = deps.get_store()
    nodes = store.list_by_tenant(tenant_id, limit=limit)

    return [n.to_dict() for n in nodes]


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    tenant_id: str = "default",
) -> dict:
    """Get a document by ID."""
    store = deps.get_store()
    doc = store.get(doc_id, tenant_id)

    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return doc.to_dict()


@router.put("/{doc_id}")
async def update_document(
    doc_id: str,
    content: str | None = None,
    title: str | None = None,
    tenant_id: str = "default",
) -> dict:
    """Update a document."""
    store = deps.get_store()
    doc = store.get(doc_id, tenant_id)

    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if title is not None:
        doc.body["title"] = title
    if content is not None:
        doc.body["content"] = content

    store.create(doc)

    return {"status": "ok"}
