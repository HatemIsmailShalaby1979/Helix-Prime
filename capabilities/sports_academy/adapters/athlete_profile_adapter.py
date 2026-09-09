"""Athlete profile adapter (v1) — basic CRM + churn-risk flags.

Builds athlete/family profiles from the read-only academy connector
(identity, program, enrollment status, attendance history, family, fee
status), the enrollment pipeline (inquiry → trial → enrolled), and
churn-risk flags derived from attendance decline. Churn signals are scored
through the reused CX engine (`churn_risk_scoring`, owning role ops_gm) so
the flag carries engine evidence rather than pack-local arithmetic alone.

Profiles and churn flags are recorded in governed memory by callers that
hold a runtime. Nothing here writes to any external system.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from connectors.contracts import ConnectorContext

DATA_MODE = "simulated_realistic"

#: Attendance rate below which an athlete is flagged at-risk without any
#: engine call (pure arithmetic fast path; the CX engine refines the score).
ATTENDANCE_RISK_THRESHOLD = 0.6

#: Minimum expected sessions before a churn flag is meaningful.
MIN_SESSIONS_FOR_RISK = 3


def athlete_profile(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    athlete_id: str,
) -> Optional[Dict[str, Any]]:
    """One athlete's full profile: identity, program, attendance, family, fees."""
    conn = connectors["academy_ops"]
    athletes = [a for a in conn.list_athletes(ctx) if a.athlete_id == athlete_id]
    if not athletes:
        return None
    athlete = athletes[0]

    families = [f for f in conn.list_families(ctx)
                if f.family_id == athlete.family_id]
    family = families[0] if families else None

    programs = [p for p in conn.list_programs(ctx)
                if p.program_id == athlete.program_id]
    program = programs[0] if programs else None

    sessions = [s for s in conn.list_sessions(ctx)
                if athlete_id in s.roster]
    checkins = [c for c in conn.list_checkins(ctx)
                if c.athlete_id == athlete_id]
    attended_session_ids = {c.session_id for c in checkins}
    attendance_history = [
        {"session_id": s.session_id, "date": s.date, "attended":
         s.session_id in attended_session_ids}
        for s in sorted(sessions, key=lambda s: (s.date, s.session_id))
    ]
    expected = len(attendance_history)
    attended = sum(1 for h in attendance_history if h["attended"])
    attendance_rate = round(attended / expected, 4) if expected else 0.0

    fee_records = [p for p in conn.list_fee_payments(ctx)
                   if p.athlete_id == athlete_id]

    return {
        "athlete_id": athlete.athlete_id,
        "name": athlete.name,
        "birth_date": athlete.birth_date,
        "age_band": _age_band(athlete.birth_date),
        "program_id": athlete.program_id,
        "program_name": program.name if program else None,
        "enrollment_status": athlete.enrollment_status,
        "family": {
            "family_id": family.family_id,
            "primary_contact_name": family.primary_contact_name,
            "phone": family.phone,
            "email": family.email,
        } if family else None,
        "attendance": {
            "expected": expected,
            "attended": attended,
            "rate": attendance_rate,
            "history": attendance_history,
        },
        "fees": [
            {"payment_id": p.payment_id, "amount": p.amount,
             "due_date": p.due_date, "paid_at": p.paid_at}
            for p in fee_records
        ],
        "tenant_id": athlete.tenant_id,
        "client_id": athlete.client_id,
    }


def enrollment_pipeline(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
) -> Dict[str, Any]:
    """Inquiry → trial → enrolled pipeline counts (CRM engine semantics)."""
    conn = connectors["academy_ops"]
    athletes = conn.list_athletes(ctx)
    records = conn.list_enrollment_records(ctx)
    by_stage: Dict[str, int] = {"inquiry": 0, "trial": 0, "enrolled": 0,
                                "renewed": 0, "churned": 0}
    for a in athletes:
        if a.enrollment_status in by_stage:
            by_stage[a.enrollment_status] += 1
    stage_notes = [
        {"enrollment_id": r.enrollment_id, "athlete_id": r.athlete_id,
         "stage": r.stage, "recorded_at": r.recorded_at, "note": r.note}
        for r in records
    ]
    return {"stage_counts": by_stage, "records": stage_notes}


