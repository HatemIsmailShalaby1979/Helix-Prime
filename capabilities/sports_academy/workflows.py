"""Academy core workflows (v1) — enrollment, attendance, renewal.

Each workflow is a pure, deterministic function over pack data. It returns a
:class:`AcademyDiagnosis` (findings + recommended actions) with evidence refs.
The runtime (S7) records each diagnosis and its recommended actions in
governed memory; nothing here executes a write. Recommended actions carry
their workflow category so the approval layer can enforce the pack's
authority boundaries (owner/approver separation of duties).
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any, Dict, Sequence, Tuple

import yaml

from .adapters.attendance_adapter import compute_attendance

_DECLARATIONS = pathlib.Path(__file__).parent / "declarations"

WORKFLOW_CATEGORIES = ("enrollment", "attendance_ops", "renewal", "facility_booking", "fee_record")

#: Session attendance below this triggers an attendance-ops escalation finding.
LOW_SESSION_ATTENDANCE = 0.6

#: Renewal reminder window: athletes whose fee is due on/before this date
#: relative to as_of receive a renewal reminder recommendation.
RENEWAL_WINDOW_DAYS = 30


@dataclass
class RiskFinding:
    category: str
    severity: str  # low | medium | high
    detail: str
    evidence_ref: str


@dataclass
class AcademyDiagnosis:
    category: str
    health_state: str  # ok | at_risk | critical
    confidence: float
    findings: Tuple[RiskFinding, ...]
    recommended_actions: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]


def load_flow_declaration(flow: str) -> Dict[str, Any]:
    path = _DECLARATIONS / f"{flow}_flow.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def enrollment_flow(enrollment_pipeline: Dict[str, Any]) -> AcademyDiagnosis:
    """Inquiry → trial → enroll → pay: flag stalled inquirers/trialists."""
    stages = enrollment_pipeline.get("stage_counts", {})
    findings = []
    if stages.get("inquiry", 0) > 0:
        findings.append(
            RiskFinding(
                "enrollment",
                "medium",
                f"{stages['inquiry']} inquiry(ies) not yet converted to trial",
                "enrollment_pipeline:inquiry",
            )
        )
    if stages.get("trial", 0) > 0:
        findings.append(
            RiskFinding(
                "enrollment",
                "high" if stages["trial"] > 1 else "medium",
                f"{stages['trial']} trial athlete(s) awaiting enrollment decision",
                "enrollment_pipeline:trial",
            )
        )
    actions = tuple(
        f"Follow up on {r['athlete_id']} ({r['stage']} since {r['recorded_at'][:10]}): {r['note']}"
        for r in enrollment_pipeline.get("records", [])
    )
    state = (
        "critical"
        if any(f.severity == "high" for f in findings)
        else ("at_risk" if findings else "ok")
    )
    return AcademyDiagnosis(
        "enrollment",
        state,
        0.85 if findings else 1.0,
        tuple(findings),
        actions,
        tuple(f.evidence_ref for f in findings),
    )


def attendance_flow(
    sessions: Sequence[Any], checkins: Sequence[Any], as_of: str
) -> AcademyDiagnosis:
    """Daily check-in → adherence report: flag low-attendance sessions."""
    att = compute_attendance(sessions, checkins)
    low = [
        (sid, row)
        for sid, row in att["by_session"].items()
        if row["roster_size"] and row["attendance_rate"] < LOW_SESSION_ATTENDANCE
    ]
    findings = [
        RiskFinding(
            "attendance_ops",
            "high" if row["attendance_rate"] < 0.4 else "medium",
            f"{sid} attendance {row['attendance_rate']:.0%} "
            f"({row['present']}/{row['roster_size']})",
            f"attendance:{sid}",
        )
        for sid, row in low
    ]
    actions = tuple(
        f"Escalate {sid} to head coach: attendance {row['attendance_rate']:.0%} "
        f"({row['present']}/{row['roster_size']})"
        for sid, row in low
    )
    state = (
        "critical"
        if any(f.severity == "high" for f in findings)
        else ("at_risk" if findings else "ok")
    )
    return AcademyDiagnosis(
        "attendance_ops",
        state,
        0.9 if findings else 1.0,
        tuple(findings),
        actions,
        tuple(f.evidence_ref for f in findings),
    )


def renewal_flow(
    athletes: Sequence[Any], fee_payments: Sequence[Any], as_of: str
) -> AcademyDiagnosis:
    """Term-end → reminder → renew/churn: flag outstanding fees + at-risk athletes."""
    findings = []
    outstanding = [p for p in fee_payments if p.paid_at is None]
    for p in outstanding:
        findings.append(
            RiskFinding(
                "renewal",
                "high",
                f"{p.athlete_id} fee {p.amount:.0f} due {p.due_date} still unpaid",
                f"fee:{p.payment_id}",
            )
        )
    at_risk = [r["athlete_id"] for r in churn_risk_signals_for(athletes, fee_payments)]
    for athlete_id in at_risk:
        findings.append(
            RiskFinding(
                "renewal",
                "medium",
                f"{athlete_id} attendance declining — renewal risk",
                f"attendance:{athlete_id}",
            )
        )
    actions = tuple(
        f"Send renewal reminder to {p.athlete_id}'s family for {p.amount:.0f} due {p.due_date}"
        for p in outstanding
    ) + tuple(f"Schedule retention conversation for {aid} before term end" for aid in at_risk)
    state = (
        "critical"
        if any(f.severity == "high" for f in findings)
        else ("at_risk" if findings else "ok")
    )
    return AcademyDiagnosis(
        "renewal",
        state,
        0.8 if findings else 1.0,
        tuple(findings),
        actions,
        tuple(f.evidence_ref for f in findings),
    )


def churn_risk_signals_for(
    athletes: Sequence[Any], fee_payments: Sequence[Any]
) -> Sequence[Dict[str, Any]]:
    """Renewal-specific churn signal: outstanding fee + active status.

    Kept separate from the athlete-profile attendance-decline flag: renewal
    risk is about the *next term*, attendance decline is about engagement.
    In v1 fixtures the outstanding fee (pay-003, ath-03) is the seeded
    renewal-risk case.
    """
    active = {a.athlete_id for a in athletes if a.enrollment_status == "active"}
    return [
        {
            "athlete_id": p.athlete_id,
            "reason": "outstanding_fee",
            "amount": p.amount,
            "due_date": p.due_date,
        }
        for p in fee_payments
        if p.paid_at is None and p.athlete_id in active
    ]
