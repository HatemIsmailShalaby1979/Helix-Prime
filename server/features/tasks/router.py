"""Task feature — task management with status tracking."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from security.identity import Identity
from server import deps
from server import scope as api_scope
from server.auth import current_identity
from server.models.node import Classification, Nature, NodeEnvelope, Provenance, TaskNode

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/")
async def create_task(
    title: str,
    request: Request,
    description: str = "",
    tenant_id: str | None = None,
    assignee: str | None = None,
    identity: Identity = Depends(current_identity),
) -> dict:
    """Create a new task."""
    tenant = api_scope.require_tenant(identity, tenant_id, route="POST /api/tasks", request=request)
    if tenant is None:
        tenant = "default"
    with deps.node_store() as store:
        node = TaskNode(
            envelope=NodeEnvelope(
                node_id=f"task_{len(store.list_by_tenant(tenant))}",
                tenant_id=tenant,
                client_id=None,
                correlation_id=f"tasks_{tenant}",
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
            body={
                "title": title,
                "description": description,
                "assignee": assignee,
                "status": "open",
            },
        )
        store.create(node)

    return {"status": "ok", "node_id": node.envelope.node_id}


@router.get("/")
async def list_tasks(
    request: Request,
    tenant_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    identity: Identity = Depends(current_identity),
) -> list[dict]:
    """List tasks with optional status filter."""
    tenant = api_scope.require_tenant(identity, tenant_id, route="GET /api/tasks", request=request)
    if tenant is None:
        tenant = "default"
    with deps.node_store() as store:
        nodes = store.list_by_tenant(tenant, limit=limit)

    if status:
        nodes = [n for n in nodes if n.body.get("status") == status]

    return [n.to_dict() for n in nodes]


@router.put("/{task_id}/status")
async def update_task_status(
    task_id: str,
    status: str,
    request: Request,
    tenant_id: str | None = None,
    identity: Identity = Depends(current_identity),
) -> dict:
    """Update task status."""
    tenant = api_scope.require_tenant(
        identity, tenant_id, route="PUT /api/tasks/{task_id}/status", request=request
    )
    if tenant is None:
        tenant = "default"
    with deps.node_store() as store:
        task = store.get(task_id, tenant)

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        task.body["status"] = status
        store.create(task)

    return {"status": "ok"}
