"""HTTP surface for the approval queue."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request

from security.identity import Identity
from server import deps
from server import scope as api_scope
from server.auth import current_identity
from server.errors import NotFound
from server.features.approvals.schemas import ApprovalRequest
from server.features.approvals.service import ApprovalService
from server.features.workflows.repository import WorkflowRepository
from server.features.workflows.schemas import WorkflowResponse

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _service() -> ApprovalService:
    return ApprovalService(deps.get_engine())


@router.get("", response_model=List[WorkflowResponse])
def queue(
    request: Request,
    limit: int = 50,
    service: ApprovalService = Depends(_service),
    identity: Identity = Depends(current_identity),
) -> List[Dict[str, Any]]:
    """Everything the governance gate has frozen, awaiting a human."""
    pending = service.pending(limit=limit)
    if api_scope.is_global(identity):
        api_scope.audit_global_access(
            identity,
            target_tenant=api_scope.GLOBAL_TARGET,
            target_client=None,
            route="GET /api/approvals",
            request=request,
        )
        return pending
    return [item for item in pending if item.get("tenant_id") == identity.tenant_id]


@router.post("/{workflow_id}", response_model=WorkflowResponse)
def decide(
    workflow_id: str,
    payload: ApprovalRequest,
    request: Request,
    service: ApprovalService = Depends(_service),
    identity: Identity = Depends(current_identity),
) -> Dict[str, Any]:
    existing = WorkflowRepository(deps.get_engine()).get(workflow_id)
    if existing is None or (
        not api_scope.is_global(identity) and existing.tenant_id != identity.tenant_id
    ):
        raise NotFound(f"workflow {workflow_id!r} not found")
    if api_scope.is_global(identity):
        api_scope.audit_global_access(
            identity,
            target_tenant=existing.tenant_id,
            target_client=existing.client_id,
            route="POST /api/approvals/{workflow_id}",
            request=request,
        )
    workflow = service.decide(workflow_id, payload)
    return WorkflowResponse(
        workflow_id=workflow.workflow_id,
        task_id=workflow.task_id,
        state=workflow.state,
        capability=workflow.capability,
        tenant_id=workflow.tenant_id,
        client_id=workflow.client_id,
        correlation_id=workflow.correlation.correlation_id,
    ).model_dump()
