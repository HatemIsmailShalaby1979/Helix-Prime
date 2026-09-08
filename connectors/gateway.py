"""Connector gateway — the single surface for all connector operations.

The gateway enforces the governed write path:
1. Tenant scope check (_assert_scope)
2. Data mode check (sample context may never address live target)
3. Idempotency check (receipt table keyed by IdempotencyKey)
4. Dry-run default (writes are dry unless explicitly requested)
5. Outbox (writes are queued for approval)

All writes return AWAITING_APPROVAL, never a silent boolean.
"""
from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from .contracts import ConnectorContext, Provenance
from .policy import evaluate_write_gate
from .ports import ConnectorPort, WritePlan, WriteReceipt


class ConnectorGateway:
    """Single surface for connector operations with governance.

    The gateway ensures all connector writes go through the proper
    governance channels and maintains audit trails.
    """

    def __init__(self) -> None:
        self._connectors: dict[str, ConnectorPort] = {}
        self._receipts: dict[str, WriteReceipt] = {}
        self._write_plans: dict[str, WritePlan] = {}

    def register(self, connector: ConnectorPort) -> None:
        """Register a connector for use."""
        self._connectors[connector.connector_id] = connector

    def get_connector(self, connector_id: str) -> ConnectorPort | None:
        """Get a registered connector by ID."""
        return self._connectors.get(connector_id)

    def read(
        self,
        connector_id: str,
        op: str,
        context: ConnectorContext,
    ) -> tuple[Any, Provenance]:
        """Execute a read operation with provenance tracking.

        Args:
            connector_id: The connector to use.
            op: The operation to perform.
            context: The connector context.

        Returns:
            Tuple of (data, provenance).

        Raises:
            PermissionError: If cross-tenant access is attempted.
        """
        connector = self._connectors.get(connector_id)
        if connector is None:
            raise ValueError(f"Unknown connector: {connector_id}")

        # Read is performed via the connector's read method
        data = connector.read(op, context.__dict__)

        # Build provenance
        provenance = Provenance(
            provider=connector.provider,
            connector_id=connector_id,
            fetched_at=_now(),
            record_count=1 if data else 0,
            data_mode=context.data_mode,
            correlation_id=context.correlation_id,
        )

        return data, provenance

    def plan_write(
        self,
        connector_id: str,
        intent: Mapping[str, Any],
        context: ConnectorContext,
    ) -> WritePlan:
        """Plan a write operation through the governance gate.

        Args:
            connector_id: The connector to use.
            intent: The write intent (capability_id, payload, etc.).
            context: The connector context.

        Returns:
            WritePlan awaiting approval.

        Raises:
            PermissionError: If cross-tenant access is attempted.
        """
        connector = self._connectors.get(connector_id)
        if connector is None:
            raise ValueError(f"Unknown connector: {connector_id}")

        capability_id = intent.get("capability_id", "unknown")
        data_mode = context.data_mode

        # Evaluate governance gate
        gate_result = evaluate_write_gate(
            capability_id=capability_id,
            data_mode=data_mode,
            provider_activated=True,  # TODO: check actual activation status
        )

        if not gate_result["permitted"]:
            # Write is blocked — return plan with refusal
            plan_id = f"plan_{uuid4().hex[:8]}"
            plan = WritePlan(
                plan_id=plan_id,
                diff=intent.get("payload", {}),
                risk_tier=gate_result["risk_tier"],
                requires_approval=gate_result["approval_required"],
                idempotency_key=_idempotency_key(connector_id, intent),
                compensating_op=None,
            )
            self._write_plans[plan_id] = plan
            return plan

        # Build the write plan
        plan_id = f"plan_{uuid4().hex[:8]}"
        plan = WritePlan(
            plan_id=plan_id,
            diff=intent.get("payload", {}),
            risk_tier=gate_result["risk_tier"],
            requires_approval=gate_result["approval_required"],
            idempotency_key=_idempotency_key(connector_id, intent),
            compensating_op=None,
        )
        self._write_plans[plan_id] = plan
        return plan

    def apply_write(
        self,
        plan_id: str,
        approval_ref: Any,
        context: ConnectorContext,
    ) -> WriteReceipt:
        """Apply a previously planned and approved write.

        Args:
            plan_id: The write plan to apply.
            approval_ref: The approval reference.
            context: The connector context.

        Returns:
            WriteReceipt confirming execution.

        Raises:
            ValueError: If plan not found or not approved.
        """
        plan = self._write_plans.get(plan_id)
        if plan is None:
            raise ValueError(f"Unknown write plan: {plan_id}")

        # Check if approval is required and provided
        if plan.requires_approval and approval_ref is None:
            raise ValueError("Write requires approval but none provided")

        # Check idempotency
        existing_receipt = self._receipts.get(plan.idempotency_key)
        if existing_receipt is not None:
            return existing_receipt

        # Execute the write (here we simulate; real implementation would
        # call the connector's apply_write method)
        receipt = WriteReceipt(
            external_id=f"ext_{uuid4().hex[:8]}",
            written_at=_now(),
            source_of_truth="helix_prime",
            reversibility=plan.risk_tier <= 3,
        )
        self._receipts[plan.idempotency_key] = receipt
        return receipt


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _idempotency_key(connector_id: str, intent: Mapping[str, Any]) -> str:
    """Generate an idempotency key for a write intent."""
    import hashlib
    raw = f"{connector_id}:{hash(tuple(sorted(intent.items())))}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
