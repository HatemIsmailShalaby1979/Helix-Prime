"""Request/response schemas for the workflow surface."""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SubmitWorkflowRequest(BaseModel):
    """
    A workflow submission.

    ``tenant_id`` and ``client_id`` are required, not optional: every downstream
    layer binds them into SQL, and a request that cannot be scoped cannot be
    stored safely.
    """

    tenant_id: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    requesting_actor: str = Field(min_length=1)
    owning_role_id: str = Field(min_length=1)
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    idempotency_key: Optional[str] = None
    correlation_id: Optional[str] = None
    timeout_seconds: Optional[int] = None


class WorkflowResponse(BaseModel):
    workflow_id: str
    task_id: Optional[str] = None
    state: str
    capability: str
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    correlation_id: str
    error: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    approval: Optional[Dict[str, Any]] = None
