"""The operations section: governed workflow submission and approval.

A manager submits a request, the governance gate holds it, and an approver
decides. There is no business logic here on purpose: the core already owns
validation, capability routing, policy, secrets scanning, classification, audit
and logging, and re-implementing any of it would create a second, weaker gate.
The service translates and scopes, and nothing more.

Workflow state changes are not duplicated into the app's `nodes` table. The
core's audit trail is the authoritative record for a workflow, and writing a
second copy would create two truths that could drift apart. The correlation id
is what ties a screen row to that trail, which is why it is on every card.
"""
from __future__ import annotations

from typing import Any

from helix_codex_app.errors import InvalidStateError
from helix_codex_app.integration import engine_bridge
from helix_codex_app.security.accounts import Account

OPEN_STATES = ("proposed", "validated", "awaiting_approval", "approved", "executing")
DECISIONS = ("approve", "reject")


def workflow_card(workflow: Any) -> dict[str, Any]:
    """Flatten a workflow into the shape the card partial renders.

    Only fields the core actually has. Nothing is invented, and the correlation
    id is always present because it is the thread back to the audit trail.
    """
    approval = getattr(workflow, "approval", None)
    return {
        "workflow_id": workflow.workflow_id,
        "state": workflow.state,
        "capability": workflow.capability,
        "tenant_id": workflow.tenant_id,
        "client_id": workflow.client_id,
        "correlation_id": workflow.correlation.correlation_id,
        "created_at": workflow.created_at,
        "requesting_actor": workflow.requesting_actor,
        "approver_id": getattr(approval, "approver_actor", None),
        "approval_note": getattr(approval, "reason", None),
        "error": _error_text(workflow),
    }


def _error_text(workflow: Any) -> str | None:
    error = getattr(workflow, "error", None)
    if error is None:
        return None
    if hasattr(error, "to_dict"):
        payload = error.to_dict()
        return str(payload.get("message") or payload)
    return str(error)


class OpsService:
    """Submit, list, inspect, and decide governed workflows."""

    def submit(
        self,
        account: Account,
        *,
        capability: str,
        input_payload: dict[str, Any] | None = None,
        requires_approval: bool = True,
        idempotency_key: str | None = None,
    ) -> Any:
        """Submit one workflow. A blank capability is a caller bug, not a gate."""
        if not capability or not capability.strip():
            raise ValueError("a workflow needs a capability")
        return engine_bridge.submit_workflow(
            account,
            capability=capability.strip(),
            input_payload=input_payload,
            requires_approval=requires_approval,
            idempotency_key=idempotency_key,
        )

    def list(self, account: Account, *, state: str | None = None, limit: int = 50) -> list[Any]:
        """Workflows in the account's tenant, newest first."""
        return engine_bridge.list_workflows(account, limit=limit, state=state)

    def detail(self, account: Account, workflow_id: str) -> Any:
        """One workflow, or NotFound. A foreign tenant's is NotFound too."""
        return engine_bridge.get_workflow(account, workflow_id)

    def approvals(self, account: Account) -> list[Any]:
        """Everything in this tenant waiting on a decision."""
        return engine_bridge.list_approvals(account)

    def approve(
        self,
        account: Account,
        workflow_id: str,
        *,
        decision: str = "approve",
        reason: str = "",
    ) -> Any:
        """Decide one workflow. A refusal must carry a reason."""
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
        workflow = self.detail(account, workflow_id)
        if workflow.state != "awaiting_approval":
            raise InvalidStateError(
                f"{workflow_id}: not awaiting a decision (state is {workflow.state!r})",
                payload={"workflow_id": workflow_id, "state": workflow.state},
            )
        if decision == "reject" and not reason.strip():
            raise ValueError("a refusal needs a reason")
        return engine_bridge.approve_workflow(account, workflow_id, decision=decision, note=reason)

    def overview(self, account: Account) -> dict[str, Any]:
        """Engine status plus the counts the ops landing page shows."""
        engines = engine_bridge.list_engines()
        workflows = self.list(account, limit=200)
        return {
            "engines": engines,
            "counts": {
                "total": len(workflows),
                "awaiting_approval": sum(1 for w in workflows if w.state == "awaiting_approval"),
                "open": sum(1 for w in workflows if w.state in OPEN_STATES),
                "closed": sum(1 for w in workflows if w.state in ("closed", "cancelled")),
            },
            "recent": [workflow_card(w) for w in workflows[:10]],
            "audit_chain_verified": engine_bridge.audit_chain_verified(),
        }

    def engine_detail(self, account: Account, engine_id: str) -> dict[str, Any]:
        """One engine's status, plus the tenant's workflows on its capabilities."""
        status = engine_bridge.engine_status(engine_id)
        capabilities = set(status["capabilities"])
        workflows = [w for w in self.list(account, limit=200) if w.capability in capabilities]
        return {
            "engine": status,
            "workflows": [workflow_card(w) for w in workflows],
        }
