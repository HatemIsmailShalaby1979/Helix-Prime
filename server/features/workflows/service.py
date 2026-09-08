"""
Workflow service — the application layer between HTTP and the control plane.

There is deliberately no business logic here. ``Engine.submit`` already owns
validation, capability routing, C3 policy, secrets scanning, classification,
audit and structured logging. Re-implementing any of it at the service layer
would create a second, weaker gate. The service translates and publishes, and
nothing more.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from contracts.task import CorrelationContext, TaskRequest
from control_plane.engine import Engine
from control_plane.workflow import Workflow, WorkflowState

from server.errors import GateAwaitingApproval, NotFound, UpstreamUnavailable
from server.features.workflows.repository import WorkflowRepository
from server.features.workflows.schemas import SubmitWorkflowRequest
from server.sse import encode, get_bus


class WorkflowService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._repo = WorkflowRepository(engine)

    @property
    def repo(self) -> WorkflowRepository:
        return self._repo

    def submit(self, request: SubmitWorkflowRequest) -> Workflow:
        correlation = CorrelationContext.new(
            tenant_id=request.tenant_id,
            client_id=request.client_id,
            correlation_id=request.correlation_id,
        )
        task_request = TaskRequest(
            request_id=f"req_{correlation.correlation_id[:20]}",
            correlation=correlation,
            requesting_actor=request.requesting_actor,
            owning_role_id=request.owning_role_id,
            capability=request.capability,
            input_payload=dict(request.input_payload),
            requires_approval=request.requires_approval,
            status="validated",
            created_at=correlation.created_at,
            tenant_id=request.tenant_id,
            client_id=request.client_id,
            idempotency_key=request.idempotency_key,
            timeout_seconds=request.timeout_seconds,
        )
        workflow = self._engine.submit(task_request)
        self._publish(workflow)
        return workflow

    def get(self, workflow_id: str) -> Workflow:
        workflow = self._repo.get(workflow_id)
        if workflow is None:
            raise NotFound(f"workflow {workflow_id!r} not found")
        return workflow

    def execute(self, workflow_id: str) -> Workflow:
        workflow = self.get(workflow_id)
        if workflow.state == WorkflowState.AWAITING_APPROVAL:
            raise GateAwaitingApproval(
                "workflow is frozen at the governance gate",
                payload=self._repo.to_response(workflow),
            )
        try:
            executed = self._engine.execute(workflow_id)
        except Exception as exc:  # noqa: BLE001 - translate, never leak a traceback
            raise UpstreamUnavailable(str(exc)) from exc
        self._publish(executed)
        return executed

    def result(self, workflow: Workflow) -> Dict[str, Any]:
        return self._engine.to_task_result(workflow).to_dict()

    def _publish(self, workflow: Workflow) -> None:
        """Push a state-change frame to anyone watching this correlation."""
        bus = get_bus()
        bus.publish_sync(
            workflow.correlation.correlation_id,
            "workflow_state",
            self._repo.to_response(workflow),
        )


def sse_frame(event: str, data: Dict[str, Any]) -> str:
    return encode(event, data)
