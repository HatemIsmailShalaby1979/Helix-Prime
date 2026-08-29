"""Restaurant capability-pack runtime (Prompt 11).

Orchestrates the VERIFIED governed core for a small restaurant:
identity, tenant isolation, governance, connectors, workflows, approvals, evidence,
memory, metrics, and metacognitive proposals. It starts read-only with synthetic data,
never activates live connectors or external writes, and never auto-improves.

Every record preserves: tenant/client identity, provenance, correlation ID, data mode,
approval state, outcome, and the audit trail.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from connectors.contracts import ConnectorContext  # noqa: E402
from memory.governed_memory import GovernedMemory  # noqa: E402
from pilot.approval import (  # noqa: E402
    create_recommendation, create_approval_draft, transition_approval,
    evaluate_approval_decision,
)
from pilot.consent import ConsentRecord, validate_consent  # noqa: E402
from pilot.config import PilotConfig  # noqa: E402
from pilot.phases import (  # noqa: E402
    READ_ONLY, SUPERVISED, ReadOnlyPeriod, ConnectorPermissions,
)
from pilot.exceptions import PilotError  # noqa: E402
from security.identity import Identity  # noqa: E402
from control_plane.workflow import Workflow, WorkflowState, CorrelationContext  # noqa: E402
from metacognition.improvement import MetacognitionEngine  # noqa: E402

from .contracts import build_restaurant_connectors  # noqa: E402
from .workflows import run_all_workflows  # noqa: E402
from .metrics import compute_restaurant_metrics  # noqa: E402
from .roles import required_approver_role  # noqa: E402
from .policies import authority_for  # noqa: E402
from .register import get_restaurant_metadata  # noqa: E402

DATA_MODE = "simulated_realistic"
DEFAULT_AS_OF = "2026-08-29T12:00:00Z"


class RestaurantCapabilityPack:
    def __init__(self, memory: GovernedMemory, *, phase: str = SUPERVISED,
                 read_only_period: Optional[ReadOnlyPeriod] = None,
                 connector_permissions: Optional[ConnectorPermissions] = None,
                 identity: Optional[Identity] = None,
                 config: Optional[PilotConfig] = None) -> None:
        self.mem = memory
        self.phase = phase
        self.read_only_period = read_only_period
        self.connector_permissions = connector_permissions or ConnectorPermissions()
        self.connector_permissions.validate()
        self.config = config or PilotConfig.from_dict({})
        self.identity = identity or Identity(actor="restaurant-operator", actor_type="human",
                                             role_id="restaurant_gm")
        self.tenant_ids: list = []
        self.client_ids: list = []
        self.diagnoses: list = []
        self.baseline_metrics: dict = {}
        self.consent: Optional[ConsentRecord] = None
        self._connectors: Optional[dict] = None

    # ----------------------------------------------------------- registration
    def register(self) -> dict:
        from .register import register_capability
        return register_capability("restaurant_operations", get_restaurant_metadata())

    # ----------------------------------------------------------- consent
    def validate_consent(self, consent: ConsentRecord, as_of: str) -> bool:
        validate_consent(consent, as_of, self.config.permitted_data_modes)
        self.consent = consent
        self.mem.add(
            kind="workflow_history", nature="verified_outcome", tenant_id=consent.tenant_id,
            client_id=consent.client_id, actor="restaurant-pack", role_id="restaurant_gm",
            source="restaurant_consent", classification="client_confidential", timestamp=as_of,
            correlation_id=consent.consent_id, confidence=1.0, evidence_refs=[consent.consent_id],
            data_mode=DATA_MODE,
            provenance={"correlation_id": consent.consent_id, "data_mode": DATA_MODE,
                        "basis": "consent_validation", "sources": [consent.consent_id]},
            body={"action": "consent_validated", "consent_id": consent.consent_id},
        )
        return True

    # ----------------------------------------------------------- read-only phase
    def enter_read_only_period(self, starts_at: str, ends_at: str) -> ReadOnlyPeriod:
        self.read_only_period = ReadOnlyPeriod(starts_at, ends_at)
        self.phase = READ_ONLY
        return self.read_only_period

    def exit_read_only_period(self, as_of: str, actor: str, role: str,
                             correlation_id: str = "restaurant-exit") -> str:
        if self.read_only_period is None:
            raise PilotError("no read-only period configured")
        self.read_only_period = ReadOnlyPeriod(self.read_only_period.starts_at, as_of)
        self.mem.add(
            kind="workflow_history", nature="verified_outcome", tenant_id="*pilot*",
            client_id="*pilot*", actor=actor, role_id=role, source="restaurant_phase",
            classification="internal", timestamp=as_of, correlation_id=correlation_id,
            confidence=1.0, evidence_refs=[], data_mode=DATA_MODE,
            provenance={"correlation_id": correlation_id, "data_mode": DATA_MODE,
                        "basis": "phase_exit", "sources": []},
            body={"action": "read_only_exited", "ends_at": as_of},
        )
        self.phase = SUPERVISED
        return self.phase

    def prepare_first_real_pilot(self, starts_at: str, ends_at: str, consent: ConsentRecord, as_of: str):
        self.validate_consent(consent, as_of)
        if not self.config.minimum_data:
            raise PilotError("first real pilot requires the minimum-data policy")
        if self.config.live_activated:
            raise PilotError("first real pilot must not activate live customer data")
        self.connector_permissions.validate()
        self.enter_read_only_period(starts_at, ends_at)
        return self

    # ----------------------------------------------------------- connectors / diagnose
    def _build_connectors(self, ctx: ConnectorContext, fixtures: dict) -> dict:
        return build_restaurant_connectors(ctx, fixtures)

    @staticmethod
    def _safe(fn, ctx, failures, label):
        try:
            return fn(ctx)
        except Exception as exc:  # degrade, never crash
            failures.append((label, str(exc)))
            return ()

    def diagnose_account(self, tenant_id, client_id, as_of, operator_actor, operator_role,
                         correlation_id, fixtures):
        ctx = ConnectorContext(tenant_id, "org-1", client_id, actor=operator_actor,
                               correlation_id=correlation_id, data_mode=DATA_MODE)
        connectors = self._build_connectors(ctx, fixtures)
        self._connectors = connectors
        failures = []
        shifts = self._safe(connectors["restaurant_ops"].list_shifts, ctx, failures, "shifts")
        inventory = self._safe(connectors["restaurant_ops"].list_inventory, ctx, failures, "inventory")
        suppliers = self._safe(connectors["restaurant_ops"].list_suppliers, ctx, failures, "suppliers")
        complaints = self._safe(connectors["restaurant_ops"].list_complaints, ctx, failures, "complaints")
        summary = self._safe(connectors["restaurant_ops"].list_daily_summary, ctx, failures, "daily_summary")

        diags = run_all_workflows(shifts, inventory, suppliers, complaints, summary, ctx, as_of)
        for label, err in failures:
            self.mem.add(
                kind="workflow_history", nature="historical_event", tenant_id=tenant_id,
                client_id=client_id, actor="restaurant-pack", role_id=operator_role,
                source="restaurant_connector", classification="client_confidential", timestamp=as_of,
                correlation_id=correlation_id, confidence=1.0, evidence_refs=[],
                data_mode=DATA_MODE,
                provenance={"correlation_id": correlation_id, "data_mode": DATA_MODE,
                            "basis": "connector_failure", "sources": []},
                body={"action": "connector_failure", "provider": "RestaurantOps", "error": err},
            )
        return diags, connectors, failures

    def _record_diagnosis_and_recommendations(self, tenant_id, client_id, as_of, operator_actor,
                                              operator_role, correlation_id, diags, data_mode):
        for d in diags:
            ev = list(d.evidence_refs)
            diag_rec = self.mem.add(
                kind="customer_context", nature="simulated_event", tenant_id=tenant_id, client_id=client_id,
                actor="restaurant-pack", role_id=operator_role, source="restaurant_diagnosis",
                classification="client_confidential", timestamp=as_of, correlation_id=correlation_id,
                confidence=d.confidence, evidence_refs=ev, data_mode=data_mode,
                provenance={"correlation_id": correlation_id, "data_mode": data_mode,
                            "basis": "restaurant_diagnosis", "sources": ev},
                body={"workflow_category": d.category, "health_state": d.health_state,
                      "open_risk_count": len(d.findings),
                      "recommended_actions": list(d.recommended_actions)},
            )
            # The recommendation is owned by the workflow's owning role (for SOD),
            # acted on here by the operator running the pack.
            owner_role = authority_for(d.category)["owner_role"]
            for action in d.recommended_actions:
                correct = (d.category == "complaint_escalation")
                rec = create_recommendation(
                    self.mem, tenant_id=tenant_id, client_id=client_id, actor=operator_actor,
                    role_id=owner_role, correlation_id=correlation_id, timestamp=as_of,
                    action=action, evidence=ev, diagnosis_ref=diag_rec.record_id,
                    correct=correct, data_mode=data_mode,
                )
                create_approval_draft(
                    self.mem, tenant_id=tenant_id, client_id=client_id, owner=operator_actor,
                    role_id=owner_role, correlation_id=correlation_id, timestamp=as_of,
                    action=action, recommendation_id=rec.record_id, evidence=[rec.record_id],
                    data_mode=data_mode,
                )

    # ----------------------------------------------------------- dry run
    def dry_run(self, tenant_client_pairs, fixtures_map, as_of=DEFAULT_AS_OF,
                operator_actor="restaurant-operator", operator_role="restaurant_gm",
                correlation_id="restaurant-dryrun", consent: Optional[ConsentRecord] = None):
        if consent is not None:
            self.validate_consent(consent, as_of)
        for tenant_id, client_id in tenant_client_pairs:
            if tenant_id not in self.tenant_ids:
                self.tenant_ids.append(tenant_id)
            if client_id not in self.client_ids:
                self.client_ids.append(client_id)
            fixtures = fixtures_map[(tenant_id, client_id)]
            diags, _connectors, _failures = self.diagnose_account(
                tenant_id, client_id, as_of, operator_actor, operator_role, correlation_id, fixtures)
            self.diagnoses.append((tenant_id, client_id, diags))
            self._record_diagnosis_and_recommendations(
                tenant_id, client_id, as_of, operator_actor, operator_role, correlation_id, diags, DATA_MODE)
        self.baseline_metrics = compute_restaurant_metrics(self.mem, self.tenant_ids)
        self.mem.add(
            kind="outcome", nature="historical_event", tenant_id="*pilot*", client_id="*pilot*",
            actor="restaurant-pack", role_id="restaurant_gm", source="restaurant_baseline",
            classification="internal", timestamp=as_of, correlation_id=correlation_id,
            confidence=1.0, evidence_refs=[], data_mode=DATA_MODE,
            provenance={"correlation_id": correlation_id, "data_mode": DATA_MODE,
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

    def approve_action(self, approval_id, approver_actor, approver_role, requester_actor,
                       requester_role, as_of=DEFAULT_AS_OF, correlation_id="restaurant-approve"):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        if self.phase == READ_ONLY:
            raise PilotError("read-only period active: committal approvals are not permitted yet")
        category = self._category_for(prev)
        req_role = required_approver_role(category) if category else "restaurant_gm"
        ok, reason = evaluate_approval_decision(
            prev, "approved", approver_actor, approver_role, requester_actor, requester_role)
        if not ok:
            raise PilotError(reason)
        if approver_role != req_role:
            raise PilotError(
                f"approver role {approver_role!r} not authorized for {category!r}; requires {req_role!r}")
        return transition_approval(
            self.mem, prev, "approved", approver_actor, approver_role, correlation_id, as_of,
            reason=f"approved by {approver_actor}")

    def deny_action(self, approval_id, reviewer, reason, as_of=DEFAULT_AS_OF, correlation_id="restaurant-deny"):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        return transition_approval(
            self.mem, prev, "denied", reviewer, prev.role_id, correlation_id, as_of,
            reason=f"denied by {reviewer}: {reason}")

    def rollback_action(self, approval_id, actor, role, reason, as_of=DEFAULT_AS_OF, correlation_id="restaurant-rollback"):
        prev = self._latest_approval(approval_id)
        if prev.kind != "approval":
            raise PilotError("not an approval record")
        new = transition_approval(
            self.mem, prev, "rolled_back", actor, role, correlation_id, as_of, reason=reason)
        self.mem.add(
            kind="workflow_history", nature="verified_outcome", tenant_id=prev.tenant_id,
            client_id=prev.client_id, actor=actor, role_id=role, source="restaurant_incident",
            classification="client_confidential", timestamp=as_of, correlation_id=correlation_id,
            confidence=1.0, evidence_refs=[prev.record_id], data_mode=prev.data_mode,
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

    # ----------------------------------------------------------- metacognitive proposals
    def generate_metacognitive_proposal(self, as_of: str, correlation_id: str,
                                        actor: str = "restaurant-operator", role: str = "restaurant_gm"):
        """Reuse the metacognitive improvement engine to propose (NOT deploy) a process
        improvement from detected restaurant outcomes. The engine never mutates runtime;
        we deliberately do not call apply_proposal, so nothing self-improves."""
        engine = MetacognitionEngine()
        tenant_id = self.tenant_ids[0] if self.tenant_ids else "t-restaurant"
        client_id = self.client_ids[0] if self.client_ids else "c-restaurant"
        proposal = engine.propose(
            kind="workflow", target="staffing_risk",
            baseline="Staffing gaps handled ad hoc by shift manager.",
            proposed="Pre-computed staffing-gap recommendation with required approver role.",
            baseline_policy={"value": {"auto": False}},
            proposed_policy={"value": {"auto": False, "owner_role": "shift_manager",
                                       "approver_role": "restaurant_gm"}},
            hypothesis="Pre-computing gaps reduces missed shift coverage and response time.",
            evidence=[f"{tenant_id}:{client_id}"],
            risk_assessment="low (read-only recommendation, human-approved before any action)",
            rollback_plan="disable recommendation; revert to ad hoc process",
            tenant_id=tenant_id, client_id=client_id, created_by=actor, role_id=role,
            correlation_id=correlation_id, timestamp=as_of, provenance={"data_mode": DATA_MODE},
        )
        # Deterministic synthetic evaluation: proposed policy covers the same cases as baseline.
        engine.evaluate(
            proposal, historical_cases=[], simulated_cases=[{"gap": True}, {"gap": False}],
            simulate=lambda policy, case: bool(case.get("gap")),
        )
        report = engine.generate_evidence_report(engine.get_proposal(proposal.proposal_id))
        # Record the PROPOSAL as governed evidence (not an applied policy).
        self.mem.add(
            kind="policy", nature="model_inference", tenant_id=tenant_id, client_id=client_id,
            actor=actor, role_id=role, source="restaurant_metacognition", classification="client_confidential",
            timestamp=as_of, correlation_id=correlation_id, confidence=0.6,
            evidence_refs=[proposal.proposal_id],
            data_mode=DATA_MODE,
            provenance={"correlation_id": correlation_id, "data_mode": DATA_MODE,
                        "basis": "metacognitive_proposal", "sources": [proposal.proposal_id]},
            body={"proposal_id": proposal.proposal_id, "applied": False,
                  "approval_state": proposal.approval_state,
                  "summary": report.get("hypothesis")},
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
            {"action": r.body.get("action"), "target": r.body.get("target"), "reason": r.body.get("reason")}
            for r in all_recs
            if r.kind == "workflow_history" and r.body.get("action") in ("connector_failure", "rollback", "incident")
        ]
        ok, _ = self.mem.verify_chain()
        metrics = compute_restaurant_metrics(self.mem, self.tenant_ids, self.baseline_metrics)
        return {
            "capability": "restaurant_operations",
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
            "metrics": metrics,
            "baseline_metrics": self.baseline_metrics,
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
            "reused_core": get_restaurant_metadata()["reused_core"],
            "final_status": self.final_status(),
        }

    def final_status(self) -> dict:
        return {
            "capability_pack_ready": True,
            "real_design_partner_approval_pending": True,
            "production_readiness": "NOT_ESTABLISHED",
            "note": "Demonstrated for one restaurant workflow only; not validated for every business.",
        }
