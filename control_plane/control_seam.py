"""
Contact-Centre Control Seam — Helix Codex OS C5.

The first end-to-end multi-agent operational scenario. One continuous pipeline,
four hops, no human in the loop except where the system decides a human is
required::

    RTA Breach Alert
        -> OPS_GM Recommendation
            -> Compliance Verification Gate
                -> WFM Forecast Recalculation

Why this exact arc
------------------
It is the shortest path that still crosses every interesting boundary in the
system:

* **RTA** produces a measured fact (adherence dropped below threshold).
* **OPS_GM** turns that fact into a proposal. A proposal is not a decision —
  the seam keeps them separate so nobody reads a recommendation as a measured
  result.
* **Compliance** is a real gate, not a rubber stamp. It applies the RoleSpec
  boundaries from the organization catalog and can freeze the run at
  ``awaiting_approval``. When it does, the run stops there and the WFM
  recalculation never happens.
* **WFM** recalculates with the approved adjustment, and the recalculated
  forecast is stamped with the breach that caused it.

Each hop carries the same ``correlation_id`` and sets the next hop's
``causation_id``, so the full chain is replayable from the audit ledger.

Failure posture
---------------
The seam never raises across its own boundary. Every hop records a typed
outcome; a breach that cannot be confirmed, a recommendation that cannot be
justified, a gate that denies, or a recalculation that fails all produce a run
whose ``final_state`` says so.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from contracts.task import CorrelationContext, TaskRequest
from control_plane.governance import evaluate_gate
from control_plane.workflow import WorkflowState
from control_plane.ports import EnginePort
from security.classification import DataClassification

SEAM_ID = "contact_centre_control_seam"
SEAM_VERSION = "1.0"

STEP_RTA_BREACH = "rta_breach_alert"
STEP_OPS_RECOMMENDATION = "ops_gm_recommendation"
STEP_COMPLIANCE_GATE = "compliance_verification_gate"
STEP_WFM_RECALCULATION = "wfm_forecast_recalculation"

SEAM_STEP_ORDER = (
    STEP_RTA_BREACH,
    STEP_OPS_RECOMMENDATION,
    STEP_COMPLIANCE_GATE,
    STEP_WFM_RECALCULATION,
)

#: Default adherence floor. Below this, the interval is a breach.
DEFAULT_ADHERENCE_THRESHOLD = 0.90

#: Cost estimate attached to an OPS_GM proposal. Crossing the role's financial
#: limit is what forces the compliance gate to freeze the run.
DEFAULT_ESTIMATED_COST_USD = 750.00


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class SeamStep:
    """One hop of the control seam, recorded whether it succeeded or not."""

    name: str
    state: str
    correlation_id: str
    causation_id: Optional[str]
    actor: str
    owning_role_id: str
    capability: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    computation_evidence: Dict[str, Any] = field(default_factory=dict)
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    error: Optional[Dict[str, str]] = None
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "actor": self.actor,
            "owning_role_id": self.owning_role_id,
            "capability": self.capability,
            "metrics": self.metrics,
            "recommendations": self.recommendations,
            "computation_evidence": self.computation_evidence,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class ControlSeamRun:
    """Complete record of one control-seam execution."""

    run_id: str
    correlation_id: str
    tenant_id: str
    client_id: str
    final_state: str
    steps: List[SeamStep] = field(default_factory=list)
    breach_detected: bool = False
    awaiting_approval: bool = False
    approval_decision: Optional[str] = None
    recalculated_forecast: Optional[Dict[str, Any]] = None
    data_mode: str = "live"
    started_at: str = field(default_factory=_now_iso)
    finished_at: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.final_state == WorkflowState.CLOSED and not self.awaiting_approval

    def step(self, name: str) -> Optional[SeamStep]:
        for s in self.steps:
            if s.name == name:
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seam_id": SEAM_ID,
            "seam_version": SEAM_VERSION,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "final_state": self.final_state,
            "breach_detected": self.breach_detected,
            "awaiting_approval": self.awaiting_approval,
            "approval_decision": self.approval_decision,
            "recalculated_forecast": self.recalculated_forecast,
            "data_mode": self.data_mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "steps": [s.to_dict() for s in self.steps],
        }


class ControlSeam:
    """
    Executes the RTA breach -> OPS_GM -> compliance -> WFM arc.

    Engines are injected as :class:`~control_plane.ports.EnginePort`
    implementations, so the seam can be exercised with a stub in tests
    without touching global registries.
    """

    def __init__(
        self,
        *,
        rta_adapter: EnginePort,
        wfm_adapter: EnginePort,
        ops_actor: str = "suby",
        compliance_actor: str = "andy",
        ops_role_id: str = "ops_gm",
        compliance_role_id: str = "compliance_quality_gm",
    ) -> None:
        self.rta_adapter = rta_adapter
        self.wfm_adapter = wfm_adapter
        self.ops_actor = ops_actor
        self.compliance_actor = compliance_actor
        self.ops_role_id = ops_role_id
        self.compliance_role_id = compliance_role_id

    # ── public entry point ──────────────────────────────────────────────────

    def run(
        self,
        *,
        tenant_id: str,
        client_id: str,
        rta_payload: Dict[str, Any],
        wfm_payload: Dict[str, Any],
        adherence_threshold: float = DEFAULT_ADHERENCE_THRESHOLD,
        estimated_cost_usd: float = DEFAULT_ESTIMATED_COST_USD,
        compliance_decision: Optional[str] = None,
        sample_data_mode: bool = False,
        correlation_id: Optional[str] = None,
    ) -> ControlSeamRun:
        """
        Execute the full arc.

        ``compliance_decision`` lets a caller pre-resolve the gate
        (``"approved"`` / ``"denied"``). When it is ``None`` the gate is left in
        whatever state ``evaluate_gate`` produced — typically
        ``awaiting_approval`` — and the run stops there. That is the real
        production path: a human decides, and the seam resumes.
        """
        correlation = CorrelationContext.new(
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
        )
        run = ControlSeamRun(
            run_id=f"seam_{uuid.uuid4().hex[:16]}",
            correlation_id=correlation.correlation_id,
            tenant_id=tenant_id,
            client_id=client_id,
            final_state=WorkflowState.PROPOSED,
            data_mode="sample" if sample_data_mode else "live",
        )

        # 1 — RTA breach detection ───────────────────────────────────────────
        breach = self._run_rta_breach(
            run=run,
            correlation=correlation,
            payload=rta_payload,
            threshold=adherence_threshold,
            sample_data_mode=sample_data_mode,
        )
        if breach.error is not None:
            run.final_state = WorkflowState.DEAD_LETTER
            run.finished_at = _now_iso()
            return run
        if not run.breach_detected:
            # No breach: the arc ends here, and that is a successful outcome.
            run.final_state = WorkflowState.CLOSED
            run.finished_at = _now_iso()
            return run

        # 2 — OPS_GM recommendation ──────────────────────────────────────────
        recommendation = self._run_ops_recommendation(
            run=run,
            correlation=correlation,
            breach=breach,
            wfm_payload=wfm_payload,
            estimated_cost_usd=estimated_cost_usd,
        )
        if recommendation.error is not None:
            run.final_state = WorkflowState.DEAD_LETTER
            run.finished_at = _now_iso()
            return run

        # 3 — Compliance verification gate ───────────────────────────────────
        gate = self._run_compliance_gate(
            run=run,
            correlation=correlation,
            recommendation=recommendation,
            estimated_cost_usd=estimated_cost_usd,
            compliance_decision=compliance_decision,
        )
        if gate.error is not None:
            run.final_state = WorkflowState.DEAD_LETTER
            run.finished_at = _now_iso()
            return run
        if run.awaiting_approval:
            run.final_state = WorkflowState.AWAITING_APPROVAL
            run.finished_at = _now_iso()
            return run
        if run.approval_decision == "denied":
            run.final_state = WorkflowState.CANCELLED
            run.finished_at = _now_iso()
            return run

        # 4 — WFM forecast recalculation ─────────────────────────────────────
        recalculation = self._run_wfm_recalculation(
            run=run,
            correlation=correlation,
            recommendation=recommendation,
            wfm_payload=wfm_payload,
            sample_data_mode=sample_data_mode,
        )
        run.final_state = (
            WorkflowState.CLOSED if recalculation.error is None else WorkflowState.DEAD_LETTER
        )
        run.finished_at = _now_iso()
        return run

    # ── hop 1: RTA breach ───────────────────────────────────────────────────

    def _run_rta_breach(
        self,
        *,
        run: ControlSeamRun,
        correlation: CorrelationContext,
        payload: Dict[str, Any],
        threshold: float,
        sample_data_mode: bool,
    ) -> SeamStep:
        request = self._request(
            correlation=correlation,
            capability="rta_adherence",
            payload=payload,
            actor=self.ops_actor,
            role_id=self.ops_role_id,
            causation=None,
        )
        outcome = self.rta_adapter.execute(request, sample_data_mode=sample_data_mode)
        result = outcome.task_result

        step = SeamStep(
            name=STEP_RTA_BREACH,
            state=self._state_for(result.status),
            correlation_id=correlation.correlation_id,
            causation_id=None,
            actor=self.ops_actor,
            owning_role_id=self.ops_role_id,
            capability="rta_adherence",
            metrics=dict(outcome.engine_result.metrics),
            computation_evidence=outcome.computation_evidence.to_dict(),
        )

        if result.status != "succeeded":
            step.error = {"code": result.error.code, "message": result.error.message}
            step.reason_code = result.error.code
            step.reason = result.error.message
            run.steps.append(step)
            return step

        adherence = self._extract_adherence(outcome.engine_result.metrics)
        if adherence is None:
            step.error = {
                "code": "indeterminate_breach",
                "message": "RTA result did not contain an adherence figure; refusing to infer a breach",
            }
            step.reason_code = "indeterminate_breach"
            step.reason = step.error["message"]
            step.state = WorkflowState.DEAD_LETTER
            run.steps.append(step)
            return step

        breach = adherence < threshold
        run.breach_detected = breach
        step.metrics["adherence"] = adherence
        step.metrics["adherence_threshold"] = threshold
        step.metrics["breach_detected"] = breach
        step.reason_code = "breach_detected" if breach else "within_threshold"
        step.reason = (
            f"adherence {adherence:.4f} is below threshold {threshold:.4f}"
            if breach
            else f"adherence {adherence:.4f} is at or above threshold {threshold:.4f}"
        )
        run.steps.append(step)
        return step

    @staticmethod
    def _extract_adherence(metrics: Dict[str, Any]) -> Optional[float]:
        for key in (
            "adherence_percentage",
            "adherence.average_adherence",
            "adherence.adherence_percentage",
            "overall_adherence",
            "adherence",
        ):
            value = metrics.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            # RTA reports adherence as a percentage in places; normalise to 0-1.
            return float(value) / 100.0 if float(value) > 1.0 else float(value)
        return None

    # ── hop 2: OPS_GM recommendation ────────────────────────────────────────

    def _run_ops_recommendation(
        self,
        *,
        run: ControlSeamRun,
        correlation: CorrelationContext,
        breach: SeamStep,
        wfm_payload: Dict[str, Any],
        estimated_cost_usd: float,
    ) -> SeamStep:
        causation = breach.correlation_id
        adherence = breach.metrics.get("adherence")
        threshold = breach.metrics.get("adherence_threshold")

        # The recommendation is arithmetic on the measured breach, not a model
        # opinion. It is tagged so downstream readers know which is which.
        shortfall = max(0.0, float(threshold) - float(adherence)) if adherence is not None else 0.0
        proposed_adjustment = self._proposed_adjustment(shortfall)

        step = SeamStep(
            name=STEP_OPS_RECOMMENDATION,
            state=WorkflowState.VALIDATED,
            correlation_id=correlation.correlation_id,
            causation_id=causation,
            actor=self.ops_actor,
            owning_role_id=self.ops_role_id,
            capability="ops_recommendation",
            metrics={
                "adherence": adherence,
                "adherence_threshold": threshold,
                "adherence_shortfall": round(shortfall, 4),
                "proposed_interval_adjustment": proposed_adjustment,
                "estimated_cost_usd": estimated_cost_usd,
                "source": "calculated",
            },
            recommendations=[
                {
                    "type": "staffing_adjustment",
                    "value": proposed_adjustment,
                    "rationale": (
                        f"adherence shortfall {shortfall:.4f} against threshold {threshold}; "
                        f"propose adjusting {proposed_adjustment} interval(s) and targeted coaching"
                    ),
                    "source": "calculated",
                }
            ],
        )

        if proposed_adjustment <= 0:
            step.error = {
                "code": "no_actionable_recommendation",
                "message": "breach is too small to justify an interval adjustment; no action proposed",
            }
            step.reason_code = step.error["code"]
            step.reason = step.error["message"]
            step.state = WorkflowState.DEAD_LETTER

        run.steps.append(step)
        return step

    @staticmethod
    def _proposed_adjustment(shortfall: float) -> int:
        """One interval per full 5 points of shortfall, at least one if any."""
        if shortfall <= 0.0:
            return 0
        return max(1, int(round(shortfall / 0.05)))

    # ── hop 3: compliance gate ──────────────────────────────────────────────

    def _run_compliance_gate(
        self,
        *,
        run: ControlSeamRun,
        correlation: CorrelationContext,
        recommendation: SeamStep,
        estimated_cost_usd: float,
        compliance_decision: Optional[str],
    ) -> SeamStep:
        confidence = 0.9 if recommendation.metrics.get("adherence") is not None else 0.4

        decision = evaluate_gate(
            self.ops_role_id,
            estimated_financial_cost=estimated_cost_usd,
            data_classification=DataClassification.INTERNAL,
            confidence_score=confidence,
            target_engine="wfm",
        )

        step = SeamStep(
            name=STEP_COMPLIANCE_GATE,
            state=decision.state,
            correlation_id=correlation.correlation_id,
            causation_id=recommendation.correlation_id,
            actor=self.compliance_actor,
            owning_role_id=self.compliance_role_id,
            capability="policy_enforcement",
            metrics={
                "estimated_cost_usd": decision.estimated_cost_usd,
                "limit_usd": decision.limit_usd,
                "confidence_score": confidence,
            },
            reason_code=decision.reason_code,
            reason=decision.reason,
        )

        if not decision.allowed:
            step.error = {"code": decision.reason_code, "message": decision.reason}
            run.steps.append(step)
            return step

        if compliance_decision is None:
            # No human has ruled yet. Freeze the run and stop the arc.
            run.awaiting_approval = True
            run.approval_decision = None
            run.steps.append(step)
            return step

        if compliance_decision not in ("approved", "denied"):
            step.error = {
                "code": "invalid_approval_decision",
                "message": f"approval decision must be 'approved' or 'denied', got {compliance_decision!r}",
            }
            step.reason_code = step.error["code"]
            step.reason = step.error["message"]
            step.state = WorkflowState.DEAD_LETTER
            run.steps.append(step)
            return step

        run.approval_decision = compliance_decision
        step.state = (
            WorkflowState.APPROVED if compliance_decision == "approved" else WorkflowState.CANCELLED
        )
        step.reason_code = f"compliance_{compliance_decision}"
        step.reason = f"compliance {compliance_decision} the OPS_GM recommendation"
        run.steps.append(step)
        return step

    # ── hop 4: WFM recalculation ────────────────────────────────────────────

    def _run_wfm_recalculation(
        self,
        *,
        run: ControlSeamRun,
        correlation: CorrelationContext,
        recommendation: SeamStep,
        wfm_payload: Dict[str, Any],
        sample_data_mode: bool,
    ) -> SeamStep:
        adjustment = int(recommendation.metrics.get("proposed_interval_adjustment") or 0)
        recalculated = dict(wfm_payload)
        recalculated["interval_adjustment"] = adjustment
        recalculated["seam_run_id"] = run.run_id
        recalculated["caused_by"] = STEP_RTA_BREACH

        request = self._request(
            correlation=correlation,
            capability="wfm_forecast",
            payload=recalculated,
            actor=self.ops_actor,
            role_id=self.ops_role_id,
            causation=recommendation.correlation_id,
        )
        outcome = self.wfm_adapter.execute(request, sample_data_mode=sample_data_mode)
        result = outcome.task_result

        step = SeamStep(
            name=STEP_WFM_RECALCULATION,
            state=self._state_for(result.status),
            correlation_id=correlation.correlation_id,
            causation_id=recommendation.correlation_id,
            actor=self.ops_actor,
            owning_role_id=self.ops_role_id,
            capability="wfm_forecast",
            metrics=dict(outcome.engine_result.metrics),
            computation_evidence=outcome.computation_evidence.to_dict(),
        )

        if result.status != "succeeded":
            step.error = {"code": result.error.code, "message": result.error.message}
            step.reason_code = result.error.code
            step.reason = result.error.message
        else:
            step.reason_code = "forecast_recalculated"
            step.reason = f"forecast recalculated with interval adjustment {adjustment}"
            run.recalculated_forecast = dict(outcome.engine_result.metrics)

        run.steps.append(step)
        return step

    # ── helpers ─────────────────────────────────────────────────────────────

    def _request(
        self,
        *,
        correlation: CorrelationContext,
        capability: str,
        payload: Dict[str, Any],
        actor: str,
        role_id: str,
        causation: Optional[str],
    ) -> TaskRequest:
        return TaskRequest(
            request_id=f"req_{uuid.uuid4().hex[:20]}",
            correlation=correlation,
            requesting_actor=actor,
            owning_role_id=role_id,
            capability=capability,
            input_payload=dict(payload),
            requires_approval=False,
            status="validated",
            created_at=_now_iso(),
            tenant_id=correlation.tenant_id,
            client_id=correlation.client_id,
        )

    @staticmethod
    def _state_for(task_status: str) -> str:
        return {
            "succeeded": WorkflowState.CLOSED,
            "failed": WorkflowState.DEAD_LETTER,
            "refused": WorkflowState.DEAD_LETTER,
            "timed_out": WorkflowState.DEAD_LETTER,
            "pending_approval": WorkflowState.AWAITING_APPROVAL,
            "awaiting_approval": WorkflowState.AWAITING_APPROVAL,
        }.get(task_status, WorkflowState.DEAD_LETTER)


def build_default_seam() -> ControlSeam:
    """Construct the seam with the registered RTA and WFM engines."""
    from engines.registry import build_port

    return ControlSeam(rta_adapter=build_port("rta"), wfm_adapter=build_port("wfm"))


__all__ = [
    "DEFAULT_ADHERENCE_THRESHOLD",
    "DEFAULT_ESTIMATED_COST_USD",
    "SEAM_ID",
    "SEAM_STEP_ORDER",
    "SEAM_VERSION",
    "STEP_COMPLIANCE_GATE",
    "STEP_OPS_RECOMMENDATION",
    "STEP_RTA_BREACH",
    "STEP_WFM_RECALCULATION",
    "ControlSeam",
    "ControlSeamRun",
    "SeamStep",
    "build_default_seam",
]
