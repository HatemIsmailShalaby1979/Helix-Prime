"""Controlled design-partner pilot runtime (Prompt 10).

Orchestrates the VERIFIED building blocks (connector layer, customer-success
wedge, governed memory, command center) into a controlled, read-only-first pilot.
It does NOT activate live connectors, cloud services, or external writes; it never
auto-improves. Every recommendation carries evidence; every committal action has
an owner + approval state; every outcome is recorded in governed memory.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_COCKPIT = str(Path(_ROOT) / "cockpit")
if _COCKPIT not in sys.path:
    sys.path.insert(0, _COCKPIT)

from connectors.contracts import ConnectorContext, CustomerSignal, SourceRef  # noqa: E402
from connectors.registry import ConnectorRegistry, KNOWN_PROVIDERS  # noqa: E402
from customer_success.wedge import diagnose, AccountContextBundle  # noqa: E402
from command_center_integration import assemble_command_center  # noqa: E402
from memory.governed_memory import GovernedMemory  # noqa: E402

from .approval import (  # noqa: E402
    create_recommendation, create_approval_draft, transition_approval,
    evaluate_approval_decision,
)
from .config import PilotConfig  # noqa: E402
from .consent import ConsentRecord, validate_consent  # noqa: E402
from .exceptions import PilotError  # noqa: E402
from .metrics import compute_pilot_metrics  # noqa: E402
from .phases import (  # noqa: E402
    READ_ONLY, SUPERVISED, CLOSED, ReadOnlyPeriod, ConnectorPermissions,
)
from .scope import (  # noqa: E402
    PilotScope, default_scope, HISTORICAL_CONSENTED, SIMULATED_REALISTIC, LIVE_CUSTOMER,
)

DEFAULT_AS_OF = "2026-08-29T12:00:00Z"


def _effective_data_mode(requested: str):
    if requested == "live_external":
        return "simulated_realistic", True
    return requested, False


def _synthetic_signals(ctx, account, tickets, as_of):
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


def _data_mode_to_nature(mode: str) -> str:
    return {"historical_consented": "historical_event",
            "simulated_realistic": "simulated_event"}.get(mode, "simulated_event")


class PilotRuntime:
    def __init__(self, config: PilotConfig, memory: GovernedMemory, scope: PilotScope = None,
                 consent: ConsentRecord = None, *, phase: str = SUPERVISED,
                 read_only_period: Optional[ReadOnlyPeriod] = None,
                 connector_permissions: Optional[ConnectorPermissions] = None) -> None:
        config.validate()
        self.config = config
        self.mem = memory
        self.scope = scope or default_scope()
        self.consent = consent
        self.tenant_ids: list = []
        self.client_ids: list = []
        self.diagnoses: list = []
        self.baseline_metrics: dict = {}
        self.phase = phase
        self.read_only_period = read_only_period
        self.connector_permissions = connector_permissions or ConnectorPermissions()
        self.connector_permissions.validate()

    # ----------------------------------------------------------- consent
    def validate_consent(self, consent: ConsentRecord, as_of: str) -> bool:
        validate_consent(consent, as_of, self.config.permitted_data_modes)
        self.consent = consent
        self.mem.add(
            kind="workflow_history", nature="verified_outcome",
            tenant_id=consent.tenant_id, client_id=consent.client_id,
            actor="pilot", role_id="customer_success_gm", source="pilot_consent",
            classification="client_confidential", timestamp=as_of,
            correlation_id=consent.consent_id, confidence=1.0,
            evidence_refs=[consent.consent_id], data_mode=HISTORICAL_CONSENTED,
            provenance={"correlation_id": consent.consent_id, "data_mode": HISTORICAL_CONSENTED,
                        "basis": "consent_validation", "sources": [consent.consent_id]},
            body={"action": "consent_validated", "consent_id": consent.consent_id},
        )
        return True

    # ----------------------------------------------------------- connectors
    def _build_connectors(self, ctx: ConnectorContext):
        reg = ConnectorRegistry(mode="fake")
        return {p: reg.get_connector(p, ctx) for p in KNOWN_PROVIDERS}

    def _build_bundle(self, connectors, ctx, as_of):
        failures = []
        account = None
        tickets = ()
        enrichment = None
        try:
            accounts = connectors["salesforce"].list_accounts(ctx)
            account = accounts[0] if accounts else None
        except Exception as exc:  # connector read failure -> degrade, never crash
            failures.append(("salesforce", str(exc)))
        if account is not None:
            try:
                tickets = connectors["zendesk"].list_tickets(ctx, account.account_id)
            except Exception as exc:
                failures.append(("zendesk", str(exc)))
            try:
                enrichment = connectors["clay"].enrich_account(ctx, account)
            except Exception as exc:
                failures.append(("clay", str(exc)))
        signals = _synthetic_signals(ctx, account, tickets, as_of)
        bundle = AccountContextBundle(
            context=ctx, account=account, tickets=tickets, enrichment=enrichment,
            signals=signals, data_mode=ctx.data_mode, as_of=as_of,
        )
        return bundle, failures

    # ----------------------------------------------------------- per-account
    def diagnose_account(self, tenant_id, client_id, as_of, operator_actor, operator_role,
                         correlation_id, connectors=None):
        effective, live_warning = _effective_data_mode("simulated_realistic")
        ctx = ConnectorContext(tenant_id, "org-1", client_id, actor=operator_actor,
                               correlation_id=correlation_id, data_mode=effective)
        if connectors is None:
            connectors = self._build_connectors(ctx)
        bundle, failures = self._build_bundle(connectors, ctx, as_of)
        diagnosis = diagnose(bundle)
        view = assemble_command_center(
            tenant_id, client_id, operator_actor, operator_role, effective, correlation_id,
            as_of, connectors=connectors, bundle=bundle, memory=self.mem,
        )
        for prov, err in failures:
            self.mem.add(
                kind="workflow_history", nature="historical_event",
                tenant_id=tenant_id, client_id=client_id, actor="pilot",
                role_id="customer_success_gm", source="pilot_connector",
                classification="client_confidential", timestamp=as_of,
                correlation_id=correlation_id, confidence=1.0, evidence_refs=[],
                data_mode=effective,
                provenance={"correlation_id": correlation_id, "data_mode": effective,
                            "basis": "connector_failure", "sources": []},
                body={"action": "connector_failure", "provider": prov, "error": err},
            )
        return diagnosis, view, bundle, failures

    def _record_diagnosis_and_recommendations(self, tenant_id, client_id, as_of, operator_actor,
                                              operator_role, correlation_id, diagnosis, data_mode):
        ev = [e.ref for e in diagnosis.evidence]
        diag_rec = self.mem.add(
            kind="customer_context", nature=_data_mode_to_nature(data_mode),
            tenant_id=tenant_id, client_id=client_id, actor="pilot",
            role_id="customer_success_gm", source="pilot_diagnosis",
            classification="client_confidential", timestamp=as_of,
            correlation_id=correlation_id, confidence=diagnosis.confidence,
            evidence_refs=ev, data_mode=data_mode,
            provenance={"correlation_id": correlation_id, "data_mode": data_mode,
                        "basis": "diagnosis", "sources": ev},
            body={"health_state": diagnosis.health_state,
                  "open_risk_count": len(diagnosis.risk_factors),
                  "recommended_actions": list(diagnosis.recommended_actions)},
        )
        for action in diagnosis.recommended_actions:
            is_esc = "escalat" in action.lower()
            correct = (diagnosis.health_state in ("at_risk", "critical")) if is_esc else True
            rec = create_recommendation(
                self.mem, tenant_id=tenant_id, client_id=client_id, actor=operator_actor,
                role_id=operator_role, correlation_id=correlation_id, timestamp=as_of,
                action=action, evidence=ev, diagnosis_ref=diag_rec.record_id,
                correct=correct, data_mode=data_mode,
            )
            create_approval_draft(
                self.mem, tenant_id=tenant_id, client_id=client_id, owner=operator_actor,
                role_id=operator_role, correlation_id=correlation_id, timestamp=as_of,
                action=action, recommendation_id=rec.record_id, evidence=[rec.record_id],
                data_mode=data_mode,
            )

    # ----------------------------------------------------------- dry run
    def dry_run(self, tenant_client_pairs, as_of=DEFAULT_AS_OF, operator_actor="pilot-operator",
                operator_role="customer_success_gm", correlation_id="pilot-dryrun",
                consent: ConsentRecord = None):
        if consent is not None:
            self.validate_consent(consent, as_of)
        for tenant_id, client_id in tenant_client_pairs:
            if tenant_id not in self.tenant_ids:
                self.tenant_ids.append(tenant_id)
            if client_id not in self.client_ids:
                self.client_ids.append(client_id)
            diagnosis, _view, _bundle, _failures = self.diagnose_account(
                tenant_id, client_id, as_of, operator_actor, operator_role, correlation_id)
            self.diagnoses.append((tenant_id, client_id, diagnosis))
            self._record_diagnosis_and_recommendations(
                tenant_id, client_id, as_of, operator_actor, operator_role, correlation_id,
                diagnosis, SIMULATED_REALISTIC)
        # Baseline measurement (pre-action; dry-run executes no committal writes).
        self.baseline_metrics = compute_pilot_metrics(self.mem, self.tenant_ids, {})
        self.mem.add(
            kind="outcome", nature="historical_event", tenant_id="*pilot*", client_id="*pilot*",
            actor="pilot", role_id="customer_success_gm", source="pilot_baseline",
            classification="internal", timestamp=as_of, correlation_id=correlation_id,
            confidence=1.0, evidence_refs=[], data_mode="simulated_realistic",
            provenance={"correlation_id": correlation_id, "data_mode": "simulated_realistic",
                        "basis": "baseline", "sources": []},
            body={"phase": "baseline", "metrics": self.baseline_metrics},
        )
        return self.summary()

    def summary(self) -> dict:
        return {
            "tenants": self.tenant_ids,
            "clients": self.client_ids,
            "diagnoses": len(self.diagnoses),
            "baseline_metrics": self.baseline_metrics,
            "audit_status": self.mem.audit_status(),
        }

    # ----------------------------------------------------------- phase / permissions
    def enter_read_only_period(self, starts_at: str, ends_at: str) -> ReadOnlyPeriod:
        self.read_only_period = ReadOnlyPeriod(starts_at, ends_at)
        self.phase = READ_ONLY
        return self.read_only_period

    def exit_read_only_period(self, as_of: str, actor: str, role: str,
                             correlation_id: str = "pilot-exit") -> str:
        if self.read_only_period is None:
            raise PilotError("no read-only period configured")
        # Record the early exit by shortening the planned window to `as_of`.
        self.read_only_period = ReadOnlyPeriod(self.read_only_period.starts_at, as_of)
        self.mem.add(
            kind="workflow_history", nature="verified_outcome", tenant_id="*pilot*",
            client_id="*pilot*", actor=actor, role_id=role, source="pilot_phase",
            classification="internal", timestamp=as_of, correlation_id=correlation_id,
            confidence=1.0, evidence_refs=[], data_mode="simulated_realistic",
            provenance={"correlation_id": correlation_id, "data_mode": "simulated_realistic",
                        "basis": "phase_exit", "sources": []},
            body={"action": "read_only_exited", "ends_at": as_of},
        )
        self.phase = SUPERVISED
        return self.phase

    def prepare_first_real_pilot(self, starts_at: str, ends_at: str, consent: ConsentRecord, as_of: str):
        """Configure the FIRST real pilot: validated consent, minimum data, no live
        data, read-only connector permissions, and a mandatory read-only period."""
        self.validate_consent(consent, as_of)
        if not self.config.minimum_data:
            raise PilotError("first real pilot requires the minimum-data policy")
        if self.config.live_activated:
            raise PilotError("first real pilot must not activate live customer data")
        self.connector_permissions.validate()
        self.enter_read_only_period(starts_at, ends_at)
        return self

    # ----------------------------------------------------------- approvals
    def _latest_approval(self, approval_id):
        return self.mem._by_id[approval_id]

    def approve_action(self, approval_id, approver_actor, approver_role, requester_actor,
                       requester_role, as_of=DEFAULT_AS_OF, correlation_id="pilot-approve"):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        if self.phase == READ_ONLY:
            raise PilotError("read-only period active: committal approvals are not permitted yet")
        ok, reason = evaluate_approval_decision(
            prev, "approved", approver_actor, approver_role, requester_actor, requester_role)
        if not ok:
            raise PilotError(reason)
        return transition_approval(
            self.mem, prev, "approved", approver_actor, approver_role, correlation_id, as_of,
            reason=f"approved by {approver_actor}")

    def deny_action(self, approval_id, reviewer, reason, as_of=DEFAULT_AS_OF, correlation_id="pilot-deny"):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        return transition_approval(
            self.mem, prev, "denied", reviewer, prev.role_id, correlation_id, as_of,
            reason=f"denied by {reviewer}: {reason}")

    def rollback_action(self, approval_id, actor, role, reason, as_of=DEFAULT_AS_OF, correlation_id="pilot-rollback"):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        new = transition_approval(
            self.mem, prev, "rolled_back", actor, role, correlation_id, as_of, reason=reason)
        self.mem.add(
            kind="workflow_history", nature="verified_outcome",
            tenant_id=prev.tenant_id, client_id=prev.client_id, actor=actor, role_id=role,
            source="pilot_incident", classification="client_confidential", timestamp=as_of,
            correlation_id=correlation_id, confidence=1.0, evidence_refs=[prev.record_id],
            data_mode=prev.data_mode,
            provenance={"correlation_id": correlation_id, "data_mode": prev.data_mode,
                        "basis": "rollback_incident", "sources": [prev.record_id]},
            body={"action": "rollback", "target": approval_id, "reason": reason},
        )
        return new

    # ----------------------------------------------------------- controls
    def tenant_isolation_ok(self, tenant_a: str, tenant_b: str) -> bool:
        a = self.mem.retrieve(tenant_id=tenant_a, include_deleted=True)
        b = self.mem.retrieve(tenant_id=tenant_b, include_deleted=True)
        return all(r.tenant_id == tenant_a for r in a) and all(r.tenant_id == tenant_b for r in b)

    def apply_retention(self, as_of: str) -> int:
        return self.mem.apply_retention(as_of)

    def final_status(self) -> dict:
        return {
            "pilot_package_ready": True,
            "real_design_partner_approval_pending": True,
            "production_readiness": "NOT_ESTABLISHED",
        }
