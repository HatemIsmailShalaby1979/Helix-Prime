"""Connector port protocol for the write path.

This module defines the `ConnectorPort` protocol that all connectors must
implement. The protocol separates reads from writes and enforces that
writes always go through a governance gate.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class WritePlan:
    """A planned write operation awaiting governance approval.

    Attributes:
        plan_id: Unique identifier for this write plan.
        diff: The proposed changes (key -> new_value).
        risk_tier: Risk classification (1-5, higher = more restrictive).
        requires_approval: Whether this write needs human approval.
        idempotency_key: Key for replay safety.
        compensating_op: Optional compensation action for rollback.
    """

    def __init__(
        self,
        plan_id: str,
        diff: Mapping[str, Any],
        risk_tier: int,
        requires_approval: bool,
        idempotency_key: str,
        compensating_op: str | None = None,
    ) -> None:
        self.plan_id = plan_id
        self.diff = dict(diff)
        self.risk_tier = risk_tier
        self.requires_approval = requires_approval
        self.idempotency_key = idempotency_key
        self.compensating_op = compensating_op


class WriteReceipt:
    """Receipt confirming a write was executed.

    Attributes:
        external_id: ID in the external system.
        written_at: ISO timestamp of write.
        source_of_truth: Which system is now authoritative.
        reversibility: Whether this write can be reversed.
    """

    def __init__(
        self,
        external_id: str,
        written_at: str,
        source_of_truth: str,
        reversibility: bool,
    ) -> None:
        self.external_id = external_id
        self.written_at = written_at
        self.source_of_truth = source_of_truth
        self.reversibility = reversibility


class ConnectorPort(Protocol):
    """Protocol that all connectors must implement."""

    connector_id: str
    provider: str

    def read(self, op: str, context: Mapping[str, Any]) -> Any:
        """Execute a read operation."""
        ...

    def plan_write(
        self,
        intent: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> WritePlan:
        """Plan a write operation. Returns a WritePlan awaiting approval."""
        ...

    def apply_write(
        self,
        plan_id: str,
        approval_ref: Any,
        context: Mapping[str, Any],
    ) -> WriteReceipt:
        """Apply a previously planned and approved write."""
        ...
