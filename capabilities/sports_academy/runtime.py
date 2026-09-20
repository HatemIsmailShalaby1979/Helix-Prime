"""Sports-academy capability-pack runtime (v1).

Orchestrates the VERIFIED governed core for one sports-academy location:
identity, tenant isolation, governance, connectors, workflows, approvals,
evidence, memory, metrics, and metacognitive proposals. It starts read-only
with synthetic data, never activates live connectors or external writes,
and never auto-improves. Mirrors RestaurantCapabilityPack (Prompt 11)
capability-for-capability.

Every record preserves: tenant/client identity, provenance, correlation ID,
data mode, approval state, outcome, and the audit trail.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from connectors.contracts import ConnectorContext  # noqa: E402
from contracts.vocabulary import CONNECTOR_SIMULATED_REALISTIC  # noqa: E402
from memory.governed_memory import GovernedMemory  # noqa: E402
from metacognition.improvement import MetacognitionEngine  # noqa: E402
from pilot.approval import (  # noqa: E402
    create_approval_draft,
    create_recommendation,
    evaluate_approval_decision,
    transition_approval,
)
from pilot.config import PilotConfig  # noqa: E402
from pilot.consent import ConsentRecord, validate_consent  # noqa: E402
from pilot.exceptions import PilotError  # noqa: E402
from pilot.phases import (  # noqa: E402
    READ_ONLY,
    SUPERVISED,
    ConnectorPermissions,
    ReadOnlyPeriod,
)
from security.identity import Identity  # noqa: E402

from .adapters.athlete_profile_adapter import (  # noqa: E402
    churn_risk_scores,
    enrollment_pipeline,
    record_churn_flags,
)
from .adapters.attendance_adapter import (  # noqa: E402
    daily_adherence_report,
    record_attendance_outcome,
)
from .adapters.facility_adapter import facility_overview  # noqa: E402
from .adapters.payment_adapter import (  # noqa: E402
    fee_status_overview,
    record_manual_payment,
)
from .contracts import build_academy_connectors  # noqa: E402
from .kpis import compute_academy_metrics, compute_all_coach_metrics  # noqa: E402
from .register import get_academy_metadata  # noqa: E402
from .roles import required_approver_role  # noqa: E402
from .workflows import (  # noqa: E402
    attendance_flow,
    enrollment_flow,
    renewal_flow,
)

DATA_MODE = CONNECTOR_SIMULATED_REALISTIC
DEFAULT_AS_OF = "2026-09-07T20:00:00Z"


class AcademyCapabilityPack:
    def __init__(
        self,
        memory: GovernedMemory,
        *,
        phase: str = SUPERVISED,
        read_only_period: Optional[ReadOnlyPeriod] = None,
        connector_permissions: Optional[ConnectorPermissions] = None,
        identity: Optional[Identity] = None,
        config: Optional[PilotConfig] = None,
    ) -> None:
        self.mem = memory
        self.phase = phase
        self.read_only_period = read_only_period
        self.connector_permissions = connector_permissions or ConnectorPermissions()
        self.connector_permissions.validate()
        self.config = config or PilotConfig.from_dict({})
        self.identity = identity or Identity(
            actor="academy-operator", actor_type="human", role_id="academy_admin"
        )
        self.tenant_ids: list = []
        self.client_ids: list = []
        self.diagnoses: list = []
        self.baseline_metrics: dict = {}
        self.consent: Optional[ConsentRecord] = None
        self._connectors: Optional[dict] = None

    # ----------------------------------------------------------- registration
    def register(self) -> dict:
        from .register import register_capability

        return register_capability("sports_academy_operations", get_academy_metadata())

    # ----------------------------------------------------------- consent
    def validate_consent(self, consent: ConsentRecord, as_of: str) -> bool:
        validate_consent(consent, as_of, self.config.permitted_data_modes)
        self.consent = consent
        self.mem.add(
            kind="workflow_history",
            nature="verified_outcome",
            tenant_id=consent.tenant_id,
            client_id=consent.client_id,
            actor="academy-pack",
            role_id="academy_admin",
            source="academy_consent",
            classification="client_confidential",
            timestamp=as_of,
            correlation_id=consent.consent_id,
            confidence=1.0,
            evidence_refs=[consent.consent_id],
            data_mode=DATA_MODE,
            provenance={
                "correlation_id": consent.consent_id,
                "data_mode": DATA_MODE,
                "basis": "consent_validation",
                "sources": [consent.consent_id],
            },
            body={"action": "consent_validated", "consent_id": consent.consent_id},
        )
        return True

    # ----------------------------------------------------------- read-only phase
    def enter_read_only_period(self, starts_at: str, ends_at: str) -> ReadOnlyPeriod:
        self.read_only_period = ReadOnlyPeriod(starts_at, ends_at)
        self.phase = READ_ONLY
        return self.read_only_period

    def exit_read_only_period(
        self, as_of: str, actor: str, role: str, correlation_id: str = "academy-exit"
    ) -> str:
        if self.read_only_period is None:
            raise PilotError("no read-only period configured")
        self.read_only_period = ReadOnlyPeriod(self.read_only_period.starts_at, as_of)
        self.mem.add(
            kind="workflow_history",
            nature="verified_outcome",
            tenant_id="*pilot*",
            client_id="*pilot*",
            actor=actor,
            role_id=role,
            source="academy_phase",
            classification="internal",
            timestamp=as_of,
            correlation_id=correlation_id,
            confidence=1.0,
            evidence_refs=[correlation_id],
            data_mode=DATA_MODE,
            provenance={
                "correlation_id": correlation_id,
                "data_mode": DATA_MODE,
                "basis": "phase_exit",
                "sources": [],
            },
            body={"action": "read_only_exited", "ends_at": as_of},
        )
        self.phase = SUPERVISED
        return self.phase

    def prepare_first_real_pilot(
        self, starts_at: str, ends_at: str, consent: ConsentRecord, as_of: str
    ):
        self.validate_consent(consent, as_of)
        if not self.config.minimum_data:
            raise PilotError("first real pilot requires the minimum-data policy")
        if self.config.live_activated:
            raise PilotError("first real pilot must not activate live customer data")
        self.connector_permissions.validate()
        self.enter_read_only_period(starts_at, ends_at)
        return self

    # ----------------------------------------------------------- connectors / diagnose
    def diagnose_account(
        self, tenant_id, client_id, as_of, operator_actor, operator_role, correlation_id, fixtures
    ):
        ctx = ConnectorContext(
            tenant_id,
            "org-1",
            client_id,
            actor=operator_actor,
            correlation_id=correlation_id,
            data_mode=DATA_MODE,
        )
        connectors = build_academy_connectors(ctx, fixtures)
        self._connectors = connectors
        conn = connectors["academy_ops"]

        attendance = daily_adherence_report(ctx, connectors, as_of)
        scores = churn_risk_scores(ctx, connectors)
        pipe = enrollment_pipeline(ctx, connectors)
        sessions = conn.list_sessions(ctx)
        checkins = conn.list_checkins(ctx)
        athletes = conn.list_athletes(ctx)
        fees = conn.list_fee_payments(ctx)
        programs = conn.list_programs(ctx)

        diags = [
            enrollment_flow(pipe),
            attendance_flow(sessions, checkins, as_of),
            renewal_flow(athletes, fees, as_of),
        ]
        return {
            "ctx": ctx,
            "connectors": connectors,
            "diags": diags,
            "attendance": attendance,
            "churn": scores,
            "pipeline": pipe,
            "kpis": compute_academy_metrics(
                athletes=athletes,
                sessions=sessions,
                checkins=checkins,
                facility_slots=conn.list_facility_slots(ctx),
                programs=programs,
            ),
            "coach_kpis": compute_all_coach_metrics(conn.list_coaches(ctx), sessions, checkins),
            "facility": facility_overview(ctx, connectors),
            "fees": fee_status_overview(ctx, connectors, athletes, programs),
        }

    def _record_diagnosis_and_recommendations(
        self, tenant_id, client_id, as_of, operator_actor, operator_role, correlation_id, bundle
    ):
        for d in bundle["diags"]:
            ev = list(d.evidence_refs)
            diag_rec = self.mem.add(
                kind="customer_context",
                nature="simulated_event",
                tenant_id=tenant_id,
                client_id=client_id,
                actor="academy-pack",
                role_id=operator_role,
                source="academy_diagnosis",
                classification="client_confidential",
                timestamp=as_of,
                correlation_id=correlation_id,
                confidence=d.confidence,
                evidence_refs=ev,
                data_mode=DATA_MODE,
                provenance={
                    "correlation_id": correlation_id,
                    "data_mode": DATA_MODE,
                    "basis": "academy_diagnosis",
                    "sources": ev,
                },
                body={
                    "workflow_category": d.category,
                    "health_state": d.health_state,
                    "open_risk_count": len(d.findings),
                    "recommended_actions": list(d.recommended_actions),
                },
            )
            for action in d.recommended_actions:
                rec = create_recommendation(
                    self.mem,
                    tenant_id=tenant_id,
                    client_id=client_id,
                    actor=operator_actor,
                    role_id=operator_role,
                    correlation_id=correlation_id,
                    timestamp=as_of,
                    action=action,
                    evidence=ev,
                    diagnosis_ref=diag_rec.record_id,
                    correct=False,
                    data_mode=DATA_MODE,
                )
                create_approval_draft(
                    self.mem,
                    tenant_id=tenant_id,
                    client_id=client_id,
                    owner=operator_actor,
                    role_id=operator_role,
                    correlation_id=correlation_id,
                    timestamp=as_of,
                    action=action,
                    recommendation_id=rec.record_id,
                    evidence=[rec.record_id],
                    data_mode=DATA_MODE,
                )

    # ----------------------------------------------------------- dry run
    def dry_run(
        self,
        tenant_client_pairs,
        fixtures_map,
        as_of=DEFAULT_AS_OF,
        operator_actor="academy-operator",
        operator_role="academy_admin",
        correlation_id="academy-dryrun",
        consent: Optional[ConsentRecord] = None,
    ):
        if consent is not None:
            self.validate_consent(consent, as_of)
        last_bundle = None
        for tenant_id, client_id in tenant_client_pairs:
            if tenant_id not in self.tenant_ids:
                self.tenant_ids.append(tenant_id)
            if client_id not in self.client_ids:
                self.client_ids.append(client_id)
            fixtures = fixtures_map[(tenant_id, client_id)]
            bundle = self.diagnose_account(
                tenant_id, client_id, as_of, operator_actor, operator_role, correlation_id, fixtures
            )
            last_bundle = bundle
            self.diagnoses.append((tenant_id, client_id, bundle["diags"]))
            record_attendance_outcome(
                self.mem,
                bundle["ctx"],
                bundle["attendance"],
                as_of,
                actor=operator_actor,
                role_id=operator_role,
            )
            record_churn_flags(
                self.mem,
                bundle["ctx"],
                bundle["churn"],
                as_of,
                actor=operator_actor,
                role_id=operator_role,
            )
            self._record_diagnosis_and_recommendations(
                tenant_id, client_id, as_of, operator_actor, operator_role, correlation_id, bundle
            )
        self.baseline_metrics = dict(last_bundle["kpis"]) if last_bundle else {}
        self.mem.add(
            kind="outcome",
            nature="historical_event",
            tenant_id="*pilot*",
            client_id="*pilot*",
            actor="academy-pack",
            role_id="academy_admin",
            source="academy_baseline",
            classification="internal",
            timestamp=as_of,
            correlation_id=correlation_id,
            confidence=1.0,
            evidence_refs=[],
            data_mode=DATA_MODE,
            provenance={
                "correlation_id": correlation_id,
                "data_mode": DATA_MODE,
                "basis": "baseline",
                "sources": [],
            },
            body={"phase": "baseline", "kpis": self.baseline_metrics},
        )
        return self.summary()

    def summary(self) -> dict:
        return {
            "tenants": self.tenant_ids,
            "clients": self.client_ids,
            "diagnoses": len(self.diagnoses),
            "baseline_kpis": self.baseline_metrics,
            "audit_status": self.mem.audit_status(),
        }

    # ----------------------------------------------------------- approvals
    def _latest_approval(self, approval_id):
        return self.mem._by_id[approval_id]

    def _category_for(self, approval_rec):
        rec_id = approval_rec.body.get("recommendation_id")
        rec = self.mem._by_id.get(rec_id)
        if rec is None:
            return None
        diag = self.mem._by_id.get(rec.body.get("diagnosis_ref"))
        return diag.body.get("workflow_category") if diag else None

    def approve_action(
        self,
        approval_id,
        approver_actor,
        approver_role,
        requester_actor,
        requester_role,
        as_of=DEFAULT_AS_OF,
        correlation_id="academy-approve",
    ):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        if self.phase == READ_ONLY:
            raise PilotError("read-only period active: committal approvals are not permitted yet")
        category = self._category_for(prev)
        req_role = required_approver_role(category) if category else "academy_owner"
        ok, reason = evaluate_approval_decision(
            prev, "approved", approver_actor, approver_role, requester_actor, requester_role
        )
        if not ok:
            raise PilotError(reason)
        if approver_role != req_role:
            raise PilotError(
                f"approver role {approver_role!r} not authorized for {category!r}; requires {req_role!r}"
            )
        return transition_approval(
            self.mem,
            prev,
            "approved",
            approver_actor,
            approver_role,
            correlation_id,
            as_of,
            reason=f"approved by {approver_actor}",
        )

    def deny_action(
        self, approval_id, reviewer, reason, as_of=DEFAULT_AS_OF, correlation_id="academy-deny"
    ):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        return transition_approval(
            self.mem,
            prev,
            "denied",
            reviewer,
            prev.role_id,
            correlation_id,
            as_of,
            reason=f"denied by {reviewer}: {reason}",
        )

    def rollback_action(
        self,
        approval_id,
        actor,
        role,
        reason,
        as_of=DEFAULT_AS_OF,
        correlation_id="academy-rollback",
    ):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        new = transition_approval(
            self.mem, prev, "rolled_back", actor, role, correlation_id, as_of, reason=reason
        )
        self.mem.add(
            kind="workflow_history",
            nature="verified_outcome",
            tenant_id=prev.tenant_id,
            client_id=prev.client_id,
            actor=actor,
            role_id=role,
            source="academy_incident",
            classification="client_confidential",
            timestamp=as_of,
            correlation_id=correlation_id,
            confidence=1.0,
            evidence_refs=[prev.record_id],
            data_mode=prev.data_mode,
            provenance={
                "correlation_id": correlation_id,
                "data_mode": prev.data_mode,
                "basis": "rollback_incident",
                "sources": [prev.record_id],
            },
            body={"action": "rollback", "target": approval_id, "reason": reason},
        )
        return new

    # ----------------------------------------------------------- manual fee recording (post-approval)
    def record_fee(
        self,
        ctx: ConnectorContext,
        *,
        athlete_id: str,
        family_id: str,
        program_id: str,
        amount: float,
        currency: str,
        due_date: str,
        paid_at,
        method_note: str,
        as_of: str,
        actor: str = "academy-operator",
        role_id: str = "academy_admin",
    ):
        """Record a manual fee — the committal write shape for fee_record."""
        if self.phase == READ_ONLY:
            raise PilotError("read-only period active: fee recording is not permitted yet")
        return record_manual_payment(
            self.mem,
            ctx,
            athlete_id=athlete_id,
            family_id=family_id,
            program_id=program_id,
            amount=amount,
            currency=currency,
            due_date=due_date,
            paid_at=paid_at,
            method_note=method_note,
            as_of=as_of,
            actor=actor,
            role_id=role_id,
        )

    # ----------------------------------------------------------- controls
    def tenant_isolation_ok(self, tenant_a: str, tenant_b: str) -> bool:
        a = self.mem.retrieve(tenant_id=tenant_a, include_deleted=True)
        b = self.mem.retrieve(tenant_id=tenant_b, include_deleted=True)
        return all(r.tenant_id == tenant_a for r in a) and all(r.tenant_id == tenant_b for r in b)

    def apply_retention(self, as_of: str) -> int:
        return self.mem.apply_retention(as_of)

    # ----------------------------------------------------------- metacognitive proposals
    def generate_metacognitive_proposal(
        self,
        as_of: str,
        correlation_id: str,
        actor: str = "academy-operator",
        role: str = "academy_admin",
    ):
        """Reuse the metacognitive improvement engine to propose (NOT deploy) a
        process improvement from academy outcomes. The engine never mutates
        runtime; apply_proposal is deliberately not called."""
        engine = MetacognitionEngine()
        tenant_id = self.tenant_ids[0] if self.tenant_ids else "t-academy"
        client_id = self.client_ids[0] if self.client_ids else "c-academy"
        proposal = engine.propose(
            kind="workflow",
            target="attendance_ops",
            baseline="Low session attendance handled ad hoc by the coach.",
            proposed="Pre-computed low-attendance escalation with head-coach approval.",
            baseline_policy={"value": {"auto": False}},
            proposed_policy={
                "value": {"auto": False, "owner_role": "coach", "approver_role": "head_coach"}
            },
            hypothesis="Pre-computing escalations reduces missed follow-ups on low-attendance sessions.",
            evidence=[f"{tenant_id}:{client_id}"],
            risk_assessment="low (read-only recommendation, human-approved before any action)",
            rollback_plan="disable recommendation; revert to ad hoc escalation",
            tenant_id=tenant_id,
            client_id=client_id,
            created_by=actor,
            role_id=role,
            correlation_id=correlation_id,
            timestamp=as_of,
            provenance={"data_mode": DATA_MODE},
        )
        engine.evaluate(
            proposal,
            historical_cases=[],
            simulated_cases=[{"low": True}, {"low": False}],
            simulate=lambda policy, case: bool(case.get("low")),
        )
        report = engine.generate_evidence_report(engine.get_proposal(proposal.proposal_id))
        self.mem.add(
            kind="policy",
            nature="model_inference",
            tenant_id=tenant_id,
            client_id=client_id,
            actor=actor,
            role_id=role,
            source="academy_metacognition",
            classification="client_confidential",
            timestamp=as_of,
            correlation_id=correlation_id,
            confidence=0.6,
            evidence_refs=[proposal.proposal_id],
            data_mode=DATA_MODE,
            provenance={
                "correlation_id": correlation_id,
                "data_mode": DATA_MODE,
                "basis": "metacognitive_proposal",
                "sources": [proposal.proposal_id],
            },
            body={
                "proposal_id": proposal.proposal_id,
                "applied": False,
                "approval_state": proposal.approval_state,
                "summary": report.get("hypothesis"),
            },
        )
        return report

    # ----------------------------------------------------------- evidence + status
    def build_evidence_pack(self, as_of: str) -> dict:
        all_recs = self.mem._records
        mode_counts: dict = {}
        for r in all_recs:
            mode_counts[r.data_mode] = mode_counts.get(r.data_mode, 0) + 1

        latest = {}
        for a in all_recs:
            if a.kind != "approval":
                continue
            rid = a.body.get("recommendation_id")
            cur = latest.get(rid)
            if cur is None or a.record_id > cur.record_id:
                latest[rid] = a
        states = [a.body.get("approval_state") for a in latest.values()]
        incidents = [
            {
                "action": r.body.get("action"),
                "target": r.body.get("target"),
                "reason": r.body.get("reason"),
            }
            for r in all_recs
            if r.kind == "workflow_history" and r.body.get("action") in ("rollback", "incident")
        ]
        ok, _ = self.mem.verify_chain()
        return {
            "capability": "sports_academy_operations",
            "generated_at": as_of,
            "tenant_ids": list(self.tenant_ids),
            "client_ids": list(self.client_ids),
            "consent": (self.consent.__dict__ if self.consent else None),
            "config": {
                "read_only_connectors": self.config.read_only_connectors,
                "tenant_isolation_enabled": self.config.tenant_isolation_enabled,
                "minimum_data": self.config.minimum_data,
                "live_activated": self.config.live_activated,
                "permitted_data_modes": list(self.config.permitted_data_modes),
            },
            "data_mode_breakdown": mode_counts,
            "live_customer_records": mode_counts.get("live_customer", 0),
            "baseline_kpis": self.baseline_metrics,
            "approval_summary": {
                "total": len(latest),
                "approved": states.count("approved"),
                "denied": states.count("denied"),
                "draft": states.count("draft"),
                "rolled_back": states.count("rolled_back"),
            },
            "incidents": incidents,
            "audit_status": self.mem.audit_status(),
            "audit_chain_intact": ok,
            "reused_core": get_academy_metadata()["reused_core"],
            "final_status": self.final_status(),
        }

    def final_status(self) -> dict:
        return {
            "capability_pack_ready": True,
            "real_design_partner_approval_pending": True,
            "production_readiness": "NOT_ESTABLISHED",
            "note": "Demonstrated for one academy location with synthetic data; not validated for live operations.",
        }