def churn_risk_signals(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    *,
    threshold: float = ATTENDANCE_RISK_THRESHOLD,
    min_sessions: int = MIN_SESSIONS_FOR_RISK,
) -> Sequence[Dict[str, Any]]:
    """Athletes whose attendance rate is below `threshold` (fast path)."""
    conn = connectors["academy_ops"]
    sessions = conn.list_sessions(ctx)
    checkins = conn.list_checkins(ctx)
    attended = {(c.athlete_id, c.session_id) for c in checkins}
    per_athlete: Dict[str, Dict[str, int]] = {}
    for s in sessions:
        for athlete_id in s.roster:
            slot = per_athlete.setdefault(athlete_id, {"expected": 0, "attended": 0})
            slot["expected"] += 1
            if (athlete_id, s.session_id) in attended:
                slot["attended"] += 1
    at_risk = []
    for athlete_id, v in per_athlete.items():
        if v["expected"] < min_sessions:
            continue
        rate = v["attended"] / v["expected"]
        if rate < threshold:
            at_risk.append({
                "athlete_id": athlete_id,
                "attendance_rate": round(rate, 4),
                "expected": v["expected"],
                "attended": v["attended"],
            })
    return sorted(at_risk, key=lambda r: r["attendance_rate"])


def churn_risk_scores(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    *,
    threshold: float = ATTENDANCE_RISK_THRESHOLD,
    min_sessions: int = MIN_SESSIONS_FOR_RISK,
) -> Dict[str, Any]:
    """Score at-risk athletes through the reused CX engine (churn_risk_scoring).

    The CX engine expects customers with KPI fields in 0..1. Each at-risk
    athlete is mapped to `csat` = attendance rate (the only signal the pack
    has in v1; sla/fcr/aht are left absent). The engine call runs under
    owning_role_id ops_gm (engine-enforced ownership) in sample mode.
    """
    from engines.cx.adapter import adapt as cx_adapt

    at_risk = list(churn_risk_signals(
        ctx, connectors, threshold=threshold, min_sessions=min_sessions))
    if not at_risk:
        return {"at_risk": [], "engine_metrics": None}
    customers = [
        {"customer_id": r["athlete_id"], "csat": r["attendance_rate"]}
        for r in at_risk
    ]
    result = cx_adapt(
        input_payload={"customers": customers, "is_sample": True},
        tenant_id=ctx.tenant_id,
        client_id=ctx.client_id,
        correlation_id=ctx.correlation_id or "academy-churn",
        causation_id=None,
        actor="academy-operator",
        owning_role_id="ops_gm",
        is_sample=True,
    )
    engine_metrics: Optional[Dict[str, Any]]
    if result.error is not None:
        engine_metrics = {"engine_error": dict(result.error)}
    else:
        engine_metrics = dict(result.metrics)
    return {"at_risk": at_risk, "engine_metrics": engine_metrics}


def record_churn_flags(
    mem,
    ctx: ConnectorContext,
    scores: Dict[str, Any],
    as_of: str,
    actor: str = "academy-operator",
    role_id: str = "academy_admin",
) -> Sequence[str]:
    """Record at-risk athletes in governed memory (recommendation kind).

    Nature is ``model_inference`` for engine-scored flags: they are
    computed signals, not verified facts, until a human acts on them.
    """
    record_ids = []
    for r in scores.get("at_risk", []):
        correlation_id = ctx.correlation_id or "academy-churn"
        rec = mem.add(
            kind="recommendation", nature="model_inference",
            tenant_id=ctx.tenant_id, client_id=ctx.client_id,
            actor=actor, role_id=role_id, source="academy_churn",
            classification="client_confidential", timestamp=as_of,
            correlation_id=correlation_id, confidence=0.8,
            evidence_refs=[r["athlete_id"]],
            data_mode=DATA_MODE,
            provenance={
                "correlation_id": correlation_id,
                "data_mode": DATA_MODE,
                "basis": "attendance_decline_churn_flag",
                "sources": [r["athlete_id"]],
            },
            body={
                "action": "follow_up_at_risk_athlete",
                "athlete_id": r["athlete_id"],
                "attendance_rate": r["attendance_rate"],
                "expected": r["expected"],
                "attended": r["attended"],
            },
        )
        record_ids.append(rec.record_id)
    return record_ids


def _age_band(birth_date: str) -> str:
    year = int(birth_date[:4])
    if year >= 2014:
        return "U12"
    if year >= 2011:
        return "U15"
    return "U18+"
