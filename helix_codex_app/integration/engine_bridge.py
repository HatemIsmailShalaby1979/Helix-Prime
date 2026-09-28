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

import hashlib
import json
import uuid
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from helix_codex_app.errors import EngineUnavailableError, NotFoundError
from helix_codex_app.integration import policy_bridge
from helix_codex_app.security.accounts import Account

WFM_ENGINE_ID = "wfm"
WFM_OWNING_ROLE = "ops_gm"
OPS_CAPABILITY = "ops_execution"
OPS_OWNING_ROLE = "ops_gm"
ENGINE_IDS: tuple[str, ...] = ("wfm", "rta", "cx", "b2b", "personnel", "crm")
AUDIT_SCAN_LIMIT = 500
# How many of the newest audit rows a correlation lookup scans. The trail has no
# index on correlation_id, so a lookup is a bounded scan of the recent tail rather
# than a query. A run older than this window reports "no rows" — see
# audit_entries_for_correlation.
AUDIT_CORRELATION_SCAN = 5000
DEFAULT_APPROVAL_DECISION = "approve"
# The app says approve/reject; the core's contract says approved/denied. The
# translation lives here, at the boundary, so neither side has to learn the
# other's vocabulary.
DECISION_TO_CONTRACT: dict[str, str] = {"approve": "approved", "reject": "denied"}

# --- The governed public WFM demo (P8.2) ---------------------------------
#
# The demo runs the REAL engine path, so the payload the app builds is declared
# once, here, and the service cannot widen it.
#
# `is_sample` is the control that matters. `engines/registry.py::_make_handler`
# reads it out of the input payload and hands it to the adapter as a parameter,
# and the adapter reports `data_mode="sample"` because of it. Nothing else in
# the payload can turn a sample run into a live one, which is why this is a
# server-owned field and never a request field.
WFM_DEMO_CAPABILITY = "wfm_forecast"
WFM_DEMO_IS_SAMPLE = True
WFM_DEMO_AVERAGE_CALLS_PER_PERIOD = 17.0
# Every field the WFM engine itself validates, as (low, high) with BOTH ends
# exclusive. These mirror `engines/wfm/adapter.py`'s own checks exactly, so the
# demo rejects a value at the edge that the engine would refuse anyway. `inf` is
# the engine's real absence of an upper bound, not a licence for a large one.
WFM_DEMO_NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "arrival_rate": (0.0, float("inf")),
    "average_handling_time": (0.0, float("inf")),
    "service_level_target": (0.0, 1.0),
    "average_calls_per_period": (0.0, float("inf")),
}


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


def authorize_read(account: Account) -> None:
    """Policy gate for read-only core surfaces.

    The cockpit service calls this before the control-plane panel reads the
    process-wide engines and audit trail. It keeps the third gate in the bridge,
    rather than relying only on the router and service checks.
    """
    policy_bridge.authorize_engine_call(
        account,
        capability=OPS_CAPABILITY,
        action="read",
        owning_role_id=OPS_OWNING_ROLE,
    )


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


def execute_workflow(account: Account, workflow_id: str) -> dict[str, Any]:
    """Run one already-submitted workflow, and report what actually happened.

    The third lifecycle gate and the first that reaches the engine handler:
    `submit_workflow` only validates and routes, so until here nothing has been
    computed. The workflow is loaded through `get_workflow` first, which is the
    tenant-ownership check — a foreign workflow raises `NotFoundError` before
    any authorization decision or engine call happens.

    The state is inspected *before* the engine is asked, because
    `Engine.execute` raises `ValueError` for every state except `executing`.
    That refusal is deliberate on the core's part, and it is why a workflow the
    governance gate held at `awaiting_approval` is reported as a governance
    outcome rather than as an engine failure: a held workflow is never forced
    through, and the reason travels back to the caller instead of being
    swallowed into a 503.
    """
    from control_plane.workflow import WorkflowState

    workflow = get_workflow(account, workflow_id)
    policy_bridge.authorize_engine_call(
        account,
        capability=workflow.capability,
        action="execute",
        owning_role_id=workflow.owning_role_id or OPS_OWNING_ROLE,
    )
    if workflow.state != WorkflowState.EXECUTING:
        return _execution_report(workflow, executed=False)
    try:
        executed = _engine().execute(workflow_id)
    except Exception as exc:  # noqa: BLE001 - translate, never leak a traceback
        raise EngineUnavailableError(f"workflow execution failed: {exc}") from exc
    return _execution_report(executed, executed=True)


