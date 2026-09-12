"""Task feature — task management with status tracking."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server import deps
from server.models.node import Classification, Nature, NodeEnvelope, Provenance, TaskNode

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/")
async def create_task(
    title: str,
    description: str = "",
    tenant_id: str = "default",
    assignee: str | None = None,
) -> dict:
    """Create a new task."""
    store = deps.get_store()

    node = TaskNode(
        envelope=NodeEnvelope(
            node_id=f"task_{len(store.list_by_tenant(tenant_id))}",
            tenant_id=tenant_id,
            client_id=None,
            correlation_id=f"tasks_{tenant_id}",
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
        body={"title": title, "description": description, "assignee": assignee, "status": "open"},
    )

    store.create(node)

    return {"status": "ok", "node_id": node.envelope.node_id}


@router.get("/")
async def list_tasks(
    tenant_id: str = "default",
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List tasks with optional status filter."""
    store = deps.get_store()
    nodes = store.list_by_tenant(tenant_id, limit=limit)

    if status:
        nodes = [n for n in nodes if n.body.get("status") == status]

    return [n.to_dict() for n in nodes]


@router.put("/{task_id}/status")
async def update_task_status(
    task_id: str,
    status: str,
    tenant_id: str = "default",
) -> dict:
    """Update task status."""
    store = deps.get_store()
    task = store.get(task_id, tenant_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    task.body["status"] = status
    store.create(task)

    return {"status": "ok"}
