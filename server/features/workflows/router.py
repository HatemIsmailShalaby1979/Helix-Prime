"""HTTP surface for workflows."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request, Response, status

from security.identity import Identity
from server import deps
from server import scope as api_scope
from server.auth import current_identity
from server.errors import GateAwaitingApproval, NotFound
from server.features.workflows.schemas import SubmitWorkflowRequest, WorkflowResponse
from server.features.workflows.service import WorkflowService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _service() -> WorkflowService:
    return WorkflowService(deps.get_engine())


def _scoped_workflow(
    service: WorkflowService,
    workflow_id: str,
    identity: Identity,
    route: str,
    request: Request,
):
    workflow = service.get(workflow_id)
    if not api_scope.is_global(identity) and workflow.tenant_id != identity.tenant_id:
        raise NotFound(f"workflow {workflow_id!r} not found")
    if api_scope.is_global(identity):
        api_scope.audit_global_access(
            identity,
            target_tenant=workflow.tenant_id,
            target_client=workflow.client_id,
            route=route,
            request=request,
        )
    return workflow


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_202_ACCEPTED)
def submit(
    payload: SubmitWorkflowRequest,
    response: Response,
    request: Request,
    service: WorkflowService = Depends(_service),
    identity: Identity = Depends(current_identity),
) -> Dict[str, Any]:
    """
    Submit a task request.

    202 because a governed submission is not a completed action. A run that the
    gate freezes returns **409** with the decision payload: it was recorded, and
    it has not happened.
    """
    api_scope.require_tenant(
        identity, payload.tenant_id, route="POST /api/workflows", request=request
    )
    api_scope.require_client(identity, payload.client_id)
    workflow = service.submit(payload)
    body = service.repo.to_response(workflow)
    if workflow.state == "awaiting_approval":
        response.status_code = status.HTTP_409_CONFLICT
    return body


@router.get("", response_model=List[WorkflowResponse])
def list_recent(
    request: Request,
    limit: int = 50,
    service: WorkflowService = Depends(_service),
    identity: Identity = Depends(current_identity),
) -> List[Dict[str, Any]]:
    workflows = service.repo.list_recent(limit=limit)
    if api_scope.is_global(identity):
        api_scope.audit_global_access(
            identity,
            target_tenant=api_scope.GLOBAL_TARGET,
            target_client=None,
            route="GET /api/workflows",
            request=request,
        )
    else:
        workflows = [w for w in workflows if w.tenant_id == identity.tenant_id]
    return [service.repo.to_response(w) for w in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get(
    workflow_id: str,
    request: Request,
    service: WorkflowService = Depends(_service),
    identity: Identity = Depends(current_identity),
) -> Dict[str, Any]:
    workflow = _scoped_workflow(
        service, workflow_id, identity, "GET /api/workflows/{workflow_id}", request
    )
    return service.repo.to_response(workflow)


@router.get("/{workflow_id}/events")
def events(
    workflow_id: str,
    request: Request,
    service: WorkflowService = Depends(_service),
    identity: Identity = Depends(current_identity),
) -> List[Dict[str, Any]]:
    """The run timeline. This is what makes a decision replayable."""
    _scoped_workflow(
        service, workflow_id, identity, "GET /api/workflows/{workflow_id}/events", request
    )
    return service.repo.events(workflow_id)


@router.post("/{workflow_id}/execute", response_model=WorkflowResponse)
def execute(
    workflow_id: str,
    response: Response,
    request: Request,
    service: WorkflowService = Depends(_service),
    identity: Identity = Depends(current_identity),
) -> Dict[str, Any]:
    _scoped_workflow(
        service, workflow_id, identity, "POST /api/workflows/{workflow_id}/execute", request
    )
    try:
        workflow = service.execute(workflow_id)
    except GateAwaitingApproval as exc:
        response.status_code = exc.http_status
        return exc.payload or {}
    return service.repo.to_response(workflow)


@router.get("/{workflow_id}/result")
def result(
    workflow_id: str,
    request: Request,
    service: WorkflowService = Depends(_service),
    identity: Identity = Depends(current_identity),
) -> Dict[str, Any]:
    workflow = _scoped_workflow(
        service, workflow_id, identity, "GET /api/workflows/{workflow_id}/result", request
    )
    return service.result(workflow)
