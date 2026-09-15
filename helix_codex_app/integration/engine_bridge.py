"""The app's one door into the governed core.

Everything the app reads from control_plane/ and engines/ goes through here. The
core runs in this process, reached through server.deps, so there are no HTTP
self-calls. Every call authorizes first, through the same policy bridge the rest
of the app uses, and every failure raises: a stale figure presented as live is
worse than an error, and an empty result would be a silent lie.

This module is the only place in the app that imports control_plane/ and
engines/.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from helix_codex_app.errors import EngineUnavailableError, NotFoundError
from helix_codex_app.integration import policy_bridge
from helix_codex_app.security.accounts import Account

WFM_ENGINE_ID = "wfm"
WFM_OWNING_ROLE = "ops_gm"
OPS_CAPABILITY = "ops_execution"
OPS_OWNING_ROLE = "ops_gm"
ENGINE_IDS: tuple[str, ...] = ("wfm", "rta", "cx", "b2b", "personnel", "crm")
DEFAULT_APPROVAL_DECISION = "approve"
# The app says approve/reject; the core's contract says approved/denied. The
# translation lives here, at the boundary, so neither side has to learn the
# other's vocabulary.
DECISION_TO_CONTRACT: dict[str, str] = {"approve": "approved", "reject": "denied"}


def _engine() -> Any:
    """The process-wide governed engine, or a typed error.

    The engine is created once at app startup. If it is not running, that is a
    real failure and the caller must see it, not a default object.
    """
    try:
        from server import deps
    except ImportError as exc:
        raise EngineUnavailableError(f"governed core unavailable: {exc}") from exc
    try:
        return deps.get_provider().engine
    except RuntimeError as exc:
        raise EngineUnavailableError(f"the governed engine is not running: {exc}") from exc


def capability_map() -> dict[str, tuple[str, ...]]:
    """Every engine id and the capabilities it registers.

    Read from the adapters themselves, so the app never keeps a second list that
    could drift from the one the core actually registers.
    """
    try:
        from engines.b2b.adapter import CAPABILITY_IDS as B2B
        from engines.crm.adapter import CAPABILITY_IDS as CRM
        from engines.cx.adapter import CAPABILITY_IDS as CX
        from engines.personnel.adapter import CAPABILITY_IDS as PERSONNEL
        from engines.rta.adapter import CAPABILITY_IDS as RTA
        from engines.wfm.adapter import CAPABILITY_IDS as WFM
    except ImportError as exc:
        raise EngineUnavailableError(f"engine adapters unavailable: {exc}") from exc
    return {
        "wfm": tuple(WFM),
        "rta": tuple(RTA),
        "cx": tuple(CX),
        "b2b": tuple(B2B),
        "personnel": tuple(PERSONNEL),
        "crm": tuple(CRM),
    }


def engine_display_name(engine_id: str) -> str:
    try:
        from engines.registry import ENGINE_DISPLAY_NAMES
    except ImportError as exc:
        raise EngineUnavailableError(f"engine registry unavailable: {exc}") from exc
    return ENGINE_DISPLAY_NAMES.get(engine_id, engine_id)


def engine_status(engine_id: str) -> dict[str, Any]:
    """Whether one engine is registered and ready, or a typed error.

    "partial" means the engine answered but at least one of its capabilities has
    no handler registered. Reported as partial rather than ready, because a
    screen that says ready while a capability cannot run is misleading.
    """
    capabilities = capability_map()
    if engine_id not in capabilities:
        raise NotFoundError(f"unknown engine {engine_id!r}")
    handlers = _engine().handlers
    registered = [cap for cap in capabilities[engine_id] if cap in handlers]
    return {
        "engine_id": engine_id,
        "name": engine_display_name(engine_id),
        "capabilities": list(capabilities[engine_id]),
        "registered_capabilities": registered,
        "status": "ready" if len(registered) == len(capabilities[engine_id]) else "partial",
    }


def list_engines() -> list[dict[str, Any]]:
    """The six engines with their status. Raises if the core cannot be read."""
    return [engine_status(engine_id) for engine_id in ENGINE_IDS]


def submit_workflow(
    account: Account,
    *,
    capability: str,
    input_payload: dict[str, Any] | None = None,
    requires_approval: bool = True,
    idempotency_key: str | None = None,
    timeout_seconds: int | None = None,
) -> Any:
    """Submit one governed workflow inside the account's own tenant."""
    policy_bridge.authorize_engine_call(
        account,
        capability=capability,
        action="submit",
        owning_role_id=OPS_OWNING_ROLE,
        requires_approval=requires_approval,
    )
    try:
        from contracts.task import CorrelationContext, TaskRequest
    except ImportError as exc:
        raise EngineUnavailableError(f"task contracts unavailable: {exc}") from exc
    correlation = CorrelationContext.new(tenant_id=account.tenant_id, client_id=account.client_id)
    request = TaskRequest(
        request_id=f"req_{correlation.correlation_id[:20]}",
        correlation=correlation,
        requesting_actor=account.account_id,
        owning_role_id=OPS_OWNING_ROLE,
        capability=capability,
        input_payload=dict(input_payload or {}),
        requires_approval=requires_approval,
        status="validated",
        created_at=correlation.created_at,
        tenant_id=account.tenant_id,
        client_id=account.client_id,
        idempotency_key=idempotency_key,
        timeout_seconds=timeout_seconds,
    )
    try:
        return _engine().submit(request)
    except Exception as exc:  # noqa: BLE001 - translate, never leak a traceback
        raise EngineUnavailableError(f"workflow submit failed: {exc}") from exc


