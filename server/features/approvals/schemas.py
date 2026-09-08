"""Approval payloads."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ApprovalRequest(BaseModel):
    """
    A human decision on a frozen run.

    ``approver_role_id`` is required and checked against the requester's role
    by the control plane: segregation of duties is enforced below this layer,
    not here. This schema only guarantees the fields arrive typed.
    """

    approver_actor: str = Field(min_length=1)
    approver_role_id: str = Field(min_length=1)
    decision: str = Field(pattern="^(approved|denied)$")
    reason: str = Field(default="", max_length=2000)
    evidence_ref: Optional[str] = None
