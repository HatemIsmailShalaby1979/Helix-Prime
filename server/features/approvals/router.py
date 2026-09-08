"""HTTP surface for the approval queue."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from server import deps
from server.features.approvals.schemas import ApprovalRequest
from server.features.approvals.service import ApprovalService
from server.features.workflows.schemas import WorkflowResponse

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _service() -> ApprovalService:
    return ApprovalService(deps.get_engine())


@router.get("", response_model=List[WorkflowResponse])
def queue(limit: int = 50, service: ApprovalService = Depends(_service)) -> List[Dict[str, Any]]:
    """Everything the governance gate has frozen, awaiting a human."""
    return service.pending(limit=limit)


@router.post("/{workflow_id}", response_model=WorkflowResponse)
def decide(
    workflow_id: str,
    payload: ApprovalRequest,
    service: ApprovalService = Depends(_service),
) -> Dict[str, Any]:
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
