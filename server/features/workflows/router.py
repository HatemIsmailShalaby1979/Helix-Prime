"""HTTP surface for workflows."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Response, status

from server import deps
from server.errors import GateAwaitingApproval
from server.features.workflows.schemas import SubmitWorkflowRequest, WorkflowResponse
from server.features.workflows.service import WorkflowService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _service() -> WorkflowService:
    return WorkflowService(deps.get_engine())


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_202_ACCEPTED)
def submit(
    payload: SubmitWorkflowRequest,
    response: Response,
    service: WorkflowService = Depends(_service),
) -> Dict[str, Any]:
    """
    Submit a task request.

    202 because a governed submission is not a completed action. A run that the
    gate freezes returns **409** with the decision payload: it was recorded, and
    it has not happened.
    """
    workflow = service.submit(payload)
    body = service.repo.to_response(workflow)
    if workflow.state == "awaiting_approval":
        response.status_code = status.HTTP_409_CONFLICT
    return body


@router.get("", response_model=List[WorkflowResponse])
def list_recent(
    limit: int = 50, service: WorkflowService = Depends(_service)
) -> List[Dict[str, Any]]:
    return [service.repo.to_response(w) for w in service.repo.list_recent(limit=limit)]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get(workflow_id: str, service: WorkflowService = Depends(_service)) -> Dict[str, Any]:
    return service.repo.to_response(service.get(workflow_id))


@router.get("/{workflow_id}/events")
def events(workflow_id: str, service: WorkflowService = Depends(_service)) -> List[Dict[str, Any]]:
    """The run timeline. This is what makes a decision replayable."""
    service.get(workflow_id)  # 404 before returning an empty timeline
    return service.repo.events(workflow_id)


@router.post("/{workflow_id}/execute", response_model=WorkflowResponse)
def execute(
    workflow_id: str,
    response: Response,
    service: WorkflowService = Depends(_service),
) -> Dict[str, Any]:
    try:
        workflow = service.execute(workflow_id)
    except GateAwaitingApproval as exc:
        response.status_code = exc.http_status
        return exc.payload or {}
    return service.repo.to_response(workflow)


@router.get("/{workflow_id}/result")
def result(workflow_id: str, service: WorkflowService = Depends(_service)) -> Dict[str, Any]:
    return service.result(service.get(workflow_id))