def _metrics_digest(metrics: dict[str, Any]) -> str:
    """A stable fingerprint of one engine result, for the evidence block."""
    canonical = json.dumps(metrics, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _execution_report(workflow: Any, *, executed: bool) -> dict[str, Any]:
    """What one execution produced, and the evidence it left behind.

    Deliberately no computation evidence. The registered handler returns
    `EngineResult.metrics` and drops `computation_evidence`
    (`engines/registry.py::_make_handler`), so there is none to report: naming a
    field the engine never produced is how a sample run gets dressed up as a
    verified one. What is reported instead is what the engine really wrote — the
    workflow and correlation ids, the terminal state, and a digest of the stored
    metrics — all of which the audit trail and the event stream corroborate.

    `succeeded` is derived from the report's OWN evidence — it was executed, it
    recorded no error, and it wrote figures — rather than from a set of terminal
    states. `closed` is not a success state on its own: it is reachable from
    `succeeded`, `compensated`, `cancelled` and `dead_letter`
    (`control_plane/workflow.py`), and a successful run of this demo ends
    `closed` (`control_plane/engine.py`), so the ambiguous state is the COMMON
    case rather than an edge one. A state-membership test therefore reports a
    dead-lettered or cancelled run as successful, and reports a closed run that
    produced no output as successful too.

    It is deliberately NOT delegated to `Engine.to_task_result`, which owns the
    related C1 mapping. That was tried and measured: `TaskResult.__post_init__`
    refuses `"failed"` with a null error, so calling it on the non-terminal
    workflow this function also reports (the governance gate holding one) raises
    rather than answering — and it answers a different question anyway, which
    TaskResult status a terminal workflow carries in the task queue.

    The raw `state` is reported beside the boolean, so nothing is hidden behind
    it, and every other field in this report describes the same evidence the
    boolean summarises.
    """
    metrics = dict(workflow.output_payload or {})
    error = workflow.error.message if workflow.error is not None else None
    report = {
        "workflow_id": workflow.workflow_id,
        "capability": workflow.capability,
        "state": workflow.state,
        "executed": executed,
        "succeeded": bool(executed and error is None and metrics),
        "correlation_id": workflow.correlation.correlation_id,
        "tenant_id": workflow.tenant_id,
        "client_id": workflow.client_id,
        "data_mode": (workflow.input_payload or {}).get("data_mode"),
        "is_sample": bool((workflow.input_payload or {}).get("is_sample", False)),
        "metrics": metrics,
        "metrics_digest": _metrics_digest(metrics) if metrics else None,
        "retry_count": workflow.retry_count,
        "error": error,
    }
    if not executed:
        report["gated"] = True
        # `WorkflowState` is a class of plain string constants, not an Enum, so
        # `workflow.state` is a `str` and `.value` on it would raise.
        reason = f"workflow is {workflow.state!r}, not 'executing' - the engine was not called"
        report["gated_reason"] = reason
    return report


def recorded_execution(workflow: Any) -> dict[str, Any]:
    """What a workflow's own record says it produced, read-only.

    `executed` is read off the event stream — a `handler_*` event means the engine
    was actually called — and everything else comes from `_execution_report`, the
    same derivation the demo endpoint uses. Reusing that function rather than
    re-deriving `succeeded` here is deliberate: two implementations of one rule is
    exactly how the two drift apart, and `succeeded` is the field a reader is most
    likely to take at face value.
    """
    events = workflow_events(workflow.workflow_id)
    executed = any(str(event.get("event_type", "")).startswith("handler_") for event in events)
    return _execution_report(workflow, executed=executed)


def kill_switch_status(tenant_id: str | None = None) -> dict[str, Any]:
    """The halt state, read-only. Nothing here engages or releases the switch."""
    return _engine().kill_switch.status(tenant_id=tenant_id)


def _audit_trail() -> Any:
    """The core's tamper-evident audit trail — the ledger the engine writes to.

    The control-plane store keeps its own `audit_events` table, but the engine's
    ordinary path writes to `security/audit.py` instead. Reading the other one
    would show an empty panel and a trivially "verified" chain, which is worse
    than showing nothing, because it looks like an answer.
    """
    try:
        from security.audit import AuditTrail
    except ImportError as exc:
        raise EngineUnavailableError(f"audit trail unavailable: {exc}") from exc
    return AuditTrail(db_path=_engine().audit_db_path)


def _audit_rows_newest_first(limit: int) -> list[dict[str, Any]]:
    """The newest `limit` audit rows as stored, newest first.

    `AuditTrail.list_records` orders by `rowid ASC` and *then* applies the limit, so
    asking it for N rows returns the OLDEST N. Keeping "the tail" of that window
    therefore keeps a month-old tail rather than a recent one. Measured 2026-09-27 on
    `security/audit.db` (36,124 rows): `list_records(500)` returned rows from
    2026-08-28 while the newest row was 2026-09-27, so the cockpit's audit panel had
    been showing August. The newest rows are read through the trail's own connection
    instead, which also keeps every stored field rather than the subset
    `AuditRecord.to_dict()` reconstructs.
    """
    trail = _audit_trail()
    try:
        rows = trail.conn.execute(
            "SELECT data FROM audit ORDER BY rowid DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        trail.close()
    return [json.loads(row[0]) for row in rows]


def recent_audit_entries(*, limit: int = 20) -> list[dict[str, Any]]:
    """The most recent audit rows, read-only, oldest-first as the trail writes them."""
    return list(reversed(_audit_rows_newest_first(limit)))


def audit_entries_for_correlation(
    correlation_id: str, *, scan_limit: int = AUDIT_CORRELATION_SCAN
) -> list[dict[str, Any]]:
    """Every recorded audit row carrying this correlation id, oldest-first.

    Read-only. **Bounded, and honest about it:** the trail indexes nothing by
    correlation id, so this scans the newest `scan_limit` rows and filters. A run
    older than that window returns no rows rather than a wrong one, which is why the
    caller must treat an empty result as "not in the scanned window", not as "this run
    has no audit trail".
    """
    return list(
        reversed(
            [
                row
                for row in _audit_rows_newest_first(scan_limit)
                if row.get("correlation_id") == correlation_id
            ]
        )
    )


def audit_chain_verified() -> bool:
    """Whether the core's audit hash chain verifies right now."""
    trail = _audit_trail()
    try:
        ok, _detail = trail.verify_chain()
        return bool(ok)
    finally:
        trail.close()


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


def wfm_demo_input_payload(
    *,
    arrival_rate: Any,
    average_handling_time: Any,
    service_level_target: Any,
    average_calls_per_period: Any = WFM_DEMO_AVERAGE_CALLS_PER_PERIOD,
) -> dict[str, Any]:
    """Build the one payload the public WFM demo is allowed to run.

    The signature *is* the whitelist. There is no `**extra` and no caller dict,
    so a request cannot smuggle in a key: not `is_sample`, not `data_mode`, not
    `data_classification`, not `max_agents`, not an estimated cost or a
    confidence score. The returned dict is built here from the named arguments
    alone, which is a stronger guarantee than filtering a payload after the
    fact — a field that was never read cannot be forwarded.

    Two of those omissions are deliberate and worth stating, because they look
    like gaps:

    * `data_classification` is left out on purpose. Both the core and
      `engines/wfm/adapter.py` read it out of the input payload, so a client
      able to set it could relabel a demo run. Omitting it takes the internal
      default the engine already applies. `estimated_financial_cost` and
      `confidence_score` are omitted for the same reason — they are
      `TaskRequest` fields the bridge owns, and the demo runs at the bounded
      autonomy defaults.
    * `max_agents` is omitted because `engines/wfm/adapter.py` never reads it.
      Accepting it would imply the demo caps staffing by a number that has no
      effect on the result.

    The numeric ranges mirror the adapter's own checks, so an impossible value
    is refused at the edge with a readable message instead of becoming a
    `DEAD_LETTER` further down.
    """
    try:
        from contracts.vocabulary import CONNECTOR_SIMULATED_REALISTIC as DATA_MODE
    except ImportError as exc:  # pragma: no cover - contracts is a hard dependency
        raise EngineUnavailableError(f"data vocabulary unavailable: {exc}") from exc

    given = {
        "arrival_rate": arrival_rate,
        "average_handling_time": average_handling_time,
        "service_level_target": service_level_target,
        "average_calls_per_period": average_calls_per_period,
    }
    payload: dict[str, Any] = {}
    for field, (low, high) in WFM_DEMO_NUMERIC_RANGES.items():
        value = given[field]
        # `bool` is an `int` subclass, so `True` would sail through as 1.0.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be a number, got {value!r}")
        value = float(value)
        if not isfinite(value) or not low < value < high:
            raise ValueError(
                f"{field} must be greater than {low} and less than {high}, got {value!r}"
            )
        payload[field] = value
    payload["is_sample"] = WFM_DEMO_IS_SAMPLE
    payload["data_mode"] = DATA_MODE
    return payload
