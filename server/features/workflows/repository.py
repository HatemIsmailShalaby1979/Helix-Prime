"""
Workflow repository — the only place that knows about the store.

Routers never touch ``Engine.store`` directly. Keeping this seam means the
storage engine can be replaced (or a real repository added per Phase 2) without
any handler changing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from control_plane.engine import Engine
from control_plane.workflow import Workflow


class WorkflowRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, workflow_id: str) -> Optional[Workflow]:
        return self._engine.store.get_workflow(workflow_id)

    def list_recent(self, limit: int = 50) -> List[Workflow]:
        return self._engine.store.list_workflows(limit=limit)

    def events(self, workflow_id: str) -> List[Dict[str, Any]]:
        events = self._engine.store.get_events(workflow_id)
        return [e.to_dict() if hasattr(e, "to_dict") else dict(e) for e in events]

    def to_response(self, workflow: Workflow) -> Dict[str, Any]:
        """Flatten a Workflow into the API shape, without inventing fields."""
        from server.features.workflows.schemas import WorkflowResponse

        payload: Dict[str, Any] = {
            "workflow_id": workflow.workflow_id,
            "task_id": workflow.task_id,
            "state": workflow.state,
            "capability": workflow.capability,
            "tenant_id": workflow.tenant_id,
            "client_id": workflow.client_id,
            "correlation_id": workflow.correlation.correlation_id,
        }
        if workflow.error is not None:
            payload["error"] = (
                workflow.error.to_dict()
                if hasattr(workflow.error, "to_dict")
                else dict(workflow.error)
            )
        return WorkflowResponse(**payload).model_dump()
