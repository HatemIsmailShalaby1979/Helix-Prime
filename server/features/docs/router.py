"""Document feature — document storage and retrieval."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from security.identity import Identity
from server import deps
from server import scope as api_scope
from server.auth import current_identity
from server.models.node import Classification, DocumentNode, Nature, NodeEnvelope, Provenance

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.post("/")
async def create_document(
    title: str,
    request: Request,
    content: str = "",
    tenant_id: str | None = None,
    identity: Identity = Depends(current_identity),
) -> dict:
    """Create a new document."""
    tenant = api_scope.require_tenant(identity, tenant_id, route="POST /api/docs", request=request)
    if tenant is None:
        tenant = "default"
    with deps.node_store() as store:
        node = DocumentNode(
            envelope=NodeEnvelope(
                node_id=f"doc_{len(store.list_by_tenant(tenant))}",
                tenant_id=tenant,
                client_id=None,
                correlation_id=f"docs_{tenant}",
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
    request: Request,
    tenant_id: str | None = None,
    limit: int = 100,
    identity: Identity = Depends(current_identity),
) -> list[dict]:
    """List documents for a tenant."""
    tenant = api_scope.require_tenant(identity, tenant_id, route="GET /api/docs", request=request)
    if tenant is None:
        tenant = "default"
    with deps.node_store() as store:
        nodes = store.list_by_tenant(tenant, limit=limit)

    return [n.to_dict() for n in nodes]


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    request: Request,
    tenant_id: str | None = None,
    identity: Identity = Depends(current_identity),
) -> dict:
    """Get a document by ID."""
    tenant = api_scope.require_tenant(
        identity, tenant_id, route="GET /api/docs/{doc_id}", request=request
    )
    if tenant is None:
        tenant = "default"
    with deps.node_store() as store:
        doc = store.get(doc_id, tenant)

    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return doc.to_dict()


@router.put("/{doc_id}")
async def update_document(
    doc_id: str,
    request: Request,
    content: str | None = None,
    title: str | None = None,
    tenant_id: str | None = None,
    identity: Identity = Depends(current_identity),
) -> dict:
    """Update a document."""
    tenant = api_scope.require_tenant(
        identity, tenant_id, route="PUT /api/docs/{doc_id}", request=request
    )
    if tenant is None:
        tenant = "default"
    with deps.node_store() as store:
        doc = store.get(doc_id, tenant)

        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        if title is not None:
            doc.body["title"] = title
        if content is not None:
            doc.body["content"] = content

        store.create(doc)

    return {"status": "ok"}
