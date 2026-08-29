"""Governed Codex Command Center integration (Prompt 6).

Pure, deterministic assembly of the unified command-center view from the VERIFIED
building blocks:
* connector layer (Prompt 4) — status / scope / provenance;
* customer-success wedge (Prompt 5) — diagnosis / approval preview / outcome memory.

This module contains NO Streamlit code so it is fully testable. The Streamlit
shell (`cockpit/codex_command_center.py::render`) calls :func:`assemble_command_center`
and draws the resulting :class:`CommandCenterView`. The cockpit remains READ-ONLY
over source systems: it only previews actions and records outcomes in memory; it
never executes an external write without explicit, cross-role approval.

Every displayed item is wrapped with a :class:`GovernanceTag` carrying tenant_id,
client_id, role, classification, correlation_id, and data mode.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from connectors.contracts import ConnectorContext, CustomerSignal, SourceRef
from customer_success.wedge import (
    AccountContextBundle,
    ApprovalPreview,
    AccountHealthDiagnosis,
    build_approval_preview,
    diagnose,
)
from memory.governed_memory import GovernedMemory

CLASSIFICATION = "client_confidential"
DEFAULT_AS_OF = "2026-08-29T12:00:00Z"


@dataclass(frozen=True)
class GovernanceTag:
    tenant_id: str
    client_id: str
    actor: str
    role_id: str
    classification: str
    correlation_id: str
    requested_data_mode: str
    effective_data_mode: str
    live_warning: bool


@dataclass(frozen=True)
class ConnectorStatusView:
    provider: str
    connector_id: str
    status: str
    health: Mapping[str, Any]
    governance: GovernanceTag


@dataclass(frozen=True)
class EvidenceTimelineEntry:
    provider: str
    record_id: str
    observed_at: str
    data_mode: str
    detail: str
    ref: str
    governance: GovernanceTag


@dataclass(frozen=True)
class OutcomeTimelineEntry:
    outcome_id: str
    decision: str
    actor: str
    role_id: str
    correlation_id: str
    rationale: str
    recorded_at: str
    diagnosis_ref: str
    nature: str
    governance: GovernanceTag


@dataclass(frozen=True)
class MemoryTimelineEntry:
    record_id: str
    kind: str
    nature: str
    classification: str
    actor: str
    role_id: str
    source: str
    correlation_id: str
    confidence: float
    data_mode: str
    timestamp: str
    summary: str
    governance: GovernanceTag


@dataclass(frozen=True)
class ApprovalDecision:
    decision: str  # allowed | denied | not_required
    reason: str


@dataclass(frozen=True)
class CommandCenterView:
    meta: GovernanceTag
    classification: str
    connector_status: tuple[ConnectorStatusView, ...]
    diagnosis: AccountHealthDiagnosis
    approval_preview: ApprovalPreview
    evidence_timeline: tuple[EvidenceTimelineEntry, ...]
    outcome_timeline: tuple[OutcomeTimelineEntry, ...]
    memory_timeline: tuple[MemoryTimelineEntry, ...]
    audit_status: str
    state_flags: Mapping[str, Any]


# --------------------------------------------------------------------------- assembly

def _effective_data_mode(requested: str) -> tuple[str, bool]:
    """Never present simulated data as live. If 'live_external' is requested but
    only fake connectors exist, fall back to simulated and raise a warning."""
    if requested == "live_external":
        return "simulated_realistic", True
    return requested, False


def _synthetic_signals(ctx: ConnectorContext, account, tickets, as_of: str) -> tuple[CustomerSignal, ...]:
    if account is None:
        return ()
    open_high = sum(
        1 for t in tickets
        if t.status.lower() not in {"closed", "solved"} and t.priority.lower() == "high"
    )
    value = -0.15 * open_high if open_high else 0.05
    sig = CustomerSignal(
        "sig-op-1", account.account_id, "support_load", float(value), as_of,
        SourceRef("OperationalTelemetry", "sig-op-1", as_of, "ops-v1", ctx.data_mode),
        ctx.tenant_id, ctx.client_id,
    )
    return (sig,)


def _state_flags(connector_status, diagnosis: AccountHealthDiagnosis, live_warning: bool) -> dict[str, Any]:
    unavailable = any(c.status in ("disconnected", "revoked") for c in connector_status)
    stale = any(r.factor == "stale_data" for r in diagnosis.risk_factors)
    contradictory = diagnosis.health_state == "contradictory"
    unknown = diagnosis.health_state == "unknown"
    alerts = []
    if unavailable:
        alerts.append("One or more connectors are unavailable; source reads are disabled.")
    if stale:
        alerts.append("Stale data detected; confidence reduced.")
    if contradictory:
        alerts.append("Contradictory source data; human review required before any action.")
    if unknown:
        alerts.append("Insufficient data for a confident diagnosis; deferred.")
    if live_warning:
        alerts.append("Live mode requested but not activated; showing simulated data only.")
    return {
        "unavailable": unavailable,
        "stale": stale,
        "contradictory": contradictory,
        "unknown": unknown,
        "live_warning": live_warning,
        "alerts": alerts,
    }


def assemble_command_center(
    tenant_id: str,
    client_id: str,
    actor: str,
    role_id: str,
    requested_data_mode: str,
    correlation_id: str,
    as_of: str = DEFAULT_AS_OF,
    *,
    client_name: str = "Demo Account",
    memory: Optional[GovernedMemory] = None,
    memory_path: Optional[str] = None,
    connectors: Optional[Mapping[str, Any]] = None,
    bundle: Optional[AccountContextBundle] = None,
) -> CommandCenterView:
    effective_data_mode, live_warning = _effective_data_mode(requested_data_mode)
    meta = GovernanceTag(
        tenant_id=tenant_id, client_id=client_id, actor=actor, role_id=role_id,
        classification=CLASSIFICATION, correlation_id=correlation_id,
        requested_data_mode=requested_data_mode, effective_data_mode=effective_data_mode,
        live_warning=live_warning,
    )
    ctx = ConnectorContext(
        tenant_id, "org-1", client_id, actor=actor,
        correlation_id=correlation_id, data_mode=effective_data_mode,
    )

    # --- connectors (Prompt 4) ---------------------------------------------
    if connectors is None:
        from connectors.registry import ConnectorRegistry, KNOWN_PROVIDERS

        reg = ConnectorRegistry(mode="fake")
        connectors = {p: reg.get_connector(p, ctx) for p in KNOWN_PROVIDERS}

    connector_status = tuple(
        ConnectorStatusView(
            c.provider, c.connector_id, c.status().value, dict(c.health_check()), meta,
        )
        for c in connectors.values()
    )

    # --- account context bundle (Prompt 5 inputs) --------------------------
    if bundle is None:
        accounts = connectors["salesforce"].list_accounts(ctx)
        account = accounts[0] if accounts else None
        tickets = connectors["zendesk"].list_tickets(ctx, account.account_id) if account else ()
        enrichment = connectors["clay"].enrich_account(ctx, account) if account else None
        signals = _synthetic_signals(ctx, account, tickets, as_of)
        bundle = AccountContextBundle(
            context=ctx, account=account, tickets=tickets,
            enrichment=enrichment, signals=signals,
            data_mode=effective_data_mode, as_of=as_of,
        )

    diagnosis = diagnose(bundle)
    preview = build_approval_preview(diagnosis)

    # --- governed organizational memory (scoped to this tenant) ------------
    mem = memory or GovernedMemory(path=memory_path)
    outcomes = mem.retrieve(
        tenant_id=tenant_id, client_id=client_id, kinds=["outcome"], include_deleted=False,
    )
    outcome_timeline = tuple(
        OutcomeTimelineEntry(
            o.record_id, o.body.get("decision", ""), o.actor, o.role_id, o.correlation_id,
            o.body.get("rationale", ""), o.timestamp, o.body.get("diagnosis_ref", ""),
            o.nature, meta,
        )
        for o in outcomes
    )
    mem_all = mem.retrieve(tenant_id=tenant_id, client_id=client_id, include_deleted=False)
    memory_timeline = tuple(
        MemoryTimelineEntry(
            m.record_id, m.kind, m.nature, m.classification, m.actor, m.role_id, m.source,
            m.correlation_id, m.confidence, m.data_mode, m.timestamp,
            json.dumps(m.body, default=str)[:200], meta,
        )
        for m in mem_all
    )

    # --- evidence + provenance timeline ------------------------------------
    evidence_timeline = tuple(
        EvidenceTimelineEntry(
            e.provider, e.record_id, e.observed_at, e.data_mode, e.detail, e.ref, meta,
        )
        for e in diagnosis.evidence
    )

    audit_status = mem.audit_status()
    state_flags = _state_flags(connector_status, diagnosis, live_warning)

    return CommandCenterView(
        meta=meta,
        classification=CLASSIFICATION,
        connector_status=connector_status,
        diagnosis=diagnosis,
        approval_preview=preview,
        evidence_timeline=evidence_timeline,
        outcome_timeline=outcome_timeline,
        memory_timeline=memory_timeline,
        audit_status=audit_status,
        state_flags=state_flags,
    )


# ------------------------------------------------------------------- approval gate

def evaluate_approval(
    view: CommandCenterView,
    approver_actor: str,
    approver_role_id: str,
    requver_actor: Optional[str] = None,
    requver_role: Optional[str] = None,
) -> ApprovalDecision:
    """Enforce separation-of-duties for the cockpit approval preview.

    * If no approval is required, return `not_required`.
    * Self-approval (approver == requester actor) is denied.
    * Same-role approval is denied.
    * Cross-role approval by the required role is allowed.
    """
    requester_actor = requver_actor or view.meta.actor
    requester_role = requver_role or view.meta.role_id
    if not view.approval_preview.required:
        return ApprovalDecision("not_required", "No approval required for this advisory action")
    if approver_actor == requester_actor:
        return ApprovalDecision("denied", "Self-approval denied (separation of duties)")
    if approver_role_id == requester_role:
        return ApprovalDecision("denied", "Same-role approval denied (separation of duties)")
    if approver_role_id != view.approval_preview.role:
        return ApprovalDecision(
            "denied",
            f"Approver role {approver_role_id!r} not authorized; required {view.approval_preview.role!r}",
        )
    return ApprovalDecision("allowed", "Cross-role approval satisfied")


# ------------------------------------------------------------------- reset demo

def reset_demo(memory: GovernedMemory) -> GovernedMemory:
    """Explicit, audited synthetic-demo reset. Source systems are never touched
    (the cockpit is read-only over them)."""
    memory.clear_for_demo(actor="local-operator", role_id="customer_success_gm", timestamp=DEFAULT_AS_OF)
    return memory