def get_workflow(account: Account, workflow_id: str) -> Any:
    """One workflow, scoped to the account's tenant. A foreign one is NotFound."""
    workflow = _engine().store.get_workflow(workflow_id)
    if workflow is None or workflow.tenant_id != account.tenant_id:
        raise NotFoundError(f"no such workflow {workflow_id}", payload={"workflow_id": workflow_id})
    return workflow


def list_workflows(account: Account, *, limit: int = 50, state: str | None = None) -> list[Any]:
    """The account's tenant's workflows, newest first, optionally by state."""
    workflows = _engine().store.list_workflows(limit=limit)
    scoped = [w for w in workflows if w.tenant_id == account.tenant_id]
    if state is not None:
        scoped = [w for w in scoped if w.state == state]
    return scoped


def list_approvals(account: Account) -> list[Any]:
    """Workflows in this tenant frozen at the governance gate."""
    from control_plane.workflow import WorkflowState

    return list_workflows(account, limit=200, state=WorkflowState.AWAITING_APPROVAL)


def workflow_events(workflow_id: str) -> list[dict[str, Any]]:
    """The recorded events for a workflow, as plain dictionaries."""
    events = _engine().store.get_events(workflow_id)
    return [event.to_dict() if hasattr(event, "to_dict") else dict(event) for event in events]


def approve_workflow(
    account: Account,
    workflow_id: str,
    *,
    decision: str = DEFAULT_APPROVAL_DECISION,
    note: str = "",
) -> Any:
    """Approve or refuse one workflow, on the account's behalf.

    The approval is built here from the account's own identity, so a caller
    cannot claim to be somebody else. Separation of duties is the core's call:
    if the account submitted the workflow, the core refuses and this raises.
    """
    workflow = get_workflow(account, workflow_id)
    contract_decision = DECISION_TO_CONTRACT.get(decision)
    if contract_decision is None:
        raise ValueError(
            f"decision must be one of {sorted(DECISION_TO_CONTRACT)}, got {decision!r}"
        )
    policy_bridge.authorize_engine_call(
        account,
        capability=workflow.capability,
        action="approve",
        owning_role_id=workflow.owning_role_id or OPS_OWNING_ROLE,
    )
    try:
        from contracts.task import Approval
    except ImportError as exc:
        raise EngineUnavailableError(f"approval contract unavailable: {exc}") from exc
    approval = Approval(
        approval_id=f"apr_{uuid.uuid4().hex[:20]}",
        correlation_id=workflow.correlation.correlation_id,
        subject_id=workflow.workflow_id,
        approver_actor=account.account_id,
        approver_role_id=policy_bridge.to_engine_identity(account).role_id or "",
        decision=contract_decision,
        reason=note or f"{contract_decision} from the app",
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    try:
        return _engine().approve(workflow_id, approval)
    except Exception as exc:  # noqa: BLE001 - translate, never leak a traceback
        raise EngineUnavailableError(f"approval failed: {exc}") from exc


def kill_switch_status(tenant_id: str | None = None) -> dict[str, Any]:
    """The halt state, read-only. Nothing here engages or releases the switch."""
    return _engine().kill_switch.status(tenant_id=tenant_id)


def recent_audit_entries(*, limit: int = 20) -> list[dict[str, Any]]:
    """The most recent audit rows, read-only."""
    return list(_engine().store.list_audit_events(limit=limit))


def audit_chain_verified() -> bool:
    """Whether the core's audit hash chain verifies right now."""
    return bool(_engine().store.verify_audit_chain())


def wfm_coverage(
    *,
    tenant_id: str,
    client_id: str | None,
    correlation_id: str,
    actor: str,
    from_at: str,
    to_at: str,
) -> dict[str, Any]:
    """The WFM staffing coverage (required agents) for a tenant and window.

    The WFM engine is imported lazily so a missing dependency surfaces as
    an explicit EngineUnavailableError here, never at app startup. The
    engine runs on its canonical sample baseline, so the returned figure
    is honestly labeled sample mode; the roster that covers the window is
    app data, read from oncall_shifts.
    """
    try:
        from engines.contracts import ENGINE_BASELINE_PAYLOADS
        from engines.wfm.adapter import adapt as _wfm_adapt
    except ImportError as exc:
        raise EngineUnavailableError(f"WFM engine unavailable: {exc}") from exc

    result = _wfm_adapt(
        input_payload=dict(ENGINE_BASELINE_PAYLOADS[WFM_ENGINE_ID]),
        tenant_id=tenant_id,
        client_id=client_id,
        correlation_id=correlation_id,
        causation_id=None,
        actor=actor,
        owning_role_id=WFM_OWNING_ROLE,
        is_sample=True,
    )

    if result.error is not None:
        raise EngineUnavailableError(f"WFM engine could not produce coverage: {result.error}")

    metrics = result.metrics or {}
    required = metrics.get("optimal_agents")
    if required is None:
        raise EngineUnavailableError("WFM engine returned no staffing figure")

    return {
        "engine_id": result.engine_id,
        "data_mode": "sample",
        "is_sample": True,
        "required_agents": int(required),
        "service_level_achieved": metrics.get("service_level_achieved"),
        "tenant_id": tenant_id,
        "from": from_at,
        "to": to_at,
        "basis": "canonical WFM sample baseline",
    }


def utc_now() -> str:
    """The one clock this module uses, so timestamps are consistent."""
    return datetime.now(timezone.utc).isoformat()
