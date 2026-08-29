"""Customer-success wedge — first commercial workflow (Prompt 5).

Account context + support-ticket history + enrichment signals + operational/customer
signals  ->  account-health diagnosis  ->  risk explanation  ->  next-best-action
recommendation  ->  approval preview  ->  outcome recorded in memory.

Design constraints:
* Evidence-backed and DETERMINISTIC for the proving phase — the diagnosis is a pure
  function of its inputs plus an explicit `as_of` timestamp (no wall clock, no RNG).
* Read-only over source data; it never writes to a provider. Committal actions are only
  *previewed* and require an explicit, cross-role approval executed by the control plane.
* Both historical and simulated data are supported and labelled visibly via `data_mode`.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from connectors.contracts import (
    Account,
    ConnectorContext,
    CustomerSignal,
    EnrichmentResult,
    SourceRef,
    SupportTicket,
)
from customer_success.health import assess_account_health  # reuse the user's deterministic base score

SCHEMA_VERSION = "1.0"
STALE_THRESHOLD_DAYS = 30

# Actions that commit the business (money / contract / external write) require approval.
COMMITTAL_ACTION_HINTS = ("concession", "discount", "upgrade", "issue", "refund", "credits")


class HealthState(str, Enum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    UNKNOWN = "unknown"
    CONTRADICTORY = "contradictory"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RiskFactor:
    factor: str
    severity: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceItem:
    provider: str
    record_id: str
    observed_at: str
    data_mode: str
    detail: str
    source_version: str
    ref: str  # stable reference id used by RiskFactor.evidence_refs


@dataclass(frozen=True)
class DiagnosisProvenance:
    data_mode: str
    correlation_id: str
    computed_at: str
    sources: tuple[str, ...]
    version: str
    basis: str


@dataclass(frozen=True)
class ApprovalPreview:
    required: bool
    role: str
    reason: str
    policy: str
    capability: str


@dataclass(frozen=True)
class AccountHealthDiagnosis:
    account_id: str
    tenant_id: str
    client_id: str
    health_state: str
    score: float
    confidence: float
    risk_factors: tuple[RiskFactor, ...]
    evidence: tuple[EvidenceItem, ...]
    recommended_action: str
    recommended_actions: tuple[str, ...]
    responsible_role: str
    approval_requirement: bool
    expected_outcome: str
    data_mode: str
    provenance: DiagnosisProvenance

    def fingerprint(self) -> str:
        """Deterministic, comparable signature for the diagnosis (used to verify
        determinism and to reference an outcome)."""
        payload = {
            "account_id": self.account_id,
            "health_state": self.health_state,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "risks": [r.factor for r in self.risk_factors],
            "evidence": [e.ref for e in self.evidence],
            "recommended_action": self.recommended_action,
            "responsible_role": self.responsible_role,
            "approval_requirement": self.approval_requirement,
            "expected_outcome": self.expected_outcome,
            "data_mode": self.data_mode,
            "correlation_id": self.provenance.correlation_id,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class AccountContextBundle:
    context: ConnectorContext
    account: Optional[Account]
    tickets: Sequence[SupportTicket]
    enrichment: Optional[EnrichmentResult]
    signals: Sequence[CustomerSignal]
    data_mode: str
    as_of: str


@dataclass(frozen=True)
class OutcomeRecord:
    outcome_id: str
    account_id: str
    tenant_id: str
    client_id: str
    diagnosis_ref: str
    decision: str  # accepted | rejected | deferred
    actor: str
    role_id: str
    correlation_id: str
    rationale: str
    recorded_at: str


class OutcomeMemory:
    """Deterministic in-memory store of recommendation outcomes.

    Outcomes are the system's 'memory' of what was decided for an account. An
    optional audit trail can be supplied to also persist an immutable
    :class:`security.audit.AuditRecord` for governance.
    """

    def __init__(self, audit_db_path: Optional[str] = None) -> None:
        self._records: list[OutcomeRecord] = []
        self._audit_db_path = audit_db_path

    def record(self, outcome: OutcomeRecord) -> OutcomeRecord:
        self._records.append(outcome)
        if self._audit_db_path:
            from security.audit import AuditRecord, AuditTrail

            trail = AuditTrail(db_path=self._audit_db_path)
            trail.append(
                AuditRecord.new(
                    event_type="customer_success_outcome",
                    actor=outcome.actor,
                    actor_type="human",
                    decision=outcome.decision,
                    correlation_id=outcome.correlation_id,
                    tenant_id=outcome.tenant_id,
                    client_id=outcome.client_id,
                    role_id=outcome.role_id,
                    input_ref=outcome.account_id,
                    output_ref=outcome.diagnosis_ref,
                )
            )
        return outcome

    def for_account(self, account_id: str) -> tuple[OutcomeRecord, ...]:
        return tuple(r for r in self._records if r.account_id == account_id)

    def all(self) -> tuple[OutcomeRecord, ...]:
        return tuple(self._records)


# --------------------------------------------------------------------------- helpers

def _parse(ts: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _days_between(observed_at: str, as_of: str) -> int:
    return (_parse(as_of) - _parse(observed_at)).days


def _evt_ref(provider: str, record_id: str) -> str:
    return f"evt:{provider}:{record_id}"


def _severity_for_signal(value: float) -> str:
    if value <= -0.5:
        return RiskSeverity.HIGH.value
    if value <= -0.2:
        return RiskSeverity.MEDIUM.value
    return RiskSeverity.LOW.value


# --------------------------------------------------------------------------- diagnosis

def diagnose(bundle: AccountContextBundle) -> AccountHealthDiagnosis:
    ctx = bundle.context
    as_of = bundle.as_of
    sources: set[str] = set()
    evidence: list[EvidenceItem] = []
    risk_factors: list[RiskFactor] = []

    account = bundle.account
    tickets = list(bundle.tickets)
    enrichment = bundle.enrichment
    signals = list(bundle.signals)

    # ---- evidence collection + staleness detection -------------------------
    if account is not None:
        sources.add(account.source.provider)
        evidence.append(EvidenceItem(
            provider=account.source.provider, record_id=account.account_id,
            observed_at=account.source.observed_at, data_mode=bundle.data_mode,
            detail=f"account lifecycle_stage={account.lifecycle_stage}",
            source_version=account.source.input_version,
            ref=_evt_ref(account.source.provider, account.account_id),
        ))

    for t in tickets:
        sources.add(t.source.provider)
        stale = _days_between(t.source.observed_at, as_of) > STALE_THRESHOLD_DAYS
        evidence.append(EvidenceItem(
            provider=t.source.provider, record_id=t.ticket_id,
            observed_at=t.source.observed_at, data_mode=bundle.data_mode,
            detail=f"support_ticket status={t.status} priority={t.priority} sla_breached={t.sla_breached}",
            source_version=t.source.input_version, ref=_evt_ref(t.source.provider, t.ticket_id),
        ))
        if stale:
            risk_factors.append(RiskFactor("stale_data", RiskSeverity.MEDIUM.value,
                                            (_evt_ref(t.source.provider, t.ticket_id),)))

    if enrichment is not None:
        sources.add(enrichment.source.provider)
        stale = _days_between(enrichment.source.observed_at, as_of) > STALE_THRESHOLD_DAYS
        evidence.append(EvidenceItem(
            provider=enrichment.source.provider, record_id=enrichment.account_id,
            observed_at=enrichment.source.observed_at, data_mode=bundle.data_mode,
            detail=f"enrichment fields={json.dumps(enrichment.fields, sort_keys=True)}",
            source_version=enrichment.source.input_version,
            ref=_evt_ref(enrichment.source.provider, enrichment.account_id),
        ))
        if stale:
            risk_factors.append(RiskFactor("stale_data", RiskSeverity.MEDIUM.value,
                                            (_evt_ref(enrichment.source.provider, enrichment.account_id),)))

    for s in signals:
        sources.add(s.source.provider)
        stale = _days_between(s.source.observed_at, as_of) > STALE_THRESHOLD_DAYS
        eid = _evt_ref(s.source.provider, s.signal_id)
        evidence.append(EvidenceItem(
            provider=s.source.provider, record_id=s.signal_id,
            observed_at=s.source.observed_at, data_mode=bundle.data_mode,
            detail=f"signal {s.signal_type}={s.value}",
            source_version=s.source.input_version, ref=eid,
        ))
        if s.value < 0:
            risk_factors.append(RiskFactor(
                f"negative_signal:{s.signal_type}", _severity_for_signal(s.value), (eid,)))
        if stale:
            risk_factors.append(RiskFactor("stale_data", RiskSeverity.MEDIUM.value, (eid,)))

    # ---- conflict detection across sources --------------------------------
    attr_values: dict[str, set[tuple[str, str]]] = {}

    def _track(attr: str, provider: str, value: Any) -> None:
        if value in (None, ""):
            return
        attr_values.setdefault(attr, set()).add((provider, str(value)))

    if account is not None:
        _track("lifecycle_stage", account.source.provider, account.lifecycle_stage)
        for k, v in (account.attributes or {}).items():
            _track(k, account.source.provider, v)
    if enrichment is not None:
        for k in ("industry", "employee_band", "research_status"):
            _track(k, enrichment.source.provider, enrichment.fields.get(k))
    for s in signals:
        if s.signal_type in ("industry", "employee_band", "lifecycle_stage"):
            _track(s.signal_type, s.source.provider, s.value)

    conflicts = [a for a, vals in attr_values.items() if len({v for _, v in vals}) > 1]
    if conflicts:
        risk_factors.append(RiskFactor(
            "conflicting_source_data", RiskSeverity.CRITICAL.value,
            tuple(_evt_ref(p, account.account_id) for p in {p for a in conflicts for p, _ in attr_values[a]}),
        ))

    # ---- base score (reuse the user's deterministic assessment) -----------
    if account is None:
        health_state = HealthState.UNKNOWN
        score = 0.0
        confidence = 0.3
        base_risks: tuple[str, ...] = ()
        base_actions: tuple[str, ...] = ()
        risk_factors.append(RiskFactor("missing_account_context", RiskSeverity.MEDIUM.value, ()))
    else:
        base = assess_account_health(ctx, account, tickets, enrichment)
        score = base.score
        confidence = base.confidence
        base_risks = base.risks
        base_actions = base.recommended_actions
        # promote base string risks into structured factors (severity heuristic)
        for r in base_risks:
            sev = RiskSeverity.HIGH.value if r.startswith("sla_breach") else RiskSeverity.MEDIUM.value
            ev_refs = tuple(e.ref for e in evidence if r.split(":")[1] in e.record_id) if ":" in r else ()
            risk_factors.append(RiskFactor(r, sev, ev_refs))
        # operational/customer signals also move the score deterministically
        for s in signals:
            if s.value < 0:
                score -= min(30.0, abs(s.value) * 40.0)
            elif s.value > 0:
                score += min(10.0, s.value * 10.0)
        score = max(0.0, min(100.0, score))

    # insufficient data -> unknown
    has_data = bool(tickets) or bool(enrichment) or bool(signals)
    if account is not None and not has_data:
        health_state = HealthState.UNKNOWN
        risk_factors.append(RiskFactor("insufficient_data", RiskSeverity.MEDIUM.value, ()))
        confidence = min(confidence, 0.4)

    # conflicting sources dominate
    if conflicts:
        health_state = HealthState.CONTRADICTORY
        confidence = min(confidence, 0.2)
    elif account is not None and not has_data:
        pass  # already UNKNOWN
    elif account is None:
        pass  # already UNKNOWN
    else:
        health_state = HealthState.AT_RISK if score < 70 else HealthState.HEALTHY

    # ---- confidence adjustments (deterministic) ---------------------------
    stale_count = sum(1 for r in risk_factors if r.factor == "stale_data")
    if stale_count:
        confidence *= max(0.4, 1.0 - 0.15 * stale_count)
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    # ---- recommended action / role / approval / outcome -------------------
    if health_state == HealthState.CONTRADICTORY:
        recommended_action = "Resolve conflicting source data via human-in-the-loop review before any action"
        expected_outcome = "Pending source reconciliation; no automated action is taken"
        responsible_role = "customer_success_gm"
    elif health_state == HealthState.UNKNOWN:
        recommended_action = "Collect more account, support, and signal data before diagnosis"
        expected_outcome = "Deferred; diagnosis confidence too low to act"
        responsible_role = "customer_success_gm"
    elif health_state == HealthState.AT_RISK:
        recommended_action = base_actions[0] if base_actions else "Prioritize SLA recovery and assign an accountable owner"
        expected_outcome = "Risk mitigated if SLA/adoption actions are completed within the SLA window"
        responsible_role = "customer_success_gm"
    else:  # HEALTHY
        recommended_action = "Maintain cadence; continue monitoring"
        expected_outcome = "Account remains stable; no immediate action required"
        responsible_role = "customer_success_gm"

    recommended_actions = tuple(dict.fromkeys((recommended_action, *base_actions)))

    is_committal = any(h in recommended_action.lower() for h in COMMITTAL_ACTION_HINTS)
    approval_requirement = bool(conflicts) or is_committal or confidence < 0.4

    # ---- provenance -------------------------------------------------------
    basis = (
        f"score={round(score, 2)}; risks={len(risk_factors)}; "
        f"signals={len(signals)}; tickets={len(tickets)}; "
        f"conflicts={len(conflicts)}"
    )
    provenance = DiagnosisProvenance(
        data_mode=bundle.data_mode,
        correlation_id=ctx.correlation_id,
        computed_at=as_of,
        sources=tuple(sorted(sources)),
        version=SCHEMA_VERSION,
        basis=basis,
    )

    account_id = account.account_id if account is not None else "unknown"
    return AccountHealthDiagnosis(
        account_id=account_id,
        tenant_id=ctx.tenant_id,
        client_id=ctx.client_id,
        health_state=health_state.value,
        score=round(score, 2),
        confidence=confidence,
        risk_factors=tuple(dict.fromkeys(risk_factors)),
        evidence=tuple(evidence),
        recommended_action=recommended_action,
        recommended_actions=recommended_actions,
        responsible_role=responsible_role,
        approval_requirement=approval_requirement,
        expected_outcome=expected_outcome,
        data_mode=bundle.data_mode,
        provenance=provenance,
    )


# --------------------------------------------------------------------------- workflow glue

def build_approval_preview(diagnosis: AccountHealthDiagnosis) -> ApprovalPreview:
    is_committal = any(h in diagnosis.recommended_action.lower() for h in COMMITTAL_ACTION_HINTS)
    required = diagnosis.approval_requirement or is_committal
    if required:
        reason = (
            "Conflicting sources or low-confidence/committal action requires cross-role approval"
            if diagnosis.health_state == HealthState.CONTRADICTORY.value or diagnosis.confidence < 0.4 or is_committal
            else "Recommended action commits the business and requires cross-role approval"
        )
        policy = "cross_role_approval_required"
    else:
        reason = "Advisory action; no approval required for monitoring only"
        policy = "no_approval_required"
    return ApprovalPreview(
        required=required,
        role=diagnosis.responsible_role,
        reason=reason,
        policy=policy,
        capability="customer_success_action",
    )


def record_outcome(
    memory: OutcomeMemory,
    diagnosis: AccountHealthDiagnosis,
    decision: str,
    actor: str,
    role_id: str,
    correlation_id: Optional[str] = None,
    rationale: str = "",
    recorded_at: Optional[str] = None,
) -> OutcomeRecord:
    """Record a recommendation decision in memory. `decision` is one of
    accepted | rejected | deferred. Rejection does NOT mutate the diagnosis."""
    outcome_id = f"{diagnosis.account_id}:{len(memory._records) + 1}"
    record = OutcomeRecord(
        outcome_id=outcome_id,
        account_id=diagnosis.account_id,
        tenant_id=diagnosis.tenant_id,
        client_id=diagnosis.client_id,
        diagnosis_ref=diagnosis.fingerprint(),
        decision=decision,
        actor=actor,
        role_id=role_id,
        correlation_id=correlation_id or diagnosis.provenance.correlation_id,
        rationale=rationale,
        recorded_at=recorded_at or diagnosis.provenance.computed_at,
    )
    return memory.record(record)


def run_wedge(
    bundle: AccountContextBundle,
    memory: OutcomeMemory,
    actor: str = "codex",
    role_id: str = "customer_success_gm",
) -> tuple[AccountHealthDiagnosis, ApprovalPreview]:
    """Full proving-phase flow: diagnose -> approval preview. Recording an
    outcome is a separate, explicit step (see :func:`record_outcome`)."""
    diagnosis = diagnose(bundle)
    preview = build_approval_preview(diagnosis)
    return diagnosis, preview
