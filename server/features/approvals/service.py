"""
Approval service.

The important property: **approval is not execution.** ``Engine.approve``
records the decision and moves the workflow out of ``awaiting_approval``; the
side effect only happens on a subsequent ``Engine.execute``. That separation is
why a denial can be proven to have prevented the action rather than merely
having been logged alongside it.
"""
from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List

from contracts.task import Approval
from control_plane.engine import Engine
from control_plane.workflow import Workflow, WorkflowState

from server.errors import NotFound
from server.features.approvals.schemas import ApprovalRequest
from server.features.workflows.repository import WorkflowRepository


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class ApprovalService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._repo = WorkflowRepository(engine)

    def pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [
            self._repo.to_response(w)
            for w in self._repo.list_recent(limit=limit)
            if w.state == WorkflowState.AWAITING_APPROVAL
        ]

    def decide(self, workflow_id: str, payload: ApprovalRequest) -> Workflow:
        workflow = self._repo.get(workflow_id)
        if workflow is None:
            raise NotFound(f"workflow {workflow_id!r} not found")
        if workflow.state != WorkflowState.AWAITING_APPROVAL:
            raise NotFound(
                f"workflow {workflow_id!r} is not awaiting approval (state {workflow.state!r})"
            )

        approval = Approval(
            approval_id=f"apr_{uuid.uuid4().hex[:20]}",
            correlation_id=workflow.correlation.correlation_id,
            subject_id=workflow.workflow_id,
            approver_actor=payload.approver_actor,
            approver_role_id=payload.approver_role_id,
            decision=payload.decision,
            reason=payload.reason or f"{payload.decision} via operator console",
            timestamp=_now(),
        )
        return self._engine.approve(workflow_id, approval)
