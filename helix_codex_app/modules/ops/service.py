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


def _chain_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Whether the rows shown link to each other, and where the linkage stops.

    A statement about *these* rows, not about the trail as a whole. The whole trail
    can fail to verify for a reason outside this run — a fork recorded months
    earlier — and reporting that here would blame this run for someone else's break.
    The screen says which of the two it is showing.
    """
    linked = True
    for previous, current in zip(rows, rows[1:], strict=False):
        if current.get("previous_hash") != previous.get("current_hash"):
            linked = False
            break
    return {
        "rows": len(rows),
        "linked": linked,
        "head_previous_hash": rows[0].get("previous_hash") if rows else None,
        "tail_hash": rows[-1].get("current_hash") if rows else None,
    }


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

    def wfm_demo(
        self,
        account: Account,
        *,
        arrival_rate: Any,
        average_handling_time: Any,
        service_level_target: Any,
        average_calls_per_period: Any = engine_bridge.WFM_DEMO_AVERAGE_CALLS_PER_PERIOD,
    ) -> dict[str, Any]:
        """Run the public WFM demo through the real governed path, end to end.

        Submit and execute, in that order, with nothing in between: the demo is
        a demonstration of the governed path, not a workflow that skips the
        gate. `requires_approval=False` is a parameter of the *demo*, not a
        weakened control — the core's bounded-autonomy rules still decide, and
        the workflow only reaches `executing` if they allow it. If they do not,
        `execute_workflow` reports the held state and the engine is never
        called, which is the honest answer for a demonstration.

        The payload is built by the bridge rather than assembled here, so the
        fields a caller may influence are exactly the four named arguments.
        """
        workflow = self.submit(
            account,
            capability=engine_bridge.WFM_DEMO_CAPABILITY,
            input_payload=engine_bridge.wfm_demo_input_payload(
                arrival_rate=arrival_rate,
                average_handling_time=average_handling_time,
                service_level_target=service_level_target,
                average_calls_per_period=average_calls_per_period,
            ),
            requires_approval=False,
        )
        return engine_bridge.execute_workflow(account, workflow.workflow_id)

    def list(self, account: Account, *, state: str | None = None, limit: int = 50) -> list[Any]:
        """Workflows in the account's tenant, newest first."""
        return engine_bridge.list_workflows(account, limit=limit, state=state)

    def detail(self, account: Account, workflow_id: str) -> Any:
        """One workflow, or NotFound. A foreign tenant's is NotFound too."""
        return engine_bridge.get_workflow(account, workflow_id)

    def audit_trail(self, account: Account, correlation_id: str) -> dict[str, Any]:
        """The governance trail already recorded for one correlation id.

        Strictly read-only, and strictly a reading of what the core wrote: no row is
        created, no decision is re-made, and nothing is recomputed. The gate decision
        comes from the audit chain's own `decision` field, the timestamps and actor
        handoff from the workflow's event stream, and the executed/succeeded state
        from the workflow record — three existing sources, none of them new.

        A correlation id this tenant does not own is reported as not found rather
        than as an empty trail, so "no such run" and "a run with nothing recorded"
        cannot be confused.
        """
        entries = engine_bridge.audit_entries_for_correlation(correlation_id)
        scoped = [row for row in entries if row.get("tenant_id") == account.tenant_id]
        workflow = None
        if scoped:
            workflow_id = next(
                (row.get("workflow_id") for row in scoped if row.get("workflow_id")), None
            )
            if workflow_id is not None:
                workflow = engine_bridge.get_workflow(account, workflow_id)
        return {
            "correlation_id": correlation_id,
            "tenant_id": account.tenant_id,
            "found": bool(scoped),
            "workflow": workflow_card(workflow) if workflow is not None else None,
            "execution": engine_bridge.recorded_execution(workflow) if workflow is not None else None,
            "events": engine_bridge.workflow_events(workflow.workflow_id) if workflow is not None else [],
            "audit": scoped,
            "chain": _chain_summary(scoped),
            "chain_verified": engine_bridge.audit_chain_verified(),
            "scan_limit": engine_bridge.AUDIT_CORRELATION_SCAN,
        }

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
